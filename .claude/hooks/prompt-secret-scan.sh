#!/usr/bin/env bash
# UserPromptSubmit: Scan user prompt for secrets before Claude processes it.
# Exit 0 = allow, Exit 2 = block (stderr shown to user; Claude never sees the message).
set -uo pipefail

input=$(cat)
prompt=$(echo "$input" | jq -r '.prompt // ""' 2>/dev/null) || prompt=""

[ -z "$prompt" ] && exit 0

# AWS Access Key
if echo "$prompt" | grep -qE 'AKIA[0-9A-Z]{16}'; then
  echo "BLOCKED: AWS Access Key detected (AKIA...). Use an environment variable or .env file instead." >&2
  exit 2
fi

# Anthropic API key
if echo "$prompt" | grep -qE 'sk-ant-[a-zA-Z0-9\-]{20,}'; then
  echo "BLOCKED: Anthropic API key detected (sk-ant-...). Use an environment variable instead." >&2
  exit 2
fi

# OpenAI API key
if echo "$prompt" | grep -qE 'sk-(proj-)?[a-zA-Z0-9]{40,}'; then
  echo "BLOCKED: OpenAI API key detected (sk-...). Use an environment variable instead." >&2
  exit 2
fi

# GitHub tokens
if echo "$prompt" | grep -qE 'gh[ps]_[a-zA-Z0-9]{36,}|github_pat_[a-zA-Z0-9_]{80,}'; then
  echo "BLOCKED: GitHub token detected (ghp_/ghs_/github_pat_...). Use an environment variable instead." >&2
  exit 2
fi

# Private key block
if echo "$prompt" | grep -qE -e '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'; then
  echo "BLOCKED: Private key detected. Never paste private keys into chat." >&2
  exit 2
fi

# Key/token assignment with long value (high-confidence generic pattern)
if echo "$prompt" | grep -qiE '(api_key|secret_key|access_token|auth_token|private_key)\s*[=:]\s*[a-zA-Z0-9+/]{32,}'; then
  echo "BLOCKED: Potential secret detected (key/token with long value). Use an environment variable instead." >&2
  exit 2
fi

exit 0
