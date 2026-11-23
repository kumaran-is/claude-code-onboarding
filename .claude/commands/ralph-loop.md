---
description: Start a Ralph Wiggum autonomous iteration loop. Claude works on the task, and when it tries to exit, the stop hook feeds the same prompt back until done. Use for long autonomous tasks, overnight work, or multi-attempt problems.
argument-hint: '"PROMPT" [--max-iterations N] [--completion-promise "TEXT"] [--verify-cmd "COMMAND"]'
allowed-tools: Bash, Read, Write
---

# Ralph Loop

Start an autonomous iteration loop for the given task.

## Setup

```bash
# Parse arguments and create state file
ARGS="$ARGUMENTS"
PROMPT_PARTS=()
MAX_ITERATIONS=10
COMPLETION_PROMISE="null"
VERIFY_CMD="null"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --max-iterations)
      MAX_ITERATIONS="$2"; shift 2 ;;
    --completion-promise)
      COMPLETION_PROMISE="$2"; shift 2 ;;
    --verify-cmd)
      VERIFY_CMD="$2"; shift 2 ;;
    *)
      PROMPT_PARTS+=("$1"); shift ;;
  esac
done
PROMPT="${PROMPT_PARTS[*]}"

if [[ -z "$PROMPT" ]]; then
  echo "❌ No prompt provided. Usage: /ralph-loop \"Your task\" --max-iterations 10"
  exit 1
fi

mkdir -p "$CLAUDE_PROJECT_DIR/.claude"

if [[ "$COMPLETION_PROMISE" != "null" ]]; then
  CP_YAML="\"$COMPLETION_PROMISE\""
else
  CP_YAML="null"
fi

if [[ "$VERIFY_CMD" != "null" ]]; then
  VC_YAML="\"$VERIFY_CMD\""
else
  VC_YAML="null"
fi

cat > "$CLAUDE_PROJECT_DIR/.claude/ralph-loop.local.md" <<EOF
---
active: true
iteration: 1
max_iterations: $MAX_ITERATIONS
completion_promise: $CP_YAML
verify_cmd: $VC_YAML
started_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
---

$PROMPT
EOF

# Progress state file (separate from the hook-managed loop file — survives loop end).
# If one already exists, KEEP it: a re-run after a crash/cancel resumes from prior progress.
RALPH_STATE="$CLAUDE_PROJECT_DIR/.claude/ralph-state.local.md"
if [[ -f "$RALPH_STATE" ]]; then
  echo "📄 Existing ralph-state.local.md found — resuming with prior progress/escalations."
  echo "   (Starting an unrelated task? Delete it first: rm .claude/ralph-state.local.md)"
else
  cat > "$RALPH_STATE" <<EOF
# Ralph loop state

## Last run
$(date -u +%Y-%m-%dT%H:%M:%SZ) · iteration 1 · loop started

## In progress
- (nothing yet)

## Completed
- (nothing yet)

## Escalated to humans (do NOT retry)
- (none)

## Lessons learned (durable discoveries — write here, not in chat)
- (none)

## Attempt counts
- (sub-task: N failed attempts)
EOF
fi

echo ""
echo "🔄 Ralph loop activated!"
echo "   Iteration:   1 of $(if [[ $MAX_ITERATIONS -gt 0 ]]; then echo $MAX_ITERATIONS; else echo '∞ (unlimited)'; fi)"
if [[ "$COMPLETION_PROMISE" != "null" ]]; then
  echo "   Promise:     $COMPLETION_PROMISE"
  if [[ "$VERIFY_CMD" != "null" ]]; then
    echo "   Verifier:    $VERIFY_CMD  (must exit 0 — the promise alone will NOT end the loop)"
  fi
  echo ""
  echo "═══════════════════════════════════════════════"
  echo "  To exit: output <promise>$COMPLETION_PROMISE</promise>"
  echo "  ONLY when the statement is GENUINELY TRUE."
  if [[ "$VERIFY_CMD" != "null" ]]; then
    echo "  The loop then runs:  $VERIFY_CMD"
    echo "  Exit happens ONLY if that command returns exit 0."
  fi
  echo "  Do NOT output a false promise to escape."
  echo "═══════════════════════════════════════════════"
fi
echo ""
echo "  Monitor:  head -5 .claude/ralph-loop.local.md"
echo "  Cancel:   /cancel-ralph"
echo ""
```

Work on this task. You will see your previous work in files and git history each iteration.

**RULES:**
1. If `--completion-promise` is set, output `<promise>EXACT_TEXT</promise>` ONLY when the statement is genuinely and completely true
2. Do NOT lie to escape — the loop is designed to run until real completion
3. Use TaskList, git log, and modified files to track progress across iterations
4. **State file (mandatory, every iteration):** READ `.claude/ralph-state.local.md` FIRST each iteration — it is your memory across iterations; never re-derive what it already records. At the END of each iteration, update it: refresh `## Last run` (timestamp · iteration · one-line summary), move finished items to `## Completed`, record the current item under `## In progress`, append durable discoveries (env quirks, broken assumptions, "X requires Y") to `## Lessons learned`, and bump `## Attempt counts` for anything that failed this iteration.
5. **Escalation — 3-attempt hard stop inside the loop:** before retrying any sub-task, check its count in `## Attempt counts`. If it has already failed 3 attempts (across iterations), do NOT try a 4th — move it to `## Escalated to humans` with one line per attempt (what you tried, what failed), then continue with the next sub-task. NEVER retry an escalated item in later iterations. **Escalate before the 3rd try on a no-progress signal too:** if the SAME normalized error (strip timestamps/IDs/paths) reproduced after your change, or your new diff reverts a prior iteration's diff (ping-pong), or you are about to re-run a strategy already listed as failed — escalate now rather than burning the remaining attempts. Record the normalized error signature next to the count so repeats are detectable across iterations.
6. **All-escalated exit:** if every remaining sub-task is escalated, do not burn the remaining iterations and do not emit a false promise — end the loop yourself with `rm "$CLAUDE_PROJECT_DIR/.claude/ralph-loop.local.md"`, then report the escalated list.
7. **Deterministic completion gate (`--verify-cmd`):** when a verifier command is set, the promise is necessary but NOT sufficient — after you emit `<promise>…</promise>` the stop hook runs the verifier and ends the loop ONLY if it exits 0. A non-zero exit REJECTS the promise and feeds the verifier's output back as your next turn; fix the root cause and re-emit only when it will pass. This keeps the authoritative completion signal in a deterministic check of the world, not your own summary of it (mirrors the `/goal` rule in `leverage-patterns.md`). NEVER weaken the verifier to make it pass.

$ARGUMENTS
