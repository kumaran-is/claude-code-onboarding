# Security

Trust boundaries, hooks, and security commands. The README is the short version. `settings.json` in this kit sets `permissions.defaultMode` to `auto` and does **not** ship allow or deny lists — PreToolUse hooks are the committed guardrails. Put personal allow rules in `.claude/settings.local.json` (gitignored).

## 18. Security Considerations

Before using Claude Code with real projects, understand the security boundaries.

### What Goes to Anthropic's API

Every prompt, file content pulled via `@file` references, and tool outputs are sent to Anthropic's API for processing. This means:

- **Never paste real API keys, passwords, or tokens into prompts** — they'll be transmitted to Anthropic's servers
- **Be cautious with `@file` references to sensitive files** — the file contents are sent as part of the prompt
- **Tool outputs (Bash, Read, etc.) are included in context** — if a command outputs secrets, they're sent too

### MCP Server Credentials

MCP servers like `postgres` and `github` require connection strings or tokens. Handle these safely:

```bash
# ✅ GOOD — credentials from environment variables
# .mcp.json
"args": ["${POSTGRES_CONNECTION_STRING}"]

# ❌ BAD — credentials hardcoded in .mcp.json
"args": ["postgresql://<user>:<pw>@localhost:5432/mydb"]   # a literal user:password in the URL
```

Always use environment variable references (`${VAR_NAME}`) in `.mcp.json` — never hardcode credentials.

### The `--dangerously-skip-permissions` Flag

This flag disables all permission prompts. Rules for safe usage:

| Environment | Safe to Use? | Why |
|-------------|-------------|-----|
| Local dev, throwaway project | ✅ Yes | Low risk, easy to reset |
| Local dev, real project | ⚠️ Caution | Claude can modify/delete files without asking |
| CI/CD pipeline | ❌ No | Automated environment with real credentials and deployment access |
| Shared/team machine | ❌ No | Other users' files and credentials may be accessible |

### Pre-configured Guardrails in This Kit

This repo includes Claude Code hooks (`.claude/hooks/`) and a git pre-commit hook (`.git/hooks/pre-commit`) that enforce security automatically:

**Claude Code hooks** — fire on Claude Code lifecycle events:

| Hook | Event | What It Prevents |
|------|-------|-----------------|
| `pre-bash-guard.sh` | PreToolUse | `rm -rf /`, force-push to main, `DROP DATABASE`, piping curl to shell |
| `pre-edit-protect-sensitive.sh` | PreToolUse | Direct edits to `.env`, private keys, credentials, lock files; unauthorized weakening of ESLint/Ruff/analysis_options/tsconfig/coverage/CI quality gates |
| `pre-compact-checkpoint.sh` | PreCompact | Compaction with no on-disk snapshot (fail-open; does not block `/compact`) |
| `pre-prompt-injection.sh` | PreToolUse | Blocks terminal escape sequences and NUL bytes; role-override phrases and chat-template delimiters in Bash/WebFetch input are reported as an advisory, never blocked |
| `pre-unicode-injection.sh` | PreToolUse | Zero-width characters, bidi overrides and isolates, tag characters, ANSI escapes, null bytes hidden in file edits (CVE-2025-53109/53110) |
| `session-claudemd-scan.sh` | SessionStart | Injection patterns in `CLAUDE.md` / `.claude/*.md` files loaded at session start |
| `stop-secret-scan.sh` | Stop | Scans changed and untracked files with the shared `post-edit-secrets-scan` pattern table (+JWT) |
| `post-edit-format.sh` | PostToolUse | Not security-related, but auto-formats to prevent malformed code commits |

**Git pre-commit hook** — fires on every `git commit`, before the commit is created:

| Hook | Location | What It Prevents |
|------|----------|-----------------|
| `pre-commit` | `.git/hooks/pre-commit` | Blocks commits containing secrets. Provider tokens, private keys, database URLs with passwords and key assignments come from the shared table in `.claude/hooks/post-edit-secrets-scan.sh` (`--patterns`), which the edit and prompt scanners use too; GCP service-account JSON, JWTs and generic `api_key`/`secret`/`token` assignments are commit-time extras. Docs (`*.md`, `*.txt`, `*example*`, `*template*`, `*.sample`) are scanned for provider tokens and private key blocks only; test fixtures and snapshots are skipped; the matched value is never printed. A missing or malformed table refuses the commit. Self-test: `bash git-hooks/pre-commit-secrets.sh --selftest` |
| `pre-commit-evaluator.sh` | `git-hooks/pre-commit-evaluator.sh` | Claude haiku scores staged diff on 4 dimensions (correctness, completeness, safety, scope). Blocks commit if overall score < threshold. Opt-in: `CLAUDE_PRECOMMIT_EVAL=1`. Threshold: `CLAUDE_PRECOMMIT_THRESHOLD` (default 7/10). |

The git hook is the last line of defence before secrets enter git history. It complements `stop-secret-scan.sh` (which catches secrets in Claude's output) by catching secrets in your own edits.

```bash
# Install (one-time, after cloning):
cp git-hooks/pre-commit-secrets.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# The hook then runs automatically on every git commit.
# Never bypass it with --no-verify. A false positive goes on the allowlist (below);
# a real secret is removed from the commit and rotated.

# To add a false-positive to the allowlist, edit the WHITELIST array in:
git-hooks/pre-commit-secrets.sh   # source (committed)
.git/hooks/pre-commit             # active copy (re-copy after editing)
```

These hooks are **defense-in-depth** — they catch mistakes but aren't a substitute for proper secret management. Always use a secrets manager (AWS Secrets Manager, HashiCorp Vault, 1Password CLI) for production credentials.

### Security Superpowers — AI-Assisted Security Tooling

Beyond the passive guardrails above, this kit ships dedicated security commands, a threat-modeling agent, and SAST skills — adapted from `claude-skill-samples/security/` and tailored to the onboarding stack (Java/Spring, NestJS, Python, Angular, Flutter):

| Tool | Invoke | What It Does |
|------|--------|--------------|
| `/security-hardening [scope]` | Command | Full-stack orchestration: SAST → threat model → architecture review → fix → hardening → validation |
| `/security-sast [path]` | Command | SAST across all stack languages (Bandit, Semgrep, ESLint Security, SpotBugs, dart analyze). Risk score 0–100. |
| `/security-dependencies [path]` | Command | CVE scan across npm / pip / Maven / pub.dev. Priority score per CVE. CycloneDX SBOM output. |
| `/xss-scan [path]` | Command | Angular-specific XSS: `bypassSecurityTrust*`, `[innerHTML]`, `ElementRef.nativeElement`. Fix patterns included. |
| `/audit-security [scope]` | Command | Full audit — now includes dependency scan as Step 5. |
| `@threat-modeling-expert` | Agent | STRIDE analysis, DFD review, attack trees, risk scoring. Call before designing any new service. |
| `threat-modeling` skill | Skill | Lazy-loaded STRIDE methodology + control library. Auto-loads references on demand. |
| `sast-configuration` skill | Skill | Lazy-loaded SAST tool config, Semgrep rules, CI/CD integration. |

**Typical security workflow:**

| Phase | Action |
|-------|--------|
| Before design | `@threat-modeling-expert` — STRIDE the new feature |
| After coding | `/security-sast src/` — catch code-level vulns |
| After coding | `/security-dependencies .` — catch CVEs in packages |
| Before release | `/audit-security` — full audit (includes dep scan) |
| Failing audit | `/security-hardening` — orchestrated remediation |

### Checklist Before Using Claude Code on a Real Project

- [ ] No real secrets in `.mcp.json` — all use `${ENV_VAR}` references
- [ ] `.env` files are in `.gitignore`
- [ ] Hooks are executable (`chmod +x .claude/hooks/*.sh`) and the git secrets hook is installed from `git-hooks/pre-commit-secrets.sh`
- [ ] Personal allow/deny rules live in `.claude/settings.local.json` — committed `settings.json` has `defaultMode: auto` and no allow/deny lists
- [ ] Team members understand what gets sent to Anthropic's API
- [ ] CI/CD pipelines do NOT use `--dangerously-skip-permissions`
