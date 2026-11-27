#!/usr/bin/env bash
# lint-commands.sh — Lint all command .md files in .claude/commands/
# bash 3.2 compatible (macOS)
#
# Official Claude Code: a command file accepts skill frontmatter except `name` and `paths`
# (the filename is the command). Invalid YAML loads the file with no fields set.
# https://code.claude.com/docs/en/skills

set -uo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_DIR="$(cd "$SCRIPT_DIR/../commands" && pwd)"
COMMANDS_DIR="$DEFAULT_DIR"
QUIET=0

yaml_frontmatter_errors() { # file paths on stdin
  python3 -c '
import sys
try:
    import yaml
except ImportError:
    print("PYYAML_MISSING"); sys.exit(0)
n = 0
for path in sys.stdin.read().splitlines():
    n += 1
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except OSError as e:
        print(f"{path}\tunreadable: {e}"); continue
    if not lines or lines[0].strip() != "---":
        print(f"{path}\tno opening --- frontmatter line"); continue
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        print(f"{path}\tfrontmatter has no closing ---"); continue
    try:
        data = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as e:
        msg = " ".join(str(e).split())
        print(f"{path}\tinvalid YAML: {msg[:200]}"); continue
    if not isinstance(data, dict):
        print(f"{path}\tfrontmatter is not a YAML mapping"); continue
    if "name" in data:
        print(f"{path}\tname is not valid on command files (filename is the command)")
    if "paths" in data:
        print(f"{path}\tpaths is not valid on command files")
print(f"PARSED {n}")
'
}

# Known-broken shell shapes in command instructions. Prints "LINE<TAB>LABEL" per hit.
# Scans fenced code (shell comments stripped) and inline `code` spans on prose lines that are not
# explanatory (a line saying the shape is wrong: not / never / no / reports / instead is skipped).
#   ${ARGUMENTS:-x}             Claude Code substitutes $ARGUMENTS textually and never applies the default
#   gate | tail ...; echo $?    $? is tail's/head's status, so a failing gate reads as 0
#   gate | summarize-test-log   $? is the summarizer's status (0 even on FAIL/UNKNOWN), not the runner's
#   flutter pub audit           not a pub subcommand (3.44: help + exit 0; 3.50.1: exit 64)
#   semgrep scan/--config without --error   exits 0 even with findings
broken_shapes() {
  awk '
    /^[[:space:]]*```/ { fence = !fence; next }
    {
      cand = ""
      if (fence) { line = $0; sub(/(^|[[:space:]])#.*$/, "", line); cand = line }
      else {
        if ($0 ~ /(^|[^[:alpha:]])(not|NOT|never|no|No|reports|instead)([^[:alpha:]]|$)/) next
        s = $0
        while (match(s, /`[^`]+`/)) { cand = cand " " substr(s, RSTART + 1, RLENGTH - 2); s = substr(s, RSTART + RLENGTH) }
      }
      if (cand == "") next
      if (cand ~ /\$\{ARGUMENTS:-/) printf "%d\t${ARGUMENTS:-...} default is never applied by Claude Code; use \"$ARGUMENTS\" and test it\n", NR
      if (cand ~ /[|][[:space:]]*(tail|head)[^;&|]*;[[:space:]]*echo[^;]*[$][?]/) printf "%d\tgate piped into tail/head before echo $? (reads the pager status, not the gate); write to a log, read $?, then tail the log\n", NR
      if (cand ~ /[|][[:space:]]*[^;\n]*summarize-test-log/) printf "%d\tgate piped into summarize-test-log.py (reads the summarizer status, not the runner); write to a log, capture rc, echo EXIT:$rc, then summarize --exit-code\n", NR
      if (cand ~ /flutter[[:space:]]+pub[[:space:]]+audit/) printf "%d\tflutter pub audit is not a command (no advisory scan runs)\n", NR
      if (cand ~ /(^|[^[:alnum:]_-])semgrep[[:space:]]+(scan|--config)/ && cand !~ /--error/) printf "%d\tsemgrep without --error exits 0 on findings\n", NR
    }' "$1"
}

selftest() {
  local self tmp out rc fail=0
  self="$SCRIPT_DIR/$(basename "$0")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  tmp=$(mktemp -d) || return 1
  hdr='---\ndescription: Fixture command for the lint selftest only.\nallowed-tools: Bash\n---\n\nThis body is long enough to pass the body length check for a command file.\n\n'
  run_case() { # $1 label, $2 body, $3 expected rc, $4 needle ("" = no broken-shape ERROR)
    rm -f "$tmp"/*.md; printf '%b%s\n' "$hdr" "$2" > "$tmp/case.md"
    out=$(bash "$self" --dir "$tmp" 2>&1); rc=$?
    if [ "$rc" -eq "$3" ] && { { [ -z "$4" ] && ! printf '%s' "$out" | grep -q 'ERROR: line'; } || { [ -n "$4" ] && printf '%s' "$out" | grep -qF -- "$4"; }; }; then echo "  ok   $1"
    else echo "  FAIL $1 (rc=$rc: $out)"; fail=1; fi
  }
  run_case "positive: \${ARGUMENTS:-} in a code block" $'```bash\nTARGET="${ARGUMENTS:-.}"\n```' 1 'default is never applied'
  run_case "positive: gate | tail; echo \$?" $'```bash\nnpm test 2>&1 | tail -20; echo "EXIT:$?"\n```' 1 'piped into tail/head'
  run_case "positive: gate | summarize-test-log" $'```bash\nnpm test 2>&1 | python3 .claude/scripts/summarize-test-log.py --log /dev/stdin; echo "EXIT:$?"\n```' 1 'piped into summarize-test-log.py'
  run_case "positive: flutter pub audit" $'Run `flutter pub audit` for CVEs.' 1 'flutter pub audit is not a command'
  run_case "positive: semgrep without --error" $'```bash\nsemgrep scan --config auto --json -o semgrep.json .\n```' 1 'semgrep without --error'
  run_case "negative: correct forms and explanatory mentions pass" $'```bash\nTARGET="$ARGUMENTS"; [ -n "$TARGET" ] || TARGET="."   # `${ARGUMENTS:-.}` is never substituted\nnpm test > test.log 2>&1; echo "EXIT:$?"; tail -20 test.log\nnpm test > test.log 2>&1; rc=$?; echo "EXIT:$rc"\npython3 .claude/scripts/summarize-test-log.py --log test.log --exit-code "$rc"\nsemgrep scan --config auto --error .\n# flutter pub audit is not a command\n```\n`cmd | tail; echo $?` reports the status of `tail`.\nThere is no `flutter pub audit` subcommand.' 0 ""
  run_fm() { # $1 label, $2 full file, $3 expected rc, $4 needle
    rm -f "$tmp"/*.md; printf '%s' "$2" > "$tmp/case.md"
    out=$(bash "$self" --dir "$tmp" 2>&1); rc=$?
    if [ "$rc" -eq "$3" ] && printf '%s' "$out" | grep -qF -- "$4"; then echo "  ok   $1"
    else echo "  FAIL $1 (rc=$rc: $out)"; fail=1; fi
  }
  run_fm "positive: unquoted colon in description" $'---\ndescription: Use when: the lint selftest runs a planted invalid YAML command.\nallowed-tools: Bash\n---\n\nThis body is long enough to pass the body length check for a command file.\n' 1 'invalid YAML'
  run_fm "positive: frontmatter name:" $'---\nname: case\ndescription: Fixture command for the lint selftest only.\nallowed-tools: Bash\n---\n\nThis body is long enough to pass the body length check for a command file.\n' 1 'filename is the command'
  run_fm "positive: frontmatter paths:" $'---\ndescription: Fixture command for the lint selftest only.\npaths:\n  - "**/*.ts"\nallowed-tools: Bash\n---\n\nThis body is long enough to pass the body length check for a command file.\n' 1 'paths is not valid on command files'
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --selftest)
      selftest; exit $?
      ;;
    --dir)
      COMMANDS_DIR="$2"
      shift 2
      ;;
    --quiet)
      QUIET=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--dir <path>] [--quiet]" >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Counters and collected data
# ---------------------------------------------------------------------------
passed=0
warned=0
failed=0

# Arrays to collect descriptions for duplicate detection (bash 3.2 compatible)
declare -a desc_values=()
declare -a desc_files=()

# Temporary output buffer per file
# We process all files first, then do duplicate check at the end.
# Store per-file results: "status|relpath|messages..."
declare -a file_results=()

# ---------------------------------------------------------------------------
# Helper: strip leading/trailing whitespace from a string
# ---------------------------------------------------------------------------
trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

# ---------------------------------------------------------------------------
# lint_file <abs_path> <rel_path>
# Appends one entry to file_results[].
# Entry format:  STATUS|REL_PATH|MSG1|MSG2|...
#   STATUS: ok | warn | fail
# ---------------------------------------------------------------------------
lint_file() {
  local abs_path="$1"
  local rel_path="$2"

  local status="ok"
  local -a messages=()

  # ---- 1. Read the file ----
  local content
  content="$(cat "$abs_path")"

  # ---- 2. Frontmatter presence check ----
  local first_line
  first_line="$(head -1 "$abs_path")"

  local has_frontmatter=0
  local fm_end_line=0   # line number (1-based) of closing ---
  local description_value=""
  local has_description=0
  local has_allowed_tools=0

  if [[ "$first_line" == "---" ]]; then
    # Find second --- (must be on its own line, after line 1)
    local line_num=0
    while IFS= read -r line; do
      line_num=$((line_num + 1))
      if [[ $line_num -eq 1 ]]; then
        continue  # skip opening ---
      fi
      if [[ "$line" == "---" ]]; then
        fm_end_line=$line_num
        break
      fi
    done < "$abs_path"

    if [[ $fm_end_line -gt 1 ]]; then
      has_frontmatter=1
    else
      # Opening --- exists but no closing ---
      has_frontmatter=0
      messages+=("ERROR: frontmatter opened with --- but never closed")
      status="fail"
    fi
  else
    messages+=("ERROR: missing frontmatter (file must start with ---)")
    status="fail"
  fi

  # ---- 3. Parse frontmatter fields (only if frontmatter found) ----
  if [[ $has_frontmatter -eq 1 ]]; then
    local in_fm=0
    local fm_line=0
    while IFS= read -r line; do
      fm_line=$((fm_line + 1))
      if [[ $fm_line -eq 1 ]]; then
        in_fm=1
        continue
      fi
      if [[ $fm_line -eq $fm_end_line ]]; then
        break
      fi
      if [[ $in_fm -eq 1 ]]; then
        # description:
        if [[ "$line" =~ ^description:[[:space:]]*(.*) ]]; then
          has_description=1
          description_value="$(trim "${BASH_REMATCH[1]}")"
        fi
        # allowed-tools:
        if [[ "$line" =~ ^allowed-tools: ]]; then
          has_allowed_tools=1
        fi
      fi
    done < "$abs_path"

    # description present?
    if [[ $has_description -eq 0 ]]; then
      messages+=("ERROR: missing required field: description")
      status="fail"
    else
      # description length > 20 chars?
      local desc_len=${#description_value}
      if [[ $desc_len -le 20 ]]; then
        messages+=("ERROR: description too short (${desc_len} chars, must be > 20)")
        status="fail"
      else
        # Record for duplicate detection
        desc_values+=("$description_value")
        desc_files+=("$rel_path")
      fi
    fi

    # allowed-tools warning
    if [[ $has_allowed_tools -eq 0 ]]; then
      messages+=("WARN: missing allowed-tools field")
      if [[ "$status" == "ok" ]]; then
        status="warn"
      fi
    fi

    yaml_err=$(printf '%s\n' "$yaml_report" | awk -F'\t' -v f="$abs_path" '$1 == f { print $2; exit }')
    if [[ -n "$yaml_err" ]]; then
      messages+=("ERROR: frontmatter ${yaml_err}")
      status="fail"
    fi
  fi

  # ---- 4. Body not empty check ----
  if [[ $has_frontmatter -eq 1 && $fm_end_line -gt 0 ]]; then
    # Extract body: everything after line fm_end_line
    local body
    body="$(tail -n +"$((fm_end_line + 1))" "$abs_path")"
    # Count non-whitespace chars
    local body_nws
    body_nws="$(printf '%s' "$body" | tr -d '[:space:]')"
    local body_len=${#body_nws}
    if [[ $body_len -le 30 ]]; then
      messages+=("ERROR: body too short or empty (${body_len} non-whitespace chars, must be > 30)")
      status="fail"
    fi
  fi

  # ---- 4b. Known-broken shell shapes ----
  local shape_line shape_msg
  while IFS="	" read -r shape_line shape_msg; do
    [[ -n "$shape_msg" ]] || continue
    messages+=("ERROR: line ${shape_line}: ${shape_msg}")
    status="fail"
  done <<EOF_SHAPES
$(broken_shapes "$abs_path")
EOF_SHAPES

  # ---- 5. Build result entry ----
  # Format: status|rel_path|msg1|msg2|...
  local entry="${status}|${rel_path}"
  for msg in "${messages[@]+"${messages[@]}"}"; do
    entry="${entry}|${msg}"
  done

  file_results+=("$entry")
}

# ---------------------------------------------------------------------------
# Collect all .md files (top-level and one level of subdirectories)
# ---------------------------------------------------------------------------
declare -a md_files_abs=()
declare -a md_files_rel=()
yaml_report=""

# Top-level .md files
for f in "$COMMANDS_DIR"/*.md; do
  [[ -f "$f" ]] || continue
  md_files_abs+=("$f")
  md_files_rel+=("$(basename "$f")")
done

# Subdirectory .md files (one level deep)
for d in "$COMMANDS_DIR"/*/; do
  [[ -d "$d" ]] || continue
  subdir_name="$(basename "$d")"
  for f in "$d"*.md; do
    [[ -f "$f" ]] || continue
    md_files_abs+=("$f")
    md_files_rel+=("${subdir_name}/$(basename "$f")")
  done
done

# ---------------------------------------------------------------------------
# Strict YAML parse (official: invalid YAML loads the command with no fields)
# ---------------------------------------------------------------------------
if [[ ${#md_files_abs[@]} -gt 0 ]]; then
  yaml_report=$(printf '%s\n' "${md_files_abs[@]}" | yaml_frontmatter_errors)
  if [[ "$yaml_report" == *PYYAML_MISSING* ]]; then
    echo "ERROR: python3 with PyYAML is required for the strict frontmatter parse (pip install pyyaml); nothing was parsed." >&2
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# Lint each file
# ---------------------------------------------------------------------------
for i in "${!md_files_abs[@]}"; do
  lint_file "${md_files_abs[$i]}" "${md_files_rel[$i]}"
done

# ---------------------------------------------------------------------------
# Duplicate description detection
# Append WARN entries to the matching file result.
# ---------------------------------------------------------------------------
declare -a dup_warned_files=()

for i in "${!desc_values[@]}"; do
  for j in "${!desc_values[@]}"; do
    if [[ $i -ge $j ]]; then
      continue
    fi
    if [[ "${desc_values[$i]}" == "${desc_values[$j]}" ]]; then
      # Mark both files as having duplicate description warning
      dup_warned_files+=("${desc_files[$i]}")
      dup_warned_files+=("${desc_files[$j]}")
    fi
  done
done

# Add duplicate warnings to existing result entries
if [[ ${#dup_warned_files[@]} -gt 0 ]]; then
  declare -a new_file_results=()
  for entry in "${file_results[@]}"; do
    IFS='|' read -ra parts <<< "$entry"
    local_status="${parts[0]}"
    local_rel="${parts[1]}"

    # Check if this file is in dup_warned_files
    is_dup=0
    for df in "${dup_warned_files[@]}"; do
      if [[ "$df" == "$local_rel" ]]; then
        is_dup=1
        break
      fi
    done

    if [[ $is_dup -eq 1 ]]; then
      entry="${entry}|WARN: duplicate description value"
      if [[ "$local_status" == "ok" ]]; then
        # Replace status
        entry="warn|${entry#ok|}"
      fi
    fi
    new_file_results+=("$entry")
  done
  file_results=("${new_file_results[@]}")
fi

# ---------------------------------------------------------------------------
# Print results
# ---------------------------------------------------------------------------
for entry in "${file_results[@]}"; do
  IFS='|' read -ra parts <<< "$entry"
  entry_status="${parts[0]}"
  entry_rel="${parts[1]}"

  # messages start at index 2
  case "$entry_status" in
    ok)
      passed=$((passed + 1))
      if [[ $QUIET -eq 0 ]]; then
        printf '✅ %s\n' "$entry_rel"
      fi
      ;;
    warn)
      warned=$((warned + 1))
      printf '⚠️  %s\n' "$entry_rel"
      for idx in "${!parts[@]}"; do
        [[ $idx -lt 2 ]] && continue
        printf '   → %s\n' "${parts[$idx]}"
      done
      ;;
    fail)
      failed=$((failed + 1))
      printf '❌ %s\n' "$entry_rel"
      for idx in "${!parts[@]}"; do
        [[ $idx -lt 2 ]] && continue
        printf '   → %s\n' "${parts[$idx]}"
      done
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "RESULT: ${passed} passed, ${warned} warned, ${failed} failed"

# ---------------------------------------------------------------------------
# Exit code
# ---------------------------------------------------------------------------
if [[ $failed -gt 0 ]]; then
  exit 1
fi
exit 0
