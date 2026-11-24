#!/usr/bin/env bash
# git-hooks/pre-commit-evaluator.sh
# Claude (haiku) evaluates staged changes before commit is allowed.
#
# Opt-in:    export CLAUDE_PRECOMMIT_EVAL=1
# Threshold: export CLAUDE_PRECOMMIT_THRESHOLD=7  (default: 7, range: 1-10)
# Model:     export CLAUDE_PRECOMMIT_MODEL=haiku   (a CLI alias, so it follows the current Haiku model)
# Timeout:   export CLAUDE_PRECOMMIT_TIMEOUT=30    (seconds; portable, no GNU `timeout` needed)
# Bypass:    git commit --no-verify
#
# Install: this script is called from .git/hooks/pre-commit
#          See git-hooks/pre-commit-secrets.sh for the combined hook.
# Test:    bash git-hooks/pre-commit-evaluator.sh --selftest   (fake CLI; never calls a model)

set -uo pipefail

# run_with_timeout SECONDS CMD... -> CMD's output and exit code; 124 when it was killed.
# Bash 3.2 / BSD safe: GNU `timeout` is absent on macOS, where `timeout 30s claude` failed instantly and
# every commit was waved through as "evaluation timed out or failed".
run_with_timeout() {
  local secs="$1" pid watcher rc; shift
  "$@" & pid=$!
  # kill the children first: a surviving child keeps the $(...) pipe open and the caller keeps waiting
  ( sleep "$secs"; pkill -TERM -P "$pid" 2>/dev/null; kill "$pid" 2>/dev/null ) >/dev/null 2>&1 & watcher=$!
  wait "$pid"; rc=$?
  kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null
  [ "$rc" -eq 143 ] && rc=124
  return "$rc"
}

selftest() {
  local self tmp fail=0 out rc
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  bash -n "$self" || { echo "FAIL control 0: bash -n"; return 1; }
  tmp=$(mktemp -d) || return 1
  (cd "$tmp" && git init -q . && printf 'x = 1\n' > a.py && git add a.py)
  fake() { printf '#!/usr/bin/env bash\n%s\n' "$1" > "$tmp/claude"; chmod +x "$tmp/claude"; }
  case_() { # want-rc needle label
    if [ "$rc" -eq "$1" ] && printf '%s' "$out" | grep -qF "$2"; then echo "ok   $3"; else echo "FAIL $3 (rc=$rc: $(printf '%s' "$out" | tail -3))"; fail=1; fi
  }
  out=$(cd "$tmp" && env -u CLAUDE_PRECOMMIT_EVAL bash "$self" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then echo "ok   negative: not opted in -> silent exit 0"; else echo "FAIL opt-out (rc=$rc)"; fail=1; fi
  fake 'printf "CORRECTNESS: 9\nCOMPLETENESS: 9\nSAFETY: 9\nSCOPE: 9\nOVERALL: 9\nVERDICT: APPROVED\nISSUES: none\n"'
  out=$(cd "$tmp" && CLAUDE_PRECOMMIT_EVAL=1 CLAUDE_BIN="$tmp/claude" bash "$self" 2>&1); rc=$?; case_ 0 "APPROVED" "negative: an APPROVED verdict lets the commit through"
  fake 'printf "CORRECTNESS: 3\nCOMPLETENESS: 3\nSAFETY: 3\nSCOPE: 3\nOVERALL: 3\nVERDICT: BLOCKED\nISSUES:\n- no tests\n"'
  out=$(cd "$tmp" && CLAUDE_PRECOMMIT_EVAL=1 CLAUDE_BIN="$tmp/claude" bash "$self" 2>&1); rc=$?; case_ 1 "BLOCKED" "positive: a BLOCKED verdict rejects the commit"
  fake 'printf "%s\n" "$@" > "'"$tmp"'/args"; printf "VERDICT: APPROVED\nOVERALL: 9\n"'
  out=$(cd "$tmp" && CLAUDE_PRECOMMIT_EVAL=1 CLAUDE_BIN="$tmp/claude" bash "$self" 2>&1); rc=$?
  if grep -qx 'haiku' "$tmp/args"; then echo "ok   the model is the 'haiku' alias (no stale dated snapshot)"; else echo "FAIL model arg: $(tr '\n' ' ' < "$tmp/args")"; fail=1; fi
  fake 'sleep 20'
  local t0=$SECONDS
  out=$(cd "$tmp" && CLAUDE_PRECOMMIT_EVAL=1 CLAUDE_PRECOMMIT_TIMEOUT=1 CLAUDE_BIN="$tmp/claude" bash "$self" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && [ $((SECONDS - t0)) -lt 10 ] && printf '%s' "$out" | grep -qF "timed out"; then
    echo "ok   a hung CLI is cut off by the portable timeout (no GNU timeout needed)"; else echo "FAIL timeout (rc=$rc, $((SECONDS - t0))s)"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}
if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# Only run when opted in
[ "${CLAUDE_PRECOMMIT_EVAL:-0}" != "1" ] && exit 0

THRESHOLD="${CLAUDE_PRECOMMIT_THRESHOLD:-7}"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"

# Verify claude CLI is available
if ! command -v "$CLAUDE_BIN" &>/dev/null; then
  echo -e "${YELLOW}  pre-commit-eval: claude CLI not found — skipping evaluation${NC}"
  exit 0
fi

# Get staged diff
DIFF=$(git diff --cached --stat 2>/dev/null)
DIFF_FULL=$(git diff --cached 2>/dev/null)

[ -z "$DIFF_FULL" ] && exit 0

# Truncate very large diffs to avoid token limits (keep first 6000 chars)
if [ "${#DIFF_FULL}" -gt 6000 ]; then
  DIFF_FULL="${DIFF_FULL:0:6000}
... [diff truncated for evaluation]"
fi

FILE_COUNT=$(git diff --cached --name-only 2>/dev/null | wc -l | tr -d ' ')

echo -e "${CYAN}  pre-commit-eval: evaluating ${FILE_COUNT} file(s) with Claude haiku...${NC}"

# Build evaluation prompt
PROMPT="You are a strict code reviewer evaluating a git commit diff.

Score this diff from 1-10 across 4 dimensions, then give an overall score:
1. Correctness (1-10): Does the code look functionally correct? Any obvious bugs?
2. Completeness (1-10): Are tests included where needed? Is the change whole?
3. Safety (1-10): Any security issues, secret leaks, dangerous patterns?
4. Scope (1-10): Is the diff focused? Or does it mix unrelated changes?

DIFF STATS:
$DIFF

FULL DIFF:
$DIFF_FULL

Respond ONLY in this exact format (no other text):
CORRECTNESS: X
COMPLETENESS: X
SAFETY: X
SCOPE: X
OVERALL: X
VERDICT: APPROVED or BLOCKED
ISSUES:
- issue 1 (if any)
- issue 2 (if any)

Where OVERALL = average of all 4 scores rounded to 1 decimal.
VERDICT = APPROVED if OVERALL >= $THRESHOLD, else BLOCKED.
If no issues, write ISSUES: none"

# Run evaluation, bounded so a hung CLI never blocks the commit
EVALUATION=$(run_with_timeout "${CLAUDE_PRECOMMIT_TIMEOUT:-30}" "$CLAUDE_BIN" -p "$PROMPT" --model "${CLAUDE_PRECOMMIT_MODEL:-haiku}" 2>/dev/null)
eval_rc=$?
if [ "$eval_rc" -ne 0 ]; then
  [ "$eval_rc" -eq 124 ] && why="timed out after ${CLAUDE_PRECOMMIT_TIMEOUT:-30}s" || why="failed (exit $eval_rc)"
  echo -e "${YELLOW}  pre-commit-eval: evaluation ${why} — allowing commit (the evaluator is advisory)${NC}"
  exit 0
fi

[ -z "$EVALUATION" ] && { echo -e "${YELLOW}  pre-commit-eval: empty response — allowing commit${NC}"; exit 0; }

# Parse scores
CORRECTNESS=$(echo "$EVALUATION" | grep -i "^CORRECTNESS:" | grep -oE '[0-9]+(\.[0-9]+)?' | head -1) || CORRECTNESS="?"
COMPLETENESS=$(echo "$EVALUATION" | grep -i "^COMPLETENESS:" | grep -oE '[0-9]+(\.[0-9]+)?' | head -1) || COMPLETENESS="?"
SAFETY=$(echo "$EVALUATION" | grep -i "^SAFETY:" | grep -oE '[0-9]+(\.[0-9]+)?' | head -1) || SAFETY="?"
SCOPE=$(echo "$EVALUATION" | grep -i "^SCOPE:" | grep -oE '[0-9]+(\.[0-9]+)?' | head -1) || SCOPE="?"
OVERALL=$(echo "$EVALUATION" | grep -i "^OVERALL:" | grep -oE '[0-9]+(\.[0-9]+)?' | head -1) || OVERALL="0"
VERDICT=$(echo "$EVALUATION" | grep -i "^VERDICT:" | sed 's/VERDICT:[[:space:]]*//' | tr '[:lower:]' '[:upper:]' | tr -d '[:space:]') || VERDICT="UNKNOWN"
ISSUES=$(echo "$EVALUATION" | sed -n '/^ISSUES:/,$ p' | tail -n +2) || ISSUES="none"

# Display result
echo ""
echo -e "  ┌─────────────────────────────────────────┐"
echo -e "  │       Claude Pre-Commit Evaluation       │"
echo -e "  ├─────────────────────────────────────────┤"
printf  "  │  Correctness:   %-24s │\n" "${CORRECTNESS}/10"
printf  "  │  Completeness:  %-24s │\n" "${COMPLETENESS}/10"
printf  "  │  Safety:        %-24s │\n" "${SAFETY}/10"
printf  "  │  Scope:         %-24s │\n" "${SCOPE}/10"
echo -e "  ├─────────────────────────────────────────┤"
printf  "  │  Overall:       %-24s │\n" "${OVERALL}/10  (threshold: ${THRESHOLD}/10)"
echo -e "  └─────────────────────────────────────────┘"

if [ "$ISSUES" != "none" ] && [ -n "$ISSUES" ]; then
  echo ""
  echo -e "${YELLOW}  Issues found:${NC}"
  while IFS= read -r line; do
    [ -n "$line" ] && echo "    $line"
  done <<< "$ISSUES"
fi
echo ""

# Verdict
if [ "$VERDICT" = "APPROVED" ]; then
  echo -e "${GREEN}  ✅ APPROVED (${OVERALL}/10 ≥ ${THRESHOLD}/10) — commit proceeding${NC}"
  echo ""
  exit 0
else
  echo -e "${RED}  ❌ BLOCKED (${OVERALL}/10 < ${THRESHOLD}/10) — commit rejected${NC}"
  echo ""
  echo -e "${YELLOW}  Options:${NC}"
  echo "    1. Fix the issues listed above and re-stage"
  echo "    2. Lower threshold: CLAUDE_PRECOMMIT_THRESHOLD=5 git commit -m \"...\""
  echo "    3. Bypass (emergencies only): git commit --no-verify"
  echo ""
  exit 1
fi
