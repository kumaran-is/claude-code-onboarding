#!/bin/bash

# Ralph Wiggum Stop Hook
# Prevents session exit when a ralph-loop is active.
# Feeds the same prompt back to Claude to continue iterating.
# Exits 0 immediately if no loop is active — zero interference with normal workflow.

#
# Loop-safety notes (verified against the hooks reference, code.claude.com/docs/en/hooks):
#   - `stop_hook_active` is true whenever Claude is already continuing because of a stop hook.
#     This hook deliberately does NOT exit on it: continuing across iterations IS the feature.
#     The loop is bounded by max_iterations here, and (when max_iterations is 0) by the harness
#     cap on consecutive stop-hook continuations (CLAUDE_CODE_STOP_HOOK_BLOCK_CAP).
#   - Subagents must never be held by the main agent's loop: if the payload carries `agent_id`
#     (subagent context) this hook exits 0 untouched. Subagent completion is normally a separate
#     SubagentStop event, so this is a belt-and-braces guard.
# Test: bash .claude/hooks/stop-ralph-loop.sh --selftest

set -euo pipefail

if [[ "${1:-}" == "--selftest" ]]; then
  SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  FAIL=0
  if bash -n "$SELF" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; exit 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; exit 1; }
  T=$(mktemp -d)
  mkdir -p "$T/.claude"
  state() { printf '%s\n' '---' 'iteration: 1' 'max_iterations: 5' 'completion_promise: "DONE"' '---' 'keep going' > "$T/.claude/ralph-loop.local.md"; }
  # The hook greps the literal "role":"assistant" on a transcript line.
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"working"}]}}' > "$T/transcript.jsonl"
  state
  OUT=$(printf '{"agent_id":"sub-1","transcript_path":"%s"}' "$T/transcript.jsonl" | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"' && grep -q '^iteration: 1$' "$T/.claude/ralph-loop.local.md"; then echo "  ok   negative: subagent payload is ignored, state untouched"; else echo "  FAIL subagent payload not ignored (out: $OUT)"; FAIL=1; fi
  state
  OUT=$(printf '{"stop_hook_active":true,"transcript_path":"%s"}' "$T/transcript.jsonl" | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if printf '%s' "$OUT" | grep -q '"decision": *"block"' && grep -q '^iteration: 2$' "$T/.claude/ralph-loop.local.md"; then echo "  ok   positive: main-agent stop (stop_hook_active=true) still continues the loop"; else echo "  FAIL main agent loop did not continue (out: $OUT)"; FAIL=1; fi
  # Termination: iteration at max_iterations ends the loop and removes the state file.
  printf '%s\n' '---' 'iteration: 5' 'max_iterations: 5' 'completion_promise: "DONE"' '---' 'keep going' > "$T/.claude/ralph-loop.local.md"
  OUT=$(printf '{"transcript_path":"%s"}' "$T/transcript.jsonl" | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"' && [[ ! -f "$T/.claude/ralph-loop.local.md" ]]; then echo "  ok   termination: max_iterations reached -> exit, state removed"; else echo "  FAIL max_iterations did not terminate (out: $OUT)"; FAIL=1; fi
  # Termination: matching <promise> ends the loop.
  state
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"all done <promise>DONE</promise>"}]}}' > "$T/transcript.jsonl"
  OUT=$(printf '{"transcript_path":"%s"}' "$T/transcript.jsonl" | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"' && [[ ! -f "$T/.claude/ralph-loop.local.md" ]]; then echo "  ok   termination: completion promise matched -> exit, state removed"; else echo "  FAIL promise did not terminate (out: $OUT)"; FAIL=1; fi
  # Termination: corrupted state file is removed, not looped on forever.
  printf '%s\n' '---' 'iteration: abc' 'max_iterations: 5' '---' 'x' > "$T/.claude/ralph-loop.local.md"
  OUT=$(printf '{"transcript_path":"%s"}' "$T/transcript.jsonl" | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"' && [[ ! -f "$T/.claude/ralph-loop.local.md" ]]; then echo "  ok   termination: corrupted state -> exit, state removed"; else echo "  FAIL corrupted state not cleaned (out: $OUT)"; FAIL=1; fi
  # No state file: zero interference.
  OUT=$(printf '{"transcript_path":"%s"}' "$T/transcript.jsonl" | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if [[ -z "$OUT" ]]; then echo "  ok   negative: no active loop -> silent exit"; else echo "  FAIL interfered without a loop (out: $OUT)"; FAIL=1; fi
  rm -rf "$T"
  if [[ "$FAIL" -eq 0 ]]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  exit "$FAIL"
fi

# Loop status notices are shown to the user through systemMessage on exit. stderr of an exit-0 hook is
# never delivered, so every notice goes through note(). The loop-continue path emits a decision instead.
NOTES=""
note() { NOTES="${NOTES}${1}"$'\n'; }
emit_notes() {
  if [[ -n "$NOTES" ]] && command -v jq >/dev/null 2>&1; then
    jq -n --arg m "$NOTES" '{systemMessage:$m}'
  fi
}
trap emit_notes EXIT

# Read hook input from stdin
HOOK_INPUT=$(cat)

# Subagent context: never hold a subagent inside the main agent's loop.
if [[ -n "$(echo "$HOOK_INPUT" | jq -r '.agent_id // empty' 2>/dev/null || true)" ]]; then
  exit 0
fi

# Check if ralph-loop is active — exit immediately if not
RALPH_STATE_FILE="$CLAUDE_PROJECT_DIR/.claude/ralph-loop.local.md"

if [[ ! -f "$RALPH_STATE_FILE" ]]; then
  exit 0
fi

# Parse YAML frontmatter (between --- markers)
FRONTMATTER=$(sed -n '/^---$/,/^---$/{ /^---$/d; p; }' "$RALPH_STATE_FILE")
ITERATION=$(echo "$FRONTMATTER" | grep '^iteration:' | sed 's/iteration: *//' || true)
MAX_ITERATIONS=$(echo "$FRONTMATTER" | grep '^max_iterations:' | sed 's/max_iterations: *//' || true)
COMPLETION_PROMISE=$(echo "$FRONTMATTER" | grep '^completion_promise:' | sed 's/completion_promise: *//' | sed 's/^"\(.*\)"$/\1/' || true)
VERIFY_CMD=$(echo "$FRONTMATTER" | grep '^verify_cmd:' | sed 's/^verify_cmd: *//' | sed 's/^"\(.*\)"$/\1/' || true)

# Validate iteration is a number
if [[ ! "$ITERATION" =~ ^[0-9]+$ ]]; then
  note "⚠️  Ralph loop: State file corrupted — 'iteration' is not a number (got: '$ITERATION')"
  note "   Stopping loop. Run /ralph-loop again to start fresh."
  rm "$RALPH_STATE_FILE"
  exit 0
fi

# Validate max_iterations is a number
if [[ ! "$MAX_ITERATIONS" =~ ^[0-9]+$ ]]; then
  note "⚠️  Ralph loop: State file corrupted — 'max_iterations' is not a number (got: '$MAX_ITERATIONS')"
  note "   Stopping loop. Run /ralph-loop again to start fresh."
  rm "$RALPH_STATE_FILE"
  exit 0
fi

# Progress state file (survives loop end — written by Claude per RULES in ralph-loop.md)
RALPH_PROGRESS_FILE="$CLAUDE_PROJECT_DIR/.claude/ralph-state.local.md"

# Check iteration limit
if [[ $MAX_ITERATIONS -gt 0 ]] && [[ $ITERATION -ge $MAX_ITERATIONS ]]; then
  note "🛑 Ralph loop: Max iterations ($MAX_ITERATIONS) reached. Stopping."
  if [[ -f "$RALPH_PROGRESS_FILE" ]]; then
    note "   Progress + escalated items: .claude/ralph-state.local.md"
  fi
  rm "$RALPH_STATE_FILE"
  exit 0
fi

# Get transcript path from hook input
TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || echo "")

if [[ -z "$TRANSCRIPT_PATH" ]] || [[ ! -f "$TRANSCRIPT_PATH" ]]; then
  note "⚠️  Ralph loop: Transcript not found — stopping loop."
  rm "$RALPH_STATE_FILE"
  exit 0
fi

# Get last assistant message text
LAST_OUTPUT=$(grep '"role":"assistant"' "$TRANSCRIPT_PATH" | tail -1 | jq -r '
  .message.content |
  map(select(.type == "text")) |
  map(.text) |
  join("\n")
' 2>/dev/null || echo "")

if [[ -z "$LAST_OUTPUT" ]]; then
  note "⚠️  Ralph loop: No assistant output found — stopping loop."
  rm "$RALPH_STATE_FILE"
  exit 0
fi

# Check for completion promise
VERIFY_FEEDBACK=""
if [[ "$COMPLETION_PROMISE" != "null" ]] && [[ -n "$COMPLETION_PROMISE" ]]; then
  PROMISE_TEXT=$(echo "$LAST_OUTPUT" | perl -0777 -pe 's/.*?<promise>(.*?)<\/promise>.*/$1/s; s/^\s+|\s+$//g; s/\s+/ /g' 2>/dev/null || echo "")
  if [[ -n "$PROMISE_TEXT" ]] && [[ "$PROMISE_TEXT" = "$COMPLETION_PROMISE" ]]; then
    # Promise asserted. If a deterministic verifier is configured, IT — not the
    # model's self-report — decides completion. The worker controls what reaches
    # this hook (the transcript); a deterministic command checks the world itself.
    # (mirrors the /goal verifier rule in leverage-patterns.md.)
    if [[ "$VERIFY_CMD" != "null" ]] && [[ -n "$VERIFY_CMD" ]]; then
      VERIFY_LOG="${RALPH_STATE_FILE}.verify.$$"
      RUN_PREFIX=""
      if command -v timeout >/dev/null 2>&1; then
        RUN_PREFIX="timeout 1800"
      fi
      if ( cd "$CLAUDE_PROJECT_DIR" && $RUN_PREFIX bash -c "$VERIFY_CMD" ) >"$VERIFY_LOG" 2>&1; then
        VERIFY_RC=0
      else
        VERIFY_RC=$?
      fi
      if [[ $VERIFY_RC -eq 0 ]]; then
        note "✅ Ralph loop: Promise '$COMPLETION_PROMISE' + verifier ('$VERIFY_CMD') exit 0. Loop complete."
        if [[ -f "$RALPH_PROGRESS_FILE" ]]; then
          note "   Run summary + lessons: .claude/ralph-state.local.md"
        fi
        rm -f "$VERIFY_LOG"
        rm "$RALPH_STATE_FILE"
        exit 0
      fi
      # Verifier FAILED — reject the promise, keep iterating with the evidence.
      VERIFY_TAIL=$(tail -n 25 "$VERIFY_LOG" 2>/dev/null || echo "")
      rm -f "$VERIFY_LOG"
      note "⛔ Ralph loop: Promise asserted but verifier '$VERIFY_CMD' exited $VERIFY_RC — rejecting promise, continuing."
      VERIFY_FEEDBACK="⛔ DETERMINISTIC VERIFIER FAILED. You emitted the completion promise, but \`$VERIFY_CMD\` exited ${VERIFY_RC} (non-zero), so the promise is REJECTED and the work is NOT done. Do NOT emit the promise again until \`$VERIFY_CMD\` exits 0 — and never weaken the verifier to force a pass. Last 25 lines of verifier output:
${VERIFY_TAIL}"
    else
      note "✅ Ralph loop: Promise detected — '$COMPLETION_PROMISE'. Loop complete."
      if [[ -f "$RALPH_PROGRESS_FILE" ]]; then
        note "   Run summary + lessons: .claude/ralph-state.local.md"
      fi
      rm "$RALPH_STATE_FILE"
      exit 0
    fi
  fi
fi

# Not done — continue loop
NEXT_ITERATION=$((ITERATION + 1))

# Extract prompt body (everything after the second ---)
PROMPT_TEXT=$(awk '/^---$/{i++; next} i>=2' "$RALPH_STATE_FILE")

if [[ -z "$PROMPT_TEXT" ]]; then
  note "⚠️  Ralph loop: No prompt text in state file — stopping."
  rm "$RALPH_STATE_FILE"
  exit 0
fi

# Update iteration counter atomically
TEMP_FILE="${RALPH_STATE_FILE}.tmp.$$"
sed "s/^iteration: .*/iteration: $NEXT_ITERATION/" "$RALPH_STATE_FILE" > "$TEMP_FILE"
mv "$TEMP_FILE" "$RALPH_STATE_FILE"

# Build system message
STATE_REMINDER="Read .claude/ralph-state.local.md first; update it before ending this iteration. 3 failed attempts on a sub-task = escalate, never retry."
if [[ "$COMPLETION_PROMISE" != "null" ]] && [[ -n "$COMPLETION_PROMISE" ]]; then
  SYSTEM_MSG="🔄 Ralph iteration $NEXT_ITERATION / $(if [[ $MAX_ITERATIONS -gt 0 ]]; then echo $MAX_ITERATIONS; else echo '∞'; fi) | Output <promise>$COMPLETION_PROMISE</promise> ONLY when genuinely true | $STATE_REMINDER"
else
  SYSTEM_MSG="🔄 Ralph iteration $NEXT_ITERATION / $(if [[ $MAX_ITERATIONS -gt 0 ]]; then echo $MAX_ITERATIONS; else echo '∞'; fi) | No completion promise set | $STATE_REMINDER"
fi

# If a verifier rejected the promise this turn, lead the next turn with that evidence.
if [[ -n "$VERIFY_FEEDBACK" ]]; then
  FEED_PROMPT="${VERIFY_FEEDBACK}

---

${PROMPT_TEXT}"
else
  FEED_PROMPT="$PROMPT_TEXT"
fi

# Block exit and feed prompt back
jq -n \
  --arg prompt "$FEED_PROMPT" \
  --arg msg "$SYSTEM_MSG" \
  '{
    "decision": "block",
    "reason": $prompt,
    "systemMessage": $msg
  }'

exit 0
