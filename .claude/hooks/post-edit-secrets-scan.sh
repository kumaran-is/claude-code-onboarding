#!/usr/bin/env bash
# PostToolUse (Write|Edit): Scan file content Claude just wrote for secrets.
# Exit 0 = allow, Exit 2 = block the write and show error to Claude.
set -uo pipefail

input=$(cat)

# Extract the file path from the tool input
file_path=$(echo "$input" | jq -r '.tool_input.file_path // ""' 2>/dev/null) || file_path=""

# Fall back to reading the written file directly if path is available
if [ -z "$file_path" ] || [ ! -f "$file_path" ]; then
  exit 0
fi

# Skip binary files and lock/asset files
echo "$file_path" | grep -qE '\.(png|jpg|jpeg|gif|ico|woff|woff2|ttf|eot|lock|map|bin|so|dylib|class|jar)$' && exit 0

content=$(cat "$file_path" 2>/dev/null) || exit 0
[ -z "$content" ] && exit 0

blocked=0
reason=""

# AWS Access Key
if echo "$content" | grep -qE 'AKIA[0-9A-Z]{16}'; then
  reason="AWS Access Key (AKIA...)"; blocked=1
fi

# Anthropic API key
if [ $blocked -eq 0 ] && echo "$content" | grep -qE 'sk-ant-[a-zA-Z0-9\-_]{20,}'; then
  reason="Anthropic API key (sk-ant-...)"; blocked=1
fi

# OpenAI API key
if [ $blocked -eq 0 ] && echo "$content" | grep -qE 'sk-(proj-)?[a-zA-Z0-9]{40,}'; then
  reason="OpenAI API key (sk-...)"; blocked=1
fi

# Google API key
if [ $blocked -eq 0 ] && echo "$content" | grep -qE 'AIza[0-9A-Za-z\-_]{35}'; then
  reason="Google API key (AIza...)"; blocked=1
fi

# GitHub tokens
if [ $blocked -eq 0 ] && echo "$content" | grep -qE 'gh[ps]_[a-zA-Z0-9]{36,}|github_pat_[a-zA-Z0-9_]{80,}'; then
  reason="GitHub token (ghp_/ghs_/github_pat_...)"; blocked=1
fi

# Slack tokens
if [ $blocked -eq 0 ] && echo "$content" | grep -qE 'xox[pboa]-[0-9]{10,}-[a-zA-Z0-9\-]+'; then
  reason="Slack token (xox...)"; blocked=1
fi

# HashiCorp Vault token
if [ $blocked -eq 0 ] && echo "$content" | grep -qE 'hv[sb]\.[A-Za-z0-9_\-]{20,}'; then
  reason="HashiCorp Vault token (hvs./hvb.)"; blocked=1
fi

# Private key block
if [ $blocked -eq 0 ] && echo "$content" | grep -qE -e '-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'; then
  reason="Private key (-----BEGIN ... PRIVATE KEY-----)"; blocked=1
fi

# Connection strings with embedded credentials
# Pattern split across vars to avoid triggering the pre-commit secret scanner on this file itself
pg_pat='postgres''://[^:]+:[^@]{6,}@[^\s]+'
mongo_pat='mongodb''(\+srv)?://[^:]+:[^@]{6,}@[^\s]+'
if [ $blocked -eq 0 ] && echo "$content" | grep -qE "${pg_pat}|${mongo_pat}"; then
  reason="Database connection string with embedded credentials"; blocked=1
fi

# Generic high-confidence: key/token assignment with long value (not a variable reference)
if [ $blocked -eq 0 ] && echo "$content" | grep -qiE '(api_key|secret_key|access_token|auth_token|private_key)\s*[=:]\s*"[a-zA-Z0-9+/\-_]{32,}"'; then
  reason="Hardcoded secret assignment (key = \"...\")"; blocked=1
fi

if [ $blocked -eq 1 ]; then
  echo "" >&2
  echo "BLOCKED: Secret detected in $file_path" >&2
  echo "Type: $reason" >&2
  echo "Do not hardcode secrets in source files. Use environment variables, .env files (gitignored), or a secrets manager." >&2
  echo "" >&2
  exit 2
fi

exit 0
