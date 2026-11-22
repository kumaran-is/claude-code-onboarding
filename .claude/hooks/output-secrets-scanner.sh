#!/usr/bin/env bash
# PostToolUse (Bash|Read|WebFetch): Scan tool OUTPUT for secrets.
# Complements post-edit-secrets-scan.sh (which covers Write|Edit).
# This covers what Claude READS BACK: bash output, file reads, web responses.
# Always exits 0 — warns but never blocks (blocking mid-read breaks Claude's flow).
set -uo pipefail

input=$(cat)

# Extract tool name and output content from the PostToolUse JSON
tool_name=$(echo "$input" | jq -r '.tool_name // ""' 2>/dev/null) || tool_name=""
# tool_response may be a string or object — normalise to string
content=$(echo "$input" | jq -r '
  if .tool_response | type == "string" then .tool_response
  elif .tool_response.output? then .tool_response.output
  elif .tool_response.content? then .tool_response.content
  else (.tool_response | tostring)
  end // ""
' 2>/dev/null) || content=""

[ -z "$content" ] && exit 0

# Skip very short outputs (< 20 chars) — no secret fits in that
[ "${#content}" -lt 20 ] && exit 0

# ─────────────────────────────────────────────────────────────────────────────
# Secret pattern detection
# ─────────────────────────────────────────────────────────────────────────────
detected=0
reason=""

# AWS Access Key
if echo "$content" | grep -qE 'AKIA[0-9A-Z]{16}'; then
  reason="AWS Access Key (AKIA...)"; detected=1
fi

# Anthropic API key
if [ $detected -eq 0 ] && echo "$content" | grep -qE 'sk-ant-[a-zA-Z0-9\-_]{20,}'; then
  reason="Anthropic API key (sk-ant-...)"; detected=1
fi

# OpenAI API key
if [ $detected -eq 0 ] && echo "$content" | grep -qE 'sk-(proj-)?[a-zA-Z0-9]{40,}'; then
  reason="OpenAI API key (sk-...)"; detected=1
fi

# Google API key
if [ $detected -eq 0 ] && echo "$content" | grep -qE 'AIza[0-9A-Za-z\-_]{35}'; then
  reason="Google API key (AIza...)"; detected=1
fi

# GitHub tokens
if [ $detected -eq 0 ] && echo "$content" | grep -qE 'gh[ps]_[a-zA-Z0-9]{36,}|github_pat_[a-zA-Z0-9_]{80,}'; then
  reason="GitHub token (ghp_/ghs_/github_pat_...)"; detected=1
fi

# Slack tokens
if [ $detected -eq 0 ] && echo "$content" | grep -qE 'xox[pboa]-[0-9]{10,}-[a-zA-Z0-9\-]+'; then
  reason="Slack token (xox...)"; detected=1
fi

# JWT tokens (3-segment base64url — common in API responses)
if [ $detected -eq 0 ] && echo "$content" | grep -qE 'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}'; then
  reason="JWT token (eyJ...)"; detected=1
fi

# Private key block
if [ $detected -eq 0 ] && echo "$content" | grep -qE -e '-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'; then
  reason="Private key block (-----BEGIN...PRIVATE KEY-----)"; detected=1
fi

# Database connection strings with embedded credentials
# Patterns split across vars to avoid triggering pre-commit scanner on this file
pg_pat='postgres''ql?://[^:]{1,64}:[^@]{6,}@[a-zA-Z0-9._-]+'
mongo_pat='mongodb''(\+srv)?://[^:]{1,64}:[^@]{6,}@[a-zA-Z0-9._-]+'
redis_pat='redis''://:[^@]{6,}@[a-zA-Z0-9._-]+'
mysql_pat='mysql''://[^:]{1,64}:[^@]{6,}@[a-zA-Z0-9._-]+'
if [ $detected -eq 0 ] && echo "$content" | grep -qE "${pg_pat}|${mongo_pat}|${redis_pat}|${mysql_pat}"; then
  reason="Database connection string with embedded credentials"; detected=1
fi

# Generic high-confidence: named secret variable with long value
if [ $detected -eq 0 ] && echo "$content" | grep -qiE '(PASSWORD|PASSWD|SECRET|API_KEY|ACCESS_TOKEN|AUTH_TOKEN|PRIVATE_KEY)\s*[=:]\s*[a-zA-Z0-9+/\-_!@#$%]{16,}'; then
  reason="Hardcoded secret in environment variable or config"; detected=1
fi

# HashiCorp Vault token
if [ $detected -eq 0 ] && echo "$content" | grep -qE 'hv[sb]\.[A-Za-z0-9_\-]{20,}'; then
  reason="HashiCorp Vault token (hvs./hvb.)"; detected=1
fi

# ─────────────────────────────────────────────────────────────────────────────
# Output warning and log (never block — exit 0 always)
# ─────────────────────────────────────────────────────────────────────────────
if [ $detected -eq 1 ]; then
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  tool_context=$(echo "$input" | jq -r '
    if .tool_name == "Bash" then "Bash: " + (.tool_input.command // "?")
    elif .tool_name == "Read" then "Read: " + (.tool_input.file_path // "?")
    elif .tool_name == "WebFetch" then "WebFetch: " + (.tool_input.url // "?")
    else .tool_name
    end
  ' 2>/dev/null | head -c 120) || tool_context="$tool_name"

  # Warn to stderr — shown to user in Claude Code UI
  echo "" >&2
  echo "⚠️  SECRET DETECTED in tool output" >&2
  echo "   Tool:    $tool_context" >&2
  echo "   Pattern: $reason" >&2
  echo "   Action:  Move credentials to .env (gitignored) or a secrets manager." >&2
  echo "            Do not reference or repeat this value in responses or commits." >&2
  echo "" >&2

  # stderr of an exit-0 hook never reaches Claude; PostToolUse additionalContext does.
  command -v jq >/dev/null 2>&1 && jq -n --arg m "A credential-like value (${reason}) appeared in the output of ${tool_context}. Do not repeat, quote, or reference the value in responses, files or commits; refer to it by name only, and suggest moving it to an environment variable or secrets manager." \
    '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'

  # Append to audit log (never fails — errors suppressed)
  LOGFILE="$CLAUDE_PROJECT_DIR/.claude/secrets-detected.log"
  {
    printf '[%s] DETECTED: %s | Tool: %s\n' \
      "$timestamp" "$reason" "$tool_context"
  } >> "$LOGFILE" 2>/dev/null || true
fi

exit 0
