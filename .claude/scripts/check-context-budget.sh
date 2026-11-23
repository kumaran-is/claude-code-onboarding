#!/usr/bin/env bash
# check-context-budget.sh — Measure the ALWAYS-LOADED context cost of this repo's instruction
# files and lint the rules corpus for structural drift.
#
# WHY: CLAUDE.md + every .claude/rules/**/*.md WITHOUT `paths:` frontmatter is loaded at launch into
# EVERY session (and every subagent that reads CLAUDE.md). Rules WITH `paths:` load only when Claude
# reads or edits a matching file, so they are listed separately and NOT counted in the total.
# Rules are discovered recursively (subdirectories of .claude/rules/ load too).
# This makes the always-loaded cost VISIBLE and tracks its growth. It does NOT tell you to "trim"
# (a heavy always-loaded design can be intentional). It is a measurement + canary tool.
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
  local tmp fail=0 f
  if bash -n "${BASH_SOURCE[0]}" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  tmp=$(mktemp -d) || return 1
  mkdir -p "$tmp/.claude/rules/web"
  printf '# Root\n' > "$tmp/CLAUDE.md"
  printf -- '---\npaths:\n  - "**/*.py"\n---\n\n# Scoped\n%s\n' "$(printf '%01000d' 0)" > "$tmp/.claude/rules/scoped.md"
  printf -- '---\npaths: "**/*.ts, **/*.tsx"\n---\n# Scoped inline\n' > "$tmp/.claude/rules/web/nested-scoped.md"
  printf '# Always\nNo frontmatter.\n' > "$tmp/.claude/rules/always.md"
  printf -- '---\ndescription: x\n---\n# Always with other frontmatter\n' > "$tmp/.claude/rules/web/nested-always.md"
  printf '# Body mentions\npaths: not frontmatter\n' > "$tmp/.claude/rules/body-paths.md"
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
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}
if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$ROOT" || { echo "Status: FAIL — cannot cd to $ROOT"; exit 1; }

MODE="${1:-report}"
BASELINE_FILE=".claude/context-budget-baseline.txt"

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
if [ "$MODE" = "--baseline" ]; then
  echo "$TOTAL_BYTES" > "$BASELINE_FILE"
  echo "  → wrote baseline ($TOTAL_BYTES bytes) to $BASELINE_FILE"
fi

echo ""
echo "Summary: ${WARN} warning(s), ${FAIL} over-limit file(s)"
# --strict fails ONLY on a file over the 150k-char ceiling. Size/growth stay advisory — a heavy always-loaded
# design can be intentional.
if [ "$MODE" = "--strict" ] && [ "$FAIL" -gt 0 ]; then
  echo "Status: FAIL — an instruction file exceeds the 150k-char ceiling; split it."
  exit 1
fi
echo "Status: report-only (advisory). Re-run with --strict to fail on a 150k-char breach."
exit 0
