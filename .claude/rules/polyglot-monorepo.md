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
---

# Polyglot monorepo guardrails

Path-scoped: loads when a **workspace-host** file at the repo root is in play (not nested app manifests). Apply an item only **if the project uses** that tool. Full decision tree: `.claude/skills/polyglot-monorepo/SKILL.md`.

- **Language-native package managers.** Dart → pub `workspace:` (+ Melos 7+ for Flutter scripts). Python → uv workspaces. Angular/TS/MCP → npm workspaces. Nx does not replace them.
- **Independent versions.** Each shipped app or service keeps its own `version:` / npm `version`. Do not `melos version` or Nx release across independently deployed units unless the human asked.
- **No unsolicited Nx.** Do not add `nx.json`, run `nx init`, or `create-nx-workspace` without explicit human approval (`CC_NX_INIT=1`). Existing `nx.json` stays. Existing `turbo.json` stays — keep Turbo; do not add Nx as a second JS orchestrator.
- **One affected-test owner per language.** Dart → Melos `--include-dependents`. JS → npm workspaces or Nx affected if `nx.json` exists. Python → uv/Make/CI paths. Do not run Melos and Nx affected on the same Dart tests.
- **Cache safety.** Never remote-cache `build_runner` / `*.g.dart`, Alembic, OpenAPI snapshots, Docker images, or env-specific deploy artifacts.
- **Cross-language API contracts** are committed snapshots plus a CI check, not inferred graph edges.
- **Protect workspace hosts and lockfiles.** Do not delete members to “simplify.” Do not Write/Edit `pubspec.lock` / `uv.lock` / `package-lock.json` (package manager via Bash only). Do not add `melos.yaml` on Melos 7+.
