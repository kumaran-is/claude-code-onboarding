#!/usr/bin/env bash
# post-edit-python-log-pii-advisory.sh — PostToolUse (Write | Edit), *.py only, check-only.
#
# Flags exception TEXT reaching a log call in the edited file: `str(exc)` / `repr(exc)` / f"{exc}" /
# `exc.args` / passing `exc` itself, `exc_info=...`, and `logger.exception(...)`. Exception messages
# carry request data (validation errors echo the body, provider errors echo the prompt), so they leak
# PII into logs. The fix is the one sanctioned helper `log_exception(logger, event, exc, **ids)`:
# `.claude/skills/deployment-ci-cd/reference/python-observability.md` section 2. The AST logic below is
# the gate published there (keep the two in sync); `type(exc).__name__` is allowed.
#
# Deterministic (AST, not regex), but advisory: an infrastructure-only site may be legitimate. Mark such
# a line with `# log-pii: ok <reason>` to silence it. Limits (documented, same as the gate): only names
# bound by `except ... as name` are tracked; `msg = str(exc); log.error(msg)` is not seen.
# Skips tests, conftest.py, migrations and virtualenvs.
#
# Contract (.claude/rules/hook-and-gate-authoring.md): always exit 0; advisory delivered as
# hookSpecificOutput.additionalContext; fails open without jq/python3 (noted once per day). A file
# that python3 cannot parse is reported once per day with the interpreter version (an older python3
# cannot parse 3.14-only syntax such as unparenthesised `except A, B:`).
# Test: bash .claude/hooks/post-edit-python-log-pii-advisory.sh --selftest
set -uo pipefail

MAX_FINDINGS=8

PY_CHECK='
import ast, sys
LOG = {"debug", "info", "warning", "warn", "error", "critical", "exception", "log", "msg"}
path = sys.argv[1]
src = open(path, encoding="utf-8", errors="replace").read()
try:
    tree = ast.parse(src, path)
except SyntaxError:
    print("PARSE_ERROR %d.%d" % sys.version_info[:2]); sys.exit(0)
lines = src.splitlines()
names = {n.name for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.name}
out = []
for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
    f = call.func
    if not (isinstance(f, ast.Attribute) and f.attr in LOG):
        continue
    if 0 < call.lineno <= len(lines) and "log-pii: ok" in lines[call.lineno - 1]:
        continue
    if f.attr == "exception":
        out.append("%d: .exception() logs the message and traceback" % call.lineno)
    for kw in call.keywords:
        if kw.arg == "exc_info":
            out.append("%d: exc_info= attaches the exception text" % call.lineno)
    for arg in [*call.args, *(k.value for k in call.keywords if k.arg != "exc_info")]:
        safe = {id(a) for c in ast.walk(arg) if isinstance(c, ast.Call)
                and isinstance(c.func, ast.Name) and c.func.id == "type" for a in c.args}
        hit = next((n.id for n in ast.walk(arg)
                    if isinstance(n, ast.Name) and n.id in names and id(n) not in safe), None)
        if hit:
            out.append("%d: exception %r passed to a log call" % (call.lineno, hit))
            break
print("\n".join(sorted(set(out), key=lambda s: int(s.split(":")[0]))))
'

note_once() { # $1 key, $2 message -> prints message once per day per key
  local marker
  marker="${TMPDIR:-/tmp}/claude-log-pii-advisory-$1-$(date +%Y%m%d 2>/dev/null || echo x)"
  [ -e "$marker" ] && return 0
  : > "$marker" 2>/dev/null || true
  printf '%s' "$2"
}

skip_path() {
  case "$1" in
    *.py) ;;
    *) return 0 ;;
  esac
  case "$1" in
    */.venv/*|*/venv/*|*/site-packages/*|*/node_modules/*|*/alembic/versions/*|*/migrations/versions/*) return 0 ;;
    */tests/*|*/test/*|*/conftest.py|conftest.py|*/test_*.py|test_*.py|*_test.py) return 0 ;;
  esac
  return 1
}

emit() { jq -n --arg m "$1" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'; }

run_hook() {
  local input file result msg
  input=$(cat)
  command -v jq >/dev/null 2>&1 || return 0
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // ""' 2>/dev/null) || file=""
  [ -n "$file" ] && [ -f "$file" ] || return 0
  skip_path "$file" && return 0
  if ! command -v python3 >/dev/null 2>&1; then
    msg=$(note_once nopython "log-PII advisory: python3 not found, edited Python files are NOT checked for exception text in log calls.")
    [ -n "$msg" ] && emit "$msg"
    return 0
  fi
  result=$(python3 -c "$PY_CHECK" "$file" 2>/dev/null) || return 0
  [ -n "$result" ] || return 0
  case "$result" in
    "PARSE_ERROR "*)
      msg=$(note_once parse "log-PII advisory: python3 ${result#PARSE_ERROR } could not parse $file, so it was NOT checked for exception text in log calls (syntax error, or syntax newer than this interpreter).")
      [ -n "$msg" ] && emit "$msg"
      return 0 ;;
  esac
  result=$(printf '%s\n' "$result" | head -"$MAX_FINDINGS")
  emit "Log-PII check (advisory) in $file: exception text reaches a log call, which leaks request data (PII, prompts) into logs.
$result
Use log_exception(logger, \"event\", exc, <non-PII ids>) (python-observability.md section 2): it logs error_type only. If a site is infrastructure-only with no user input, mark the line '# log-pii: ok <reason>'."
  return 0
}

selftest() {
  local self fail=0 tmp out rc
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   control 0: parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1 || { echo "  FAIL jq and python3 required"; return 1; }
  tmp=$(mktemp -d) || return 1
  run() { printf '{"tool_input":{"file_path":"%s"}}' "$1" | TMPDIR="$tmp" /bin/bash "$self" 2>"$tmp/err"; }
  expect_has() {
    if printf '%s' "$2" | jq -e --arg n "$3" '.hookSpecificOutput.hookEventName == "PostToolUse" and (.hookSpecificOutput.additionalContext | contains($n))' >/dev/null 2>&1 && [ ! -s "$tmp/err" ]
    then echo "  ok   positive: $1"; else echo "  FAIL $1 (got: $2 err: $(cat "$tmp/err"))"; fail=1; fi
  }
  expect_silent() { if [ -z "$2" ] && [ ! -s "$tmp/err" ]; then echo "  ok   negative: $1"; else echo "  FAIL $1 (got: $2)"; fail=1; fi; }

  mkdir -p "$tmp/app" "$tmp/tests"
  cat > "$tmp/app/bad.py" <<'PY'
import logging
logger = logging.getLogger(__name__)
def call():
    try:
        pass
    except ValueError as exc:
        logger.error("llm_call_failed", error=str(exc))
        logger.warning(f"failed: {exc}")
        logger.error("failed", exc_info=True)
        logger.exception("failed")
PY
  out=$(run "$tmp/app/bad.py")
  expect_has "str(exc) in a log call" "$out" "7: exception 'exc' passed to a log call"
  expect_has "f-string with exc" "$out" "8: exception 'exc'"
  expect_has "exc_info=True" "$out" "9: exc_info="
  expect_has "logger.exception()" "$out" "10: .exception()"
  cat > "$tmp/app/good.py" <<'PY'
import logging
logger = logging.getLogger(__name__)
def call(request_id: str) -> None:
    try:
        pass
    except ValueError as exc:
        logger.error("llm_call_failed", error_type=type(exc).__name__, request_id=request_id)
        logger.error("pool_reset", detail=str(exc))  # log-pii: ok infrastructure error, no user input
        raise
PY
  out=$(run "$tmp/app/good.py"); expect_silent "type(exc).__name__ and an allow-marked line" "$out"
  cp "$tmp/app/bad.py" "$tmp/tests/test_bad.py"
  out=$(run "$tmp/tests/test_bad.py"); expect_silent "test file skipped" "$out"
  printf 'logger.error(str(exc))\n' > "$tmp/app/notes.md"
  out=$(run "$tmp/app/notes.md"); expect_silent "non-Python file skipped" "$out"
  printf 'def broken(:\n' > "$tmp/app/broken.py"
  out=$(run "$tmp/app/broken.py"); expect_has "unparseable file reported, not silently clean" "$out" "could not parse"
  out=$(run "$tmp/app/broken.py"); expect_silent "parse note throttled (once per day)" "$out"
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
