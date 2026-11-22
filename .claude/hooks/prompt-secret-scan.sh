#!/usr/bin/env bash
# UserPromptSubmit: Scan user prompt for secrets before Claude processes it.
# Exit 0 = allow, Exit 2 = block (stderr shown to user; Claude never sees the message).
# Only fixed, provider-issued key shapes block (deterministic). JWT-shaped strings are NOT blocked:
# sample tokens in docs and test fixtures would make it noisy.
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
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  exit "$fail"
fi

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

# Google API key (Gemini / Google Cloud API keys)
if echo "$prompt" | grep -qE 'AIza[0-9A-Za-z_-]{35}'; then
  echo "BLOCKED: Google API key detected (AIza...). Use an environment variable or secret manager instead." >&2
  exit 2
fi

# Langfuse secret key
if echo "$prompt" | grep -qE 'sk-lf-[0-9a-zA-Z-]{20,}'; then
  echo "BLOCKED: Langfuse secret key detected (sk-lf-...). Use an environment variable instead." >&2
  exit 2
fi

# Slack tokens
if echo "$prompt" | grep -qE 'xox[baprs]-[0-9A-Za-z-]{10,}'; then
  echo "BLOCKED: Slack token detected (xox?-...). Use an environment variable instead." >&2
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
