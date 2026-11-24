#!/usr/bin/env bash
# check-context-budget.sh — Measure the ALWAYS-LOADED context cost of this repo's instruction
# files and lint the rules corpus for structural drift.
#
# WHY: CLAUDE.md + every .claude/rules/**/*.md WITHOUT `paths:` frontmatter is loaded at launch into
# EVERY session (and every subagent that reads CLAUDE.md). Rules WITH `paths:` load only when Claude
# reads or edits a matching file, so they are listed separately and NOT counted in the total.
# Rules are discovered recursively (subdirectories of .claude/rules/ load too).
# It makes the always-loaded cost visible and holds it under a total budget:
#   TOTAL_GOAL     warns (report and --strict)        — time to move procedure into a skill
#   TOTAL_CEILING  fails under --strict               — lower it after a trim, never raise it to fit
# Canaries (.claude/context-canaries.tsv): fixed-string anchors of critical rules that must stay in an
# always-loaded file. A missing anchor fails --strict, so trimming cannot silently drop a STOP rule.
#
# Usage:
#   bash .claude/scripts/check-context-budget.sh             # report (always exits 0)
#   bash .claude/scripts/check-context-budget.sh --strict     # exit 1 if a hard cap is breached
#   bash .claude/scripts/check-context-budget.sh --baseline   # write current total as the baseline
#   bash .claude/scripts/check-context-budget.sh --selftest   # controls for the always-loaded classifier
#
# Token estimate is ~chars/4 (approximate — varies by content).
set -uo pipefail

# 0 = the rule has a `paths:` key in its leading YAML frontmatter (path-scoped), 1 = always loaded.
is_path_scoped() {
  awk 'NR == 1 { if ($0 != "---") exit 1; next }
       $0 == "---" { exit found ? 0 : 1 }
       /^paths:/ { found = 1 }
       END { if (NR <= 1) exit 1 }' "$1"
}

selftest() {
  local tmp fail=0 f out rc
  if bash -n "${BASH_SOURCE[0]}" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  tmp=$(mktemp -d) || return 1
  mkdir -p "$tmp/.claude/rules/web"
  printf '# Root\n' > "$tmp/CLAUDE.md"
  printf -- '---\npaths:\n  - "**/*.py"\n---\n\n# Scoped\n%s\n' "$(printf '%01000d' 0)" > "$tmp/.claude/rules/scoped.md"
  printf -- '---\npaths: "**/*.ts, **/*.tsx"\n---\n# Scoped inline\n' > "$tmp/.claude/rules/web/nested-scoped.md"
  printf '# Always\nNo frontmatter.\n' > "$tmp/.claude/rules/always.md"
  printf -- '---\ndescription: x\n---\n# Always with other frontmatter\n' > "$tmp/.claude/rules/web/nested-always.md"
  printf '# Body mentions\npaths: not frontmatter\n' > "$tmp/.claude/rules/body-paths.md"
  printf 'base pin\tNo frontmatter.\n' > "$tmp/.claude/context-canaries.tsv"   # a valid canary for the base fixture
  out=$(CLAUDE_PROJECT_DIR="$tmp" bash "${BASH_SOURCE[0]}" 2>&1)
  for f in .claude/rules/always.md .claude/rules/web/nested-always.md .claude/rules/body-paths.md CLAUDE.md; do
    if printf '%s\n' "$out" | sed -n '/ALWAYS-LOADED/,/Always-loaded total/p' | grep -qF "$f"; then echo "  ok   always-loaded: $f"
    else echo "  FAIL $f missing from the always-loaded list"; fail=1; fi
  done
  for f in .claude/rules/scoped.md .claude/rules/web/nested-scoped.md; do
    if printf '%s\n' "$out" | sed -n '/PATH-SCOPED/,$p' | grep -qF "$f" &&
       ! printf '%s\n' "$out" | sed -n '/ALWAYS-LOADED/,/Always-loaded total/p' | grep -qF "$f"; then echo "  ok   path-scoped, excluded from total: $f"
    else echo "  FAIL $f counted as always-loaded"; fail=1; fi
  done
  want=$(cat "$tmp/CLAUDE.md" "$tmp/.claude/rules/always.md" "$tmp/.claude/rules/web/nested-always.md" "$tmp/.claude/rules/body-paths.md" | wc -c | tr -d ' ')
  if printf '%s' "$out" | grep -qF "Always-loaded total: ${want} bytes"; then echo "  ok   total = ${want} bytes (scoped rules excluded)"
  else echo "  FAIL total is not ${want} bytes: $(printf '%s' "$out" | grep 'Always-loaded total')"; fail=1; fi
  out=$(CLAUDE_PROJECT_DIR="$tmp" bash "${BASH_SOURCE[0]}" --strict 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qF "Status: PASS (--strict)"; then echo "  ok   negative: --strict under the ceiling exits 0 and says PASS"
  else echo "  FAIL --strict under the ceiling: rc=$rc $(printf '%s' "$out" | tail -1)"; fail=1; fi
  awk 'BEGIN { print "# Big"; for (i = 0; i < 1600; i++) printf "%0100d\n", 0 }' > "$tmp/.claude/rules/big.md"
  out=$(CLAUDE_PROJECT_DIR="$tmp" bash "${BASH_SOURCE[0]}" --strict 2>&1); rc=$?
  if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qF "exceeds the 150k-char ceiling"; then echo "  ok   positive: --strict fails on a 160k-char rule file"
  else echo "  FAIL --strict did not fail on a 160k-char rule file: rc=$rc"; fail=1; fi
  out=$(CLAUDE_PROJECT_DIR="$tmp" bash "${BASH_SOURCE[0]}" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qF "report-only"; then echo "  ok   negative: report mode stays exit 0 on the same breach"
  else echo "  FAIL report mode: rc=$rc"; fail=1; fi
  rm -f "$tmp/.claude/rules/big.md"
  # total ceiling: positive (over) and negative (under), via the selftest-only overrides
  out=$(CLAUDE_PROJECT_DIR="$tmp" CONTEXT_TOTAL_GOAL=10 CONTEXT_TOTAL_CEILING=20 bash "${BASH_SOURCE[0]}" --strict 2>&1); rc=$?
  if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qF "> ceiling 20"; then echo "  ok   positive: --strict fails when the always-loaded total exceeds TOTAL_CEILING"
  else echo "  FAIL total ceiling not enforced: rc=$rc"; fail=1; fi
  out=$(CLAUDE_PROJECT_DIR="$tmp" CONTEXT_TOTAL_GOAL=10 CONTEXT_TOTAL_CEILING=99999 bash "${BASH_SOURCE[0]}" --strict 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qF "over the GOAL 10"; then echo "  ok   negative: over the GOAL only warns (exit 0)"
  else echo "  FAIL goal breach should warn, not fail: rc=$rc"; fail=1; fi
  # canaries: anchor in an always-loaded file = green; in a path-scoped file only = red; neighbour deleted = green
  printf '# Always\nNo frontmatter.\n- Pinned STOP rule alpha.\n- Neighbour rule beta.\n' > "$tmp/.claude/rules/always.md"
  printf -- '---\npaths:\n  - "**/*.py"\n---\n- Scoped-only rule gamma.\n' > "$tmp/.claude/rules/scoped.md"
  printf '# canaries\nalpha pin\tPinned STOP rule alpha.\n' > "$tmp/canaries.tsv"
  out=$(CLAUDE_PROJECT_DIR="$tmp" CONTEXT_CANARY_FILE="$tmp/canaries.tsv" CONTEXT_TOTAL_CEILING=99999 bash "${BASH_SOURCE[0]}" --strict 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qF "ok   alpha pin"; then echo "  ok   negative: pinned anchor present in an always-loaded file passes"
  else echo "  FAIL present canary: rc=$rc"; fail=1; fi
  printf '# Always\nNo frontmatter.\n- Pinned STOP rule alpha.\n' > "$tmp/.claude/rules/always.md"
  out=$(CLAUDE_PROJECT_DIR="$tmp" CONTEXT_CANARY_FILE="$tmp/canaries.tsv" CONTEXT_TOTAL_CEILING=99999 bash "${BASH_SOURCE[0]}" --strict 2>&1); rc=$?
  if [ "$rc" -eq 0 ]; then echo "  ok   negative: deleting a NEIGHBOUR of the pinned rule stays green"
  else echo "  FAIL neighbour deletion turned red: rc=$rc"; fail=1; fi
  printf '# Always\nNo frontmatter.\n- Neighbour rule beta.\n' > "$tmp/.claude/rules/always.md"
  out=$(CLAUDE_PROJECT_DIR="$tmp" CONTEXT_CANARY_FILE="$tmp/canaries.tsv" CONTEXT_TOTAL_CEILING=99999 bash "${BASH_SOURCE[0]}" --strict 2>&1); rc=$?
  if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qF "MISSING alpha pin"; then echo "  ok   positive: deleting the pinned rule fails --strict and names it"
  else echo "  FAIL deleted canary not caught: rc=$rc"; fail=1; fi
  printf 'gamma pin\tScoped-only rule gamma.\n' > "$tmp/canaries.tsv"
  out=$(CLAUDE_PROJECT_DIR="$tmp" CONTEXT_CANARY_FILE="$tmp/canaries.tsv" CONTEXT_TOTAL_CEILING=99999 bash "${BASH_SOURCE[0]}" --strict 2>&1); rc=$?
  if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qF "MISSING gamma pin"; then echo "  ok   positive: an anchor only in a PATH-SCOPED rule counts as missing"
  else echo "  FAIL path-scoped anchor counted as always-loaded: rc=$rc"; fail=1; fi
  printf '# only comments\n' > "$tmp/canaries.tsv"
  out=$(CLAUDE_PROJECT_DIR="$tmp" CONTEXT_CANARY_FILE="$tmp/canaries.tsv" CONTEXT_TOTAL_CEILING=99999 bash "${BASH_SOURCE[0]}" --strict 2>&1); rc=$?
  if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qF "has no entries"; then echo "  ok   positive: an empty canary file fails (a gate that checks nothing)"
  else echo "  FAIL empty canary file passed: rc=$rc"; fail=1; fi
  out=$(CLAUDE_PROJECT_DIR="$tmp" CONTEXT_CANARY_FILE="$tmp/absent.tsv" CONTEXT_TOTAL_CEILING=99999 bash "${BASH_SOURCE[0]}" --strict 2>&1); rc=$?
  if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qF "No canary file"; then echo "  ok   positive: a deleted canary file fails --strict"
  else echo "  FAIL missing canary file passed: rc=$rc"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}
if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$ROOT" || { echo "Status: FAIL — cannot cd to $ROOT"; exit 1; }

MODE="${1:-report}"
BASELINE_FILE=".claude/context-budget-baseline.txt"
CANARY_FILE="${CONTEXT_CANARY_FILE:-.claude/context-canaries.tsv}"

# Total always-loaded budget (bytes of CLAUDE.md + rules without `paths:`). Ceilings only fall: after a
# trim, lower both to just above the new total in the same change. Raising them needs a written reason
# in the PR. Override only for the selftest (CONTEXT_TOTAL_GOAL / CONTEXT_TOTAL_CEILING).
TOTAL_GOAL="${CONTEXT_TOTAL_GOAL:-60500}"
TOTAL_CEILING="${CONTEXT_TOTAL_CEILING:-62000}"

# Per-file size guard for instruction files (applies to path-scoped rules too). Very large instruction
# files load poorly; split before you get near this. The exact loader limit is not documented, so this
# is a house ceiling, not a Claude Code constant.
CHAR_LIMIT=150000
WARN_AT=120000   # 80% of the ceiling — time to plan a split

FILES=("CLAUDE.md")
SCOPED=()
RULE_COUNT=0
while IFS= read -r f; do
  RULE_COUNT=$((RULE_COUNT + 1))
  if is_path_scoped "$f"; then SCOPED+=("$f"); else FILES+=("$f"); fi
done < <(find .claude/rules -name '*.md' -type f 2>/dev/null | sort)
if [ ! -f CLAUDE.md ] && [ "$RULE_COUNT" -eq 0 ]; then
  echo "Status: FAIL — no CLAUDE.md and no .claude/rules/*.md under $ROOT (nothing was measured)"; exit 1
fi

echo "Always-Loaded Context Budget"
echo "============================"
echo "Root: $ROOT"
echo ""
printf "%-48s %10s %9s %7s\n" "FILE (ALWAYS-LOADED)" "BYTES" "~TOKENS" "LINES"
printf "%-48s %10s %9s %7s\n" "------------------------------------------------" "----------" "---------" "-------"

TOTAL_BYTES=0
WARN=0
FAIL=0
ROWS=""
for f in "${FILES[@]}"; do
  [ -f "$f" ] || continue
  b=$(wc -c < "$f" | tr -d ' ')
  ROWS+="${b}	${f}"$'\n'
done

size_flag() { # $1 bytes -> prints flag, bumps WARN/FAIL
  if [ "$1" -gt "$CHAR_LIMIT" ]; then printf '  ✗ OVER 150k CEILING'; return 2
  elif [ "$1" -gt "$WARN_AT" ]; then printf '  ⚠ approaching 150k ceiling'; return 1; fi
  return 0
}

while IFS=$'\t' read -r bytes file; do
  [ -z "${file:-}" ] && continue
  tokens=$((bytes / 4))
  lines=$(wc -l < "$file" | tr -d ' ')
  flag=$(size_flag "$bytes"); rc=$?
  [ "$rc" -eq 2 ] && FAIL=$((FAIL + 1)); [ "$rc" -eq 1 ] && WARN=$((WARN + 1))
  printf "%-48s %10d %9d %7d%s\n" "$file" "$bytes" "$tokens" "$lines" "$flag"
  TOTAL_BYTES=$((TOTAL_BYTES + bytes))
done < <(printf '%s' "$ROWS" | sort -rn -k1)

TOTAL_TOKENS=$((TOTAL_BYTES / 4))
echo ""
echo "  Always-loaded total: ${TOTAL_BYTES} bytes  (~${TOTAL_TOKENS} tokens, est chars/4)"
echo "  Files: ${#FILES[@]}  |  loaded at launch into every session"

echo ""
printf "%-48s %10s  %s\n" "FILE (PATH-SCOPED, loads on matching file access)" "BYTES" ""
SCOPED_BYTES=0
for f in ${SCOPED[@]+"${SCOPED[@]}"}; do
  b=$(wc -c < "$f" | tr -d ' ')
  flag=$(size_flag "$b"); rc=$?
  [ "$rc" -eq 2 ] && FAIL=$((FAIL + 1)); [ "$rc" -eq 1 ] && WARN=$((WARN + 1))
  printf "%-48s %10d%s\n" "$f" "$b" "$flag"
  SCOPED_BYTES=$((SCOPED_BYTES + b))
done
echo "  Path-scoped total: ${SCOPED_BYTES} bytes in ${#SCOPED[@]} file(s) (not in the always-loaded total)"

# ── Growth delta vs optional baseline ────────────────────────────────────────
if [ -f "$BASELINE_FILE" ]; then
  base=$(tr -dc '0-9' < "$BASELINE_FILE")
  if [ -n "$base" ] && [ "$base" -gt 0 ]; then
    delta=$((TOTAL_BYTES - base))
    pct=$(( delta * 100 / base ))
    echo "  Baseline: ${base} bytes  |  delta: ${delta} bytes (${pct}%)"
    if [ "$delta" -gt 0 ] && [ "$pct" -ge 10 ]; then
      echo "  ⚠ Always-loaded cost grew ≥10% since baseline — confirm the growth is intentional."
      WARN=$((WARN + 1))
    fi
  fi
fi
TOTAL_STATUS=ok
if [ "$TOTAL_BYTES" -gt "$TOTAL_CEILING" ]; then
  echo "  ✗ Always-loaded total ${TOTAL_BYTES} exceeds the CEILING ${TOTAL_CEILING}: move procedure into a skill or path-scoped rule."
  TOTAL_STATUS=over
elif [ "$TOTAL_BYTES" -gt "$TOTAL_GOAL" ]; then
  echo "  ⚠ Always-loaded total ${TOTAL_BYTES} is over the GOAL ${TOTAL_GOAL} (ceiling ${TOTAL_CEILING})."
  WARN=$((WARN + 1))
else
  echo "  Budget: total ${TOTAL_BYTES} ≤ goal ${TOTAL_GOAL} (ceiling ${TOTAL_CEILING})"
fi

# ── Canaries: each anchor must appear in at least one ALWAYS-LOADED file ─────
CANARY_MISSING=0
CANARY_COUNT=0
if [ -f "$CANARY_FILE" ]; then
  echo ""
  echo "Canaries ($CANARY_FILE):"
  while IFS=$'\t' read -r label anchor; do
    case "$label" in ''|'#'*) continue ;; esac
    [ -n "${anchor:-}" ] || { echo "  ✗ malformed canary line (no TAB-separated anchor): $label"; CANARY_MISSING=$((CANARY_MISSING + 1)); continue; }
    CANARY_COUNT=$((CANARY_COUNT + 1))
    hit=""
    for f in "${FILES[@]}"; do
      [ -f "$f" ] && grep -qF -- "$anchor" "$f" && { hit="$f"; break; }
    done
    if [ -n "$hit" ]; then echo "  ok   $label ($hit)"
    else echo "  ✗ MISSING $label: \"$anchor\" is in no always-loaded file"; CANARY_MISSING=$((CANARY_MISSING + 1)); fi
  done < "$CANARY_FILE"
  if [ "$CANARY_COUNT" -eq 0 ]; then echo "  ✗ canary file has no entries (a canary gate that checks nothing)"; CANARY_MISSING=$((CANARY_MISSING + 1)); fi
  echo "  Canaries: $((CANARY_COUNT - CANARY_MISSING > 0 ? CANARY_COUNT - CANARY_MISSING : 0))/${CANARY_COUNT} present"
else
  echo ""
  echo "  ✗ No canary file at $CANARY_FILE: critical always-loaded rules are not pinned (fails --strict)."
  CANARY_MISSING=$((CANARY_MISSING + 1))
fi

if [ "$MODE" = "--baseline" ]; then
  echo "$TOTAL_BYTES" > "$BASELINE_FILE"
  echo "  → wrote baseline ($TOTAL_BYTES bytes) to $BASELINE_FILE"
fi

echo ""
echo "Summary: ${WARN} warning(s), ${FAIL} over-limit file(s)"
# --strict fails on: a file over the 150k-char ceiling, the always-loaded total over TOTAL_CEILING, or a
# missing canary. The GOAL and the growth-vs-baseline delta stay advisory.
if [ "$MODE" = "--strict" ]; then
  reasons=""
  [ "$FAIL" -gt 0 ] && reasons="${reasons} an instruction file exceeds the 150k-char ceiling;"
  [ "$TOTAL_STATUS" = over ] && reasons="${reasons} always-loaded total ${TOTAL_BYTES} > ceiling ${TOTAL_CEILING};"
  [ "$CANARY_MISSING" -gt 0 ] && reasons="${reasons} ${CANARY_MISSING} canary anchor(s) missing;"
  if [ -n "$reasons" ]; then echo "Status: FAIL —${reasons}"; exit 1; fi
  echo "Status: PASS (--strict) — total ${TOTAL_BYTES} ≤ ceiling ${TOTAL_CEILING}, ${CANARY_COUNT} canaries present, no file over 150k."
else
  echo "Status: report-only (advisory). Re-run with --strict to enforce the ceiling and canaries."
fi
exit 0
