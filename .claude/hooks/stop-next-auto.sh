#!/bin/bash

# Outer `/next --auto` Stop hook.
# Continues the multi-story coordinator when auto state is running.
# Exits 0 immediately if auto is inactive, a foreign session owns it, or
# the inner Ralph loop is active — zero interference with HITL `/next`.
# Test: bash .claude/hooks/stop-next-auto.sh --selftest

set -euo pipefail

COORDINATOR=""
find_coordinator() {
  local c="$CLAUDE_PROJECT_DIR/.claude/skills/next-issue/scripts/check-next-auto.py"
  if [[ -f "$c" ]]; then
    printf '%s' "$c"
    return 0
  fi
  c="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../skills/next-issue/scripts/check-next-auto.py"
  if [[ -f "$c" ]]; then
    printf '%s' "$c"
    return 0
  fi
  return 1
}

if [[ "${1:-}" == "--selftest" ]]; then
  SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  FAIL=0
  if bash -n "$SELF" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; exit 1; fi
  command -v python3 >/dev/null 2>&1 || { echo "  FAIL python3 required"; exit 1; }
  COORDINATOR=$(CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}" find_coordinator) || true
  if [[ -n "$COORDINATOR" ]]; then echo "  ok   coordinator present"; else echo "  FAIL coordinator missing"; exit 1; fi

  SETTINGS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../settings.json"
  if command -v jq >/dev/null 2>&1 && jq -e '.hooks.Stop[] | .hooks[] | select(.command | contains("stop-next-auto.sh"))' "$SETTINGS" >/dev/null 2>&1; then
    echo "  ok   registered: settings.json Stop -> stop-next-auto.sh"
  else
    echo "  FAIL settings.json does not register Stop -> stop-next-auto.sh"; FAIL=1
  fi
  if command -v jq >/dev/null 2>&1 && jq -e '.permissions.defaultMode == "auto" and ((.permissions | keys) == ["defaultMode"])' "$SETTINGS" >/dev/null 2>&1; then
    echo "  ok   regression: settings.json permissions unchanged"
  else
    echo "  FAIL permissions drifted"; FAIL=1
  fi
  if command -v jq >/dev/null 2>&1 && jq -e '.model == "sonnet"' "$SETTINGS" >/dev/null 2>&1; then
    echo "  ok   regression: settings.json model remains sonnet"
  else
    echo "  FAIL model drifted"; FAIL=1
  fi

  T=$(mktemp -d)
  mkdir -p "$T/.claude"
  # Negative: no auto state, no decision.
  OUT=$(printf '{"session_id":"s1","transcript_path":"%s"}' "$T/t.jsonl" | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if [[ -z "$OUT" ]] || ! printf '%s' "$OUT" | grep -q '"decision"'; then echo "  ok   negative: no auto state -> silent exit"; else echo "  FAIL interfered without auto state (out: $OUT)"; FAIL=1; fi

  # Negative: subagent payload ignored.
  OUT=$(printf '{"agent_id":"sub-1","session_id":"s1"}' | CLAUDE_PROJECT_DIR="$T" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"'; then echo "  ok   negative: subagent payload ignored"; else echo "  FAIL subagent drove auto loop"; FAIL=1; fi

  # Negative: inner Ralph owns Stop.
  printf 'active\n' > "$T/.claude/ralph-loop.local.md"
  python3 - "$T" <<'PY'
import json, sys, time
from pathlib import Path
root = Path(sys.argv[1])
d = root / "next-auto"
d.mkdir()
(d / "state.json").write_text(json.dumps({
    "version": 1, "mode": "auto", "status": "running", "session_id": "s1",
    "scope": {"kind": "issues", "selector": [1], "issue_numbers": [1], "fingerprint": "x"},
    "current": {"issue": 1, "phase": "implement", "attempts": 0, "review_rounds": 0},
    "completed": [], "blocked": [], "hook_iteration": 0,
    "started_at": time.time(), "updated_at": time.time(),
    "budget": {"max_stories": 5, "max_story_attempts": 3, "max_duration_seconds": 3600,
               "max_review_rounds": 3, "max_hook_iterations": 50, "cost_metered": False},
}), encoding="utf-8")
PY
  OUT=$(printf '{"session_id":"s1"}' | CLAUDE_PROJECT_DIR="$T" NEXT_AUTO_STATE_DIR="$T/next-auto" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"'; then echo "  ok   negative: Ralph active -> auto hook silent"; else echo "  FAIL auto hook ran during Ralph (out: $OUT)"; FAIL=1; fi
  rm -f "$T/.claude/ralph-loop.local.md"

  # Positive: owning session continues.
  OUT=$(printf '{"session_id":"s1"}' | CLAUDE_PROJECT_DIR="$T" NEXT_AUTO_STATE_DIR="$T/next-auto" bash "$SELF" 2>/dev/null) || true
  if printf '%s' "$OUT" | grep -q '"decision": *"block"'; then echo "  ok   positive: owning session continues auto loop"; else echo "  FAIL owning session did not continue (out: $OUT)"; FAIL=1; fi

  # Negative: foreign session ignored.
  OUT=$(printf '{"session_id":"other"}' | CLAUDE_PROJECT_DIR="$T" NEXT_AUTO_STATE_DIR="$T/next-auto" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"'; then echo "  ok   concurrent: foreign session ignored"; else echo "  FAIL foreign session drove auto loop"; FAIL=1; fi

  # Cap: never emit decision:block at the platform bound.
  python3 - "$T" <<'PY'
import json, sys, time
from pathlib import Path
p = Path(sys.argv[1]) / "next-auto" / "state.json"
st = json.loads(p.read_text())
st["hook_iteration"] = 5
p.write_text(json.dumps(st))
PY
  OUT=$(printf '{"session_id":"s1"}' | CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=3 CLAUDE_PROJECT_DIR="$T" NEXT_AUTO_STATE_DIR="$T/next-auto" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision": *"block"'; then echo "  ok   cap: Stop-hook bound does not emit block"; else echo "  FAIL cap still blocked (out: $OUT)"; FAIL=1; fi

  # Missing python: fail-closed (do not drive).
  OUT=$(printf '{"session_id":"s1"}' | PATH="/usr/bin:/bin" NEXT_AUTO_FORCE_NO_PYTHON=1 CLAUDE_PROJECT_DIR="$T" NEXT_AUTO_STATE_DIR="$T/next-auto" bash "$SELF" 2>/dev/null) || true
  if ! printf '%s' "$OUT" | grep -q '"decision"'; then echo "  ok   robustness: missing python does not drive"; else echo "  FAIL missing python drove the loop"; FAIL=1; fi

  rm -rf "$T"
  if [[ "$FAIL" -eq 0 ]]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  exit "$FAIL"
fi

HOOK_INPUT=$(cat)

# Fail-closed: do not drive a loop if python is missing.
if [[ "${NEXT_AUTO_FORCE_NO_PYTHON:-}" == "1" ]] || ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

COORDINATOR=$(find_coordinator) || exit 0

STATE_ARGS=()
if [[ -n "${NEXT_AUTO_STATE_DIR:-}" ]]; then
  STATE_ARGS=(--state-dir "$NEXT_AUTO_STATE_DIR")
fi

# Coordinator prints JSON or nothing. Empty = noop.
OUT=$(printf '%s' "$HOOK_INPUT" | python3 "$COORDINATOR" --hook-stop "${STATE_ARGS[@]}" 2>/dev/null) || true
if [[ -z "$OUT" ]]; then
  exit 0
fi
printf '%s' "$OUT"
exit 0
