#!/usr/bin/env bash
# UserPromptSubmit: Scan user prompt for secrets before Claude processes it.
# Exit 0 = allow, Exit 2 = block (stderr shown to user; Claude never sees the message).
# Token shapes come from the shared table (`post-edit-secrets-scan.sh --patterns`), so every scanner agrees.
# Two classes are skipped here because they are common and harmless in chat: connection strings
# (local dev database URLs with a sample user and password) and bearer examples. JWT-shaped strings are not in the table.
# Test: bash .claude/hooks/prompt-secret-scan.sh --selftest
set -uo pipefail

if [ "${1:-}" = "--selftest" ]; then
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  fail=0
  if bash -n "$self" 2>/dev/null; then echo "  ok   control 0: parses (bash -n)"; else echo "  FAIL does not parse"; exit 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; exit 1; }
  probe() { jq -n --arg p "$1" '{prompt:$p}' | /bin/bash "$self" 2>&1 >/dev/null; }
  check() { # $1 label, $2 prompt, $3 expected rc, $4 needle in stderr ("" = expect silence)
    local err rc
    err=$(probe "$2"); rc=$?
    local ok=0
    if [ -z "$4" ]; then [ -z "$err" ] && ok=1; else printf '%s' "$err" | grep -qF "$4" && ok=1; fi
    if [ "$rc" -eq "$3" ] && [ "$ok" -eq 1 ]; then echo "  ok   $1"; else echo "  FAIL $1 (rc=$rc err=$err)"; fail=1; fi
  }
  body=$(printf 'Ab1%.0s' $(seq 1 12))                       # 36 chars of [A-Za-z0-9]
  check "positive: AWS access key" "key AK""IA$(printf 'Q%.0s' $(seq 1 16))" 2 "AWS Access Key"
  check "positive: Google API key" "GOOGLE_API_KEY=AI""za${body:0:35}" 2 "Google API key"
  check "positive: Langfuse secret key" "sk-l""f-1234abcd-5678-ef00-aaaa-bbbbccccdddd" 2 "Langfuse secret key"
  check "positive: Slack token" "xox""b-1234567890-abcdefghij" 2 "Slack token"
  check "negative: plain question" "Why does RESOURCE_EXHAUSTED appear in the eval run?" 0 ""
  check "negative: placeholder names" "set GOOGLE_API_KEY and LANGFUSE_SECRET_KEY in .env" 0 ""
  check "negative: short AIza mention" "keys start with AI""za but this is prose" 0 ""
  check "negative: empty prompt" "" 0 ""
  check "positive: fine-grained GitHub token (shared table)" "github""_pat_$(printf 'A1_%.0s' $(seq 1 28))" 2 "GitHub token"
  check "positive: unquoted .env paste (KEY=value)" "API_KEY=$(printf 'Q%.0s' $(seq 1 40))" 2 "unquoted"
  check "positive: Slack user token xoxp-1-..." "xox""p-1-2345678901-abcdefghijkl" 2 "Slack token"
  check "negative: Slack placeholder in prose" "set SLACK_BOT_TOKEN to your xox""b-your-bot-token value" 0 ""
  check "negative: a dev connection string in chat is not blocked" "use postgres""://postgres:postgres@localhost:5432/app" 0 ""
  tmpd=$(mktemp -d); mkdir -p "$tmpd/h"; cp "$self" "$tmpd/h/"
  out=$(jq -n --arg p "AK""IA$(printf 'Q%.0s' $(seq 1 16))" '{prompt:$p}' | /bin/bash "$tmpd/h/$(basename "$self")" 2>/dev/null); rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qF "NOT checked"; then echo "  ok   missing shared table -> says NOT checked (never silent)"
  else echo "  FAIL missing table (rc=$rc out=$out)"; fail=1; fi
  printf '#!/usr/bin/env bash\necho "no tabs"\n' > "$tmpd/h/post-edit-secrets-scan.sh"
  out=$(jq -n --arg p "AK""IA$(printf 'Q%.0s' $(seq 1 16))" '{prompt:$p}' | /bin/bash "$tmpd/h/$(basename "$self")" 2>/dev/null); rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qF "NOT checked"; then echo "  ok   malformed table (no usable rows) -> says NOT checked"
  else echo "  FAIL malformed table (rc=$rc out=$out)"; fail=1; fi
  rm -rf "$tmpd"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  exit "$fail"
fi

input=$(cat)
if ! command -v jq >/dev/null 2>&1; then  # static JSON: never silent when the scan cannot run
  printf '%s\n' '{"systemMessage": "Prompt secret scan NOT checked: jq not found."}'
  exit 0
fi
prompt=$(echo "$input" | jq -r '.prompt // ""' 2>/dev/null) || prompt=""

[ -z "$prompt" ] && exit 0

SCANNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/post-edit-secrets-scan.sh"
patterns=$("$BASH" "$SCANNER" --patterns 2>/dev/null) || patterns=""
rows=$(printf '%s\n' "$patterns" | grep -c '	' || true)
if [ "${rows:-0}" -lt 15 ] || ! printf '%s\n' "$patterns" | grep -q '^AWS Access Key'; then
  jq -n '{systemMessage: "Prompt secret scan NOT checked: the shared pattern table (.claude/hooks/post-edit-secrets-scan.sh) is missing or broken."}'
  exit 0
fi
while IFS="	" read -r label re; do
  [ -n "$re" ] || continue
  case "$label" in "Database connection"*|"Literal bearer"*) continue ;; esac
  flags=-qE; case "$label" in Hardcoded*) flags=-qiE ;; esac
  if grep "$flags" -e "$re" <<EOF_PROMPT
$prompt
EOF_PROMPT
  then
    echo "BLOCKED: $label detected in your prompt. Use an environment variable or a secret manager; never paste credentials into chat." >&2
    exit 2
  fi
done <<EOF_PATTERNS
$patterns
EOF_PATTERNS
exit 0
