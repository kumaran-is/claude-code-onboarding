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
  # Quality-config weakening: semantic (not a blanket ban). Uses a real temp tree so
  # Write/Edit reconstruction can diff against disk.
  local tmp qout qrc script
  script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../scripts/check-quality-config-weakening.py"
  if ! command -v python3 >/dev/null 2>&1; then echo "  FAIL python3 required for quality-config selftest"; return 1; fi
  python3 "$script" --selftest >/dev/null || { echo "  FAIL check-quality-config-weakening.py --selftest"; fail=1; }
  tmp=$(mktemp -d) || return 1
  mkdir -p "$tmp/src" "$tmp/.github/workflows"
  printf '%s\n' "rules: { 'no-unused-vars': 'error' }" > "$tmp/eslint.config.js"
  printf '%s\n' '{ "compilerOptions": { "strict": true, "skipLibCheck": false } }' > "$tmp/tsconfig.json"
  printf '%s\n' "run: npm test" > "$tmp/.github/workflows/ci.yml"
  printf '%s\n' "export const x = 1;" > "$tmp/src/app.ts"

  qout=$(jq -n --arg f "$tmp/eslint.config.js" --arg c "rules: { 'no-unused-vars': 'off' }" '{tool_name:"Write",tool_input:{file_path:$f,content:$c}}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1); qrc=$?
  if [ "$qrc" -eq 2 ] && printf '%s' "$qout" | grep -q 'quality-config weakening'; then
    echo "  ok   positive: eslint severity drop is blocked"
  else echo "  FAIL eslint weaken: exit $qrc $qout"; fail=1; fi

  qout=$(jq -n --arg f "$tmp/eslint.config.js" --arg c "rules: { 'no-unused-vars': 'error', 'eqeqeq': 'error' }" '{tool_name:"Write",tool_input:{file_path:$f,content:$c}}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1); qrc=$?
  if [ "$qrc" -eq 0 ] && [ -z "$qout" ]; then
    echo "  ok   negative: eslint strengthening is allowed"
  else echo "  FAIL eslint strengthen: exit $qrc $qout"; fail=1; fi

  qout=$(jq -n --arg f "$tmp/eslint.config.js" --arg c "rules: { 'no-unused-vars': 'off' }
// quality-config-exception: temporary waiver while the unused-vars baseline is rebuilt for the parser" '{tool_name:"Write",tool_input:{file_path:$f,content:$c}}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1); qrc=$?
  if [ "$qrc" -eq 0 ]; then
    echo "  ok   positive: auditable quality-config-exception allows the weaken"
  else echo "  FAIL exception: exit $qrc $qout"; fail=1; fi

  qout=$(jq -n --arg f "$tmp/tsconfig.json" --arg old '"strict": true' --arg new '"strict": false' '{tool_name:"Edit",tool_input:{file_path:$f,old_string:$old,new_string:$new}}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1); qrc=$?
  if [ "$qrc" -eq 2 ] && printf '%s' "$qout" | grep -q 'strict flag off'; then
    echo "  ok   positive: Edit tsconfig strict:false is blocked"
  else echo "  FAIL tsconfig edit: exit $qrc $qout"; fail=1; fi

  qout=$(jq -n --arg f "$tmp/.github/workflows/ci.yml" --arg c "run: npm test || true" '{tool_name:"Write",tool_input:{file_path:$f,content:$c}}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1); qrc=$?
  if [ "$qrc" -eq 2 ] && printf '%s' "$qout" | grep -q '|| true'; then
    echo "  ok   positive: CI quality || true is blocked"
  else echo "  FAIL ci pipe: exit $qrc $qout"; fail=1; fi

  qout=$(jq -n --arg f "$tmp/src/app.ts" --arg c "export const x = 1; // skipLibCheck: true" '{tool_name:"Write",tool_input:{file_path:$f,content:$c}}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1); qrc=$?
  if [ "$qrc" -eq 0 ] && [ -z "$qout" ]; then
    echo "  ok   negative: non-quality source file is not gated"
  else echo "  FAIL source file gated: exit $qrc $qout"; fail=1; fi

  # regression: .env still blocked after the quality-config branch
  qout=$(jq -n --arg f "$tmp/.env" '{tool_name:"Write",tool_input:{file_path:$f,content:"x"}}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1); qrc=$?
  if [ "$qrc" -eq 2 ] && printf '%s' "$qout" | grep -q '.env files'; then
    echo "  ok   regression: .env still blocked"
  else echo "  FAIL .env regression: exit $qrc $qout"; fail=1; fi

  rm -rf "$tmp"
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

# --- Quality-config weakening (semantic; not a ban on all config edits) ---
# Detector: .claude/scripts/check-quality-config-weakening.py. Fail-open if python3
# is missing (say so once). Exit 2 only on a real finding without an auditable
# quality-config-exception. Secret/lock blocks above still apply first.
quality_config_check() {
  local payload out rc marker key script root
  case "$file" in
    *eslint.config.*|*/.eslintrc*|*/ruff.toml|*/.ruff.toml|*/pyproject.toml|*/analysis_options.y*ml|*/tsconfig*.json|*jest.config.*|*vitest.config.*|*karma.config*|*/.nycrc*|*/codecov.y*ml|*/.coveragerc|*/package.json|*/.github/workflows/*.yml|*/.github/workflows/*.yaml) ;;
    *) return 0 ;;
  esac
  script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../scripts/check-quality-config-weakening.py"
  root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
  if ! command -v python3 >/dev/null 2>&1; then
    key=$(printf '%s' "$root" | cksum | awk '{print $1}')
    marker="${TMPDIR:-/tmp}/claude-quality-config-python-missing-$key"
    if [ ! -e "$marker" ]; then
      : > "$marker" 2>/dev/null || true
      echo "quality-config: python3 missing; weakening detection skipped this session" >&2
    fi
    return 0
  fi
  [ -f "$script" ] || return 0
  payload=$(mktemp) || return 0
  printf '%s' "$input" > "$payload"
  out=$(python3 "$script" --payload "$payload" --root "$root" 2>/dev/null)
  rc=$?
  rm -f "$payload"
  case "$rc" in
    1)
      printf '%s' "$out" >&2
      return 1
      ;;
    0) return 0 ;;
    *) return 0 ;;  # detector broken or crash: fail-open
  esac
}

if quality_config_check; then
  :
else
  exit 2
fi

# All clear
exit 0
