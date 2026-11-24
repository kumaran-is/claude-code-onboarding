#!/usr/bin/env bash
# Content-pin gate for build inputs: every GitHub Action `uses:` pinned to a 40-hex commit SHA, every
# Dockerfile `FROM` pinned by `@sha256:` digest, no `COPY --from=<image-ref>`, no `:latest`.
# Local actions (`./...`) and `docker://` refs with a digest are allowed. Markdown (CI templates in skills, commands,
# agents) is checked for `uses:` only, and also accepts an `@<placeholder>` such as `@<40-hex-sha>`. Rationale and how to resolve pins:
# .claude/skills/deployment-ci-cd/reference/python-ci-supply-chain.md section 3.
# usage: check-pins.sh <file>...   |   check-pins.sh --selftest
# exit: 0 clean, 1 violations, 2 nothing to scan (zero files is a failure, never clean)
set -u

scan() {  # prints violations; returns 1 if any
  local f=$1 hits
  case "$f" in
    *.yml|*.yaml)
      hits=$(grep -nE '^[[:space:]-]*uses:[[:space:]]+["'"'"']?[^./[:space:]"'"'"']' "$f" | grep -vE '@[0-9a-f]{40}["'"'"']?([[:space:]]|$)|docker://[^[:space:]]+@sha256:[0-9a-f]{64}') ;;
    *.md)  # templates teach the pattern: same uses: rule, placeholders allowed
      hits=$(grep -nE '^[[:space:]-]*uses:[[:space:]]+["'"'"']?[A-Za-z0-9_.-]+/[^[:space:]"'"'"']*@' "$f" | grep -vE '@[0-9a-f]{40}["'"'"']?([[:space:]]|$)|@<[^>]+>') ;;
    *)  # FROM <earlier stage name> is a reference, not an image: stage names come from `AS <name>`
      hits=$(awk 'BEGIN { IGNORECASE = 1 }
        toupper($1) == "FROM" {
          img = ""; for (i = 2; i <= NF; i++) if ($i !~ /^--/) { img = $i; break }
          for (i = 2; i < NF; i++) if (toupper($i) == "AS") stage[tolower($(i + 1))] = 1
          if (img == "" || tolower(img) == "scratch" || (tolower(img) in stage) || img ~ /@sha256:[0-9a-f]{64}$/) next
          print NR ":" $0 }' "$f"
             grep -nE '^COPY[[:space:]]+--from=[^[:space:]]*[:/.]|:latest' "$f") ;;
  esac
  [ -z "$hits" ] && return 0
  printf '%s\n' "$hits" | sed "s|^|$f: |"
  return 1
}

selftest() {
  local self fail=0 out
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  ok() { if [ "$1" = 0 ]; then echo "  ok   $2"; else echo "  FAIL $2"; fail=1; fi; }
  bash -n "$self"; ok $? "parses (bash -n)"
  d=$(mktemp -d)   # global on purpose: the EXIT trap runs after this function returns
  trap 'rm -rf "$d"' EXIT INT TERM
  sha40=$(printf '0%.0s' $(seq 40)); sha64=$(printf 'a%.0s' $(seq 64))
  printf 'steps:\n  - uses: actions/checkout@%s # v7.0.1\n  - uses: ./.github/actions/local\n' "$sha40" > "$d/good.yml"
  printf 'steps:\n  - uses: actions/checkout@v7\n' > "$d/bad.yml"
  printf 'FROM python:3.14-slim@sha256:%s AS base\nFROM base AS final\nFROM --platform=$BUILDPLATFORM base\nFROM scratch\n' "$sha64" > "$d/Dockerfile.good"
  printf 'FROM python:3.14-slim\nCOPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv\n' > "$d/Dockerfile.bad"
  scan "$d/good.yml" >/dev/null; ok $? "negative: SHA-pinned and local actions are clean"
  scan "$d/Dockerfile.good" >/dev/null; ok $? "negative: digest-pinned FROM, FROM <earlier stage> and scratch are clean"
  printf 'steps:\n  - uses: "actions/checkout@%s" # v7\n' "$sha40" > "$d/quoted.yml"
  scan "$d/quoted.yml" >/dev/null; ok $? "negative: a quoted SHA-pinned uses is clean"
  printf 'FROM base AS x\n' > "$d/Dockerfile.nostage"
  out=$(scan "$d/Dockerfile.nostage"); [ -n "$out" ]; ok $? "positive: FROM <name> that is not an earlier stage is still flagged"
  out=$(scan "$d/bad.yml"); [ -n "$out" ] && case "$out" in *"actions/checkout@v7"*) true ;; *) false ;; esac; ok $? "positive: a tag-pinned action is reported with file:line"
  out=$(scan "$d/Dockerfile.bad"); [ "$(printf '%s\n' "$out" | grep -c .)" -ge 2 ]; ok $? "positive: undigested FROM and COPY --from=<image> are both reported"
  printf '```yaml\n- uses: actions/checkout@%s # v7.0.1\n- uses: google-github-actions/auth@<40-hex-sha>\n```\nText uses: a@v1 in prose.\n' "$sha40" > "$d/good.md"
  scan "$d/good.md" >/dev/null; ok $? "negative: SHA-pinned and <placeholder> refs in a Markdown template are clean"
  printf '```yaml\n      - uses: actions/setup-node@v4\n```\n' > "$d/bad.md"
  out=$(scan "$d/bad.md"); case "$out" in *"setup-node@v4"*) true ;; *) false ;; esac; ok $? "positive: a tag-pinned action in a Markdown template is reported"
  "$BASH" "$self" >/dev/null 2>&1; [ $? -eq 2 ]; ok $? "zero files -> exit 2, never clean"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
[ "$#" -gt 0 ] || { echo "no files given: scanning nothing is a failure"; exit 2; }
rc=0
for f in "$@"; do
  [ -f "$f" ] || { echo "missing file: $f"; exit 2; }
  scan "$f" || rc=1
done
echo "scanned: $# file(s)"
exit $rc
