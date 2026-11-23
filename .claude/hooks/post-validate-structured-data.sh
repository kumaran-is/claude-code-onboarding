#!/usr/bin/env bash
# PostToolUse (Write|Edit): syntax-check .json / .yaml / .yml files after they are written.
# Advisory only (always exit 0): a parse error goes to Claude as hookSpecificOutput.additionalContext
# (systemMessage would reach only the user, so the model would never fix the file).
#
# The file path is passed to the parsers as an argument, never interpolated into code: the previous
# version ran python3 -c "...open('$FILE_PATH')..." (a quote in a file name executed code) and built
# its JSON reply with a heredoc (a quote in the parse error produced invalid JSON).
# JSON-with-comments files (tsconfig*.json, .vscode/*.json, *.jsonc) are skipped: they are not JSON.
# YAML needs PyYAML; when it is missing the check is skipped and that is said once per session.
# Test: bash .claude/hooks/post-validate-structured-data.sh --selftest
set -uo pipefail

YAML_CHECK='import sys, yaml
with open(sys.argv[1], encoding="utf-8") as fh:
    list(yaml.safe_load_all(fh))'

advise() { # $1 message
  jq -n --arg m "$1" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
}

run_hook() {
  local input file err marker
  input=$(cat)
  command -v jq >/dev/null 2>&1 || return 0
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || file=""
  [ -n "$file" ] && [ -f "$file" ] || return 0
  case "$file" in
    */tsconfig*.json|*/jsconfig*.json|*/.vscode/*.json|*/devcontainer.json|*.jsonc) return 0 ;;
    *.json)
      err=$(jq empty "$file" 2>&1) && return 0
      advise "Invalid JSON in $file: $err. Fix the syntax before relying on this file." ;;
    *.yaml|*.yml)
      if ! python3 -c 'import yaml' >/dev/null 2>&1; then
        marker="${TMPDIR:-/tmp}/claude-structured-data-nopyyaml"
        [ -f "$marker" ] && return 0
        : > "$marker" 2>/dev/null
        advise "YAML syntax check skipped: python3 with PyYAML is not available (shown once)."
        return 0
      fi
      err=$(python3 -c "$YAML_CHECK" "$file" 2>&1 | tail -n 4) && [ -z "$err" ] && return 0
      advise "Invalid YAML in $file: $err" ;;
  esac
  return 0
}

selftest() {
  local self fail=0 tmp out f
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  probe() { jq -n --arg f "$1" '{tool_name:"Write",tool_input:{file_path:$f}}' | "$BASH" "$self" 2>&1; }
  expect() { # $1 label, $2 file, $3 expected fragment ("" = silent)
    out=$(probe "$2")
    if [ -z "$3" ]; then
      if [ -z "$out" ]; then echo "  ok   $1"; else echo "  FAIL $1 (unexpected: $out)"; fail=1; fi
    elif printf '%s' "$out" | jq -e --arg s "$3" '.hookSpecificOutput.additionalContext | contains($s)' >/dev/null 2>&1; then
      echo "  ok   $1"
    else echo "  FAIL $1 (got: $out)"; fail=1; fi
  }
  printf '{"a": 1,}\n' > "$tmp/bad.json";  expect "positive: invalid JSON reported as valid JSON reply" "$tmp/bad.json" "Invalid JSON"
  printf '{"a": "q\\"uote", "b": [1, 2]}\n' > "$tmp/ok.json"; expect "negative: valid JSON silent" "$tmp/ok.json" ""
  printf '// comment\n{"compilerOptions": {}}\n' > "$tmp/tsconfig.json"; expect "negative: tsconfig (JSONC) skipped" "$tmp/tsconfig.json" ""
  if python3 -c 'import yaml' >/dev/null 2>&1; then
    printf 'a: [1, 2\nb: c\n' > "$tmp/bad.yaml"; expect "positive: invalid YAML reported" "$tmp/bad.yaml" "Invalid YAML"
    printf 'a: 1\n---\nb: 2\n' > "$tmp/multi.yml"; expect "negative: multi-document YAML silent" "$tmp/multi.yml" ""
    # A quote in the file name must not execute code (old hook: open('$FILE_PATH')).
    f="$tmp/x'); open('pwned','w').write('1'); ('.yaml"; printf 'a: [\n' > "$f"
    out=$(cd "$tmp" && probe "$f")
    if [ ! -e "$tmp/pwned" ] && printf '%s' "$out" | jq -e '.hookSpecificOutput' >/dev/null 2>&1; then
      echo "  ok   positive: quote in file name is data, not code (reply is valid JSON)"
    else echo "  FAIL file name injection or invalid reply ($out)"; fail=1; fi
  else
    echo "  NOT RUN YAML controls (PyYAML missing)"
  fi
  printf 'x' > "$tmp/a.md"; expect "negative: other extensions ignored" "$tmp/a.md" ""
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
