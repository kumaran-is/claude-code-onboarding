#!/usr/bin/env bash
# PreToolUse (Edit|Write): block invisible or control characters that can hide instructions in
# written content. Exit 2 = block (reason on stderr), exit 0 = allow.
#
# Blocks: zero-width chars (U+200B-U+200D, U+FEFF), bidi overrides/isolates (U+202A-U+202E,
# U+2066-U+2069), NUL, Unicode tag chars (U+E0000-U+E007F), ANSI escape sequences (ESC [ ] or ().
# Warns (advisory, additionalContext): Cyrillic look-alike letters, or Greek mixed with Latin.
#
# The checks run on decoded code points inside jq. The previous version used `grep -P`, which BSD
# grep on macOS rejects (exit 2 inside an `if`), so every Unicode check silently passed there.
# Overlong UTF-8 is not checked: the hook input is JSON-decoded text, where an overlong sequence
# cannot survive as bytes.
# References: CVE-2025-53109/53110 (Unicode sandbox escape).
# Test: bash .claude/hooks/pre-unicode-injection.sh --selftest
set -uo pipefail

# Prints the first finding (category) for the tool input on stdin, or nothing.
CLASSIFY='
(.tool_name // "") as $t
| (if $t == "Write" then (.tool_input.content // "")
   elif $t == "Edit" then (.tool_input.new_string // "")
   else "" end) as $c
| ($c | explode) as $cp
| if any($cp[]; (. >= 8203 and . <= 8205) or . == 65279) then "zero-width"
  elif any($cp[]; (. >= 8234 and . <= 8238) or (. >= 8294 and . <= 8297)) then "bidi"
  elif any($cp[]; . == 0) then "nul"
  elif any($cp[]; . >= 917504 and . <= 917631) then "tag"
  elif any($cp[]; . == 27) and ($c | test("\u001b[\\[\\]()]")) then "ansi"
  elif any($cp[]; . == 1072 or . == 1077 or . == 1086 or . == 1088 or . == 1089 or . == 1093) then "homoglyph"
  elif any($cp[]; . >= 913 and . <= 969) and ($c | test("[A-Za-z]")) then "homoglyph"
  else empty end'

run_hook() {
  local input finding marker
  input=$(cat)
  if ! command -v jq >/dev/null 2>&1; then
    marker="${TMPDIR:-/tmp}/claude-unicode-hook-nojq"
    if [ ! -f "$marker" ]; then
      : > "$marker" 2>/dev/null
      echo "pre-unicode-injection: jq not found; Unicode injection checks are DISABLED until jq is installed." >&2
      return 1 # non-blocking error: shown once, the edit proceeds
    fi
    return 0
  fi
  finding=$(printf '%s' "$input" | jq -r "$CLASSIFY" 2>/dev/null) || finding=""
  case "$finding" in
    zero-width) echo "BLOCKED: zero-width character (U+200B-U+200D or U+FEFF) in the written content. It can hide instructions." >&2; return 2 ;;
    bidi) echo "BLOCKED: bidirectional override/isolate character (U+202A-U+202E or U+2066-U+2069). It can disguise code or commands." >&2; return 2 ;;
    nul) echo "BLOCKED: NUL character in the written content. It can truncate strings in downstream tools." >&2; return 2 ;;
    tag) echo "BLOCKED: Unicode tag character (U+E0000-U+E007F). It can embed invisible data." >&2; return 2 ;;
    ansi) echo "BLOCKED: ANSI escape sequence (raw ESC byte). It can manipulate terminal display. Write the escape as text (for example \\033[) instead." >&2; return 2 ;;
    homoglyph)
      jq -n --arg m "Unicode advisory: the content mixes Cyrillic/Greek look-alike letters with Latin text. Confirm this is intended multilingual text, not an identifier or filter bypass." \
        '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$m}}'
      return 0 ;;
  esac
  return 0
}

selftest() {
  local self fail=0 out rc
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  # $1 tool, $2 content (raw bytes, built with printf so this file holds no invisible characters)
  probe() {
    jq -n --arg t "$1" --arg c "$2" '{tool_name:$t,tool_input:{file_path:"/x/a.md",content:$c,old_string:"a",new_string:$c}}' | "$BASH" "$self" 2>&1
  }
  check() { # $1 label, $2 tool, $3 content, $4 expected rc, $5 expected message fragment ("" = silent)
    out=$(probe "$2" "$3"); rc=$?
    local msg_ok=1
    if [ -z "$5" ]; then [ -z "$out" ] || msg_ok=0
    else case "$out" in *"$5"*) ;; *) msg_ok=0 ;; esac; fi
    if [ "$rc" -eq "$4" ] && [ "$msg_ok" -eq 1 ]; then echo "  ok   $1"
    else echo "  FAIL $1 (exit $rc, expected $4: $out)"; fail=1; fi
  }
  check "positive: zero-width space blocked (Write)" Write "$(printf 'safe\342\200\213text')" 2 "zero-width"
  check "positive: BOM blocked (Edit)" Edit "$(printf 'x\357\273\277y')" 2 "zero-width"
  check "positive: RLO override blocked" Write "$(printf 'a\342\200\256b')" 2 "bidirectional"
  check "positive: isolate U+2066 blocked" Edit "$(printf 'a\342\201\246b')" 2 "bidirectional"
  check "positive: tag character blocked" Write "$(printf 'a\363\240\200\201b')" 2 "tag character"
  check "positive: ANSI escape blocked" Write "$(printf 'x\033[31mred')" 2 "ANSI escape"
  out=$(jq -n '{tool_name:"Write",tool_input:{file_path:"/x/a",content:"a\u0000b"}}' | "$BASH" "$self" 2>&1); rc=$?
  if [ "$rc" -eq 2 ] && printf '%s' "$out" | grep -qF "NUL character"; then echo "  ok   positive: NUL blocked"; else echo "  FAIL NUL (exit $rc: $out)"; fail=1; fi
  check "advisory: Cyrillic look-alike warns, exit 0" Write "$(printf 'p\320\260ypal')" 0 "additionalContext"
  check "negative: plain ASCII and accented Latin pass silently" Write "$(printf 'caf\303\251 r\303\251sum\303\251 \\033[ text')" 0 ""
  check "negative: CJK and emoji pass silently" Write "$(printf '\346\227\245\346\234\254 \360\237\230\200')" 0 ""
  check "negative: other tools ignored" Read "$(printf 'a\342\200\213b')" 0 ""
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit $?
