#!/usr/bin/env bash
# UserPromptSubmit hook: Correction Signal Detector
#
# Scans the user's prompt for correction signal patterns defined in CLAUDE.md.
# When detected, injects a hard reminder into context — Claude must write a
# lessons.md entry BEFORE responding to the corrected task.
#
# Correction signals (from CLAUDE.md self-improvement loop):
#   - "that's wrong", "not like that", "you missed X"
#   - User re-states something already said
#   - User explicitly points out a repeated mistake
#   - User overrides a decision made independently

set -uo pipefail

INPUT=$(cat)

# Extract the user prompt text
PROMPT=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    # Handle both string and array message formats
    # UserPromptSubmit delivers the text in the prompt field; message is a fallback
    msg = data.get('prompt', '') or data.get('message', '') or ''
    if isinstance(msg, list):
        # Extract text content from message array
        parts = [p.get('text','') for p in msg if isinstance(p,dict) and p.get('type')=='text']
        print(' '.join(parts).lower())
    else:
        print(str(msg).lower())
except Exception:
    print('')
" 2>/dev/null || echo "")

if [ -z "$PROMPT" ]; then
    echo '{"continue": true}'
    exit 0
fi

# Correction signal patterns (case-insensitive, already lowercased above)
CORRECTION_PATTERNS=(
    "that's wrong"
    "thats wrong"
    "not like that"
    "you missed"
    "you forgot"
    "wrong version"
    "wrong path"
    "that is wrong"
    "you should have"
    "i already said"
    "i told you"
    "again you"
    "you did it again"
    "same mistake"
    "fix this mistake"
    "you got it wrong"
    "don't do that"
    "never do that"
    "you misunderstood"
    "that was wrong"
)

DETECTED=""
for PATTERN in "${CORRECTION_PATTERNS[@]}"; do
    if echo "$PROMPT" | grep -qiF "$PATTERN" 2>/dev/null; then
        DETECTED="$PATTERN"
        break
    fi
done

if [ -n "$DETECTED" ] && command -v jq >/dev/null 2>&1; then
    MSG="CORRECTION SIGNAL DETECTED (\"$DETECTED\"). The CLAUDE.md self-improvement loop applies: before responding, open .claude/rules/lessons.md, check whether this mistake already has an entry (increment its [xN] counter), otherwise add a new 4-line entry, and only then fix the correction. Skip the lesson for preference changes or first-time clarifications."
    jq -n --arg m "$MSG" '{hookSpecificOutput:{hookEventName:"UserPromptSubmit",additionalContext:$m}}'
else
    echo '{"continue": true}'
fi
