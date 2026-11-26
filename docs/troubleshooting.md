# Troubleshooting

Extended diagnostics. The README covers the three most common failures.

## 22. Troubleshooting

### `command not found: claude`

Your shell can't find the Claude binary. Add it to your PATH:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### "Context too large" error

```
> /compact                          # Quick reset
> /compact "keep the auth work"     # Preserves specified context
```

**Prevention:** use `/compact` every ~50 operations in long sessions, or start a fresh session for new features.

### Edit tool fails with "string not found"
Claude's Edit tool requires an exact string match including whitespace and indentation. Fix:

```
> Read the file again to see exact content
```
If the string appears multiple times, provide more surrounding context for uniqueness.

### MCP server not connecting

Run `/mcp` to check status. 
```
> /mcp
```
Check the status output. Common fixes:
- Ensure `npx` is available (requires Node.js)
- For GitHub MCP, set your token: `export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token`
- Restart Claude Code after changing `.mcp.json`
- On Windows, MCP servers need a `cmd` wrapper: `"command": "cmd", "args": ["/c", "npx", "-y", "package-name"]`

### Claude isn't using skills or agents

- Verify the files exist: `ls .claude/agents/` and `ls .claude/skills/`
- Check that each file has valid YAML frontmatter (`---` delimiters)
- Try referencing explicitly: "Use the java-spring-api skill"

### Background task not responding
```
> /tasks          # or /bashes — check status
> /kill <id>      # Stop the stuck task
```

### Permission errors

Never use `sudo` with npm installs. Fix global permissions instead:

```bash
npm config set prefix ~/.npm-global
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Put personal allow rules in `.claude/settings.local.json` (gitignored). Committed `settings.json` uses `defaultMode: auto` with no allow/deny lists; hooks remain the project guardrails.

### Windows-Specific Setup

**Hooks require a Bash shell.** The `.claude/hooks/*.sh` scripts won't run natively on Windows. Options:

| Approach | How | Trade-off |
|----------|-----|-----------|
| **WSL 2 (recommended)** | Install WSL 2, run Claude Code from a WSL terminal | Full Linux compatibility, hooks work natively |
| **Git Bash** | Install Git for Windows, use Git Bash as your terminal | Most hooks work, occasional path issues |
| **Rewrite as .ps1** | Convert bash hooks to PowerShell scripts | Native Windows, but requires rewriting and testing each hook |

If using WSL 2:
```bash
# Install WSL 2 (from PowerShell as admin)
wsl --install

# Clone the repo inside WSL, not on /mnt/c/
cd ~ && git clone <repo-url>

# Run Claude Code from WSL
claude
```

**MCP servers on Windows** may need a `cmd` wrapper in `.mcp.json`:
```json
"command": "cmd",
"args": ["/c", "npx", "-y", "package-name"]
```

### Run diagnostics

When something isn't working and you're not sure why:

```bash
claude doctor              # General health check
claude --debug             # Full debug logging
claude --debug "mcp"       # Debug a specific category
```
