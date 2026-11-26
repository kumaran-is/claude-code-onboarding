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

# Slash commands (/verify) and no-ops are not deterministic gates. A completion
# promise plus one of these is NOT proof. Destructive git/gh must never be a gate.
verify_cmd_unusable() {
  local c="${1:-}"
  c="${c#"${c%%[![:space:]]*}"}"
  c="${c%"${c##*[![:space:]]}"}"
  [[ -n "$c" && "$c" != "null" ]] || return 0
  local first
  first=$(printf '%s\n' "$c" | awk '{print $1}')
  case "$first" in
    true|:|echo|/bin/true|/usr/bin/true) return 0 ;;
  esac
  [[ "$c" == "exit 0" ]] && return 0
  printf '%s' "$c" | grep -qE '(bash|sh|zsh)[[:space:]]+-c[[:space:]]+['\''"]?(true|:|exit 0)' && return 0
  case "$first" in
    /*)
      if printf '%s' "$first" | grep -q '^/[A-Za-z][A-Za-z0-9_-]*$'; then
        return 0
      fi
      ;;
  esac
  printf '%s' "$c" | grep -qE '(^|[[:space:]])(git[[:space:]]+(commit|push|merge|reset)|gh[[:space:]]+pr[[:space:]]+merge)' && return 0
  return 1
}

yaml_unquote() {
  local v="${1:-}"
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  if [[ "$v" == \"*\" ]]; then
    v="${v#\"}"
    v="${v%\"}"
  fi
  printf '%s' "$v"
}

# Exit 0 if this Stop event may drive the loop. A stored session_id that does
# not match the payload (or an empty payload) is a foreign/unidentified session.
session_owns_loop() {
  local stored="${1:-}" payload="${2:-}"
  [[ "$stored" == "null" ]] && stored=""
  if [[ -n "$stored" ]]; then
    [[ -n "$payload" && "$payload" == "$stored" ]]
    return $?
  fi
  return 0
}

run_verify_cmd() {
  local cmd="$1"
  local log="$2"
  local secs="${RALPH_VERIFY_TIMEOUT:-1800}"
  local rc=0
  if command -v python3 >/dev/null 2>&1; then
    ( cd "$CLAUDE_PROJECT_DIR" && python3 -c '
import subprocess, sys
cmd, secs = sys.argv[1], float(sys.argv[2])
try:
    r = subprocess.run(["bash", "-c", cmd], timeout=secs)
    raise SystemExit(r.returncode)
except subprocess.TimeoutExpired:
    raise SystemExit(124)
' "$cmd" "$secs" ) >"$log" 2>&1 || rc=$?
    return "$rc"
  fi
  ( cd "$CLAUDE_PROJECT_DIR" && bash -c "$cmd" ) >"$log" 2>&1 || rc=$?
  return "$rc"
}

ralph_escalate() {
  local why="$1"
  local progress="${RALPH_PROGRESS_FILE:-$CLAUDE_PROJECT_DIR/.claude/ralph-state.local.md}"
  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)
  mkdir -p "$(dirname "$progress")" 2>/dev/null || true
  if [[ ! -f "$progress" ]]; then
    printf '%s\n' "# Ralph loop state" "" "## Escalated to humans (do NOT retry)" "- (none)" > "$progress"
  fi
  if ! grep -q '^## Escalated to humans' "$progress" 2>/dev/null; then
    printf '\n## Escalated to humans (do NOT retry)\n' >> "$progress"
  fi
  printf '%s\n' "- ESCALATED $ts · iteration ${ITERATION:-?} · $why" >> "$progress"
}

record_verify_evidence() {
  local rc="$1"
  local cmd="$2"
  local progress="${RALPH_PROGRESS_FILE:-$CLAUDE_PROJECT_DIR/.claude/ralph-state.local.md}"
  local ts stamp tree dirty
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)
  tree=$(git -C "$CLAUDE_PROJECT_DIR" rev-parse HEAD 2>/dev/null || echo nogit)
  dirty=$(git -C "$CLAUDE_PROJECT_DIR" status --porcelain -uall 2>/dev/null | python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest()[:16])' 2>/dev/null || echo none)
  mkdir -p "$(dirname "$progress")" 2>/dev/null || true
  if [[ ! -f "$progress" ]]; then
    printf '%s\n' "# Ralph loop state" "" "## Last verify (hook-written)" > "$progress"
  fi
  if ! grep -q '^## Last verify' "$progress" 2>/dev/null; then
    printf '\n## Last verify (hook-written)\n' >> "$progress"
  fi
  printf '%s\n' "- $ts · exit=$rc · cmd=$cmd · HEAD=$tree · dirty=$dirty" >> "$progress"
  if [[ "$rc" == "0" ]]; then
    stamp="$CLAUDE_PROJECT_DIR/.claude/scripts/review_state.py"
    if [[ ! -f "$stamp" ]]; then
      stamp="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../scripts/review_state.py"
    fi
    if [[ -f "$stamp" ]]; then
      python3 "$stamp" stamp write verify --mode ralph --note "hook exit=0 cmd=$cmd HEAD=$tree" --exit-code 0 >/dev/null 2>&1 || true
    fi
  fi
}

bind_session_id() {
  local sid="$1"
  local f="$RALPH_STATE_FILE"
  [[ "$sid" =~ ^[A-Za-z0-9._-]+$ ]] || return 1
  if grep -q '^session_id:' "$f"; then
    awk -v sid="$sid" '/^session_id:/ { print "session_id: \"" sid "\""; next } { print }' "$f" > "${f}.sid.$$"
  else
    awk -v sid="$sid" '
      /^---$/ { c++; print; if (c==1) print "session_id: \"" sid "\""; next }
      { print }
    ' "$f" > "${f}.sid.$$"
  fi
  mv "${f}.sid.$$" "$f"
}

sha256_text() {
  printf '%s' "$1" | python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.read().strip().encode()).hexdigest())' 2>/dev/null || true
}

contract_checker() {
  local c="$CLAUDE_PROJECT_DIR/.claude/skills/next-issue/scripts/check-next-issue.py"
  if [[ -f "$c" ]]; then
    printf '%s' "$c"
    return 0
  fi
  c="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../skills/next-issue/scripts/check-next-issue.py"
  if [[ -f "$c" ]]; then
    printf '%s' "$c"
    return 0
  fi
  return 1
}

# Exit 0 if no snapshot or the live tree still matches. Exit 1 on WEAKENED.
check_contract_snapshot() {
  local progress="${RALPH_PROGRESS_FILE:-$CLAUDE_PROJECT_DIR/.claude/ralph-state.local.md}"
  local checker tmp rc
  checker=$(contract_checker) || return 0
  [[ -f "$progress" ]] || return 0
  grep -q '^## Contract snapshot' "$progress" 2>/dev/null || return 0
  tmp=$(mktemp)
  python3 -c '
import pathlib, sys
t = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
marker = t.find("## Contract snapshot")
if marker < 0:
    raise SystemExit(0)
chunk = t[marker:]
i = chunk.find("```json")
j = chunk.find("```", i + 7) if i >= 0 else -1
if i < 0 or j < 0:
    raise SystemExit(0)
pathlib.Path(sys.argv[2]).write_text(chunk[i + 7:j].strip() + "\n", encoding="utf-8")
' "$progress" "$tmp" || { rm -f "$tmp"; return 0; }
  [[ -s "$tmp" ]] || { rm -f "$tmp"; return 0; }
  python3 "$checker" --check-contract "$tmp" --root "$CLAUDE_PROJECT_DIR" >/dev/null 2>&1
  rc=$?
  if [[ $rc -eq 0 ]]; then
    # Frontmatter hashes captured at loop start must still match the snapshot JSON.
    snap_ac=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("ac_sha256") or "")' "$tmp" 2>/dev/null || true)
    snap_cmd=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("verify_cmd_sha256") or "")' "$tmp" 2>/dev/null || true)
    if [[ -n "${AC_SHA:-}" && "$AC_SHA" != "null" && -n "$snap_ac" && "$snap_ac" != "$AC_SHA" ]]; then
      rc=1
    fi
    if [[ -n "${CMD_SHA:-}" && "$CMD_SHA" != "null" && -n "$snap_cmd" && "$snap_cmd" != "$CMD_SHA" ]]; then
      rc=1
    fi
  fi
  rm -f "$tmp"
  return "$rc"
}

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
  req() { printf '%s\n' '---' 'iteration: 1' 'max_iterations: 5' 'completion_promise: "DONE"' "verify_cmd: $1" 'require_verify: true' 'session_id: "t1"' '---' 'keep going' > "$T/.claude/ralph-loop.local.md"; }
  pay() { printf '{"session_id":"t1","transcript_path":"%s"}' "$T/transcript.jsonl"; }
  # False promise cannot bypass a failing machine gate.
  req '"ls /nonexistent-ralph-verify-gate"'
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"ship it <promise>DONE</promise>"}]}}' > "$T/transcript.jsonl"
  OUT=$(pay | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if printf '%s' "$OUT" | grep -q '"decision": *"block"' && grep -q '^iteration: 2$' "$T/.claude/ralph-loop.local.md" && printf '%s' "$OUT" | grep -q 'DETERMINISTIC VERIFIER FAILED'; then echo "  ok   negative: false promise + failing verify_cmd does not complete"; else echo "  FAIL false promise bypassed the gate (out: $OUT)"; FAIL=1; fi
  if grep -q 'exit=' "$T/.claude/ralph-state.local.md" 2>/dev/null; then echo "  ok   evidence: hook recorded verify exit"; else echo "  FAIL hook did not record verify evidence"; FAIL=1; fi
  # Slash command is not a shell verifier — promise must not complete.
  req '"/verify full"'
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"<promise>DONE</promise>"}]}}' > "$T/transcript.jsonl"
  OUT=$(pay | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if printf '%s' "$OUT" | grep -q '"decision": *"block"' && [[ -f "$T/.claude/ralph-loop.local.md" ]] && printf '%s' "$OUT" | grep -qi 'not a shell command\|unusable verifier\|DETERMINISTIC VERIFIER FAILED'; then echo "  ok   negative: slash-command verify_cmd cannot complete"; else echo "  FAIL slash verify_cmd completed or silent (out: $OUT)"; FAIL=1; fi
  # Wrapped no-op must not complete.
  req '"bash -c true"'
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"<promise>DONE</promise>"}]}}' > "$T/transcript.jsonl"
  OUT=$(pay | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if printf '%s' "$OUT" | grep -q '"decision": *"block"' && [[ -f "$T/.claude/ralph-loop.local.md" ]]; then echo "  ok   negative: wrapped no-op verify_cmd cannot complete"; else echo "  FAIL wrapped no-op completed (out: $OUT)"; FAIL=1; fi
  # require_verify with no command: promise alone is insufficient.
  req 'null'
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"<promise>DONE</promise>"}]}}' > "$T/transcript.jsonl"
  OUT=$(pay | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if printf '%s' "$OUT" | grep -q '"decision": *"block"' && [[ -f "$T/.claude/ralph-loop.local.md" ]]; then echo "  ok   negative: require_verify rejects promise-only completion"; else echo "  FAIL require_verify allowed promise-only (out: $OUT)"; FAIL=1; fi
  # Real verifier exit 0 + promise completes.
  req '"test -d .claude"'
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"<promise>DONE</promise>"}]}}' > "$T/transcript.jsonl"
  OUT=$(pay | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"' && [[ ! -f "$T/.claude/ralph-loop.local.md" ]]; then echo "  ok   positive: promise + real verify_cmd exit 0 completes"; else echo "  FAIL real verifier did not complete (out: $OUT)"; FAIL=1; fi
  # Timeout: hung verifier cannot complete.
  req '"python3 -c \"import time; time.sleep(8)\""'
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"<promise>DONE</promise>"}]}}' > "$T/transcript.jsonl"
  OUT=$(pay | RALPH_VERIFY_TIMEOUT=1 CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if printf '%s' "$OUT" | grep -q '"decision": *"block"' && grep -q '^iteration: 2$' "$T/.claude/ralph-loop.local.md"; then echo "  ok   timeout: hung verify_cmd does not complete"; else echo "  FAIL timeout did not reject (out: $OUT)"; FAIL=1; fi
  # Stagnation: max_iterations 5 stops even with a promise that has not passed the gate.
  printf '%s\n' '---' 'iteration: 5' 'max_iterations: 5' 'completion_promise: "DONE"' 'verify_cmd: "ls /nonexistent-ralph-stagnation"' 'require_verify: true' 'session_id: "t1"' '---' 'keep going' > "$T/.claude/ralph-loop.local.md"
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"<promise>DONE</promise>"}]}}' > "$T/transcript.jsonl"
  OUT=$(pay | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"' && [[ ! -f "$T/.claude/ralph-loop.local.md" ]] && grep -q 'ESCALATED' "$T/.claude/ralph-state.local.md"; then echo "  ok   stagnation: max_iterations reached -> ESCALATED"; else echo "  FAIL stagnation did not escalate (out: $OUT)"; FAIL=1; fi
  # Stop-hook block cap: never emit decision:block at the platform bound.
  printf '%s\n' '---' 'iteration: 2' 'max_iterations: 10' 'completion_promise: "DONE"' 'session_id: "t1"' '---' 'keep going' > "$T/.claude/ralph-loop.local.md"
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"working"}]}}' > "$T/transcript.jsonl"
  OUT=$(pay | CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=3 CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"' && [[ ! -f "$T/.claude/ralph-loop.local.md" ]] && grep -q 'ESCALATED' "$T/.claude/ralph-state.local.md"; then echo "  ok   cap: Stop-hook bound escalates without block"; else echo "  FAIL cap did not escalate (out: $OUT)"; FAIL=1; fi
  # require_verify with empty session_id cannot be driven by an unidentified payload.
  printf '%s\n' '---' 'iteration: 1' 'max_iterations: 5' 'completion_promise: "DONE"' 'verify_cmd: "test -d .claude"' 'require_verify: true' '---' 'keep going' > "$T/.claude/ralph-loop.local.md"
  OUT=$(printf '{"transcript_path":"%s"}' "$T/transcript.jsonl" | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"' && grep -q '^iteration: 1$' "$T/.claude/ralph-loop.local.md"; then echo "  ok   isolation: empty session_id + require_verify is not driven"; else echo "  FAIL empty session drove require_verify loop (out: $OUT)"; FAIL=1; fi
  # Concurrent session: foreign session_id must not mutate or continue the loop.
  printf '%s\n' '---' 'iteration: 1' 'max_iterations: 5' 'completion_promise: "DONE"' 'session_id: "sess-a"' 'verify_cmd: "test -d .claude"' 'require_verify: true' '---' 'keep going' > "$T/.claude/ralph-loop.local.md"
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"working"}]}}' > "$T/transcript.jsonl"
  OUT=$(printf '{"session_id":"sess-b","transcript_path":"%s"}' "$T/transcript.jsonl" | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"' && grep -q '^iteration: 1$' "$T/.claude/ralph-loop.local.md"; then echo "  ok   concurrent: foreign session is ignored, state untouched"; else echo "  FAIL foreign session drove the loop (out: $OUT)"; FAIL=1; fi
  # Owning session continues.
  OUT=$(printf '{"session_id":"sess-a","transcript_path":"%s"}' "$T/transcript.jsonl" | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if printf '%s' "$OUT" | grep -q '"decision": *"block"' && grep -q '^iteration: 2$' "$T/.claude/ralph-loop.local.md"; then echo "  ok   concurrent: owning session continues"; else echo "  FAIL owning session did not continue (out: $OUT)"; FAIL=1; fi
  # Empty payload session_id cannot steal a bound loop.
  printf '%s\n' '---' 'iteration: 1' 'max_iterations: 5' 'completion_promise: "DONE"' 'session_id: "sess-a"' '---' 'keep going' > "$T/.claude/ralph-loop.local.md"
  OUT=$(printf '{"transcript_path":"%s"}' "$T/transcript.jsonl" | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"' && grep -q '^iteration: 1$' "$T/.claude/ralph-loop.local.md"; then echo "  ok   concurrent: unidentified session cannot steal a bound loop"; else echo "  FAIL empty session_id stole the loop (out: $OUT)"; FAIL=1; fi
  # Bind: require_verify with no stored session_id takes the payload id and continues.
  printf '%s\n' '---' 'iteration: 1' 'max_iterations: 5' 'completion_promise: "DONE"' 'verify_cmd: "test -d .claude"' 'require_verify: true' '---' 'keep going' > "$T/.claude/ralph-loop.local.md"
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"working"}]}}' > "$T/transcript.jsonl"
  OUT=$(printf '{"session_id":"bind-1","transcript_path":"%s"}' "$T/transcript.jsonl" | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if printf '%s' "$OUT" | grep -q '"decision": *"block"' && grep -q 'session_id: "bind-1"' "$T/.claude/ralph-loop.local.md"; then echo "  ok   isolation: empty stored session binds payload id"; else echo "  FAIL bind did not take payload session (out: $OUT)"; FAIL=1; fi
  # Duplicate JSON: continue path emits a single decision object (use the bind continue output).
  njson=$(printf '%s' "$OUT" | python3 -c 'import json,sys; t=sys.stdin.read(); n=0
raw=t
while raw.strip():
    raw=raw.lstrip()
    try:
        obj, idx = json.JSONDecoder().raw_decode(raw)
    except Exception:
        break
    n += 1
    raw = raw[idx:]
print(n)' 2>/dev/null || echo 0)
  if [[ "$njson" == "1" ]]; then echo "  ok   robustness: continue path emits one JSON object"; else echo "  FAIL duplicate JSON on continue (count=$njson out=$OUT)"; FAIL=1; fi
  # Invalid session id characters must not be written into frontmatter.
  printf '%s\n' '---' 'iteration: 1' 'max_iterations: 5' 'completion_promise: "DONE"' 'verify_cmd: "test -d .claude"' 'require_verify: true' '---' 'keep going' > "$T/.claude/ralph-loop.local.md"
  OUT=$(printf '{"session_id":"bad/id","transcript_path":"%s"}' "$T/transcript.jsonl" | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"' && grep -q '^iteration: 1$' "$T/.claude/ralph-loop.local.md" && ! grep -q 'bad/id' "$T/.claude/ralph-loop.local.md"; then echo "  ok   isolation: invalid session id is not bound"; else echo "  FAIL invalid session id was bound (out: $OUT)"; FAIL=1; fi
  # Missing jq: do not drive or delete the loop.
  printf '%s\n' '---' 'iteration: 1' 'max_iterations: 5' 'completion_promise: "DONE"' 'session_id: "t1"' '---' 'keep going' > "$T/.claude/ralph-loop.local.md"
  OUT=$(pay | RALPH_FORCE_NO_JQ=1 CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"' && grep -q '^iteration: 1$' "$T/.claude/ralph-loop.local.md"; then echo "  ok   robustness: missing jq does not drive or destroy the loop"; else echo "  FAIL missing jq drove or deleted the loop (out: $OUT)"; FAIL=1; fi
  # Worktree mismatch: foreign CLAUDE_PROJECT_DIR is ignored (state file is in $T).
  printf '%s\n' '---' 'iteration: 1' 'max_iterations: 5' 'completion_promise: "DONE"' 'session_id: "t1"' "worktree: \"$T/other-tree\"" '---' 'keep going' > "$T/.claude/ralph-loop.local.md"
  OUT=$(pay | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"' && grep -q '^iteration: 1$' "$T/.claude/ralph-loop.local.md"; then echo "  ok   isolation: worktree mismatch is ignored"; else echo "  FAIL worktree mismatch drove the loop (out: $OUT)"; FAIL=1; fi
  # Contract WEAKENED: verify exit 0 is not completion if tests were skipped.
  printf '%s\n' 'void main() { test("empty", () {}, skip: true); }' > "$T/t_widget_test.dart"
  {
    printf '%s\n' '---' 'iteration: 1' 'max_iterations: 5' 'completion_promise: "DONE"' 'verify_cmd: "test -d .claude"' 'require_verify: true' 'session_id: "t1"' '---' 'keep going'
  } > "$T/.claude/ralph-loop.local.md"
  python3 -c '
import hashlib, json, pathlib
p = pathlib.Path("'"$T"'")
(p/".claude"/"ralph-state.local.md").write_text(
    "# Ralph loop state\n\n## Contract snapshot\n```json\n"
    + json.dumps({
        "ac_sha256": hashlib.sha256(b"empty state widget test exits 0").hexdigest(),
        "verify_cmd": "test -d .claude",
        "verify_cmd_sha256": hashlib.sha256(b"test -d .claude").hexdigest(),
        "test_files": ["t_widget_test.dart"],
        "test_sha256": {"t_widget_test.dart": "x"},
        "assert_count": 1,
        "skip_count": 0,
        "quality_files": [],
        "quality_sha256": {},
        "cov_floor": None,
    }, sort_keys=True)
    + "\n```\n"
)
'
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"<promise>DONE</promise>"}]}}' > "$T/transcript.jsonl"
  OUT=$(pay | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if printf '%s' "$OUT" | grep -q '"decision": *"block"' && [[ -f "$T/.claude/ralph-loop.local.md" ]] && printf '%s' "$OUT" | grep -qi 'WEAKENED\|CONTRACT'; then echo "  ok   integrity: WEAKENED contract rejects exit-0 verifier"; else echo "  FAIL weakened contract completed (out: $OUT)"; FAIL=1; fi
  # verify_cmd hash mutation rejects completion.
  MUT=$(python3 -c 'import hashlib; print(hashlib.sha256(b"flutter test").hexdigest())')
  printf '%s\n' '---' 'iteration: 1' 'max_iterations: 5' 'completion_promise: "DONE"' 'verify_cmd: "test -d .claude"' 'require_verify: true' 'session_id: "t1"' "verify_cmd_sha256: \"$MUT\"" '---' 'keep going' > "$T/.claude/ralph-loop.local.md"
  printf '%s\n' '{"role":"assistant","message":{"content":[{"type":"text","text":"<promise>DONE</promise>"}]}}' > "$T/transcript.jsonl"
  OUT=$(pay | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if printf '%s' "$OUT" | grep -q '"decision": *"block"' && [[ -f "$T/.claude/ralph-loop.local.md" ]]; then echo "  ok   integrity: mutated verify_cmd hash rejects completion"; else echo "  FAIL mutated verifier completed (out: $OUT)"; FAIL=1; fi
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

# Missing jq: do not drive or destroy an active loop (fail-closed isolation).
if ! command -v jq >/dev/null 2>&1 || [[ "${RALPH_FORCE_NO_JQ:-}" == "1" ]]; then
  exit 0
fi

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
COMPLETION_PROMISE=$(yaml_unquote "$(echo "$FRONTMATTER" | grep '^completion_promise:' | sed 's/completion_promise: *//' || true)")
VERIFY_CMD=$(yaml_unquote "$(echo "$FRONTMATTER" | grep '^verify_cmd:' | sed 's/^verify_cmd: *//' || true)")
STORED_SESSION=$(yaml_unquote "$(echo "$FRONTMATTER" | grep '^session_id:' | sed 's/^session_id: *//' || true)")
REQUIRE_VERIFY=$(yaml_unquote "$(echo "$FRONTMATTER" | grep '^require_verify:' | sed 's/^require_verify: *//' || true)")
STORED_WORKTREE=$(yaml_unquote "$(echo "$FRONTMATTER" | grep '^worktree:' | sed 's/^worktree: *//' || true)")
AC_SHA=$(yaml_unquote "$(echo "$FRONTMATTER" | grep '^ac_sha256:' | sed 's/^ac_sha256: *//' || true)")
CMD_SHA=$(yaml_unquote "$(echo "$FRONTMATTER" | grep '^verify_cmd_sha256:' | sed 's/^verify_cmd_sha256: *//' || true)")

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

PAYLOAD_SESSION=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
if [[ "$REQUIRE_VERIFY" == "true" || "$REQUIRE_VERIFY" == "yes" ]]; then
  if [[ -z "$STORED_SESSION" || "$STORED_SESSION" == "null" ]]; then
    if [[ -z "$PAYLOAD_SESSION" ]]; then
      exit 0
    fi
    if ! bind_session_id "$PAYLOAD_SESSION"; then
      exit 0
    fi
    STORED_SESSION="$PAYLOAD_SESSION"
  fi
fi
if ! session_owns_loop "$STORED_SESSION" "$PAYLOAD_SESSION"; then
  # Foreign or unidentified session: zero interference, do not increment or complete.
  exit 0
fi
if [[ -n "$STORED_WORKTREE" && "$STORED_WORKTREE" != "null" ]]; then
  here="${CLAUDE_PROJECT_DIR:-}"
  if [[ -n "$here" && "$here" != "$STORED_WORKTREE" ]]; then
    exit 0
  fi
fi

# Bound by max_iterations AND the native consecutive Stop-hook continuation cap.
EFFECTIVE_MAX="$MAX_ITERATIONS"
if [[ "${CLAUDE_CODE_STOP_HOOK_BLOCK_CAP:-}" =~ ^[1-9][0-9]*$ ]]; then
  CAP=$((CLAUDE_CODE_STOP_HOOK_BLOCK_CAP - 1))
  [[ $CAP -lt 1 ]] && CAP=1
  if [[ $EFFECTIVE_MAX -eq 0 || $EFFECTIVE_MAX -gt $CAP ]]; then
    EFFECTIVE_MAX=$CAP
  fi
fi
if [[ $EFFECTIVE_MAX -gt 0 ]] && [[ $ITERATION -ge $EFFECTIVE_MAX ]]; then
  ralph_escalate "bound reached (iteration=$ITERATION max_iterations=$MAX_ITERATIONS stop_hook_cap=${CLAUDE_CODE_STOP_HOOK_BLOCK_CAP:-unset})"
  note "🛑 Ralph loop: ESCALATED at iteration $ITERATION (bound $EFFECTIVE_MAX). Stopping."
  if [[ -f "$RALPH_PROGRESS_FILE" ]]; then
    note "   Progress + escalated items: .claude/ralph-state.local.md"
  fi
  rm "$RALPH_STATE_FILE"
  exit 0
fi

# Get transcript path from hook input
TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || echo "")

if [[ -z "$TRANSCRIPT_PATH" ]] || [[ ! -f "$TRANSCRIPT_PATH" ]]; then
  ralph_escalate "transcript missing"
  note "⚠️  Ralph loop: Transcript not found — ESCALATED, stopping loop."
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
  ralph_escalate "no assistant output"
  note "⚠️  Ralph loop: No assistant output found — ESCALATED, stopping loop."
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
    NEED_VERIFY=0
    if [[ "$REQUIRE_VERIFY" == "true" || "$REQUIRE_VERIFY" == "yes" ]]; then
      NEED_VERIFY=1
    fi
    if [[ "$VERIFY_CMD" != "null" && -n "$VERIFY_CMD" ]]; then
      NEED_VERIFY=1
    fi
    if [[ $NEED_VERIFY -eq 1 ]]; then
      if verify_cmd_unusable "$VERIFY_CMD"; then
        record_verify_evidence "unusable" "$VERIFY_CMD"
        VERIFY_FEEDBACK="⛔ DETERMINISTIC VERIFIER FAILED. You emitted the completion promise, but \`$VERIFY_CMD\` is not a shell command this hook can run (slash commands like /verify are not executable; no-ops like true/: / echo / exit 0 are not gates; git commit/push/merge/reset and gh pr merge are forbidden). The promise is REJECTED. Set --verify-cmd to the same stack command you actually ran from verify.md (for example flutter test, npm exec --no -- ng test --watch=false, npx vitest run, uv run --no-sync pytest -q, ./mvnw test -q)."
      else
        VERIFY_LOG="${RALPH_STATE_FILE}.verify.$$"
        if run_verify_cmd "$VERIFY_CMD" "$VERIFY_LOG"; then
          VERIFY_RC=0
        else
          VERIFY_RC=$?
        fi
        record_verify_evidence "$VERIFY_RC" "$VERIFY_CMD"
        if [[ $VERIFY_RC -eq 0 ]]; then
          LIVE_CMD_SHA=$(sha256_text "$VERIFY_CMD")
          if [[ -n "$CMD_SHA" && "$CMD_SHA" != "null" && -n "$LIVE_CMD_SHA" && "$LIVE_CMD_SHA" != "$CMD_SHA" ]]; then
            VERIFY_FEEDBACK="⛔ CONTRACT WEAKENED. The live --verify-cmd hash does not match verify_cmd_sha256 captured at loop start. The promise is REJECTED. Restore the approved verifier; do not swap it to force a pass."
            ralph_escalate "verify_cmd hash mutated"
          elif ! check_contract_snapshot; then
            VERIFY_FEEDBACK="⛔ CONTRACT WEAKENED. Tests, acceptance criteria, coverage floor, or the verifier were altered relative to the approved snapshot. The promise is REJECTED. TDD-added assertions are allowed only after independent /review-code; skipped/deleted tests and dropped gates are ESCALATED."
            ralph_escalate "contract WEAKENED after verify exit 0"
          else
            note "✅ Ralph loop: Promise '$COMPLETION_PROMISE' + verifier ('$VERIFY_CMD') exit 0. Loop complete."
            if [[ -f "$RALPH_PROGRESS_FILE" ]]; then
              note "   Run summary + lessons: .claude/ralph-state.local.md"
            fi
            rm -f "$VERIFY_LOG"
            rm "$RALPH_STATE_FILE"
            exit 0
          fi
        fi
        if [[ $VERIFY_RC -ne 0 ]]; then
          VERIFY_TAIL=$(tail -n 25 "$VERIFY_LOG" 2>/dev/null || echo "")
          rm -f "$VERIFY_LOG"
          if [[ $VERIFY_RC -eq 124 ]]; then
            VERIFY_FEEDBACK="⛔ DETERMINISTIC VERIFIER FAILED. You emitted the completion promise, but \`$VERIFY_CMD\` timed out (exit 124), so the promise is REJECTED and the work is NOT done. Do NOT emit the promise again until \`$VERIFY_CMD\` exits 0 — and never weaken the verifier to force a pass. Last 25 lines of verifier output:
${VERIFY_TAIL}"
          else
            VERIFY_FEEDBACK="⛔ DETERMINISTIC VERIFIER FAILED. You emitted the completion promise, but \`$VERIFY_CMD\` exited ${VERIFY_RC} (non-zero), so the promise is REJECTED and the work is NOT done. Do NOT emit the promise again until \`$VERIFY_CMD\` exits 0 — and never weaken the verifier to force a pass. Last 25 lines of verifier output:
${VERIFY_TAIL}"
          fi
        else
          rm -f "$VERIFY_LOG"
        fi
      fi
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

# Disable the notes trap so continue-path JSON is a single object (note()+jq used to emit two).
trap - EXIT
jq -n \
  --arg prompt "$FEED_PROMPT" \
  --arg msg "$SYSTEM_MSG" \
  '{
    "decision": "block",
    "reason": $prompt,
    "systemMessage": $msg
  }'

exit 0
