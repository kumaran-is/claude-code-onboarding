#!/usr/bin/env bash
# .claude/scripts/lint-agents.sh
# Usage: lint-agents.sh [--dir <path>] [--quiet] | --selftest
# Exit 0 = all pass, Exit 1 = failures found (or no agent files found: a lint that saw nothing fails)
#
# Tool grants: an AGENT is granted tools only by `tools:`. `allowed-tools:` is a skill/command field and
# is IGNORED in agent frontmatter, so an agent that declares only `allowed-tools:` silently inherits
# every tool (including Write/Edit). It is an error here.
# Least privilege (warning, does not fail yet): an agent named *-reviewer / *-auditor / *-evaluator /
# *-checker / *-challenger should declare `disallowedTools: Write, Edit`, must not grant Write/Edit in
# `tools:` and must not declare `memory:` (memory re-grants Write/Edit for its memory directory).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_DIR="${SCRIPT_DIR}/../agents"
QUIET=false

# Strict YAML parse of agent frontmatter (ADVISORY: reported as WARN, never fails the lint yet; many
# agent descriptions still carry unquoted ": " or multi-line <example> blocks). Same parser as lint-skills.sh.
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

# Parse arguments
selftest() {
  local self tmp out rc fail=0
  self="${SCRIPT_DIR}/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   control 0: parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  tmp=$(mktemp -d) || return 1
  mk() { # $1 file, $2 extra frontmatter lines, $3 body
    printf -- '---\nname: %s\ndescription: A fixture agent used only by the lint selftest.\nmodel: sonnet\nvibe: calm\ncolor: blue\nemoji: "x"\n%b---\n%b\n' \
      "${1%.md}" "$2" "$3" > "$tmp/$1"
  }
  check() { # $1 label, $2 expected rc, $3 needle ("" = none)
    out=$(bash "$self" --dir "$tmp" 2>&1); rc=$?
    if [ "$rc" -eq "$2" ] && { [ -z "$3" ] || printf '%s' "$out" | grep -qF -- "$3"; }; then echo "  ok   $1"
    else echo "  FAIL $1 (rc=$rc out=$out)"; fail=1; fi
    rm -f "$tmp"/*.md
  }
  mk yamlbad.md 'tools: Read\n' 'Body.'; sed -i.bak 's/^description: .*/description: Use when: the lint selftest runs/' "$tmp/yamlbad.md"; rm -f "$tmp/yamlbad.md.bak"
  check "advisory: invalid YAML frontmatter warns, exit stays 0" 0 "WARN yaml (yamlbad.md): invalid YAML"
  mk exdesc.md 'tools: Read\n' 'Body.'; sed -i.bak 's/^description: .*/description: Use for fixtures.\\n\\n<example>\\nUser: hi\\n<\/example>/' "$tmp/exdesc.md"; rm -f "$tmp/exdesc.md.bak"
  check "positive: <example> inside the description -> fail" 1 "description embeds <example> blocks"
  mk longdesc.md 'tools: Read\n' 'Body.'; out=$(AGENT_DESC_WARN_CHARS=30 bash "$self" --dir "$tmp" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qF "WARN description size (longdesc.md)"; then echo "  ok   warning: description over the size threshold warns, exit 0"; else echo "  FAIL long description (rc=$rc out=$out)"; fail=1; fi
  rm -f "$tmp"/*.md
  mk yamlok.md 'tools: Read\n' 'Body.'; check "negative: valid frontmatter -> 0 strict-parse failures" 0 "0 of 1 agent file(s) fail a strict parse"
  check "no agent files -> fail" 1 "no agent files"
  mk good.md 'tools: Read, Grep\n' 'Body.'; check "negative: tools: grant passes" 0 "1 passed, 0 failed"
  mk legacy.md 'allowed-tools: Read, Grep\n' 'Body.'; check "positive: allowed-tools only -> fail" 1 "allowed-tools is ignored for agents"
  mk none.md '' 'Body.'; check "positive: no tools: -> fail" 1 "missing required field: tools"
  mk x-reviewer.md 'tools: Read, Grep, Glob, Write\nmemory: project\n' '## Success Metrics'; check "warning: reviewer grants Write, has memory, no disallowedTools" 0 "WARN reviewer least-privilege"
  mk y-reviewer.md 'tools: Read, Grep, Glob\ndisallowedTools: Write, Edit\n' '## Success Metrics'
  out=$(bash "$self" --dir "$tmp" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && ! printf '%s' "$out" | grep -q WARN; then echo "  ok   negative: read-only reviewer has no warning"; else echo "  FAIL read-only reviewer (rc=$rc out=$out)"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --selftest)
      selftest
      exit $?
      ;;
    --dir)
      AGENTS_DIR="$2"
      shift 2
      ;;
    --quiet)
      QUIET=true
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--dir <path>] [--quiet]" >&2
      exit 1
      ;;
  esac
done

AGENTS_DIR="$(cd "$AGENTS_DIR" && pwd)"

VALID_COLORS="green blue red orange yellow purple"
REQUIRED_FIELDS="name description model vibe color emoji"
DESC_WARN_CHARS="${AGENT_DESC_WARN_CHARS:-1000}"

passed=0
failed=0
# seen_names stored as newline-separated "name:filename" pairs (bash 3 compatible)
seen_names_list=""

# Extract frontmatter: content between first and second '---' line
get_frontmatter() {
  local file="$1"
  awk 'NR==1 && /^---/ { found=1; next }
       found && /^---/ { exit }
       found { print }' "$file"
}

# Extract a field value from frontmatter (handles quoted and unquoted values)
get_field() {
  local frontmatter="$1"
  local field="$2"
  echo "$frontmatter" | grep -E "^${field}:" | head -1 | sed "s/^${field}:[[:space:]]*//" | sed 's/^"//' | sed 's/"$//' | sed "s/^'//" | sed "s/'$//"
}

for agent_file in "$AGENTS_DIR"/*.md; do
  [[ -f "$agent_file" ]] || continue
  filename="$(basename "$agent_file")"
  agent_errors=()

  # ── 1. Verify frontmatter delimiters exist ────────────────────────────────
  delimiter_count=$(grep -c "^---" "$agent_file" 2>/dev/null || true)
  if [[ "$delimiter_count" -lt 2 ]]; then
    agent_errors+=("missing frontmatter delimiters (need at least two '---' lines)")
  fi

  frontmatter="$(get_frontmatter "$agent_file")"

  # ── 2. Required fields ────────────────────────────────────────────────────
  for field in $REQUIRED_FIELDS; do
    value="$(get_field "$frontmatter" "$field")"
    if [[ -z "$value" ]]; then
      agent_errors+=("missing required field: ${field}")
    fi
  done

  # ── 3. tools: must be present; allowed-tools: is not a grant for agents ───
  if echo "$frontmatter" | grep -qE "^allowed-tools:"; then
    agent_errors+=("allowed-tools is ignored for agents (the agent inherits ALL tools); declare tools: instead")
  elif ! echo "$frontmatter" | grep -qE "^tools:"; then
    agent_errors+=("missing required field: tools (an agent without tools: inherits ALL tools)")
  fi

  # ── 3b. Least privilege for review/audit agents (warning only) ────────────
  agent_warnings=()
  case "${filename%.md}" in
    *-reviewer|*-auditor|*-evaluator|*-checker|*-challenger)
      if echo "$frontmatter" | grep -E "^tools:" | grep -qE "(^|[^A-Za-z])(Write|Edit|MultiEdit|NotebookEdit)([^A-Za-z]|$)"; then
        agent_warnings+=("tools: grants Write/Edit to a review agent")
      fi
      dis_line=$(echo "$frontmatter" | grep -E "^disallowedTools:" | head -1)
      if ! { echo "$dis_line" | grep -q "Write" && echo "$dis_line" | grep -q "Edit"; }; then
        agent_warnings+=("missing disallowedTools: Write, Edit")
      fi
      if echo "$frontmatter" | grep -qE "^memory:"; then
        agent_warnings+=("declares memory: (re-grants Write/Edit for its memory directory)")
      fi
      ;;
  esac

  # ── 4. Valid color value ──────────────────────────────────────────────────
  color_value="$(get_field "$frontmatter" "color")"
  if [[ -n "$color_value" ]]; then
    color_valid=false
    for valid in $VALID_COLORS; do
      if [[ "$color_value" == "$valid" ]]; then
        color_valid=true
        break
      fi
    done
    if [[ "$color_valid" == false ]]; then
      agent_errors+=("invalid color '${color_value}' (valid: ${VALID_COLORS})")
    fi
  fi

  # ── 5. Emoji field must be non-empty ──────────────────────────────────────
  emoji_raw=$(echo "$frontmatter" | grep -E "^emoji:" | head -1 | sed 's/^emoji:[[:space:]]*//')
  emoji_stripped=$(echo "$emoji_raw" | tr -d '"'"'"' ')
  if [[ -z "$emoji_stripped" ]]; then
    agent_errors+=("emoji field is empty or missing an emoji character")
  fi

  # ── 6. Description length > 20 chars ─────────────────────────────────────
  desc_value="$(get_field "$frontmatter" "description")"
  desc_len=${#desc_value}
  if [[ "$desc_len" -le 20 ]]; then
    agent_errors+=("description too short (${desc_len} chars, need > 20)")
  fi
  # Descriptions are loaded into every session's agent list: examples go in the body, size stays bounded.
  if [[ "$desc_value" == *"<example>"* ]]; then
    agent_errors+=("description embeds <example> blocks; move them to a '## Dispatch examples' body section")
  fi
  if [[ "$desc_len" -gt "$DESC_WARN_CHARS" ]]; then
    agent_desc_warn="description is ${desc_len} chars (> ${DESC_WARN_CHARS}); keep triggers, move detail to the body"
  else
    agent_desc_warn=""
  fi

  # ── 7. reviewer/auditor filenames must have ## Success Metrics ────────────
  base_noext="${filename%.md}"
  if echo "$base_noext" | grep -qiE "(reviewer|auditor)"; then
    # Check body (after closing frontmatter ---)
    body=$(awk 'BEGIN{count=0} /^---/{count++; if(count==2){found=1; next}} found{print}' "$agent_file")
    if ! echo "$body" | grep -qE "^## Success Metrics"; then
      agent_errors+=("reviewer/auditor agent missing '## Success Metrics' section in body")
    fi
  fi

  # ── 8. Unique name check ──────────────────────────────────────────────────
  name_value="$(get_field "$frontmatter" "name")"
  if [[ -n "$name_value" ]]; then
    existing_owner=$(echo "$seen_names_list" | grep -E "^${name_value}:" | head -1 | sed "s/^${name_value}://")
    if [[ -n "$existing_owner" ]]; then
      agent_errors+=("duplicate name '${name_value}' (also used by ${existing_owner})")
    else
      seen_names_list="${seen_names_list}${name_value}:${filename}"$'\n'
    fi
  fi

  # ── Report ─────────────────────────────────────────────────────────────────
  if [[ ${#agent_errors[@]} -eq 0 ]]; then
    passed=$((passed + 1))
    if [[ "$QUIET" == false ]]; then
      echo "✅ $filename"
    fi
    for w in ${agent_warnings[@]+"${agent_warnings[@]}"}; do
      echo "   WARN reviewer least-privilege ($filename): $w"
    done
    [[ -n "$agent_desc_warn" ]] && echo "   WARN description size ($filename): $agent_desc_warn"
  else
    failed=$((failed + 1))
    echo "❌ $filename"
    for err in "${agent_errors[@]}"; do
      echo "   → $err"
    done
    for w in ${agent_warnings[@]+"${agent_warnings[@]}"}; do
      echo "   WARN reviewer least-privilege ($filename): $w"
    done
  fi
done

yaml_report=$(ls "$AGENTS_DIR"/*.md 2>/dev/null | yaml_frontmatter_errors)
if [[ "$yaml_report" == *PYYAML_MISSING* ]]; then
  echo "WARN yaml: strict frontmatter parse NOT RUN (python3 with PyYAML not found)"
else
  yaml_bad=$(printf '%s\n' "$yaml_report" | grep -vc '^PARSED ' || true)
  printf '%s\n' "$yaml_report" | awk -F'\t' '!/^PARSED / && NF > 1 { n = split($1, p, "/"); printf "   WARN yaml (%s): %s\n", p[n], $2 }'
  echo "YAML frontmatter (advisory): ${yaml_bad:-0} of $(printf '%s\n' "$yaml_report" | awk '/^PARSED /{print $2}') agent file(s) fail a strict parse"
fi

echo ""
if [[ $((passed + failed)) -eq 0 ]]; then
  echo "RESULT: no agent files found in ${AGENTS_DIR} (a lint that saw nothing fails)"
  exit 1
fi
echo "RESULT: ${passed} passed, ${failed} failed"

if [[ "$failed" -gt 0 ]]; then
  exit 1
fi
exit 0
