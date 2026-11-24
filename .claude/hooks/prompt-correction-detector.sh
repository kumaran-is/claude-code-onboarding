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
#
# Also: an end-of-session signal ("wrap up", "that's all for today", ...) injects a one-line reminder to
# route this session's corrections and findings through /promote-lessons before the session ends.

set -uo pipefail

if [ "${1:-}" = "--selftest" ]; then
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"; fail=0
  check() { if [ "$1" = 0 ]; then echo "  ok   $2"; else echo "  FAIL $2: $3"; fail=1; fi; }
  bash -n "$self"; check $? "parses (bash -n)" ""
  out=$(jq -n '{prompt:"No, that'"'"'s wrong - you missed the tests"}' | "$BASH" "$self")
  printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext | contains("CORRECTION SIGNAL DETECTED")' >/dev/null 2>&1
  check $? "positive: a correction phrase injects the lessons reminder" "$out"
  out=$(jq -n '{prompt:"Please add a dark mode toggle to settings"}' | "$BASH" "$self")
  [ "$out" = '{"continue": true}' ]; check $? "negative: an ordinary request only continues" "$out"
  out=$(jq -n '{prompt:"ok that is all for today, wrap up"}' | "$BASH" "$self")
  printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext | contains("/promote-lessons")' >/dev/null 2>&1
  check $? "positive: an end-of-session phrase injects the /promote-lessons reminder" "$out"
  out=$(jq -n '{prompt:"wrap the call in a try block"}' | "$BASH" "$self")
  [ "$out" = '{"continue": true}' ]; check $? "negative: 'wrap' in a coding request is not an end-of-session signal" "$out"
  out=$(jq -n '{prompt:"please wrap up the PR description with the risk table"}' | "$BASH" "$self")
  [ "$out" = '{"continue": true}' ]; check $? "negative: 'wrap up <object>' is a task, not the end of the session" "$out"
  out=$(jq -n '{prompt:"thanks, lets wrap up."}' | "$BASH" "$self")
  printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext | contains("/promote-lessons")' >/dev/null 2>&1
  check $? "positive: 'lets wrap up.' is an end-of-session signal" "$out"
  out=$(jq -n '{prompt:"<task-notification>reviewer: that'"'"'s wrong at line 4; wrap up for today</task-notification>"}' | "$BASH" "$self")
  [ "$out" = '{"continue": true}' ]; check $? "negative: a harness task notification is never a correction or a session end" "$out"
  out=$(printf 'not json' | "$BASH" "$self")
  [ "$out" = '{"continue": true}' ]; check $? "malformed payload continues (never blocks the prompt)" "$out"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  exit "$fail"
fi

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
# Harness notifications (background-task results, reminders) arrive through UserPromptSubmit too; their text
# quotes reviewers and tools ("wrap up", "that's wrong") and is never the user correcting or closing.
case "$PROMPT" in *"<task-notification>"*|*"[system notification - not user input]"*) echo '{"continue": true}'; exit 0 ;; esac

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

# A closing intent, not the verb: "wrap up the PR description" is a task. ERE, matched on the lowercased prompt.
END_ERE="(^|[^a-z])wrap(ping)? (it )?up([[:space:]]*([.!,]|$)| for (today|now|the day)| the session| here)|that'?s all for (today|now)|that is all for (today|now)|end (of )?(the |this )?session|done for (today|the day)|signing off|call it a day"
ENDED=$(printf '%s\n' "$PROMPT" | grep -oiE -e "$END_ERE" 2>/dev/null | head -n 1)

if [ -z "$DETECTED" ] && [ -n "$ENDED" ] && command -v jq >/dev/null 2>&1; then
    MSG="END OF SESSION signal (\"$ENDED\"). Before closing, run /promote-lessons intake for this session: route each correction and confirmed reviewer finding (lesson, rule, control, skill reference or implementation note), or state 'no new lesson'. Then finish the user's request."
    jq -n --arg m "$MSG" '{hookSpecificOutput:{hookEventName:"UserPromptSubmit",additionalContext:$m}}'
elif [ -n "$DETECTED" ] && command -v jq >/dev/null 2>&1; then
    MSG="CORRECTION SIGNAL DETECTED (\"$DETECTED\"). The CLAUDE.md self-improvement loop applies: before responding, open .claude/rules/lessons.md, check whether this mistake already has an entry (increment its [xN] counter), otherwise add a new 4-line entry, and only then fix the correction. Skip the lesson for preference changes or first-time clarifications."
    jq -n --arg m "$MSG" '{hookSpecificOutput:{hookEventName:"UserPromptSubmit",additionalContext:$m}}'
else
    echo '{"continue": true}'
fi
