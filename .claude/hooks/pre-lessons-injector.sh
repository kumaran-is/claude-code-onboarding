#!/bin/bash
# Hook: Lessons Injector — injects lessons.md into sub-agent context
# Event: PreToolUse (Agent)
#
# Problem: the built-in Explore/Plan sub-agents (and any agent whose definition sets omitClaudeMd)
# start without CLAUDE.md and .claude/rules/, so accumulated corrections are lost across the
# agent boundary. Other sub-agents already inherit lessons.md; for them this is a harmless repeat.
# Solution: Intercept Agent tool calls and append lessons.md content
# to the prompt parameter as additionalContext.

set -e

# Read hook input from stdin
INPUT=$(cat)

# Extract tool name
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')

# Only intercept Agent tool calls
if [[ "$TOOL_NAME" != "Agent" ]]; then
  echo '{"continue": true}'
  exit 0
fi

# Locate lessons.md
LESSONS_FILE="${CLAUDE_PROJECT_DIR:-.}/.claude/rules/lessons.md"

if [[ ! -f "$LESSONS_FILE" ]]; then
  echo '{"continue": true}'
  exit 0
fi

# Check if lessons.md has any actual entries (not just headers/empty)
ENTRY_COUNT=$(grep -c '^\#\# \[' "$LESSONS_FILE" 2>/dev/null || echo "0")

if [[ "$ENTRY_COUNT" -eq 0 ]]; then
  echo '{"continue": true}'
  exit 0
fi

# Extract lessons content (skip the header/purpose section, get entries only)
LESSONS_CONTENT=$(sed -n '/^## \[/,$p' "$LESSONS_FILE" | head -60)

if [[ -z "$LESSONS_CONTENT" ]]; then
  echo '{"continue": true}'
  exit 0
fi

# Inject as additionalContext (systemMessage visible to the sub-agent)
ESCAPED_CONTENT=$(echo "$LESSONS_CONTENT" | jq -Rs .)

cat <<EOF
{
  "continue": true,
  "additionalContext": "TEAM LESSONS (from .claude/rules/lessons.md — corrections accumulated across sessions):\n${LESSONS_CONTENT}\n\nApply these lessons to avoid repeating known mistakes."
}
EOF
