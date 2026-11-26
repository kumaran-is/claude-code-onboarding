---
name: aws-aidlc-integration
description: "Use when the user says /setup-aidlc, install AI-DLC, configure AWS AI-DLC, aidlc config, aidlc doctor, or add the official awslabs aidlc-workflows harness to a Claude Code project. Installs and validates the upstream native aidlc CLI beside this toolkit. Not /next, not SDD, not a copy of the AI-DLC engine."
allowed-tools: Bash, Read, Glob, Grep
argument-hint: "[--pin X.Y.Z] [--upgrade] [--doctor] [--project DIR]"
metadata:
  domain: workflow
  role: orchestrator
  scope: project
  triggers: /setup-aidlc, setup-aidlc, install AI-DLC, configure AI-DLC, aidlc config, aidlc doctor, awslabs aidlc-workflows
  related-skills: next-issue, verification-before-completion, subagent-driven-development
last-reviewed: "2026-11-26"
---

# AWS AI-DLC integration (`/setup-aidlc`)

## Iron Law

**NEVER pipe a remote installer into a shell. NEVER run `aidlc config` until discover, preflight, compatibility, and human approval have all passed. Do not copy upstream AI-DLC skills, agents, commands, hooks, or engine into this toolkit. Do not invoke `/next` or `/aidlc` from the other workflow.**

AI-DLC remains an independently installed and maintained upstream product
([awslabs/aidlc-workflows](https://github.com/awslabs/aidlc-workflows)).

## How this skill is organised

| Path | Covers |
|---|---|
| `references/official-commands.md` | Exact official install, config, doctor, update, pin, uninstall |
| `references/compatibility.md` | Ownership matrix and conflict stops |
| `scripts/check-aidlc-setup.py` | Discover, preflight, compat, install-plan, recovery; `--selftest` |

## Invocation

| Command | Behaviour |
|---|---|
| `/setup-aidlc` | Discover → preflight → compat → plan → **wait for approval** → official install/config → doctor |
| `/setup-aidlc --pin X.Y.Z` | Same, with official `--version` / `aidlc config --pin` |
| `/setup-aidlc --upgrade` | Official `aidlc update` then dry-run refresh |
| `/setup-aidlc --doctor` | Health + installed vs latest stable only |

Do not hardcode a release id. Discover latest **stable** at execution time
(`releases/latest`, skip previews). Report installed versus available.

## Independence

This toolkit owns `/next` (including optional `--auto`), `/verify`, `/review-code`,
`/ship`, Ralph, SDD, stack skills, and existing security/CI gates.

AWS AI-DLC owns `/aidlc`, its phases, agents, profiles, approval gates, `aidlc/`
workspace, and upstream updates.

A team may use either `/next` or `/aidlc`. Neither command may start the other.
Do not merge their lifecycle orchestration.

## Steps

Run from the **target project root** (not Property Harbor, not a random extra repo
unless the user named it).

```bash
python3 .claude/skills/aws-aidlc-integration/scripts/check-aidlc-setup.py --selftest
python3 .claude/skills/aws-aidlc-integration/scripts/check-aidlc-setup.py --scan-skill
python3 .claude/skills/aws-aidlc-integration/scripts/check-aidlc-setup.py --discover --root "$PWD"
python3 .claude/skills/aws-aidlc-integration/scripts/check-aidlc-setup.py --preflight --root "$PWD"
python3 .claude/skills/aws-aidlc-integration/scripts/check-aidlc-setup.py --latest-stable
python3 .claude/skills/aws-aidlc-integration/scripts/check-aidlc-setup.py --compat --root "$PWD"
python3 .claude/skills/aws-aidlc-integration/scripts/check-aidlc-setup.py --install-plan --os "$(uname -s)"
python3 .claude/skills/aws-aidlc-integration/scripts/check-aidlc-setup.py --config-plan
python3 .claude/skills/aws-aidlc-integration/scripts/check-aidlc-setup.py --recovery --root "$PWD"
```

`--latest-stable` may hit GitHub. If it fails, say so and continue with a
human-supplied pin; do not invent a version.

1. **Discover** — project root, OS, Claude Code version, toolkit presence, `aidlc`
   binary, installed version, latest stable, `aidlc/` workspace, `.aidlc-version`.
2. **Preflight** — `.claude/` settings, hooks, commands, skills, MCP, permissions.
3. **Compatibility** — `--compat`. `BLOCKED` → stop and show alternatives
   (`references/compatibility.md`). Never silently overwrite.
4. **Plan** — print install-plan + `aidlc config --harness claude --dry-run` (when
   the CLI exists). Preserve `model` (toolkit default sonnet),
   `permissions.defaultMode`, existing hooks, and MCP. **Wait for explicit
   human approval** before any write.
5. **Install** — official native installer only (`references/official-commands.md`).
   Download to a file, inspect, attest/checksum, then run. NEVER pipe.
6. **Configure** — `aidlc config --harness claude --mcp none --yes` after a clean
   dry-run. Do not pass `--force`. Do not enable default MCP unless the human asked.
7. **Preserve** — re-read settings; if `model` or `defaultMode` changed, STOP and
   restore from git / the dry-run notes.
8. **Validate** — `aidlc doctor`, `aidlc version`, confirm `/aidlc` is the upstream
   command (not this toolkit). Confirm `/next` still exists and this skill did
   not edit it.
9. **Report** — installed version, available version, files touched, warnings,
   manual PATH steps, next steps (`/aidlc` vs `/next`).

`--upgrade` uses `aidlc update` then the same dry-run/approve/doctor loop.
`--doctor` is read-only.

Failed or partial setup → `--recovery` (do not delete `aidlc/` on a guess).
Removal → official `aidlc uninstall` per lifecycle docs; it does not delete
unrelated project files.

## Not this skill

| Need | Use |
|---|---|
| Next GitHub story | `/next` |
| Verify / ship | `/verify`, `/ship` |
| SDD ledger | `subagent-driven-development` |
| AI-DLC workflow itself | `/aidlc` after this setup |

## Verify

```bash
python3 .claude/skills/aws-aidlc-integration/scripts/check-aidlc-setup.py --selftest
python3 .claude/skills/aws-aidlc-integration/scripts/check-aidlc-setup.py --scan-skill
```
