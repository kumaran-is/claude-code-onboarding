#!/usr/bin/env bash
# PreToolUse (Write|Edit): block modifications to sensitive files.
# Exit 0 = allow, Exit 2 = block (reason sent to Claude via stderr).
# Env templates (.env.example/.sample/.template/.dist) are allowed: scaffold commands write them with
# placeholder values; post-edit-secrets-scan.sh still flags a real token written into one.
# Test: bash .claude/hooks/pre-edit-protect-sensitive.sh --selftest
set -uo pipefail

selftest() {
  local self fail=0 out rc f
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  while IFS='|' read -r f want frag; do
    [ -n "$f" ] || continue
    out=$(jq -n --arg f "$f" '{tool_name:"Write",tool_input:{file_path:$f,content:"x"}}' | "$BASH" "$self" 2>&1); rc=$?
    local ok=0
    if [ "$want" -eq 0 ]; then [ -z "$out" ] && ok=1; else case "$out" in *"$frag"*) ok=1 ;; esac; fi
    if [ "$rc" -eq "$want" ] && [ "$ok" -eq 1 ]; then
      echo "  ok   $f -> exit $want"
    else echo "  FAIL $f (exit $rc, expected $want: $out)"; fail=1; fi
  done <<'EOF_CASES'
/repo/.env|2|.env files
/repo/apps/api/.env.local|2|.env files
/repo/.env.production|2|.env files
/repo/.git/hooks/pre-commit|2|.git/ internals
/repo/config/secrets.yaml|2|credential/secret
/repo/keys/server.pem|2|key/certificate
/repo/infra/prod.tfvars|2|Terraform
/repo/package-lock.json|2|lock files
/repo/.claude/state/review/main/ledger.json|2|review evidence
/repo/.claude/state/review/feat__x/stamps/review.json|2|review evidence
/repo/.Claude/State/review/main/ledger.json|2|review evidence
/repo/.claude//state/review/main/ledger.json|2|review evidence
/repo/.claude/./state/review/main/ledger.json|2|review evidence
/repo/.claude/statements.md|0|
/repo/.git/claude-state/review/main/ledger.json|2|.git/ internals
/repo/.env.example|0|
/repo/apps/api/.env.sample|0|
/repo/.env.template|0|
/repo/src/environment.ts|0|
/repo/docs/keys.md|0|
EOF_CASES
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}
if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi

# Read the tool input JSON from stdin
input=$(cat)
file=$(echo "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || file=""

# Skip if no file path detected
[ -z "$file" ] && exit 0

# --- Git internals: hooks, config and objects must change through git, never through file edits ---
if echo "$file" | grep -qE '(^|/)\.git/'; then
  echo "BLOCKED: Cannot modify .git/ internals via Write/Edit (hooks, config, objects). Use git commands." >&2
  exit 2
fi

# --- Enforcement-kit evidence: the ledger and stamps are written only by review_state.py and the kit's hooks ---
# Case-insensitive (APFS) and with // and /./ collapsed, so path spellings do not dodge it.
if printf '%s\n' "$file" | sed -e 's#//*#/#g' -e 's#/\./#/#g' | grep -qiE '(^|/)(\.claude/state|\.git/claude-state)/'; then
  echo "BLOCKED: .git/claude-state (legacy .claude/state) holds review evidence (ledger, stamps); only review_state.py and the enforcement kit write it." >&2
  exit 2
fi

# --- Environment and secret files (templates with placeholder values are allowed) ---
if echo "$file" | grep -qE '(^|/)\.env($|\..+)' && ! echo "$file" | grep -qE '(^|/)\.env\.(example|sample|template|dist)$'; then
  echo "BLOCKED: Cannot modify .env files. Edit environment files manually to prevent accidental secret exposure." >&2
  exit 2
fi

if echo "$file" | grep -qiE '(secrets\.ya?ml|credentials\.json|service[-_]?account.*\.json)'; then
  echo "BLOCKED: Cannot modify credential/secret files. Edit these manually." >&2
  exit 2
fi

# --- Private keys and certificates ---
if echo "$file" | grep -qE '\.(pem|key|p12|pfx|jks|keystore)$'; then
  echo "BLOCKED: Cannot modify key/certificate files. Handle these manually." >&2
  exit 2
fi

# --- Terraform state and variable files ---
if echo "$file" | grep -qE '(terraform\.tfvars(\.json)?|terraform\.tfstate(\.backup)?|\.tfvars(\.json)?)$'; then
  echo "BLOCKED: Cannot modify Terraform state/vars files. Edit these manually." >&2
  exit 2
fi

# --- Cloud provider credential directories ---
if echo "$file" | grep -qE '(\.aws/credentials|\.kube/config|\.gcloud/)'; then
  echo "BLOCKED: Cannot modify cloud provider credential files. Edit these manually." >&2
  exit 2
fi

# --- Lock files (prevent accidental corruption) ---
# NOTE: This hook only fires on Write/Edit tools, NOT on Bash.
# Running package managers via Bash (npm install, flutter pub get, pip install, etc.)
# correctly updates lock files without triggering this guard.
if echo "$file" | grep -qE '(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|pubspec\.lock|poetry\.lock|uv\.lock)$'; then
  echo "BLOCKED: Cannot directly edit lock files via Write/Edit. Use the package manager through Bash instead (e.g., npm install, flutter pub get, pip install, uv sync)." >&2
  exit 2
fi

# All clear
exit 0
