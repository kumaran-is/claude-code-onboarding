#!/usr/bin/env bash
# lint-skills.sh — Lint all SKILL.md files in the skills directory
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="${SCRIPT_DIR}/../skills"
QUIET=0

# Strict YAML parse of every frontmatter block in one python pass. Prints "path<TAB>error" per failing file and
# "PARSED <n>" last. The awk field checks below accept frontmatter that YAML rejects (an unquoted ": " in a
# description, a tab, a bad indent), and Claude Code then cannot read the skill's name/description.
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
        print(f"{path}\tfrontmatter is not a YAML mapping")
print(f"PARSED {n}")
'
}

if [[ "${1:-}" == "--selftest" ]]; then
  self="${BASH_SOURCE[0]}"
  bash -n "$self" || { echo "  FAIL does not parse"; exit 1; }
  echo "  ok   parses (bash -n)"
  tmp=$(mktemp -d) || exit 1
  mkdir -p "$tmp/good" "$tmp/bad" "$tmp/badname"
  printf -- '---\nname: good\ndescription: "Use when: x happens. Covers a, b."\nmetadata:\n  triggers: x, y\nallowed-tools: Read\n---\n# Good\n\n## Iron Law\nx\n' > "$tmp/good/SKILL.md"
  out=$(bash "$self" --dir "$tmp/good" 2>&1); rc=$?
  fail=0
  if [[ $rc -eq 0 ]] && ! printf '%s' "$out" | grep -q "invalid YAML"; then echo "  ok   negative: valid frontmatter (quoted colon) passes"; else echo "  FAIL clean fixture: rc=$rc $out"; fail=1; fi
  printf -- '---\nname: bad\ndescription: Use when: x happens\nallowed-tools: Read\n---\n# Bad\n' > "$tmp/bad/SKILL.md"
  out=$(bash "$self" --dir "$tmp/bad" 2>&1); rc=$?
  if [[ $rc -eq 1 ]] && printf '%s' "$out" | grep -q "bad/SKILL.md" && printf '%s' "$out" | grep -q "invalid YAML"; then echo "  ok   positive: unquoted ': ' in description fails with invalid YAML"; else echo "  FAIL planted bad YAML not caught: rc=$rc $out"; fail=1; fi
  printf -- '---\nname: Bad_Name\ndescription: "Use when: handling a planted spec violation."\nmetadata:\n  triggers: x, y\nallowed-tools: Read\n---\n# Bad\n\n## Iron Law\nx\n' > "$tmp/badname/SKILL.md"
  out=$(bash "$self" --dir "$tmp/badname" 2>&1); rc=$?
  if [[ $rc -eq 1 ]] && printf '%s' "$out" | grep -q "Agent Skills spec"; then echo "  ok   positive: spec-illegal name fails via check-skill-spec"; else echo "  FAIL planted spec name not caught: rc=$rc $out"; fail=1; fi
  spec_self=$(python3 "${SCRIPT_DIR}/../skills/writing-skills/scripts/check-skill-spec.py" --selftest 2>&1); spec_rc=$?
  if [[ $spec_rc -eq 0 ]] && printf '%s' "$spec_self" | grep -q "selftest PASS"; then echo "  ok   negative: check-skill-spec.py --selftest PASS"; else echo "  FAIL check-skill-spec selftest: rc=$spec_rc $spec_self"; fail=1; fi
  rm -rf "$tmp"
  [[ $fail -eq 0 ]] && echo "selftest PASS" || echo "selftest FAIL"
  exit $fail
fi

# Parse flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      SKILLS_DIR="$2"
      shift 2
      ;;
    --quiet)
      QUIET=1
      shift
      ;;
    *)
      echo "Unknown flag: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$SKILLS_DIR" ]]; then
  echo "ERROR: Skills directory not found: $SKILLS_DIR" >&2
  exit 1
fi

# Counters
passed=0
warned=0
failed=0
any_errors=0

# Collect all name values for duplicate detection (bash 3.2 compatible — no associative arrays)
# We'll do two passes: first collect names, then lint
all_names=""
all_name_files=""

# First pass: collect names
while IFS= read -r skill_file; do
  frontmatter=$(awk '/^---/{count++; if(count==2) exit; if(count==1) next} count==1{print}' "$skill_file")
  name_val=$(echo "$frontmatter" | awk '/^name:/{sub(/^name:[[:space:]]*/, ""); print; exit}')
  if [[ -n "$name_val" ]]; then
    all_names="${all_names}${name_val}"$'\n'
    all_name_files="${all_name_files}${name_val}::${skill_file}"$'\n'
  fi
done < <(find "$SKILLS_DIR" -name "SKILL.md" | sort)

yaml_report=$(find "$SKILLS_DIR" -name "SKILL.md" | sort | yaml_frontmatter_errors)
if [[ "$yaml_report" == *PYYAML_MISSING* ]]; then
  echo "ERROR: python3 with PyYAML is required for the strict frontmatter parse (pip install pyyaml); nothing was parsed." >&2
  exit 1
fi
echo "YAML frontmatter: $(printf '%s\n' "$yaml_report" | awk '/^PARSED /{print $2}') file(s) parsed strictly"

SPEC_HELPER="${SCRIPT_DIR}/../skills/writing-skills/scripts/check-skill-spec.py"
if [[ ! -f "$SPEC_HELPER" ]]; then
  echo "ERROR: missing Agent Skills spec checker: $SPEC_HELPER" >&2
  exit 1
fi
spec_report=$(python3 "$SPEC_HELPER" --dir "$SKILLS_DIR" --activation --machine 2>&1); spec_rc=$?
if [[ $spec_rc -eq 2 ]]; then
  echo "ERROR: check-skill-spec.py usage failure: $spec_report" >&2
  exit 1
fi

# Second pass: lint each file
while IFS= read -r skill_file; do
  skill_dir_name=$(basename "$(dirname "$skill_file")")/SKILL.md

  # Extract frontmatter (lines between first and second ---)
  frontmatter=$(awk '/^---/{count++; if(count==2) exit; if(count==1) next} count==1{print}' "$skill_file")

  # Extract body (lines after second ---)
  body=$(awk '/^---/{count++; next} count>=2{print}' "$skill_file")

  errors=""
  warnings=""

  yaml_err=$(printf '%s\n' "$yaml_report" | awk -F'\t' -v f="$skill_file" '$1 == f { print $2; exit }')
  if [[ -n "$yaml_err" ]]; then
    errors="${errors}   → ERROR: frontmatter ${yaml_err}\n"
  fi

  spec_errs=$(printf '%s\n' "$spec_report" | awk -F'\t' -v f="$skill_file" '$1=="SPEC" && $2==f { print $3 }')
  if [[ -n "$spec_errs" ]]; then
    while IFS= read -r se; do
      [[ -n "$se" ]] && errors="${errors}   → ERROR: ${se}\n"
    done <<< "$spec_errs"
  fi

  # Check required field: name
  name_val=$(echo "$frontmatter" | awk '/^name:/{sub(/^name:[[:space:]]*/, ""); print; exit}')
  if [[ -z "$name_val" ]]; then
    errors="${errors}   → ERROR: missing required field: name\n"
  fi

  # Check required field: description (> 20 chars)
  # Handles both inline and YAML block scalar (> or |) multiline descriptions
  desc_val=$(echo "$frontmatter" | awk '/^description:/{sub(/^description:[[:space:]]*/, ""); print; exit}')
  if [[ -z "$desc_val" ]]; then
    errors="${errors}   → ERROR: missing required field: description\n"
  elif [[ "$desc_val" == ">" || "$desc_val" == "|" ]]; then
    # YAML block scalar — content is on following indented lines; always valid
    :
  elif [[ ${#desc_val} -le 20 ]]; then
    errors="${errors}   → ERROR: description must be > 20 chars (got ${#desc_val})\n"
  fi

  # Check required field: metadata: block
  metadata_line=$(echo "$frontmatter" | awk '/^metadata:/{print; exit}')
  if [[ -z "$metadata_line" ]]; then
    errors="${errors}   → ERROR: missing required field: metadata\n"
  fi

  # Check required field: metadata.triggers (indented triggers: under metadata)
  triggers_line=$(echo "$frontmatter" | awk '/^[[:space:]]+triggers:/{print; exit}')
  if [[ -z "$triggers_line" ]]; then
    errors="${errors}   → ERROR: missing required field: metadata.triggers\n"
  fi

  # Check warning: ## Iron Law section in body (strongly recommended, not required)
  iron_law=$(echo "$body" | grep -c '^## Iron Law' || true)
  if [[ "$iron_law" -eq 0 ]]; then
    warnings="${warnings}   → WARN: missing ## Iron Law section\n"
  fi

  # Check warning: allowed-tools
  allowed_tools=$(echo "$frontmatter" | awk '/^allowed-tools:/{print; exit}')
  if [[ -z "$allowed_tools" ]]; then
    warnings="${warnings}   → WARN: missing allowed-tools field\n"
  fi

  # Check warning: body length > 500 lines
  body_lines=$(echo "$body" | wc -l | tr -d ' ')
  if [[ "$body_lines" -gt 500 ]]; then
    warnings="${warnings}   → WARN: body is ${body_lines} lines (recommended ≤ 500)\n"
  fi

  # Check duplicate name
  if [[ -n "$name_val" ]]; then
    # Count how many files have this name
    dup_count=$(echo "$all_name_files" | grep -c "^${name_val}::" || true)
    if [[ "$dup_count" -gt 1 ]]; then
      # Only report if this is not the first occurrence
      first_file=$(echo "$all_name_files" | grep "^${name_val}::" | head -1 | cut -d':' -f3-)
      if [[ "$skill_file" != "$first_file" ]]; then
        errors="${errors}   → ERROR: duplicate name '${name_val}' (also in $(basename "$(dirname "$first_file")")/SKILL.md)\n"
      fi
    fi
  fi

  # Determine status
  if [[ -n "$errors" ]]; then
    failed=$((failed + 1))
    any_errors=1
    echo "❌ ${skill_dir_name}"
    printf "%b" "$errors"
    if [[ -n "$warnings" ]]; then
      printf "%b" "$warnings"
    fi
  elif [[ -n "$warnings" ]]; then
    warned=$((warned + 1))
    if [[ $QUIET -eq 0 ]]; then
      echo "⚠️  ${skill_dir_name}"
      printf "%b" "$warnings"
    else
      echo "⚠️  ${skill_dir_name}"
      printf "%b" "$warnings"
    fi
  else
    passed=$((passed + 1))
    if [[ $QUIET -eq 0 ]]; then
      echo "✅ ${skill_dir_name}"
    fi
  fi

done < <(find "$SKILLS_DIR" -name "SKILL.md" | sort)

echo ""
echo "RESULT: ${passed} passed, ${warned} warned, ${failed} failed"

act_fail=0
while IFS=$'\t' read -r kind status cid detail; do
  [[ "$kind" == "ACTIVATION" ]] || continue
  if [[ "$status" == "FAIL" ]]; then
    act_fail=$((act_fail + 1))
    echo "   → ERROR: activation ${cid}: ${detail}"
  elif [[ "$QUIET" -eq 0 && "$status" == "PASS" ]]; then
    echo "   activation ${cid}: PASS"
  fi
done <<< "$(printf '%s\n' "$spec_report")"

if [[ "$act_fail" -gt 0 ]]; then
  any_errors=1
  echo "ACTIVATION: ${act_fail} failed (Agent Skills trigger eval)"
fi

if [[ $any_errors -eq 1 ]]; then
  exit 1
fi
exit 0
