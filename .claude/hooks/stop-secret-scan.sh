#!/usr/bin/env bash
# Stop: scan files changed in the working tree (tracked changes AND new untracked files) for secrets.
# Advisory: always exit 0, the warning goes to the user as systemMessage. Not a substitute for the
# git pre-commit scanner or CI secret scanning.
#
# Token shapes come from post-edit-secrets-scan.sh --scan-file (the single pattern table), so this
# hook also catches secrets written through Bash, which the per-edit hook never sees. JWTs are an
# extra advisory-only check here (too common in fixtures to block on).
# Test: bash .claude/hooks/stop-secret-scan.sh --selftest
set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCANNER="$HOOK_DIR/post-edit-secrets-scan.sh"
JWT_RE='eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'
MAX_FILES=200

scan_changed() { # $1 repo dir -> prints "  - file (label)" lines
  local dir="$1" changed tokens jwt
  changed=$( cd "$dir" && { git diff --name-only HEAD 2>/dev/null || git diff --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } | sort -u | head -n "$MAX_FILES" )
  [ -n "$changed" ] || return 0
  ( cd "$dir" || exit 0
    tokens=$(printf '%s\n' "$changed" | "$BASH" "$SCANNER" --scan-files)
    [ -z "$tokens" ] || printf '%s\n' "$tokens" | awk -F'\t' '{ printf "  - %s (%s)\n", $1, $2 }'
    # JWT: advisory extra, only for files the token table did not already report
    jwt=$(printf '%s\n' "$changed" | while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done |
          grep -vE '\.(png|jpg|jpeg|gif|ico|woff2?|ttf|lock|map)$' | tr '\n' '\0' | xargs -0 grep -lE -e "$JWT_RE" 2>/dev/null)
    [ -z "$jwt" ] || printf '%s\n' "$jwt" | while IFS= read -r f; do
      case "
$tokens" in *"
$f	"*) ;; *) printf '  - %s (JWT)\n' "$f" ;; esac
    done )
}

run_hook() {
  local hits msg
  cat > /dev/null 2>&1 || true
  command -v jq >/dev/null 2>&1 || return 0
  [ -f "$SCANNER" ] || { jq -n --arg m "stop-secret-scan: $SCANNER is missing; the end-of-turn secret scan did not run." '{systemMessage:$m}'; return 0; }
  hits=$(scan_changed "${CLAUDE_PROJECT_DIR:-$(pwd)}")
  [ -n "$hits" ] || return 0
  msg="SECRET SCAN WARNING: possible credentials in changed files:
${hits}
Review these before committing; prefer environment variables or a secrets manager."
  jq -n --arg m "$msg" '{systemMessage:$m}'
}

selftest() {
  local self fail=0 tmp out p_aws p_jwt
  self="$HOOK_DIR/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 && command -v git >/dev/null 2>&1 || { echo "  FAIL jq and git required"; return 1; }
  tmp=$(mktemp -d) || return 1
  ( cd "$tmp" && git init -q && git -c user.email=t@t -c user.name=t commit -q --allow-empty -m init ) || { echo "  FAIL git init"; return 1; }
  printf 'export const ok = process.env.API_KEY;\n' > "$tmp/clean.ts"
  out=$(echo '{}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1)
  if [ -z "$out" ]; then echo "  ok   negative: clean untracked file is silent"; else echo "  FAIL false positive: $out"; fail=1; fi
  p_aws="AK""IA$(printf '%016d' 0 | tr 0 Q)"
  printf 'const k = "%s";\n' "$p_aws" > "$tmp/leak.ts"
  p_jwt="ey""J$(printf '%012d' 0 | tr 0 a).ey""J$(printf '%012d' 0 | tr 0 b).$(printf '%012d' 0 | tr 0 c)"
  printf 'token: %s\n' "$p_jwt" > "$tmp/fixture.yaml"
  out=$(echo '{}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1)
  if printf '%s' "$out" | jq -e '.systemMessage | contains("leak.ts (AWS Access Key") and contains("fixture.yaml (JWT)")' >/dev/null 2>&1; then
    echo "  ok   positive: untracked AWS key (shared table) and JWT reported"
  else echo "  FAIL positive not reported: $out"; fail=1; fi
  if printf '%s' "$out" | grep -qF -- "$p_aws"; then echo "  FAIL secret value echoed"; fail=1; else echo "  ok   value never echoed"; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
