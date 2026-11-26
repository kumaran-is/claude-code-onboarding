# Claude-Mem (optional)

Persistent memory across Claude Code sessions. The README keeps a one-command install; this page is the full setup including team sharing.

## 6. Install Claude-Mem (Persistent Memory) *(Optional)*

Claude Code forgets everything between sessions. **[Claude-Mem](https://github.com/thedotmack/claude-mem)** gives Claude persistent memory across sessions. 

Inside a Claude Code CLI session, run:

```
> /plugin marketplace add thedotmack/claude-mem
> /plugin install claude-mem
```

Then **restart Claude Code** (`/exit`) or restart (close and reopen) the vscode.

### What Claude-Mem Does

- **Automatically captures** what Claude Code does (file edits, decisions, tool usage)
- **Compresses** sessions into searchable memory using AI
- **Injects relevant context** at the start of new sessions
- **Web viewer** at `http://localhost:37777` to browse memory

Verify with: Inside a Claude Code CLI session, run:

```
> Do you have any memory from previous sessions?
```

### 6a. Set Up Team Memory Sharing *(Optional)*

Once each developer has claude-mem installed individually, **[claude-mem-sync](https://github.com/lopadova/claude-mem-sync)** lets the team share selected observations (decisions, bug fixes, discoveries) across a shared GitHub repo — so your team's collective knowledge grows over time.

Run the one-shot setup command inside a Claude Code session:

```
> /setup-team-memory
```

This command:
- Installs and configures `claude-mem-sync`
- Creates `.claude/memories/` folder structure in the repo
- Adds a GitHub Actions workflow that auto-merges contributions on push
- Updates `.gitignore` to keep raw contributions local
- Schedules weekly exports (Fridays 4pm) and imports (Saturdays 9am)
- Prints a full pass/fail verification table at the end

Safe to re-run — skips any step already completed. Each developer runs it once on their machine; the shared infrastructure files (workflow, memories folder) are committed once and shared via the repo.
