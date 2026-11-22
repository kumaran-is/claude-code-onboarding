#!/usr/bin/env bash
# PreToolUse → Write|Edit|MultiEdit: Block modifications to sensitive files.
# Exit 0 = allow, Exit 2 = block (reason sent to Claude via stderr).
set -uo pipefail

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

# --- Environment and secret files ---
if echo "$file" | grep -qE '(^|/)\.env($|\..+)'; then
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
