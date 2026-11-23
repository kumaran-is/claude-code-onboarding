---
name: asc-cli-usage
description: "How to run the App Store Connect `asc` CLI: auth, flags, output formats, pagination, timeouts. Use when designing or debugging any asc command. Load before the other asc-* skills."
allowed-tools: Bash, Read
metadata:
  triggers: asc command, asc CLI, App Store Connect CLI, asc auth, asc flags, asc pagination, asc output, asc help, asc env vars
  related-skills: asc-id-resolver, asc-release-flow, asc-submission-health
  domain: mobile-deployment
  role: specialist
  scope: deployment
  output-format: commands
last-reviewed: "2026-03-15"
---

# asc CLI Usage

## Iron Law

**NEVER GENERATE ASC COMMANDS WITHOUT RUNNING `asc --help` OR SUBCOMMAND `--help` FIRST**

Always use `--help` to discover current flags and subcommands. The asc CLI evolves — never assume flags from memory.

## Command discovery
- Always use `--help` to discover commands and flags.
  - `asc --help`
  - `asc builds --help`
  - `asc builds list --help`

## Flag conventions
- Use explicit long flags (e.g., `--app`, `--output`).
- No interactive prompts; destructive operations require `--confirm`.
- Use `--paginate` when the user wants all pages.

## Output formats
- Default output is minified JSON.
- Use `--output table` or `--output markdown` only for human-readable output.
- `--pretty` is only valid with JSON output.

## Authentication and defaults
- Prefer keychain auth via `asc auth login`.
- Fallback env vars: `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_PRIVATE_KEY_PATH`, `ASC_PRIVATE_KEY`, `ASC_PRIVATE_KEY_B64`.
- `ASC_APP_ID` can provide a default app ID.

## Timeouts
- `ASC_TIMEOUT` / `ASC_TIMEOUT_SECONDS` control request timeouts.
- `ASC_UPLOAD_TIMEOUT` / `ASC_UPLOAD_TIMEOUT_SECONDS` control upload timeouts.

## Documentation Sources

| Source | How to Access | Purpose |
|--------|--------------|---------|
| asc CLI help | `asc --help`, `asc <command> --help` | Discover current flags, subcommands, and options |
| asc subcommand help | `asc builds --help`, `asc submit --help` | Command-specific flags and usage |
