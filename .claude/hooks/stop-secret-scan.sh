#!/usr/bin/env bash
# Stop: Scan modified files for potential secrets/API keys when Claude finishes.
# This is a lightweight warning — not a substitute for proper secret scanning in CI.
# Exit 0 always (warnings only, never blocks).
set -uo pipefail

# Read and discard stdin (hook protocol sends JSON, but we don't need it)
cat > /dev/null 2>&1 || true

# Get list of files changed in the working tree (staged + unstaged)
changed=$(git diff --name-only HEAD 2>/dev/null || git diff --name-only 2>/dev/null || true)

# Nothing changed, nothing to scan
[ -z "$changed" ] && exit 0

# Common secret patterns:
#   AKIA...          → AWS Access Key
#   AIza...          → Google API Key
#   ghp_...          → GitHub Personal Access Token
#   sk-...           → OpenAI / Stripe Secret Key
#   sk-ant-...       → Anthropic API Key
#   eyJ...           → JWT token (base64-encoded JSON)
#   -----BEGIN...    → Private key (RSA, EC, DSA, OPENSSH)
#   xox[pboa]-...    → Slack token (bot, user, app)
#   hvs./hvb.        → HashiCorp Vault token
#   sbp_/supabase    → Supabase service/anon keys
#   postgres://...   → PostgreSQL connection string with password
#   mongodb+srv://   → MongoDB connection string with password
patterns='AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z\-_]{35}|ghp_[0-9a-zA-Z]{36}|sk-[0-9a-zA-Z]{20,}|sk-ant-[0-9a-zA-Z\-_]{20,}|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----|xox[pboa]-[0-9]{10,}-[a-zA-Z0-9-]+|hv[sb]\.[A-Za-z0-9_-]{20,}|sbp_[0-9a-zA-Z]{20,}|postgres://[^:]+:[^@]+@[^\s]+|mongodb(\+srv)?://[^:]+:[^@]+@[^\s]+'

hits=""
while IFS= read -r file; do
  [ -f "$file" ] || continue
  # Skip binary files and common non-source files
  echo "$file" | grep -qE '\.(png|jpg|jpeg|gif|ico|woff|woff2|ttf|eot|lock|map)$' && continue
  if grep -qE "$patterns" "$file" 2>/dev/null; then
    hits="$hits  - $file"$'\n'
  fi
done <<< "$changed"

if [ -n "$hits" ] && command -v jq >/dev/null 2>&1; then
  # stderr of an exit-0 hook is not delivered anywhere; systemMessage is shown to the user.
  msg="SECRET SCAN WARNING: possible API keys or secrets in changed files:
${hits}Review these before committing; prefer environment variables or a secrets manager."
  jq -n --arg m "$msg" '{systemMessage:$m}'
fi

exit 0
