#!/usr/bin/env bash
# session-mcp-governance.sh — SessionStart: MCP supply-chain / tamper guard.
#
# WHY: .mcp.json wires MCP servers that can reach your DB, cloud, browser, payments, network,
# etc. skill-triggers.md §P0 ("Scan Before Trust") + its trusted-MCP table say to vet a newly
# added server before trusting it — but that was PROSE, not enforced. This hook enforces it:
# it warns at session start if the active MCP set drifts from the approved allowlist, or if
# .mcp.json changed since it was last approved (the CVE-2025-54135/54136 post-approval-tamper
# class). Advisory only — always exits 0 (a SessionStart blocker would lock you out on any
# legit change).
#
# Check 3 (hygiene, advisory): credentials in args/env/headers/url (a ${VAR} in args is expanded into the
# process list, visible to `ps`), and npx/bunx/uvx packages that are unpinned or @latest. Names the server
# and the field, NEVER the value.
#
# jq-only (no yq dep). Hashes the CANONICAL jq form so cosmetic reformatting ≠ tamper.
# Test: bash .claude/hooks/session-mcp-governance.sh --selftest
# Re-approve after a REVIEWED change:  bash .claude/hooks/session-mcp-governance.sh --approve
#
# NB: do NOT read stdin. SessionStart sends JSON on stdin, but this hook doesn't use it, and
# draining with `cat` blocks forever when stdin is an open non-tty pipe (e.g. under a wrapper).
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
MCP_JSON="$ROOT/.mcp.json"
ALLOWLIST="$ROOT/.claude/mcp-allowlist.txt"
HASHFILE="$ROOT/.claude/mcp-config.sha256"

# Hygiene findings as TSV "server<TAB>kind<TAB>detail". Details carry field names only, never values.
HYGIENE_JQ='
def credname: test("(?i)(api[-_]?key|token|secret|passw(or)?d|credential|authorization|private[-_]?key|^pat$|_pat$)");
def credflag: test("^--?[A-Za-z0-9_-]*(?i:key|token|secret|password|passwd|credential)[A-Za-z0-9_-]*$");
def tokenshape: test("AKIA[0-9A-Z]{16}|sk-ant-[A-Za-z0-9_-]{20,}|sk-(proj-)?[A-Za-z0-9_-]{32,}|gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}|xox[abposr]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}|npm_[A-Za-z0-9]{36}|glpat-[A-Za-z0-9_-]{20,}|[sr]k_live_[A-Za-z0-9]{16,}|://[^/:@ ]+:[^/@ ]+@");
def isref: test("^\\$\\{[A-Za-z_][A-Za-z0-9_]*(:-[^}]*)?\\}$");
def hasref: test("\\$\\{");
def pinned_npm: test("^(@[^/@]+/)?[^@]+@[0-9]");
def pinned_py: test("(==|@)[0-9]");
.mcpServers // {} | to_entries[] | .key as $n | .value as $s | ($s.args // [] | map(tostring)) as $a |
( ($a | to_entries[] | .key as $i | .value as $v |
    if ($v | tokenshape) then [$n, "credential", "literal credential in args[\($i)]"]
    elif ($v | test("^--?[^=]+=")) and ($v | sub("=.*"; "") | credflag) then
      [$n, "credential", "\($v | sub("=.*"; "")) in args" + (if ($v | sub("^[^=]*="; "") | hasref) then " (the ${VAR} is expanded into argv, visible in the process list: pass it via env)" else " has a LITERAL value" end)]
    elif $i > 0 and ($a[$i - 1] | credflag) and ($v | test("^-") | not) then
      [$n, "credential", "\($a[$i - 1]) value in args" + (if ($v | hasref) then " (expanded into argv, visible in the process list: pass it via env)" else " is LITERAL" end)]
    else empty end),
  ($s.env // {} | to_entries[] | (.value | tostring) as $v |
    select(($v | tokenshape) or ((.key | credname) and ($v | length) > 0 and ($v | isref | not))) |
    [$n, "credential", "literal value for env \(.key) (use ${VAR})"]),
  ($s.headers // {} | to_entries[] | (.value | tostring) as $v |
    select(($v | tokenshape) or ((.key | credname) and ($v | hasref | not))) |
    [$n, "credential", "literal value for header \(.key) (use ${VAR})"]),
  (($s.url // "") | select(tokenshape or test("[?&](?i:api[-_]?key|key|token|access_token|secret)=[^&$]")) | [$n, "credential", "credential in url"]),
  (if ($s.command // "" | test("(^|/)(npx|bunx)$")) then
     ([$a[] | select(test("^-") | not)][0] // "") as $p |
     if $p == "" then empty
     elif ($p | test("@(latest|next)$")) then [$n, "unpinned", "\($p | sub("^.*@"; "@")) tag"]
     elif ($p | pinned_npm | not) then [$n, "unpinned", "no version"]
     else empty end
   elif ($s.command // "" | test("(^|/)uvx$")) then
     (if ($a | index("--from")) then $a[($a | index("--from")) + 1] else [$a[] | select(test("^-") | not)][0] end // "") as $p |
     if $p != "" and ($p | pinned_py | not) then [$n, "unpinned", "no version"] else empty end
   else empty end)
) | @tsv'

selftest() { # runs this hook as a subprocess against throw-away project dirs; never touches the real .mcp.json
  local self fail=0 tmp out rc lit
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  hook() { CLAUDE_PROJECT_DIR="$1" "$BASH" "$self" < /dev/null; }
  ctx() { printf '%s' "$1" | jq -r '.hookSpecificOutput.additionalContext // ""' 2>/dev/null; }
  lit="sk_live_""$(printf 'Z%.0s' 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24)" # built at runtime: no literal token in this file
  mkdir -p "$tmp/bad/.claude" "$tmp/good/.claude"
  jq -n --arg lit "$lit" '{mcpServers: {
    pay: {command: "npx", args: ["-y", "@acme/pay-mcp@latest", "--api-key=${PAY_KEY}"]},
    lit: {command: "npx", args: ["-y", "lit-mcp@2.0.1", "--token", $lit]},
    envlit: {command: "npx", args: ["-y", "@acme/env-mcp"], env: {ACME_API_KEY: "plain-value-123"}},
    hdr: {type: "http", url: "https://mcp.example.test/mcp", headers: {Authorization: "Bearer static-abc"}},
    py: {command: "uvx", args: ["--from", "docs-mcp", "docs-mcp"]}}}' > "$tmp/bad/.mcp.json"
  jq -n '{mcpServers: {
    pay: {command: "npx", args: ["-y", "@acme/pay-mcp@3.4.1"], env: {PAY_KEY: "${PAY_KEY}"}},
    hdr: {type: "http", url: "https://mcp.example.test/mcp", headers: {Authorization: "Bearer ${MCP_TOKEN}"}},
    py: {command: "uvx", args: ["--from", "docs-mcp==1.2.0", "docs-mcp"]},
    local: {command: "node", args: ["dist/index.js", "--port", "8080"]}}}' > "$tmp/good/.mcp.json"
  for d in bad good; do CLAUDE_PROJECT_DIR="$tmp/$d" "$BASH" "$self" --approve > /dev/null; done
  out=$(hook "$tmp/bad"); rc=$?; out=$(ctx "$out")
  [ "$rc" -eq 0 ] && echo "  ok   advisory: exit 0 with findings" || { echo "  FAIL exit $rc"; fail=1; }
  for want in "pay — --api-key in args (the" "@latest tag" "lit — literal credential in args" "env ACME_API_KEY" "header Authorization" "py (no version)" "envlit (no version)"; do
    if printf '%s' "$out" | grep -qF -- "$want"; then echo "  ok   positive: reports '$want'"; else echo "  FAIL missing '$want' (got: $out)"; fail=1; fi
  done
  if printf '%s' "$out" | grep -qF -e "$lit" -e "plain-value-123" -e "static-abc"; then echo "  FAIL a secret VALUE was printed"; fail=1; else echo "  ok   negative: no credential value is printed"; fi
  out=$(ctx "$(hook "$tmp/good")")
  if [ -z "$out" ]; then echo "  ok   negative: pinned packages + \${VAR} env/headers are silent"; else echo "  FAIL clean config not silent (got: $out)"; fail=1; fi
  jq '.mcpServers.extra = {command: "npx", args: ["-y", "extra-mcp@1.0.0"]}' "$tmp/good/.mcp.json" > "$tmp/good/m" && mv "$tmp/good/m" "$tmp/good/.mcp.json"
  out=$(ctx "$(hook "$tmp/good")")
  if printf '%s' "$out" | grep -q 'UNAPPROVED' && printf '%s' "$out" | grep -q 'CHANGED since last approval'; then echo "  ok   positive: unapproved server + hash drift still reported"; else echo "  FAIL drift checks (got: $out)"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}
if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi

[ -f "$MCP_JSON" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then jq -S -c . "$1" 2>/dev/null | sha256sum | awk '{print $1}'
  else jq -S -c . "$1" 2>/dev/null | shasum -a 256 | awk '{print $1}'; fi
}

# ── --approve: snapshot current .mcp.json as the approved baseline ────────────
if [ "${1:-}" = "--approve" ]; then
  jq -r '.mcpServers // {} | keys[]' "$MCP_JSON" 2>/dev/null | sort > "$ALLOWLIST"
  sha256_of "$MCP_JSON" > "$HASHFILE"
  echo "Approved MCP baseline written:"
  echo "  $ALLOWLIST  ($(wc -l < "$ALLOWLIST" | tr -d ' ') servers)"
  echo "  $HASHFILE   ($(cat "$HASHFILE"))"
  exit 0
fi

ACTIVE=$(jq -r '.mcpServers // {} | keys[]' "$MCP_JSON" 2>/dev/null | sort)
[ -z "$ACTIVE" ] && exit 0

WARN=0
MSG=""
# stderr of an exit-0 hook is never delivered, so findings are collected and emitted as JSON at the end.
note() { MSG="${MSG}${1}"$'\n'; }

# ── Check 1: allowlist drift ─────────────────────────────────────────────────
if [ ! -f "$ALLOWLIST" ]; then
  note "⚠️  MCP governance: no approved allowlist yet ($ALLOWLIST)."
  note "      Vet your servers (skill-triggers.md §P0), then: bash .claude/hooks/session-mcp-governance.sh --approve"
  WARN=1
else
  UNAPPROVED=$(comm -23 <(printf '%s\n' "$ACTIVE") <(sort "$ALLOWLIST"))
  REMOVED=$(comm -13 <(printf '%s\n' "$ACTIVE") <(sort "$ALLOWLIST"))
  if [ -n "$UNAPPROVED" ]; then
    note "⚠️  MCP governance: UNAPPROVED server(s) active in .mcp.json — vet before trusting:"
    note "$(printf '      - %s\n' $UNAPPROVED)"
    note "      (skill-triggers.md §P0 scan, then: bash .claude/hooks/session-mcp-governance.sh --approve)"
    WARN=1
  fi
  [ -n "$REMOVED" ] && note "MCP governance: approved server(s) no longer active: $(echo $REMOVED | tr '\n' ' ')"
fi

# ── Check 2: config integrity (post-approval tamper) ─────────────────────────
if [ -f "$HASHFILE" ]; then
  CUR=$(sha256_of "$MCP_JSON")
  STORED=$(tr -dc 'a-f0-9' < "$HASHFILE")
  if [ -n "$CUR" ] && [ -n "$STORED" ] && [ "$CUR" != "$STORED" ]; then
    note "⚠️  MCP governance: .mcp.json CHANGED since last approval (content hash mismatch)."
    note "      Review the diff for unauthorized server/command/env/url edits (CVE-2025-54135/54136 class)."
    note "      If the change is legitimate: bash .claude/hooks/session-mcp-governance.sh --approve"
    WARN=1
  fi
fi

# ── Check 3: hygiene (credentials outside env refs, unpinned packages) ──────
HYG=$(jq -r "$HYGIENE_JQ" "$MCP_JSON" 2>&1); HYG_RC=$?
if [ "$HYG_RC" -ne 0 ]; then
  note "MCP hygiene check could not run (jq exit $HYG_RC); credentials and pins in .mcp.json were NOT checked."
elif [ -n "$HYG" ]; then
  CRED=$(printf '%s\n' "$HYG" | awk -F'\t' '$2 == "credential" { printf "      - %s — %s\n", $1, $3 }')
  UNPIN=$(printf '%s\n' "$HYG" | awk -F'\t' '$2 == "unpinned" { printf "%s%s (%s)", sep, $1, $3; sep = ", " }')
  if [ -n "$CRED" ]; then
    note "⚠️  MCP hygiene: credential exposure in .mcp.json (values not shown):"
    note "$CRED"
    note "      Pass secrets only as env entries that reference \${VAR}; never as args (visible in the process list) or literals."
  fi
  if [ -n "$UNPIN" ]; then
    note "MCP hygiene: unpinned server packages (supply-chain drift on every start): $UNPIN"
    note "      Pin exact versions: npx -y <pkg>@<x.y.z>, uvx --from <pkg>==<x.y.z>; re-approve after review."
  fi
fi

LOGFILE="$ROOT/.claude/mcp-governance-detected.log"
if [ "$WARN" -eq 1 ]; then
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "?")
  printf '[%s] MCP governance warning emitted\n' "$ts" >> "$LOGFILE" 2>/dev/null || true
fi

if [ -n "$MSG" ]; then
  jq -n --arg m "$MSG" '{systemMessage:$m, hookSpecificOutput:{hookEventName:"SessionStart", additionalContext:$m}}'
fi

exit 0
