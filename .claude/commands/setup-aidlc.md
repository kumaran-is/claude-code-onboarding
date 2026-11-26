---
name: setup-aidlc
description: "Install, configure, validate, or upgrade the official AWS AI-DLC CLI for Claude Code in the current project. Use for /setup-aidlc, install AI-DLC, aidlc config, or aidlc doctor. Delegates to aws-aidlc-integration. Not /next and not a copy of the AI-DLC engine."
argument-hint: "[--pin X.Y.Z] [--upgrade] [--doctor] [--project DIR]"
allowed-tools: Bash, Read, Glob, Grep
---

# /setup-aidlc

Load `.claude/skills/aws-aidlc-integration/SKILL.md` and follow it. Do not install or run `aidlc config` until that skill's discover, preflight, compatibility, and human approval steps pass. Do not pipe a remote installer into a shell. Do not copy upstream AI-DLC files into this toolkit. Do not invoke `/next`. Do not change `model` or `permissions.defaultMode` unless the human explicitly approved a listed diff.

**Request:** $ARGUMENTS
