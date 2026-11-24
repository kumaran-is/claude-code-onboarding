#!/usr/bin/env bash
# check-mcp-register.sh — the MCP risk register and .mcp.json must describe the same servers.
#
# Register: the table in `.claude/skills/security-reviewer/reference/mcp-security.md` §7. The first cell
# of each row names one or more servers in backticks; `*` is a glob (`gcp-*`). Checked both ways:
#   every .mcp.json server matches a register name    (a new server without a reviewed risk entry)
#   every register name matches a .mcp.json server     (a stale row for a server that was removed)
# Which servers are APPROVED stays with .claude/mcp-allowlist.txt + session-mcp-governance.sh; this only
# keeps the human-readable risk register honest.
#
# Usage: bash .claude/scripts/check-mcp-register.sh [--selftest]    (exit 0 clean, 1 drift or no input)
set -uo pipefail

check() { # $1 .mcp.json, $2 register markdown -> findings on stdout, exit status
  python3 - "$1" "$2" <<'PY'
import fnmatch, json, re, sys
mcp_path, reg_path = sys.argv[1], sys.argv[2]
try:
    servers = sorted(json.load(open(mcp_path)).get("mcpServers", {}))
except (OSError, ValueError) as exc:
    print(f"FAIL cannot read {mcp_path}: {exc}"); sys.exit(1)
try:
    text = open(reg_path).read()
except OSError as exc:
    print(f"FAIL cannot read {reg_path}: {exc}"); sys.exit(1)
sec = re.search(r"^## 7\..*?(?=^## |\Z)", text, re.S | re.M)
if not sec:
    print(f"FAIL no '## 7.' risk-register section in {reg_path}"); sys.exit(1)
names = []
for line in sec.group(0).splitlines():
    if not line.startswith("| `"):
        continue
    first = line.split("|")[1]
    names += [n for n in re.findall(r"`([^`]+)`", first) if re.fullmatch(r"[a-z0-9*][a-z0-9*_-]*", n)]
if not servers or not names:
    print(f"FAIL nothing to compare: {len(servers)} server(s) in {mcp_path}, {len(names)} register name(s)"); sys.exit(1)
bad = 0
for s in servers:
    if not any(fnmatch.fnmatchcase(s, n) for n in names):
        print(f"MISSING  .mcp.json server '{s}' has no row in the risk register"); bad += 1
for n in names:
    if not any(fnmatch.fnmatchcase(s, n) for s in servers):
        print(f"STALE    register row '{n}' matches no .mcp.json server"); bad += 1
print(f"check-mcp-register: {len(servers)} server(s), {len(names)} register name(s); {bad} finding(s)")
sys.exit(1 if bad else 0)
PY
}

selftest() {
  local tmp fail=0 out rc
  bash -n "${BASH_SOURCE[0]}" 2>/dev/null && echo "  ok   parses (bash -n)" || { echo "  FAIL does not parse"; return 1; }
  tmp=$(mktemp -d) || return 1
  printf '{"mcpServers":{"alpha":{},"gcp-run":{},"gcp-iam":{}}}' > "$tmp/mcp.json"
  printf '# x\n## 7. Register\n| Server | Status |\n|---|---|\n| `alpha` (npx alpha@1.0.0) | ok |\n| `gcp-*` (`.mcp.json`: x) | elevated |\n## 8. Next\n| `ghost` | not in section 7 |\n' > "$tmp/reg.md"
  out=$(check "$tmp/mcp.json" "$tmp/reg.md"); rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qF "0 finding(s)"; then echo "  ok   negative: names, globs and multi-name cells match; '.mcp.json' and other sections ignored"
  else echo "  FAIL clean register: rc=$rc $out"; fail=1; fi
  printf '{"mcpServers":{"alpha":{},"gcp-run":{},"beta":{}}}' > "$tmp/mcp.json"
  out=$(check "$tmp/mcp.json" "$tmp/reg.md"); rc=$?
  if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qF "MISSING  .mcp.json server 'beta'"; then echo "  ok   positive: a configured server without a register row fails"
  else echo "  FAIL missing row not caught: rc=$rc $out"; fail=1; fi
  printf '{"mcpServers":{"alpha":{}}}' > "$tmp/mcp.json"
  out=$(check "$tmp/mcp.json" "$tmp/reg.md"); rc=$?
  if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qF "STALE    register row 'gcp-*'"; then echo "  ok   positive: a register row for a removed server fails"
  else echo "  FAIL stale row not caught: rc=$rc $out"; fail=1; fi
  printf '# no section\n' > "$tmp/reg.md"
  out=$(check "$tmp/mcp.json" "$tmp/reg.md"); rc=$?
  if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qF "no '## 7.'"; then echo "  ok   positive: a missing register section fails (never a vacuous pass)"
  else echo "  FAIL missing section passed: rc=$rc $out"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
check "$ROOT/.mcp.json" "$ROOT/.claude/skills/security-reviewer/reference/mcp-security.md"
