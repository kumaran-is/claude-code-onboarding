#!/usr/bin/env bash
# session-mcp-governance.sh — SessionStart: MCP supply-chain / tamper guard.
#
# WHY: .mcp.json wires MCP servers that can reach your DB, cloud, browser, payments, network,
# etc. skill-triggers.md §P0 ("Scan Before Trust") + its trusted-MCP table say to vet a newly
# added server before trusting it — but that was PROSE, not enforced. This hook enforces it:
# it warns at session start if the active MCP set drifts from the approved allowlist, or if
# .mcp.json changed since it was last approved (the CVE-2025-54135/54136 post-approval-tamper
# class). Advisory only — always exits 0 (a SessionStart blocker would lock you out on any
# legit change).
#
# jq-only (no yq dep). Hashes the CANONICAL jq form so cosmetic reformatting ≠ tamper.
# Re-approve after a REVIEWED change:  bash .claude/hooks/session-mcp-governance.sh --approve
#
# NB: do NOT read stdin. SessionStart sends JSON on stdin, but this hook doesn't use it, and
# draining with `cat` blocks forever when stdin is an open non-tty pipe (e.g. under a wrapper).
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
MCP_JSON="$ROOT/.mcp.json"
ALLOWLIST="$ROOT/.claude/mcp-allowlist.txt"
HASHFILE="$ROOT/.claude/mcp-config.sha256"

[ -f "$MCP_JSON" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then jq -S -c . "$1" 2>/dev/null | sha256sum | awk '{print $1}'
  else jq -S -c . "$1" 2>/dev/null | shasum -a 256 | awk '{print $1}'; fi
}

# ── --approve: snapshot current .mcp.json as the approved baseline ────────────
if [ "${1:-}" = "--approve" ]; then
  jq -r '.mcpServers // {} | keys[]' "$MCP_JSON" 2>/dev/null | sort > "$ALLOWLIST"
  sha256_of "$MCP_JSON" > "$HASHFILE"
  echo "Approved MCP baseline written:"
  echo "  $ALLOWLIST  ($(wc -l < "$ALLOWLIST" | tr -d ' ') servers)"
  echo "  $HASHFILE   ($(cat "$HASHFILE"))"
  exit 0
fi

ACTIVE=$(jq -r '.mcpServers // {} | keys[]' "$MCP_JSON" 2>/dev/null | sort)
[ -z "$ACTIVE" ] && exit 0

WARN=0
MSG=""
# stderr of an exit-0 hook is never delivered, so findings are collected and emitted as JSON at the end.
note() { MSG="${MSG}${1}"$'\n'; }

# ── Check 1: allowlist drift ─────────────────────────────────────────────────
if [ ! -f "$ALLOWLIST" ]; then
  note "⚠️  MCP governance: no approved allowlist yet ($ALLOWLIST)."
  note "      Vet your servers (skill-triggers.md §P0), then: bash .claude/hooks/session-mcp-governance.sh --approve"
  WARN=1
else
  UNAPPROVED=$(comm -23 <(printf '%s\n' "$ACTIVE") <(sort "$ALLOWLIST"))
  REMOVED=$(comm -13 <(printf '%s\n' "$ACTIVE") <(sort "$ALLOWLIST"))
  if [ -n "$UNAPPROVED" ]; then
    note "⚠️  MCP governance: UNAPPROVED server(s) active in .mcp.json — vet before trusting:"
    note "$(printf '      - %s\n' $UNAPPROVED)"
    note "      (skill-triggers.md §P0 scan, then: bash .claude/hooks/session-mcp-governance.sh --approve)"
    WARN=1
  fi
  [ -n "$REMOVED" ] && note "MCP governance: approved server(s) no longer active: $(echo $REMOVED | tr '\n' ' ')"
fi

# ── Check 2: config integrity (post-approval tamper) ─────────────────────────
if [ -f "$HASHFILE" ]; then
  CUR=$(sha256_of "$MCP_JSON")
  STORED=$(tr -dc 'a-f0-9' < "$HASHFILE")
  if [ -n "$CUR" ] && [ -n "$STORED" ] && [ "$CUR" != "$STORED" ]; then
    note "⚠️  MCP governance: .mcp.json CHANGED since last approval (content hash mismatch)."
    note "      Review the diff for unauthorized server/command/env/url edits (CVE-2025-54135/54136 class)."
    note "      If the change is legitimate: bash .claude/hooks/session-mcp-governance.sh --approve"
    WARN=1
  fi
fi

LOGFILE="$ROOT/.claude/mcp-governance-detected.log"
if [ "$WARN" -eq 1 ]; then
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "?")
  printf '[%s] MCP governance warning emitted\n' "$ts" >> "$LOGFILE" 2>/dev/null || true
fi

if [ -n "$MSG" ]; then
  jq -n --arg m "$MSG" '{systemMessage:$m, hookSpecificOutput:{hookEventName:"SessionStart", additionalContext:$m}}'
fi

exit 0
