---
description: Start a Ralph Wiggum autonomous iteration loop. Claude works on the task, and when it tries to exit, the stop hook feeds the same prompt back until done. Use for long autonomous tasks, overnight work, or multi-attempt problems.
argument-hint: '"PROMPT" [--max-iterations N] [--completion-promise "TEXT"] [--verify-cmd "COMMAND"]'
allowed-tools: Bash, Read, Write
---

# Ralph Loop

Start an autonomous iteration loop for the given task.

## Setup

```bash
# Arguments: $ARGUMENTS
# Claude: fill PROMPT, MAX_ITERATIONS, COMPLETION_PROMISE, VERIFY_CMD, REQUIRE_VERIFY, and SESSION_ID
# from the arguments above BEFORE running this block. Do not parse them
# with `$#`/`shift`: a Bash tool call has no positional parameters, so such a loop never runs (every option
# was ignored and the prompt was always empty). Use single quotes; write a literal ' as '\''.
PROMPT='<task text — every argument that is not an option>'
MAX_ITERATIONS=10                  # --max-iterations N  (/next --fix-loop MUST be 5)
COMPLETION_PROMISE="null"          # --completion-promise "TEXT" → 'TEXT'
VERIFY_CMD="null"                  # --verify-cmd "COMMAND"     → 'COMMAND'  (a real shell command, NEVER /verify)
REQUIRE_VERIFY=false               # true when invoked from /next --fix-loop
# Session identity: prefer the runtime env; if empty, replace with the current
# Claude Code session id before running. Isolation will not work without it.
SESSION_ID="${CLAUDE_SESSION_ID:-}"
WORKTREE="${CLAUDE_PROJECT_DIR:-}"
AC_SHA="${RALPH_AC_SHA256:-}"
CMD_SHA="${RALPH_VERIFY_CMD_SHA256:-}"
case "$MAX_ITERATIONS" in ''|*[!0-9]*) echo "❌ --max-iterations must be a whole number"; exit 1 ;; esac

if [[ -z "$PROMPT" || "$PROMPT" == "<task text"* ]]; then
  echo "❌ No prompt provided. Usage: /ralph-loop \"Your task\" --max-iterations 10"
  exit 1
fi

mkdir -p "$CLAUDE_PROJECT_DIR/.claude"

RALPH_LOOP_FILE="$CLAUDE_PROJECT_DIR/.claude/ralph-loop.local.md"
if [[ -f "$RALPH_LOOP_FILE" ]]; then
  EXISTING_SID=$(grep '^session_id:' "$RALPH_LOOP_FILE" | sed 's/session_id: *//' | sed 's/^"\(.*\)"$/\1/' || true)
  if [[ -n "$EXISTING_SID" && "$EXISTING_SID" != "null" && -n "$SESSION_ID" && "$EXISTING_SID" != "$SESSION_ID" ]]; then
    echo "❌ Active Ralph loop belongs to another session ($EXISTING_SID)."
    echo "   Do not overwrite it. Wait, or ask that session to /cancel-ralph."
    exit 1
  fi
fi

if [[ "$VERIFY_CMD" != "null" && -n "$VERIFY_CMD" ]]; then
  VALIDATE="$CLAUDE_PROJECT_DIR/.claude/skills/next-issue/scripts/check-next-issue.py"
  if [[ -f "$VALIDATE" ]]; then
    python3 "$VALIDATE" --validate-verify-cmd "$VERIFY_CMD" || exit 1
  fi
fi

if [[ "$REQUIRE_VERIFY" == "true" || "$REQUIRE_VERIFY" == "yes" ]]; then
  if [[ "$VERIFY_CMD" == "null" || -z "$VERIFY_CMD" ]]; then
    echo "❌ /next --fix-loop requires --verify-cmd with a real shell command (not /verify)."
    exit 1
  fi
  case "$MAX_ITERATIONS" in
    ''|0|*[!0-9]*) echo "❌ --max-iterations must be a whole number"; exit 1 ;;
  esac
  if [[ "$MAX_ITERATIONS" -gt 5 ]]; then
    echo "❌ /next --fix-loop caps --max-iterations at 5 (got $MAX_ITERATIONS)."
    exit 1
  fi
fi

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

if [[ -n "$SESSION_ID" ]]; then
  SID_YAML="\"$SESSION_ID\""
else
  SID_YAML="null"
fi

if [[ "$REQUIRE_VERIFY" == "true" || "$REQUIRE_VERIFY" == "yes" ]]; then
  RV_YAML="true"
else
  RV_YAML="false"
fi

if [[ -n "$WORKTREE" ]]; then
  WT_YAML="\"$WORKTREE\""
else
  WT_YAML="null"
fi

if [[ -z "$CMD_SHA" && "$VERIFY_CMD" != "null" && -n "$VERIFY_CMD" ]] && command -v python3 >/dev/null 2>&1; then
  CMD_SHA=$(printf '%s' "$VERIFY_CMD" | python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.read().strip().encode()).hexdigest())' 2>/dev/null || true)
fi
if [[ -n "$AC_SHA" ]]; then
  AC_YAML="\"$AC_SHA\""
else
  AC_YAML="null"
fi
if [[ -n "$CMD_SHA" ]]; then
  CMD_SHA_YAML="\"$CMD_SHA\""
else
  CMD_SHA_YAML="null"
fi

cat > "$RALPH_LOOP_FILE" <<EOF
---
active: true
iteration: 1
max_iterations: $MAX_ITERATIONS
completion_promise: $CP_YAML
verify_cmd: $VC_YAML
session_id: $SID_YAML
require_verify: $RV_YAML
worktree: $WT_YAML
ac_sha256: $AC_YAML
verify_cmd_sha256: $CMD_SHA_YAML
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

## Last verify (hook-written — do not invent PASS lines)
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
  if [[ "$REQUIRE_VERIFY" == "true" || "$REQUIRE_VERIFY" == "yes" ]]; then
    echo "   Gate:        require_verify=true (promise-only completion is disabled)"
  fi
  if [[ -n "$SESSION_ID" ]]; then
    echo "   Session:     $SESSION_ID"
  else
    echo "   Session:     (unset — concurrent sessions can interfere; set CLAUDE_SESSION_ID)"
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
4. **State file (mandatory, every iteration):** READ `.claude/ralph-state.local.md` FIRST each iteration — it is your memory across iterations; never re-derive what it already records. At the END of each iteration, update it: refresh `## Last run` (timestamp · iteration · one-line summary), move finished items to `## Completed`, record the current item under `## In progress`, append durable discoveries (env quirks, broken assumptions, "X requires Y") to `## Lessons learned`, and bump `## Attempt counts` for anything that failed this iteration. Never write `## Last verify` or a PASS claim — the Stop hook is the only writer. Never edit `## Contract snapshot`, `ac_sha256`, or `verify_cmd` / `verify_cmd_sha256` (PreCompact restores those unchanged).
5. **Escalation — 3-attempt hard stop inside the loop:** before retrying any sub-task, check its count in `## Attempt counts`. If it has already failed 3 attempts (across iterations), do NOT try a 4th — move it to `## Escalated to humans` with one line per attempt (what you tried, what failed), then continue with the next sub-task. NEVER retry an escalated item in later iterations. **Escalate before the 3rd try on a no-progress signal too:** if the SAME normalized error (strip timestamps/IDs/paths) reproduced after your change, or your new diff reverts a prior iteration's diff (ping-pong), or you are about to re-run a strategy already listed as failed — escalate now rather than burning the remaining attempts. Record the normalized error signature next to the count so repeats are detectable across iterations.
6. **All-escalated exit:** if every remaining sub-task is escalated, do not burn the remaining iterations and do not emit a false promise — end the loop yourself with `rm "$CLAUDE_PROJECT_DIR/.claude/ralph-loop.local.md"`, then report the escalated list.
7. **Deterministic completion gate (`--verify-cmd`):** when a verifier command is set (or `require_verify: true`), the promise is necessary but NOT sufficient — after you emit `<promise>…</promise>` the stop hook runs the verifier and ends the loop ONLY if it exits 0. A non-zero exit, a timeout, a slash command (`/verify`), a no-op (`true`, `:`, `exit 0`), or a destructive git/gh command REJECTS the promise. `/verify` is a Claude Code command, not a shell binary — pass the stack command you actually ran from `verify.md` (for example `flutter test`, `npm exec --no -- ng test --watch=false`, `npx vitest run`, `uv run --no-sync pytest -q`, `./mvnw test -q`). NEVER weaken the verifier to make it pass.
8. **Session isolation:** the Stop hook ignores payloads whose `session_id` does not match `session_id` in `.claude/ralph-loop.local.md`. Empty `session_id` plus `require_verify: true` is fail-closed until a payload binds it. Do not start a second loop over another session's file. `/cancel-ralph` is a human cancel and may delete the loop file. Progress in `.claude/ralph-state.local.md` and PreCompact checkpoints are unchanged and remain the resume surface. Approved `ac_sha256` / `verify_cmd_sha256` must be copied back from the PreCompact snapshot if compaction rewrote them.

$ARGUMENTS
