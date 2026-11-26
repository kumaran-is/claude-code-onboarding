#!/usr/bin/env bash
# PreCompact: persist a concise, secret-free snapshot so compaction can be resumed.
# Reuses /checkpoint log format and the existing SDD ledger --status. Not a second
# memory system. Not a lessons classifier.
#
# Contract (Claude Code hooks reference, PreCompact):
#   - stdin JSON: hook_event_name, trigger (manual|auto), custom_instructions
#   - exit 2 blocks compaction (we never do that — fail-open, always exit 0)
#   - hookSpecificOutput is invalid for this event (schema reject)
#   - systemMessage / continue are discarded
#   - exit-0 stdout becomes compaction-summary instructions (cap 10_000 chars)
# Matcher: none (manual and auto). Fast, bounded, noninteractive.
# Test: bash .claude/hooks/pre-compact-checkpoint.sh --selftest
set -uo pipefail

MAX_STDOUT=4000
MAX_NAMES=40
MAX_STAT=30
MAX_SDD=40

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
kit_root="$(cd "$here/../.." && pwd)"

cap_chars() { # stdin -> first MAX_STDOUT chars, marker if truncated
  python3 -c "
import sys
t = sys.stdin.read()
cap = $MAX_STDOUT
if len(t) > cap:
    sys.stdout.write(t[:cap] + '\n[truncated]\n')
else:
    sys.stdout.write(t)
" 2>/dev/null || { head -c "$MAX_STDOUT"; echo; }
}

redact_secrets() {
  # Names-only snapshot; still strip token-shaped values if a command leaks one.
  python3 -c "
import re, sys
t = sys.stdin.read()
t = re.sub(r'(?i)(api[_-]?key|token|secret|password|passwd|authorization)\s*[:=]\s*\S+', r'\1: [redacted]', t)
t = re.sub(r'AKIA[0-9A-Z]{16}', '[redacted]', t)
t = re.sub(r'sk-ant-[A-Za-z0-9_-]{20,}', '[redacted]', t)
t = re.sub(r'ghp_[A-Za-z0-9]{20,}', '[redacted]', t)
sys.stdout.write(t)
" 2>/dev/null || cat
}

snapshot() {
  local root trigger ts name sha branch dirty_n porcelain stat_out sdd_out ledger_py log dest line
  root="${CLAUDE_PROJECT_DIR:-$PWD}"
  trigger="unknown"
  if command -v jq >/dev/null 2>&1 && [ -n "${PRECOMPACT_INPUT:-}" ]; then
    trigger=$(printf '%s' "$PRECOMPACT_INPUT" | jq -r '.trigger // "unknown"' 2>/dev/null) || trigger="unknown"
  fi
  case "$trigger" in auto|manual) ;; *) trigger="unknown" ;; esac

  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "unknown-time")
  name="precompact-${trigger}-$(date -u +"%H%M%S" 2>/dev/null || echo x)"

  sha="unknown"
  branch="unknown"
  dirty_n=0
  porcelain=""
  stat_out=""
  if git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    sha=$(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo unknown)
    branch=$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
    porcelain=$(git -C "$root" status --porcelain -uall 2>/dev/null | head -n "$MAX_NAMES" || true)
    dirty_n=$(printf '%s\n' "$porcelain" | grep -c . || true)
    stat_out=$(git -C "$root" diff --stat HEAD 2>/dev/null | head -n "$MAX_STAT" || true)
  fi

  mkdir -p "$root/.claude/temp/precompact" 2>/dev/null || true
  log="$root/.claude/checkpoints.log"
  line="${ts}|${name}|${sha}|${dirty_n} files changed"
  if [ -d "$root/.claude" ] || mkdir -p "$root/.claude" 2>/dev/null; then
    printf '%s\n' "$line" >> "$log" 2>/dev/null || true
  fi

  sdd_out="SDD ledger: none"
  ledger_py="$root/.claude/skills/subagent-driven-development/scripts/check-sdd-ledger.py"
  if [ ! -f "$ledger_py" ]; then
    ledger_py="$kit_root/.claude/skills/subagent-driven-development/scripts/check-sdd-ledger.py"
  fi
  if [ -f "$ledger_py" ] && [ -d "$root/.claude/temp/sdd" ]; then
    sdd_out=$(python3 "$ledger_py" --status --root "$root" 2>/dev/null | head -n "$MAX_SDD" || true)
    [ -n "$sdd_out" ] || sdd_out="SDD ledger: none"
  fi

  loop_file="$root/.claude/ralph-loop.local.md"
  state_file="$root/.claude/ralph-state.local.md"
  ralph_fm=""
  contract_block=""
  if [ -f "$loop_file" ]; then
    ralph_fm=$(sed -n '/^---$/,/^---$/{ /^---$/d; p; }' "$loop_file" 2>/dev/null | grep -E '^(ac_sha256|verify_cmd|verify_cmd_sha256|session_id|require_verify|worktree|completion_promise|max_iterations|iteration):' || true)
  fi
  if [ -f "$state_file" ]; then
    contract_block=$(awk '
      /^## Contract snapshot/ {p=1}
      /^## / && p && !/^## Contract snapshot/ {exit}
      p {print}
    ' "$state_file" 2>/dev/null || true)
  fi

  auto_line="(no /next --auto state)"
  auto_json=""
  if git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    common=$(git -C "$root" rev-parse --git-common-dir 2>/dev/null || true)
    if [ -n "$common" ]; then
      case "$common" in
        /*) ;;
        *) common="$root/$common" ;;
      esac
      auto_json="$common/claude-state/next-auto/state.json"
    fi
  fi
  if [ -n "$auto_json" ] && [ -f "$auto_json" ]; then
    auto_line=$(python3 -c '
import json,sys
p=sys.argv[1]
try:
    st=json.load(open(p))
except Exception:
    print("/next --auto state: unreadable")
    raise SystemExit
cur=st.get("current") or {}
print("/next --auto status=%s issue=%s phase=%s" % (
    st.get("status") or "unknown",
    cur.get("issue") if cur else "-",
    cur.get("phase") if cur else "-",
))
' "$auto_json" 2>/dev/null || echo "/next --auto state: present")
  fi

  dest=""
  if [ -d "$root/.claude/temp/precompact" ]; then
    dest="$root/.claude/temp/precompact/latest.md"
    {
      printf '%s\n' "# PreCompact snapshot"
      printf '%s\n' "trigger: $trigger"
      printf '%s\n' "written: $ts"
      printf '%s\n' "branch: $branch"
      printf '%s\n' "sha: $sha"
      printf '%s\n' "dirty: $dirty_n"
      printf '%s\n' "checkpoint: $line"
      printf '%s\n' ""
      printf '%s\n' "## Git (names only)"
      if [ -n "$porcelain" ]; then printf '%s\n' "$porcelain"; else printf '%s\n' "(clean)"; fi
      printf '%s\n' ""
      printf '%s\n' "## Diff stat"
      if [ -n "$stat_out" ]; then printf '%s\n' "$stat_out"; else printf '%s\n' "(no unstaged/uncommitted diff vs HEAD)"; fi
      printf '%s\n' ""
      printf '%s\n' "## SDD ledger"
      printf '%s\n' "$sdd_out"
      printf '%s\n' ""
      printf '%s\n' "## Ralph loop contract (restore unchanged)"
      if [ -n "$ralph_fm" ]; then printf '%s\n' "$ralph_fm"; else printf '%s\n' "(no active ralph-loop.local.md)"; fi
      if [ -n "$contract_block" ]; then printf '%s\n' "$contract_block"; fi
      printf '%s\n' ""
      printf '%s\n' "## Next --auto coordinator"
      printf '%s\n' "$auto_line"
      printf '%s\n' ""
      printf '%s\n' "## Resume"
      printf '%s\n' "This file is the secret-free PreCompact snapshot. The matching /checkpoint log line is in .claude/checkpoints.log."
      printf '%s\n' "A ledger row is never verification proof. Do not redispatch a complete SDD task whose verify exit is 0."
      printf '%s\n' "If ralph-loop.local.md still exists after compact, copy ac_sha256, verify_cmd, and verify_cmd_sha256 from this snapshot back into its frontmatter if they differ — approved acceptance criteria and the exact verifier must survive PreCompact, resume, and context reset unchanged."
      printf '%s\n' "If /next --auto status is running, after compact run python3 .claude/skills/next-issue/scripts/check-next-auto.py --resume and continue that phase; do not freeze a new scope."
    } > "$dest" 2>/dev/null || dest=""
  fi

  printf '%s\n' "A PreCompact snapshot is at .claude/temp/precompact/latest.md (secret-free names and SDD status only)."
  printf '%s\n' "Checkpoint: $name @ $sha ($dirty_n files). Branch: $branch."
  if printf '%s' "$sdd_out" | grep -q '^plan:'; then
    printf '%s\n' "SDD ledger was current at compact time; after compaction run TaskList then check-sdd-ledger.py --status."
  else
    printf '%s\n' "SDD ledger: none."
  fi
  printf '%s\n' "The snapshot is not verification evidence."
}

run_hook() {
  PRECOMPACT_INPUT=$(cat || true)
  snapshot | redact_secrets | cap_chars
  return 0
}

selftest() {
  local self fail=0 tmp out rc settings payload secret dest log
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }

  settings="$kit_root/.claude/settings.json"
  if jq -e '.hooks.PreCompact[] | .hooks[] | select(.command | contains("pre-compact-checkpoint.sh"))' "$settings" >/dev/null 2>&1; then
    echo "  ok   registered: settings.json PreCompact -> pre-compact-checkpoint.sh"
  else
    echo "  FAIL settings.json does not register PreCompact -> pre-compact-checkpoint.sh"; fail=1
  fi
  if jq -e '.permissions.defaultMode == "auto" and ((.permissions | keys) == ["defaultMode"])' "$settings" >/dev/null 2>&1; then
    echo "  ok   regression: settings.json permissions unchanged (defaultMode auto only)"
  else
    echo "  FAIL permissions drifted: $(jq -c '.permissions' "$settings")"; fail=1
  fi
  if jq -e '.hooks.PreCompact[] | .hooks[] | select((.command | contains("pre-compact-checkpoint.sh")) and (.timeout <= 10))' "$settings" >/dev/null 2>&1; then
    echo "  ok   timeout is bounded (<=10s)"
  else
    echo "  FAIL PreCompact timeout missing or >10s"; fail=1
  fi

  tmp=$(mktemp -d) || return 1
  git -C "$tmp" init -q
  git -C "$tmp" -c user.email=t@t -c user.name=t commit --allow-empty -q -m init
  mkdir -p "$tmp/.claude/temp/sdd/demo" "$tmp/docs/plans"
  printf '# Plan: Demo\n' > "$tmp/docs/plans/demo.md"
  printf '%s\n' '{"plan_path":"docs/plans/demo.md","updated_at":"2026-01-01T00:00:00+00:00","tasks":[{"id":"1","title":"Add foo","status":"complete","verify":{"exit_code":0,"claimed_pass":true},"stale":false,"inconsistent":false},{"id":"2","title":"Add bar","status":"in_progress","verify":{"exit_code":null},"stale":false,"inconsistent":false}]}' > "$tmp/.claude/temp/sdd/demo/ledger.json"
  secret='SK-LIVE-NOT-A-REAL-SECRET-VALUE-XYZ'
  printf '%s\n' "$secret" > "$tmp/.env"
  printf 'notes\n' > "$tmp/notes.txt"
  git -C "$tmp" add notes.txt
  git -C "$tmp" -c user.email=t@t -c user.name=t commit -q -m notes
  printf 'dirty notes\n' >> "$tmp/notes.txt"

  payload=$(jq -n '{hook_event_name:"PreCompact",trigger:"auto",custom_instructions:null,transcript_path:"/tmp/transcript.jsonl"}')
  out=$(printf '%s' "$payload" | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self"); rc=$?
  dest="$tmp/.claude/temp/precompact/latest.md"
  log="$tmp/.claude/checkpoints.log"
  if [ "$rc" -eq 0 ]; then echo "  ok   positive: exit 0 (fail-open / does not block compaction)"
  else echo "  FAIL exit $rc (must be 0)"; fail=1; fi
  if printf '%s' "$out" | grep -q 'hookSpecificOutput'; then
    echo "  FAIL stdout must not be hookSpecificOutput JSON: $out"; fail=1
  else echo "  ok   stdout is not hookSpecificOutput (PreCompact schema)"; fi
  if printf '%s' "$out" | grep -q '^A PreCompact snapshot is at'; then
    echo "  ok   positive: compaction-summary instructions on stdout"
  else echo "  FAIL stdout missing snapshot pointer: $out"; fail=1; fi
  if [ -f "$dest" ] && grep -q 'precompact-auto-' "$log" 2>/dev/null; then
    echo "  ok   positive: wrote snapshot and /checkpoint log line"
  else echo "  FAIL missing snapshot or checkpoints.log"; fail=1; fi
  if grep -q 'task 2' "$dest" && grep -q 'in_progress' "$dest"; then
    echo "  ok   positive: SDD ledger status in snapshot"
  else echo "  FAIL SDD status missing from snapshot"; fail=1; fi
  if grep -q 'notes.txt' "$dest" && ! grep -q 'dirty notes' "$dest"; then
    echo "  ok   positive: git names only (no file contents)"
  else echo "  FAIL snapshot leaked file contents or missed names"; fail=1; fi
  if grep -q "$secret" "$dest" "$log" 2>/dev/null || printf '%s' "$out" | grep -q "$secret"; then
    echo "  FAIL secret from .env leaked into snapshot/stdout"; fail=1
  else echo "  ok   negative: .env contents are not in the snapshot"; fi
  if grep -q 'transcript.jsonl' "$dest" 2>/dev/null; then
    echo "  FAIL transcript_path persisted"; fail=1
  else echo "  ok   negative: transcript path is not persisted"; fi

  # Compaction recovery: approved AC hash + exact verifier survive in the snapshot.
  mkdir -p "$tmp/.claude"
  printf '%s\n' '---' 'iteration: 2' 'max_iterations: 5' 'verify_cmd: "flutter test"' 'ac_sha256: "abc123ac"' 'verify_cmd_sha256: "def456cmd"' 'session_id: "sess-precompact"' 'require_verify: true' '---' 'keep going' > "$tmp/.claude/ralph-loop.local.md"
  printf '%s\n' '# Ralph loop state' '' '## Contract snapshot' '```json' '{"ac_sha256":"abc123ac","verify_cmd":"flutter test"}' '```' > "$tmp/.claude/ralph-state.local.md"
  out=$(printf '%s' "$payload" | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self"); rc=$?
  dest="$tmp/.claude/temp/precompact/latest.md"
  if [ "$rc" -eq 0 ] && grep -q 'ac_sha256: "abc123ac"' "$dest" && grep -q 'verify_cmd: "flutter test"' "$dest" && grep -q 'verify_cmd_sha256: "def456cmd"' "$dest" && grep -q 'survive PreCompact' "$dest"; then
    echo "  ok   positive: AC hash and exact verifier persist across PreCompact"
  else echo "  FAIL PreCompact dropped AC/verifier hashes"; fail=1; fi
  if grep -q 'session_id: "sess-precompact"' "$dest" && grep -q 'require_verify: true' "$dest"; then
    echo "  ok   positive: session bind and require_verify persist"
  else echo "  FAIL session/require_verify missing from snapshot"; fail=1; fi
  # Resume must not rewrite hashes: snapshot is the source of truth, live loop file still has them.
  if grep -q 'ac_sha256: "abc123ac"' "$tmp/.claude/ralph-loop.local.md" && grep -q 'verify_cmd: "flutter test"' "$tmp/.claude/ralph-loop.local.md"; then
    echo "  ok   regression: PreCompact does not mutate live loop frontmatter"
  else echo "  FAIL PreCompact mutated ralph-loop.local.md"; fail=1; fi

  common=$(git -C "$tmp" rev-parse --git-common-dir)
  case "$common" in /*) ;; *) common="$tmp/$common" ;; esac
  mkdir -p "$common/claude-state/next-auto"
  printf '%s\n' '{"status":"running","current":{"issue":42,"phase":"verify"},"session_id":"s-precompact"}' > "$common/claude-state/next-auto/state.json"
  out=$(printf '%s' "$payload" | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self"); rc=$?
  dest="$tmp/.claude/temp/precompact/latest.md"
  if [ "$rc" -eq 0 ] && grep -q 'status=running' "$dest" && grep -q 'issue=42' "$dest" && grep -q 'phase=verify' "$dest"; then
    echo "  ok   positive: /next --auto coordinator status survives PreCompact"
  else echo "  FAIL PreCompact dropped next-auto status"; fail=1; fi

  # fail-open: broken git / missing jq still exit 0
  out=$(printf '%s' "$payload" | CLAUDE_PROJECT_DIR="/no/such/precompact-root-$$" "$BASH" "$self"); rc=$?
  if [ "$rc" -eq 0 ]; then echo "  ok   negative: missing project dir still exit 0"
  else echo "  FAIL missing dir blocked compaction (exit $rc)"; fail=1; fi

  # empty stdin (toolkit-lint runs --selftest with /dev/null; this is the live path)
  out=$(printf '' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self"); rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q 'PreCompact snapshot'; then
    echo "  ok   negative: empty stdin still snapshots and exits 0"
  else echo "  FAIL empty stdin: rc=$rc $out"; fail=1; fi

  # bounded stdout
  if [ "${#out}" -le 5000 ]; then echo "  ok   stdout bounded (${#out} chars)"
  else echo "  FAIL stdout too large: ${#out}"; fail=1; fi

  # mutation: checkpoint append is required — a snapshot without the log line is a failed control
  if grep -q '|precompact-' "$log"; then echo "  ok   regression: checkpoint log uses existing pipe format"
  else echo "  FAIL log format drifted"; fail=1; fi

  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
# Fail-open: an unbound variable or git failure must not block compaction (exit 2 would).
trap 'exit 0' EXIT
run_hook || printf '%s\n' "A PreCompact snapshot could not be written; compaction continues. Run TaskList after compact."
exit 0
