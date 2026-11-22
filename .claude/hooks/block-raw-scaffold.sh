#!/bin/bash
# PreToolUse (Bash) hook — blocks raw project-creation commands unless the call carries an explicit,
# per-command scaffold authorization.
#
# Why: new projects must come from the scaffold commands (standard structure, pinned versions, design
# system). Sub-agents run headlessly, cannot invoke slash commands, and used to fall back to a raw
# `flutter create`, skipping that structure.
#
# Authorization (the scaffold commands do this themselves in their first step):
#   CC_SCAFFOLD=<scaffold-command-name> <raw creator command>
#   e.g.  CC_SCAFFOLD=scaffold-flutter-app flutter create --org com.example my_app
# - It applies to that single command only: nothing persists between calls, there is no state file
#   to leave behind, and it is visible in the transcript.
# - The value must name the scaffold command that owns that technology; a Flutter marker does not
#   authorize `ng new`.
# - Every authorized call is appended to .claude/state/scaffold-audit.log (gitignored).
# Anything else that matches a raw creator is blocked (exit 2).
#
# Test: bash .claude/hooks/block-raw-scaffold.sh --selftest

LOG_DIR="${CLAUDE_PROJECT_DIR:-.}/.claude/state"

# <scaffold command>#<raw-creator ERE>#<label>#<technology>   ('#' is the field separator; the ERE may contain '|')
RULES=(
  'scaffold-flutter-app#flutter[[:space:]]+create#flutter create#Flutter / Dart'
  'scaffold-angular-app#(ng[[:space:]]+new|npx[[:space:]]+@angular/cli(@[^[:space:]]+)?[[:space:]]+new)#ng new / npx @angular/cli new#Angular'
  'scaffold-nestjs-api#(npx[[:space:]]+@nestjs/cli[[:space:]]+new|nest[[:space:]]+new)#npx @nestjs/cli new / nest new#NestJS'
  'scaffold-python-api#django-admin[[:space:]]+startproject#django-admin startproject#Python / Django'
  'scaffold-spring-api#(spring[[:space:]]+init|mvn[[:space:]]+archetype:generate)#spring init / mvn archetype:generate#Java / Spring Boot'
)

block() { # $1 matched label, $2 scaffold command, $3 tech
  cat >&2 <<EOF
BLOCKED: raw project creation detected ($1, $3).
New projects must come from the scaffold command. In the MAIN session run the Skill tool:
    skill: "$2"   args: "<project-name>"
The scaffold command itself runs the raw creator with an explicit marker:
    CC_SCAFFOLD=$2 $1 ...
Sub-agents cannot invoke slash commands: run the scaffold first, then hand them the scaffolded path.
See .claude/rules/leverage-patterns.md (Orchestrator Pre-Flight).
EOF
  exit 2
}

evaluate() { # $1 = command text. Exits 2 via block() on a violation; returns 0 otherwise.
  local cmd="$1" rule name rx label tech lead remaining
  for rule in "${RULES[@]}"; do
    IFS='#' read -r name rx label tech <<<"$rule"
    # A creator counts as a command whether or not VAR=value assignments precede it (FOO=1 flutter create ...).
    lead='(^|[;&|][[:space:]]*)([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*'
    # Replace each AUTHORIZED occurrence with a neutral token, then see whether a raw one is left.
    # '#' is the sed delimiter because the creator patterns contain '/'. If sed fails, keep the original
    # command so the raw check below still runs (fail closed, never fail open).
    remaining=$(printf '%s' "$cmd" | sed -E "s#(^|[;&|][[:space:]]*)CC_SCAFFOLD=${name}[[:space:]]+${rx}#\1AUTHORIZED_SCAFFOLD#g" 2>/dev/null) || remaining="$cmd"
    [ -n "$remaining" ] || remaining="$cmd"
    if printf '%s' "$remaining" | grep -qE "${lead}${rx}([[:space:]]|\$)"; then
      block "$label" "$name" "$tech"
    fi
    if [ "$remaining" != "$cmd" ]; then
      mkdir -p "$LOG_DIR" 2>/dev/null && printf '%s | %s | %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$name" "$(printf '%s' "$cmd" | head -c 200)" >> "$LOG_DIR/scaffold-audit.log" 2>/dev/null
    fi
  done
  # React Native has no scaffold command yet: warn only (stderr), never block.
  if printf '%s' "$cmd" | grep -qE '(npx[[:space:]]+react-native[[:space:]]+init|npx[[:space:]]+create-expo-app|npx[[:space:]]+@react-native-community/cli[[:space:]]+init)([[:space:]]|$)'; then
    echo "WARNING: raw React Native project creation; consider the mobile-developer skill first (no scaffold command exists)." >&2
  fi
  return 0
}

selftest() {
  local fail=0 t
  t=$(mktemp -d); LOG_DIR="$t"
  chk() { # label expected(0|2) command
    ( evaluate "$3" ) >/dev/null 2>&1; local rc=$?
    if [ "$rc" = "$2" ]; then echo "  ok   $1"; else echo "  FAIL $1 (exit $rc, want $2)"; fail=1; fi
  }
  chk "positive: bare flutter create is blocked"                         2 'flutter create my_app'
  chk "positive: chained flutter create is blocked"                      2 'cd /tmp && flutter create my_app'
  chk "positive: ng new / nest new / django / spring blocked"            2 'ng new web'
  chk "positive: npx @angular/cli@latest new blocked"                    2 'npx @angular/cli@latest new web'
  chk "negative: authorized angular scaffold is allowed"                 0 'CC_SCAFFOLD=scaffold-angular-app npx @angular/cli@latest new web --style=scss'
  chk "positive: npx @nestjs/cli new blocked"                            2 'npx @nestjs/cli new api'
  chk "positive: nest new blocked"                                       2 'nest new api'
  chk "positive: django-admin startproject blocked"                      2 'django-admin startproject site'
  chk "positive: mvn archetype:generate blocked"                         2 'mvn archetype:generate -DgroupId=a'
  chk "negative: authorized flutter create is allowed"                   0 'CC_SCAFFOLD=scaffold-flutter-app flutter create --org com.example my_app'
  chk "negative: authorized after cd is allowed"                         0 'cd /tmp/x && CC_SCAFFOLD=scaffold-flutter-app flutter create app'
  chk "negative: authorized nestjs is allowed"                           0 'CC_SCAFFOLD=scaffold-nestjs-api npx @nestjs/cli new api --skip-git'
  chk "adversarial: marker for the WRONG technology is blocked"          2 'CC_SCAFFOLD=scaffold-angular-app flutter create my_app'
  chk "adversarial: made-up marker value is blocked"                     2 'CC_SCAFFOLD=yes flutter create my_app'
  chk "adversarial: second raw create after an authorized one is blocked" 2 'CC_SCAFFOLD=scaffold-flutter-app flutter create a; flutter create b'
  chk "adversarial: marker on an unrelated command does not authorize"   2 'CC_SCAFFOLD=scaffold-flutter-app echo hi; flutter create b'
  chk "negative: unrelated flutter commands are untouched"               0 'flutter pub get && flutter test && flutter analyze'
  chk "negative: text that only mentions flutter create"                 0 'grep -rn "flutter create" docs'
  chk "negative: ordinary commands are untouched"                        0 'ls -la && git status'
  # the audit trail records authorized calls
  ( evaluate 'CC_SCAFFOLD=scaffold-flutter-app flutter create audited_app' ) >/dev/null 2>&1
  if grep -q 'scaffold-flutter-app | CC_SCAFFOLD' "$t/scaffold-audit.log" 2>/dev/null; then echo "  ok   authorized call is written to the audit log"; else echo "  FAIL audit log entry missing"; fail=1; fi
  rm -rf "$t"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi

INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('tool_input', {}).get('command', ''))
except Exception:
    print('')
" 2>/dev/null)
[ -z "$COMMAND" ] && exit 0
evaluate "$COMMAND"
exit 0
