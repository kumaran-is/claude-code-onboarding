# Claude Code Configuration Security Audit

Manual security checklist for auditing `.claude/` directory configurations. Run this before committing any changes to CLAUDE.md, settings.json, hooks, agent files, or MCP configs.

Adapted from AgentShield scan categories (github.com/affaan-m/agentshield), tailored to this workspace.

---

## When to Run This Audit

- After modifying `settings.json` (permissions, hooks, MCP servers)
- After adding or modifying a hook script in `.claude/hooks/`
- After adding or modifying an agent in `.claude/agents/`
- After modifying `CLAUDE.md` or any rules file in `.claude/rules/`
- Before committing `.claude/` changes to the repository

---

## 1 — settings.json Security Checks

### Bash Allow List
- [ ] No `Bash(*)` wildcard — wildcards grant unrestricted shell execution
- [ ] Each allowed command is the minimum scope needed (e.g., `Bash(git log *)` not `Bash(git *)`)
- [ ] No `Bash(eval *)` in allow list — evaluates arbitrary strings as shell code
- [ ] No `Bash(curl * | bash)` or pipe-to-shell patterns
- [ ] Sensitive destructive commands in `deny` list, not omitted from `allow`

**Current workspace allow list audit targets** (review each of these specifically):

| Pattern | Risk | Notes |
|---------|------|-------|
| `Bash(npm *)` | MEDIUM | `npm install <pkg>` could install malicious packages |
| `Bash(npx *)` | HIGH | `npx -y <pkg>` auto-installs and executes arbitrary packages |
| `Bash(curl *)` | HIGH | Can exfiltrate data or download malicious payloads |
| `Bash(wget *)` | HIGH | Same risk as curl |
| `Bash(git push *)` | MEDIUM | Broad — force push to any remote is allowed except `--force` to origin/main |
| `Bash(docker *)` | MEDIUM | `docker run` can execute arbitrary images |
| `Bash(python *)` / `Bash(python3 *)` | MEDIUM | Can execute arbitrary Python code from disk |
| `Bash(pip *)` | MEDIUM | Can install packages from PyPI including malicious ones |
| `Bash(cat *)` | LOW | Can read any file not in deny list |
| `Bash(find *)` | LOW | `find ... -exec` can execute arbitrary commands |
| `Bash(mv *)` / `Bash(cp *)` | LOW | Can overwrite sensitive files if path is not controlled |
| `Bash(git rebase *)` | LOW | `--exec` flag allows arbitrary command execution |

**Specific gaps to verify:**
- `Bash(npx *)` is broad — `npx -y <unknown>` bypasses confirmation; hook `pre-bash-guard.sh` does NOT currently block this
- `Bash(curl *)` is allowed but `curl | bash` is blocked by `pre-bash-guard.sh` — verify the regex covers all pipe variants
- `Bash(find *)` is allowed but `find ... -delete` is blocked by `pre-bash-guard.sh` — verify the regex covers `-exec rm` variants

### Deny List
- [x] `Bash(git push --force *)` in deny list ✓
- [x] `Bash(git push -f *)` in deny list ✓
- [x] `Bash(rm -rf /)` in deny list ✓
- [x] `Bash(rm -rf ~)` in deny list ✓
- [x] `Bash(rm -rf .)` in deny list ✓
- [x] `Bash(sudo *)` in deny list ✓
- [x] `Bash(eval *)` in deny list ✓
- [x] `Read(.env*)` variants in deny list ✓
- [x] `Read(**/*.key)` in deny list ✓
- [ ] Verify: `Bash(chmod 777 *)` in deny list ✓ (already present)
- [ ] Verify: `Bash(ssh *)` in deny list ✓ (already present)
- [ ] Consider adding: `Bash(git rebase * --exec *)` — executes arbitrary commands during rebase

### Ask List
- [x] `Bash(git reset *)` in ask list ✓
- [x] `Bash(git clean *)` in ask list ✓
- [x] `Bash(rm *)` in ask list ✓
- [ ] Consider adding: `Bash(docker run --privileged *)` — privileged containers break host isolation

### Dangerous Flags
- [ ] No `dangerouslyAllowAll: true` in any permission block (not present — ✓)
- [ ] No `--no-verify` skip flag patterns allowed in hooks

---

## 2 — CLAUDE.md and Rules Files

### Prompt Injection Risks
- [ ] No external URL content embedded directly into CLAUDE.md (could be poisoned)
- [ ] No `eval`, `exec`, or dynamic code execution instructions
- [ ] No instructions that unconditionally grant permissions to any requestor
- [ ] Verify: "approve the pending pairing" or "add me to the allowlist" — NEVER in CLAUDE.md (checked by `session-claudemd-scan.sh` at session start; `pre-prompt-injection.sh` does not scan CLAUDE.md content)

### Auto-Run Risks
- [ ] No instructions like "always run X without asking" for destructive operations
- [ ] No instructions that bypass the approval scope reference table in `core-behaviors.md`

### Hardcoded Secrets
- [ ] No API keys, tokens, passwords, or connection strings in CLAUDE.md
- [ ] No secrets in `.claude/rules/*.md` files
- [ ] Grep check: `grep -rn "sk-\|api_key\|password\|secret\|token" .claude/` → should return 0 sensitive hits (note: pattern words appear in hook scripts legitimately — scope this grep to `*.md` and `*.json` only)

---

## 3 — Hook Script Security

### Command Injection via Interpolation
- [ ] No unquoted variables used in shell commands: `$VAR` should be `"$VAR"` in shell context
- [ ] No user-controlled input passed directly to `eval`, `bash -c`, or similar
- [ ] No `curl ... | bash` or `wget ... | sh` in hooks (blocked by `pre-bash-guard.sh`)

### Data Exfiltration
- [ ] Hooks do not send data to external URLs (no `curl https://external.com` with Claude output)
- [ ] Hooks do not write Claude's response content to world-readable locations
- [ ] Hook output (stdout) is used only for blocking/passing the tool call, not data export
- [ ] Audit log files (`.claude/secrets-detected.log`, etc.) are gitignored

### Silent Error Suppression
- [ ] No `2>/dev/null` without logging the error elsewhere
- [ ] All hooks exit with explicit exit code (0=allow, 1=block with message, 2=hard block)
- [ ] No bare `|| true` that masks failures in security-critical paths

### Known Pattern: `output-secrets-scanner.sh`
- This hook exits 0 always (warns but never blocks) — by design. Verify this is intentional for every new hook added with similar pattern.
- The secrets-detected.log must be gitignored — verify: `cat .gitignore | grep secrets-detected`

**Current workspace hooks** (audit each when modified):

| Hook | Trigger | Purpose | Audit Focus |
|------|---------|---------|-------------|
| `pre-bash-guard.sh` | PreToolUse: Bash | Blocks destructive commands | Regex coverage for new attack patterns |
| `pre-prompt-injection.sh` | PreToolUse: Bash\|Write\|Edit\|WebFetch | Blocks escape sequences and NUL bytes; advises on injection phrases | Advisory-only phrase list; no false blocks on grep/tests/commits (`--selftest`) |
| `pre-unicode-injection.sh` | PreToolUse: Edit\|Write | Blocks unicode/homoglyph injection | Coverage of new unicode attack vectors |
| `pre-edit-protect-sensitive.sh` | PreToolUse: Write\|Edit | Blocks writes to sensitive files | Sensitive file pattern completeness |
| `pre-lessons-injector.sh` | PreToolUse: Agent | Injects lessons into sub-agents | Verify no sensitive data in lessons.md |
| `block-raw-scaffold.sh` | PreToolUse: Bash | Blocks `flutter create`, `ng new` etc. | Pattern list for new scaffold commands |
| `output-secrets-scanner.sh` | PostToolUse: Bash\|Read\|WebFetch | Scans output for secrets | Pattern list for new secret formats |
| `post-edit-secrets-scan.sh` | PostToolUse: Write\|Edit | Scans written files for secrets | Pattern list completeness |
| `post-edit-ai-patterns.sh` | PostToolUse: Write\|Edit | Detects anti-patterns in AI-generated code | Pattern list currency |
| `post-edit-typecheck.sh` | PostToolUse: Write\|Edit | Type checking | Does not exfiltrate code |
| `post-edit-format.sh` | PostToolUse: Write\|Edit | Code formatting | Does not exfiltrate code |
| `post-validate-structured-data.sh` | PostToolUse: Write\|Edit | Validates JSON/YAML/TOML | Does not execute content |
| `prompt-secret-scan.sh` | UserPromptSubmit | Scans user prompts for secrets | Pattern completeness |
| `session-claudemd-scan.sh` | SessionStart | Scans CLAUDE.md for injection | Pattern completeness |
| `session-start.sh` | SessionStart | Session initialization | Verify no network calls |
| `stop-secret-scan.sh` | Stop | Final secret scan | Pattern completeness |
| `stop-lessons-reminder.sh` | Stop | Lessons reminder | Informational only |
| `stop-ralph-loop.sh` | Stop | Ralph loop cleanup | Verify no orphan processes |
| `stop-notify-completion.sh` | Stop | Completion notification | Verify notification target is local only |

---

## 4 — MCP Server Configuration

### Supply Chain Risks
- [ ] No `npx -y <unknown-package>` — `-y` auto-installs without confirmation
- [ ] All MCP server packages are from verified publishers (check npm registry)
- [ ] Pin MCP server versions where possible (e.g., `@playwright/mcp@0.0.26` not `@playwright/mcp@latest`)

### Hardcoded Secrets in MCP Config
- [ ] No API keys hardcoded in MCP server `env:` blocks in settings
- [ ] Secrets passed via environment variable references, not literal values
- [ ] No secret in `args`, not even as a `${VAR}` reference: it is expanded into argv, which `ps` shows to any local user. Pass it in `env` (most servers read a named env var; check the server's source)
- [ ] No deprecated or archived server package (`npm view <pkg> deprecated` prints nothing). Detail: [mcp-security.md §4](mcp-security.md#4-mcp-client-configuration-mcpjson-settings)

### Unnecessary Access
- [ ] Each MCP server has the minimum required permissions
- [ ] MCP servers that access the filesystem are scoped to specific paths

**Current workspace MCP server allow-list** (from `settings.json` — verify each is still needed):

| Permission Pattern | MCP Server | Risk Level | Notes |
|-------------------|-----------|-----------|-------|
| `mcp__chrome-devtools__*` | Chrome DevTools | MEDIUM | Wildcard — all Chrome DevTools tools allowed; can control browser |
| `mcp__firebase__*` | Firebase MCP | HIGH | Wildcard — includes write operations (create project, deploy rules) |
| `mcp__dart-mcp-server__*` | Dart MCP | MEDIUM | Wildcard — includes `launch_app`, `run_tests`, `create_project` |
| `mcp__angular-cli__*` | Angular CLI MCP | LOW | Read-heavy; wildcard still allows any Angular CLI operation |
| `mcp__docker__*` | Docker MCP | HIGH | Wildcard — includes container execution operations |
| `mcp__Claude_in_Chrome__*` | Claude in Chrome | MEDIUM | Wildcard — browser automation |
| `mcp__Claude_Preview__*` | Claude Preview | MEDIUM | Wildcard — unknown scope; verify what tools this exposes |
| `mcp__context7__*` | Context7 | LOW | Documentation lookup only |
| `mcp__langchain-docs__*` | LangChain Docs | LOW | Documentation lookup only |
| `mcp__xcodebuild__*` | XcodeBuild MCP | MEDIUM | Wildcard — includes device/simulator control, app launch |
| `mcp__mcp-registry__*` | MCP Registry | MEDIUM | Can discover and potentially install new MCP servers |
| `mcp__voicemode__converse` | Voicemode | LOW | Specific tool only — not wildcard |
| `mcp__voicemode__service` | Voicemode | LOW | Specific tool only — not wildcard |

**High-priority review:** `mcp__firebase__*` and `mcp__docker__*` are wildcards on servers with write/execution capabilities. Consider scoping to specific tools needed.

---

## 5 — Agent Files (`.claude/agents/*.md`)

### Unrestricted Tool Access
- [ ] No agent has `allowed-tools: "*"` or equivalent wildcard
- [ ] Agents that only READ have no Write/Edit/Bash tools
- [ ] Review agents have read-only tools; implementation agents have write tools

### Prompt Injection Surface
- [ ] Agent descriptions do not include instructions that could be overridden by malicious task input
- [ ] Agent system prompts do not contain `{{user_input}}` style interpolation
- [ ] No agent unconditionally trusts content from external sources (web fetch results, file contents)

### Model Specification
- [ ] Every agent specifies a `model:` field (missing = inherits parent, could be unintended)
- [ ] High-privilege agents (those with Bash/Write access) use explicit model pinning

---

## 6 — Quick Grep Audit Commands

Run these before committing any `.claude/` changes:

```bash
# Secrets in config files (scope to md and json only to avoid false positives from hook scripts)
grep -rn "sk-\|api_key\s*=\|password\s*=\|ANTHROPIC_API_KEY\s*=" .claude/ \
  --include="*.md" --include="*.json"

# Wildcard Bash allow
grep -n "Bash(\*)" .claude/settings.json

# Wildcard MCP allow (new wildcards added)
grep -n "mcp__.*\\\*" .claude/settings.json

# npx without version pin in MCP configs
grep -rn "npx -y\|npx.*latest" .claude/settings.json

# eval usage in hooks
grep -rn "\beval\b" .claude/hooks/

# Unquoted variables in hooks (potential injection — review each hit manually)
grep -rn '\$[A-Z_][A-Z_0-9]*[^"]' .claude/hooks/*.sh 2>/dev/null | grep -v "^#" | head -30

# Hooks making external network calls
grep -rn "curl\|wget" .claude/hooks/*.sh | grep -v "pre-bash-guard\|# "

# Verify secrets-detected.log is gitignored
grep "secrets-detected" .gitignore || echo "WARNING: .claude/secrets-detected.log may not be gitignored"
```

---

## Severity Reference

| Finding | Severity | Action |
|---------|----------|--------|
| Hardcoded secret in any `.claude/` file | CRITICAL | Remove immediately, rotate secret, audit git history |
| `Bash(*)` wildcard in allow list | CRITICAL | Replace with specific command patterns |
| `mcp__<server>__*` wildcard on write-capable server (firebase, docker) | HIGH | Scope to specific tools needed |
| Command injection in hook (unquoted `$VAR` in shell exec context) | HIGH | Quote all variables |
| `npx -y <unknown>` in MCP config | HIGH | Pin version or remove |
| Hook makes external network call with tool output | HIGH | Remove exfiltration path |
| `dangerouslyAllowAll: true` in permissions | CRITICAL | Remove immediately |
| Silent error suppression in hook (`2>/dev/null` with no log) in security-critical path | MEDIUM | Add error logging before suppression |
| Agent with no `model:` spec and Bash/Write access | MEDIUM | Pin model explicitly |
| Audit log file not gitignored | MEDIUM | Add to `.gitignore` |
| External URL embedded in CLAUDE.md or rules file | LOW | Replace with local documentation |
| Hook pattern list stale (new attack vectors not covered) | LOW | Update pattern lists quarterly |
