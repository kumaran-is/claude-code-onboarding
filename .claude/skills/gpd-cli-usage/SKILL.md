---
name: gpd-cli-usage
description: "How to run the Google Play Developer `gpd` CLI: service-account auth (GPD_SERVICE_ACCOUNT_KEY), flags, output, pagination, safety conventions. Use when designing or debugging any gpd command. Load before the other gpd-* skills."
allowed-tools: Bash, Read
metadata:
  triggers: gpd command, gpd CLI, Google Play CLI, gpd auth, gpd flags, gpd output, Play Developer CLI, GPD_SERVICE_ACCOUNT_KEY, gpd help, gpd pagination
  related-skills: gpd-id-resolver, gpd-release-flow, gpd-submission-health
  domain: mobile-deployment
  role: specialist
  scope: deployment
  output-format: commands
last-reviewed: "2026-03-15"
---

# GPD CLI Usage

## Iron Law

**NEVER GENERATE GPD COMMANDS WITHOUT RUNNING `gpd --help` OR SUBCOMMAND `--help` FIRST**

Always use `--help` to discover current flags and subcommands. The gpd CLI evolves — never assume flags from memory.

## Command discovery
- Always use `--help` to confirm commands and flags.
  - `gpd --help`
  - `gpd publish --help`
  - `gpd monetization --help`

## Flag conventions
- Use explicit long flags (for example: `--package`, `--track`, `--status`).
- No interactive prompts; destructive operations require `--confirm`.
- Use `--all` when the user wants all pages.

## Output formats
- Default output is minified JSON.
- Use `--pretty` for readable JSON during debugging.

## Authentication and defaults
- Service account auth via `GPD_SERVICE_ACCOUNT_KEY` is required.
- Validate access for a package:
  - `gpd auth check --package com.example.app`

## Safety
- Use `--dry-run` when available before destructive operations.
- Prefer edit lifecycle (`gpd publish edit create`) for multi-step publishing.

## Anti-Patterns

- **Don't generate gpd commands from memory.** The gpd CLI evolves — flags and subcommands change between versions. Always run `gpd <subcommand> --help` before generating a command; the Iron Law exists for this reason.
- **Don't omit `--confirm` on destructive operations.** Commands like `gpd publish halt` and `gpd publish rollback` require `--confirm`; omitting it will either fail or prompt interactively, breaking automation.
- **Don't use short flags in scripts.** Always use explicit long flags (`--package`, `--track`, `--status`) to ensure scripts are readable and resilient to positional changes.

## Verify

After running any gpd command:
- Check that the exit code is `0`: `echo $?` — a non-zero exit means the operation failed even if no error was printed.
- Validate auth before running a sequence: `gpd auth check --package com.example.app` — a missing or expired `GPD_SERVICE_ACCOUNT_KEY` will cause silent failures mid-sequence.

## Documentation Sources

| Source | How to Access | Purpose |
|--------|--------------|---------|
| gpd CLI help | `gpd --help`, `gpd <command> --help` | Discover current flags, subcommands, and options |
| gpd subcommand help | `gpd publish --help`, `gpd monetization --help` | Command-specific flags and usage |
