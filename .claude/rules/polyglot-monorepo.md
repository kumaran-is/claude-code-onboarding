---
paths:
  - "**/nx.json"
  - "**/turbo.json"
  - "**/lerna.json"
  - "**/pnpm-workspace.yaml"
  - "**/melos.yaml"
  - "**/pubspec.yaml"
  - "**/package.json"
  - "**/pyproject.toml"
  - "**/Makefile"
  - "**/Taskfile.yml"
  - "**/Taskfile.yaml"
  - "**/Taskfile.dist.yml"
  - "**/settings.gradle"
  - "**/settings.gradle.kts"
  - "**/pom.xml"
---

# Polyglot monorepo guardrails (MONO-ARCH-001)

Path-scoped: loads when a **workspace-host** file is in play. Apply an item only **if the project uses** that tool. Full decision tree: `.claude/skills/polyglot-monorepo/SKILL.md`. Modes: **native-only** · **melos-only** · **nx-only** · **nx-plus-melos**. Human approval before setup or migration.

- **Language-native package managers.** Dart → pub `workspace:` (+ Melos 8.x for Flutter scripts). Python → uv workspaces. Angular/TS/MCP → npm/pnpm workspaces. Java → Gradle/Maven. Nx does not replace them.
- **Independent versions.** Each shipped app or service keeps its own `version:` / npm `version`. Do not `melos version` or Nx release across independently deployed units unless the human asked.
- **No unsolicited Nx.** Do not add `nx.json`, run `nx init`, or `create-nx-workspace` without explicit human approval (`CC_NX_INIT=1`). Existing `nx.json` stays. Existing `turbo.json` stays — keep Turbo; do not add Nx as a second JS orchestrator.
- **One affected-test owner per language.** Dart → Melos. JS → npm workspaces or Nx affected if `nx.json` exists. Python → uv/Make/CI paths, plus explicit Nx `implicitDependencies` when Nx is used. Do not run Melos and Nx affected on the same Dart tests.
- **Unique Flutter bridge.** In NX + MELOS, one Nx project (`flutter-workspace`) delegates to Melos. Do not model every Dart package as an Nx project.
- **Cache safety.** Never cache `deploy`, `migrate`, `release`, `docker-push`. Generated/codegen/OpenAPI/`build_runner` start at `cache: false`. Task-level Nx 24 affected needs declared `inputs` (including `^default` / contract globs); a graph edge is not enough.
- **Python/Java edges are not inferred from JS imports.** Explicit `implicitDependencies` or a verified plugin (`@nx/gradle`). Fail closed if the graph cannot prove affected correctness (`audit_monorepo_graph.py`).
- **Git baseline** from this repository (`origin/HEAD` / actual default branch), never a hardcoded `main`.
- **Protect workspace hosts and lockfiles.** Do not delete members to “simplify.” Do not Write/Edit `pubspec.lock` / `uv.lock` / `package-lock.json` (package manager via Bash only). Do not add `melos.yaml` on Melos 7+.
- **Never overwrite** this kit's `CLAUDE.md`, `AGENTS.md`, or `.mcp.json`. Product-repo `nx configure-ai-agents` is opt-in with `CC_NX_INIT=1` only.
