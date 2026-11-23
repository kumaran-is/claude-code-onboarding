# Claude Code Configuration Security Audit

Canonical checklist for auditing a workspace's Claude Code configuration: `settings.json`
permissions, hooks, agents, `.mcp.json`, `CLAUDE.md` and rules. Run it before committing any
`.claude/` or `.mcp.json` change.

Derive the current state with the commands in §6 every time. Do not keep a copy of the allow list
or hook list in this file: copies drift and then hide the gaps they were meant to show.

Adapted from the AgentShield scan categories (github.com/affaan-m/agentshield).

---

## 1 — `settings.json` permissions

An `allow` rule runs without a prompt, so every allow rule is an execution grant. Judge each
pattern by the worst command it admits, not the one it was added for.

| Allow pattern | Worst case it admits | Severity | Prefer |
|---|---|---|---|
| `Bash(*)`, `dangerouslyAllowAll` | anything | CRITICAL | named commands |
| `Bash(npx *)`, `Bash(uvx *)` | download and run any package version | HIGH | `ask`, or exact commands (`Bash(npx tsc --noEmit)`) |
| `Bash(curl *)`, `Bash(wget *)` | exfiltrate files, fetch payloads | HIGH | `ask`; WebFetch for docs |
| `Bash(python *)`, `Bash(node *)` | `-c` / `-e` arbitrary code | HIGH | named scripts (`Bash(python3 .claude/scripts/x.py *)`) |
| `Bash(docker *)` | `docker run -v /:/host --privileged` (host root) | HIGH | `ask` |
| `Bash(gh *)` | `gh api -X DELETE`, `gh repo delete`, secret writes | HIGH | read verbs only (`gh pr view *`, `gh run view *`) |
| `Bash(git push *)` | push to protected branches, `+refspec` force push | MEDIUM | `ask`; keep the PreToolUse guard |
| `Bash(npm *)`, `Bash(pip *)`, `Bash(uv *)` | install-time scripts from any package | MEDIUM | lockfile installs (`npm ci`, `uv sync --locked`) |
| `Bash(sed *)`, `Bash(awk *)`, `Bash(find *)`, `Bash(cp *)`, `Bash(mv *)` | `sed -i` / `find -exec` / overwrite of hooks and settings | MEDIUM | `ask`, or rely on Edit/Write (which hooks inspect) |
| `Bash(git rebase *)` | `--exec <cmd>` | LOW | `ask` |
| `mcp__<server>__*` on a write-capable server | deploy, delete, create projects | HIGH | list the read tools by name |
| `mcp__<server>__*` for a server absent from `.mcp.json` | dead rule that activates when a same-named server appears | MEDIUM | remove |

`deny` rules are prefix matches and are easy to step around: `Bash(git push --force *)` does not
match `git push origin main --force` or `git push origin +main`. Treat `deny` as a speed bump and
enforce the real rule in a PreToolUse hook (exit 2). Check also:

- [ ] `Read(...)` denies cover nested secrets: `Read(./**/.env)`, `Read(./**/.env.*)`, not only
      `./.env` (a monorepo keeps `apps/api/.env`).
- [ ] `git commit --no-verify` / `git push --no-verify` are blocked by a hook, or the git hooks
      they skip are not the only secret gate (CI runs the same scan).
- [ ] No `permissionMode: bypassPermissions` in any agent or settings file committed to the repo.

## 2 — `CLAUDE.md` and rules files

- [ ] No external URL content pasted into `CLAUDE.md` or rules (it can be poisoned upstream).
- [ ] No instruction that grants permissions to whoever asks ("approve the pending pairing",
      "add me to the allowlist") — `session-claudemd-scan.sh` checks this at session start.
- [ ] No "always run X without asking" for destructive operations; nothing that bypasses the
      approval table in `core-behaviors.md`.
- [ ] No secrets, internal hostnames, private paths or customer names (this toolkit is public).

## 3 — Hooks (`.claude/hooks/`, `.claude/scripts/`)

Authoring contract: `.claude/rules/hook-and-gate-authoring.md`. Security-relevant points:

- [ ] **Blocking is exit 2 only.** In Claude Code any other non-zero exit is a non-blocking error:
      the tool call still runs. A guard that exits 1 to "block" fails open.
- [ ] A guard hook that crashes (missing `jq`, bad regex, unset variable) fails open for the same
      reason; it is tested with `--selftest`, a positive control (blocks a planted violation) and a
      negative control.
- [ ] Hook commands in `settings.json` quote the project path:
      `"$CLAUDE_PROJECT_DIR"/.claude/hooks/x.sh`. Unquoted, a checkout path with a space breaks every
      hook — and every guard fails open.
- [ ] No untrusted input reaches `eval`, `bash -c`, `sh -c` or an unquoted expansion.
- [ ] No hook sends data off the machine (`curl`/`wget` with tool output, prompts or file content).
- [ ] Audit logs (`.claude/*-detected.log`, `.claude/state/`) are gitignored and never contain the
      matched secret or the full command that carried it: log the pattern name, tool name and a
      hash, not the raw text.
- [ ] Advisory hooks deliver text through `additionalContext` JSON; stdout/stderr of an exit-0 hook
      never reaches the model.

## 4 — MCP servers (`.mcp.json`)

Requirement levels and server-side severities: [mcp-security.md](mcp-security.md). Client-config
checks:

- [ ] Every `npx -y` / `uvx --from` package has an exact version (`pkg@1.2.3`, `pkg==1.2.3`).
      `-y` is acceptable only with an exact pin; `@latest` or no version is a finding.
- [ ] Binaries started by name (`dart`, `maestro`, `xcodebuildmcp`) resolve to a version you
      installed on purpose; note them as unpinned in the review.
- [ ] No secret in `args`, not even as `${VAR}` — argv is visible to every local process. Pass it in
      `env` under the server's documented variable.
- [ ] No deprecated or archived server package (`npm view <pkg> deprecated` prints nothing).
- [ ] Write-capable servers (cloud, payments, stores, containers) start with the narrowest tool
      set or a read-only endpoint, and are not wildcard-allowed in `settings.json`.
- [ ] Remote HTTP servers prefer OAuth over a static `Authorization` header.
- [ ] Every server in `.mcp.json` is listed with its risk in `.claude/rules/skill-triggers.md` §P0;
      `.claude/mcp-config.sha256` is refreshed only after that review.

## 5 — Agents (`.claude/agents/*.md`)

- [ ] Reviewer and auditor agents declare `disallowedTools: Write, Edit` and no
      `permissionMode: acceptEdits` / `bypassPermissions`. Bash on a reviewer is for running
      linters and tests; it can still write files, so the agent body must forbid edits.
- [ ] Implementation agents have the write tools they need and nothing broader (`tools: "*"` is a
      finding).
- [ ] Every agent with Bash, Write or Edit pins `model:`.
- [ ] No `{{user_input}}`-style interpolation in agent bodies; agents treat fetched pages, file
      contents and tool output as data, never as instructions.
- [ ] `memory:` agents write `.claude/agent-memory/`, which is gitignored; durable lessons go
      through `/promote-lessons`.

## 6 — Commands that derive the current state

```bash
# Allow / ask / deny rules as they are now
jq -r '.permissions | to_entries[] | .key as $k | .value[] | "\($k)\t\(.)"' .claude/settings.json

# Broad execution grants (review every hit against the §1 table)
jq -r '.permissions.allow[]' .claude/settings.json \
  | grep -E '^Bash\((\*|npx|uvx|curl|wget|python3?|node|docker|gh|sed|awk|find|cp|mv) ' 

# Wildcard MCP grants and whether the server still exists in .mcp.json
jq -r '.permissions.allow[] | select(startswith("mcp__"))' .claude/settings.json
jq -r '.mcpServers | keys[]' .mcp.json

# MCP launch lines: unpinned packages and secrets in argv
jq -r '.mcpServers | to_entries[] | "\(.key)\t\(.value.command // .value.url) \((.value.args // []) | join(" "))"' .mcp.json

# Hook commands with an unquoted project path
jq -r '.. | objects | select(has("command")) | .command' .claude/settings.json | grep -v '^"\$CLAUDE_PROJECT_DIR"' 

# Guard hooks that "block" with exit 1 (fails open)
grep -nE 'exit 1|sys\.exit\(1\)' .claude/hooks/pre-*

# Reviewer agents with edit-capable permission modes
grep -lE '^permissionMode: *(acceptEdits|bypassPermissions)' .claude/agents/*.md

# Secrets in config and docs (hook scripts legitimately contain the patterns)
git grep -nIE 'sk-ant-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36,}' -- '*.md' '*.json' '*.yaml'

# Runtime logs are ignored and untracked
git check-ignore -v .claude/secrets-detected.log .claude/state/x .claude/agent-memory/x/MEMORY.md
git ls-files .claude | grep -E '\.log$|/state/|agent-memory'
```

## Severity reference

| Finding | Severity |
|---|---|
| Hardcoded secret in any tracked file | CRITICAL — remove, rotate, purge history |
| `Bash(*)`, `dangerouslyAllowAll`, committed `bypassPermissions` | CRITICAL |
| Guard hook that blocks with exit 1, or crashes open | HIGH |
| Unprompted package execution or network egress (`npx *`, `curl *`, `python *`, `docker *`) | HIGH |
| Wildcard MCP grant on a write-capable server | HIGH |
| Secret in MCP `args`; deprecated MCP package with credentials | HIGH |
| Hook sends tool output off the machine | HIGH |
| Unquoted `$CLAUDE_PROJECT_DIR` in hook commands | MEDIUM |
| Audit log stores the matched secret or full command | MEDIUM |
| Nested `.env` not covered by `Read` deny | MEDIUM |
| Reviewer agent with `acceptEdits` | MEDIUM |
| Stale `mcp__*` allow rule for a server not in `.mcp.json` | MEDIUM |
| Unpinned binary MCP server | LOW |
