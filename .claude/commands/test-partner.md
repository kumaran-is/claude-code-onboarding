---
name: test-partner
description: "Paired manual QA: Claude guides one step at a time while you tap or click, watches logs, records defects, and verifies retests. Use for /test-partner, partner testing, pass fail shot, or watch logs while I test. Maestro for Flutter Android/iOS; Playwright for web; Chrome DevTools MCP for diagnostics."
argument-hint: "[--target flutter-android|flutter-ios|angular|react|web] [--flow <name>] [--device auto|<id>]"
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

# /test-partner

Load `.claude/skills/test-partner/SKILL.md` and follow it. The developer is the actor; do not tap for them unless they ask. Do not fix findings until they ask. Do not substitute a browser for Flutter Android/iOS.

**Request:** $ARGUMENTS

## 1. Gate

```bash
python3 .claude/skills/test-partner/scripts/check-test-partner.py --selftest
python3 .claude/skills/test-partner/scripts/check-test-partner.py --scan-skill
```

Both must exit 0. Then detect target, select tools, confirm the ledger dir is gitignored, and start Phase 0.

## 2. Not this command

- Scripted web E2E → `browser-testing`
- Scripted Flutter E2E → Maestro via `flutter-mobile`
- Known defect root-cause → `/debug`
- Next implementation task → `/next`
