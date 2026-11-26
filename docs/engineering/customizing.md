# Customizing the kit

How to add or remove agents, commands, skills, and hooks. The README lists the five practical steps; this page has the templates.

## 20. Customizing the Kit

This kit is a starting point — customize it for your team's stack and workflows.

### Adding a New Agent

Create a file in `.claude/agents/` with YAML frontmatter:

```markdown
---
name: my-agent
description: One-line description of when to use this agent. Claude reads this to decide when to activate it.
model: sonnet
tools: Bash, Read, Write, Edit, Glob, Grep
skills:
  - my-related-skill
---

# My Agent Name

You are a [role] specializing in [domain].

## Your Responsibilities
1. First responsibility
2. Second responsibility

## How to Work
1. Read the `my-related-skill` skill before writing code
2. Follow [specific conventions]

## Key Rules
- Rule 1
- Rule 2
```

**Usage:** `@my-agent Do something specific`

### Adding a New Slash Command

Create a file in `.claude/commands/` with YAML frontmatter:

```markdown
---
description: What this command does (shown in /help)
argument-hint: "[parameter description]"
allowed-tools: Bash, Read, Write, Edit
---

# Command Title

**Input:** $ARGUMENTS

## Steps
1. First step — explain what to do
2. Second step — reference skills or agents if needed
3. Final step — verify and report

Use the `my-skill` skill for patterns and templates.
```

**Usage:** `/my-command some argument here`

**Key notes:**
- `$ARGUMENTS` is replaced with whatever the user types after the command name
- `argument-hint` shows up in autocomplete to guide the user
- `allowed-tools` restricts which tools the command can use
- Add `disable-model-invocation: true` to prevent the command from using sub-agents

### Adding a New Skill

Create a directory in `.claude/skills/` with a `SKILL.md` file:

```
.claude/skills/my-skill/
├── SKILL.md                    # Entry point (keep under 5KB)
└── reference/                  # Detailed docs loaded on-demand
    ├── templates.md            # Code templates
    ├── patterns.md             # Design patterns
    └── troubleshooting.md      # Common issues and fixes
```

**SKILL.md structure:**

```markdown
---
name: my-skill
description: |
  Use this skill when the user asks about [domain].
  Triggers: [list of keywords or contexts that activate this skill].
---

# My Skill

## Overview
What this skill covers and when it applies.

## Quick Reference
| Task | Pattern |
|------|---------|
| Common task 1 | Brief pattern |
| Common task 2 | Brief pattern |

## Detailed References
When working on [specific task]:
→ Read `reference/templates.md` for code templates

When troubleshooting:
→ Read `reference/troubleshooting.md`
```

**Key notes:**
- Keep `SKILL.md` under 5KB — it loads into context when activated
- Put detailed content in `reference/` files — they load on-demand, saving tokens
- The `description` field is critical — Claude uses it to decide when to activate the skill
- Skills activate automatically based on context. Users don't invoke them directly

### Adding a New Hook

1. Create the script in `.claude/hooks/`:

```bash
#!/usr/bin/env bash
# Brief description of what this hook does
set -uo pipefail

# Read tool input from stdin
input=$(cat)
file=$(echo "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || file=""

# Your logic here
# Exit 0 = allow/pass, Exit 2 = block (message via stderr)

exit 0
```

2. Make it executable:

```bash
chmod +x .claude/hooks/my-hook.sh
```

3. Register it in `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/my-hook.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

**Hook events and matchers:**

| Event | Matcher | Use Case |
|-------|---------|----------|
| `PreToolUse` | `Bash`, `Write`, `Edit`, `WebFetch` | Block dangerous operations before they happen |
| `PostToolUse` | `Write`, `Edit` | Auto-format, lint, or validate after changes |
| `Stop` | *(no matcher)* | Run tests, scan for secrets when Claude finishes |
| `UserPromptSubmit` | *(no matcher)* | Enrich or validate user prompts before processing |

### Removing Components You Don't Need

If your team doesn't use a particular stack, remove the corresponding files to reduce noise:

```bash
# Example: Remove Flutter-related components if you don't use Flutter
rm .claude/agents/flutter-mobile.md
rm .claude/agents/flutter-security-expert.md
rm .claude/agents/riverpod-reviewer.md
rm .claude/agents/accessibility-auditor.md
rm .claude/agents/ui-standards-expert.md
rm -rf .claude/skills/flutter-mobile/
rm -rf .claude/skills/riverpod-patterns/
rm -rf .claude/skills/ui-standards-tokens/
rm .claude/commands/scaffold-flutter-app.md

# Update CLAUDE.md to remove Flutter references from the tech stack table
```

Also disable unused MCP servers in `.mcp.json` by setting `"disabled": true`.

### Version Update Guide

When a framework releases a new major version, update these files:

| To Update... | Edit These Files |
|---|---|
| Angular version | `CLAUDE.md` (tech stack), `.claude/skills/angular-spa/SKILL.md`, `.claude/agents/angular-spa.md` |
| Spring Boot version | `CLAUDE.md`, `.claude/skills/java-spring-api/SKILL.md`, `.claude/agents/java-spring-api.md` |
| NestJS version | `CLAUDE.md`, `.claude/skills/nestjs-api/SKILL.md`, `.claude/agents/nestjs-api.md` |
| Flutter/Dart version | `CLAUDE.md`, `.claude/skills/flutter-mobile/SKILL.md`, `.claude/agents/flutter-mobile.md` |
| Python version | `CLAUDE.md`, `.claude/skills/python-dev/SKILL.md`, `.claude/agents/python-dev.md` |
| LangChain/LangGraph | `CLAUDE.md`, `.claude/skills/agentic-ai-dev/SKILL.md`, `.claude/agents/agentic-ai-dev.md` |

**Process:**
1. Update version numbers in the files above
2. Update any changed API patterns in skill `reference/` files
3. Test with a scaffold command to verify the generated code compiles
4. Commit as `docs: update [framework] to vX.Y`

---
