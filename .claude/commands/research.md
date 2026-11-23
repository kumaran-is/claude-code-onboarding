---
name: research
description: "Mine Reddit for real customer pain points and unmet needs"
argument-hint: "[topic]"
allowed-tools: Read, Write, Glob, Grep, WebSearch, WebFetch
---

Mine Reddit for real customer pain points and unmet needs.

Usage: /research [topic]

Examples:
  /research property management apps
  /research fitness tracking
  /research freelance invoicing tools

This command searches Reddit for threads about the topic, pulls full comment feeds, extracts structured pain points using behavioral evidence analysis, and outputs a ranked top-10 opportunities report.

Output: research/[topic]/pain-points.md

The report can be fed into /backlog to generate a validated feature backlog.

Use the reddit-research agent (`.claude/agents/reddit-research.md`) to execute this task. Pass the topic from the user's input. If no topic was provided, ask for one.

$ARGUMENTS
