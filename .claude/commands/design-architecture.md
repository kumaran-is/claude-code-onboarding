---
description: Design system architecture with diagrams, API contracts, and deployment topology for a given feature or system
argument-hint: "[system or feature requirements]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Design System Architecture

Design the architecture for the following system or feature:

**Requirements:** $ARGUMENTS

## Steps
1. Clarify and summarize the requirements and NFRs
1b. **Monorepo tooling (MONO-ARCH-001)** — if the system is more than one package, or the repo already has `workspace:` / `workspaces` / `[tool.uv.workspace]` / `nx.json` / `turbo.json` / `Makefile` / `settings.gradle*`: load `polyglot-monorepo`, run `python3 .claude/skills/polyglot-monorepo/scripts/discover_monorepo.py --root <repo>`, and record `recommendation.mode` (`native-only` / `melos-only` / `nx-only` / `nx-plus-melos`), `mode_status`, package managers, and `detected.git_baseline` in the ADR. **Stop for human approval** before `nx init`, a Flutter Nx bridge, or lockfile changes. `candidate-needs-approval` is not permission to add Nx. After an approved Nx/bridge setup, run `audit_monorepo_graph.py --root --expect`. Do not create `/scaffold-monorepo`. Spec: `docs/Nx_Melos_Polyglot_Monorepo_Architecture_Spec.md`.
2. Create a C4 System Context diagram (Mermaid)
3. Create a component-level architecture diagram (Mermaid)
4. Define key API contracts (OpenAPI YAML snippets)
5. Draw sequence diagrams for critical flows (Mermaid)
6. Provide a Docker Compose setup for local development
7. Write an ADR (Architecture Decision Record) for the key technology choice
8. Summarize trade-offs and next steps

Use the architecture-design skill for templates.
Save output files to a `docs/architecture/` directory.
