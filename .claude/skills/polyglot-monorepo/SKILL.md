---
name: polyglot-monorepo
description: "Use when choosing or migrating polyglot monorepo tooling: Dart pub workspaces, Melos, uv workspaces, npm workspaces, Nx, Makefile or Taskfile. Triggers when: set up a monorepo, Melos vs Nx, uv workspace members, npm workspaces, affected builds, remote cache, join a workspace, do not add Nx."
allowed-tools: Read, Bash, Glob, Grep
metadata:
  triggers: polyglot monorepo, Melos vs Nx, uv workspace, npm workspaces, affected builds, remote cache, Taskfile, join a workspace, do not add Nx
  related-skills: flutter-mobile, uv-package-manager, architecture-design, python-dev, angular-spa, mcp-builder
  domain: architecture
  role: architect
  scope: design
  output-format: document
last-reviewed: "2026-11-26"
---

## Iron Law

**Language-native package managers first. Never add Nx, `melos.yaml`, or a second orchestrator without explicit human approval. Never cache generated code, migrations, OpenAPI snapshots, or deployment images.**

# Polyglot Monorepo

Decision skill only. It does **not** replace Melos, uv, npm, or Nx docs. Run discovery, pick tools, then load the stack skill that owns implementation.

Official docs (re-check before pinning): [Melos](https://melos.invertase.dev/) · [Melos agents](https://melos.invertase.dev/agents) · [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/) · [npm workspaces](https://docs.npmjs.com/cli/using-npm/workspaces) · [Nx AI](https://nx.dev/docs/getting-started/ai-setup) · [Nx MCP](https://nx.dev/docs/reference/nx-mcp) · [Nx multi-language](https://nx.dev/docs/features/multi-language-support)

## 1. Discover (do this first)

```bash
python3 .claude/skills/polyglot-monorepo/scripts/discover_monorepo.py --root <repo>
python3 .claude/skills/polyglot-monorepo/scripts/discover_monorepo.py --find-host <path>   # host dir or exit 1
```

Treat the JSON as the inventory. Do not invent a fourth package manager. Do not rewrite lockfiles (`pre-edit-protect-sensitive.sh` blocks Write/Edit of `package-lock.json`, `uv.lock`, `pubspec.lock`).

| Signal | Means |
|--------|--------|
| Root `pubspec.yaml` `workspace:` | Dart pub workspace |
| Root `dev_dependencies.melos` + `melos:` | Melos 7+ (no `melos.yaml`). Default when **two or more** Dart packages. |
| `melos.yaml` | Legacy Melos — migrate, do not extend |
| `[tool.uv.workspace]` | uv workspace |
| `package.json` `workspaces` | npm workspaces (`"*"` for members; not yarn `workspace:`) |
| `nx.json` | Nx **already** in use — keep; do not rip out |
| `turbo.json` | Keep Turbo for JS; do **not** add Nx |
| `Makefile` / `Taskfile.y*ml` / `Taskfile.dist.yml` | Lightweight polyglot orchestrator |

## 2. Decision tree

```
START
+-- Flutter/Dart packages?
|     YES -> Dart pub workspace
|           Melos 7+ by default when 2+ Dart packages (scoped scripts, --diff, --include-dependents)
|           Implementation: flutter-mobile / flutter-build-and-workspace.md
|           Version each shipped app in ITS pubspec (store build numbers). Never melos version by default.
+-- Python packages?
|     YES -> uv workspaces (one uv.lock)
|           Member with a different requires-python stays OUTSIDE (own lock) — uv-package-manager
+-- Angular / Node / MCP packages?
|     YES -> npm workspaces first
|           Nx ONLY if ALL of: JS/TS project count is high, affected+cache is a measured CI cost,
|           human approved, and Flutter is NOT moved under Nx
+-- Cross-language tasks (compose, gates, release)?
      Makefile or Taskfile unless Nx already owns JS CI
```

**Default for a new mixed repo:** Dart workspace + Melos (Flutter) + uv + npm + Makefile. That is enough.

**Nx is optional, never default.** Verdicts from discover: `do-not-add` (no `nx.json`, not JS-heavy) · `keep` (`nx.json` present) · `justified` (`nx.json` + expanded npm members ≥ 8, no Dart) · `candidate-needs-approval` (expanded npm members ≥ 8, **no** `nx.json`, not mixed Dart/uv — ask the human; do not add it unsolicited). `packages/*` is expanded; a glob string is not a member count of 1.

## 3. Melos vs Nx (complement or duplicate)

| | Melos | Nx |
|---|---|---|
| Owns | Flutter/Dart scripts, dependents, codegen order | JS/TS task graph, affected, remote cache |
| Official Flutter plugin | Yes (Melos) | No first-party; community plugins only |
| Cross-language imports | No | Only with custom `implicitDependencies` / `project.json` |
| Duplicate if | Both select Flutter tests | Agent runs `melos test` **and** `nx affected -t test` on Dart |

Use **one owner for affected tests per language**: Melos for Dart, Nx (if present) for JS, path filters / Makefile for Python. OpenAPI → generated TS is a **snapshot CI gate**, not a graph edge.

## 4. Greenfield vs migration

**Greenfield:** create the language workspace first (`/scaffold-flutter-app`, `/scaffold-python-api`, `/scaffold-angular-app`, `/scaffold-mcp-server`). Then join — see [reference/discover-and-migrate.md](reference/discover-and-migrate.md). Do not run `/scaffold-monorepo` (it does not exist).

**Migration:** additive only. Keep existing lockfiles and workspace members. Ask before `nx init`, `create-nx-workspace`, `nx configure-ai-agents`, replacing a lockfile, or moving packages. Hook: `block-raw-scaffold.sh` blocks raw Nx init unless `CC_NX_INIT=1`, and blocks **new** `nx.json` / `melos.yaml`.

## 5. Route implementation (do not copy it here)

| Need | Load |
|------|------|
| Melos scripts, `resolution: workspace`, `dart run melos` | `flutter-mobile` → `reference/flutter-build-and-workspace.md` |
| uv members, `--all-packages`, 3.13 island | `uv-package-manager` |
| FastAPI service as a member | `python-dev` + `/scaffold-python-api` |
| Angular CLI + npm workspaces | `angular-spa` + `/scaffold-angular-app` |
| MCP as an npm member | `mcp-builder` + `/scaffold-mcp-server` |
| System C4 / ADR | `architecture-design` + `/design-architecture` |
| Nx cache, MCP, `configure-ai-agents` | [reference/nx-and-mcp.md](reference/nx-and-mcp.md) — product repo only |

Do **not** copy Invertase Melos skills or Nrwl Nx skills into this kit. Do **not** register Melos MCP (docs.page only). Do **not** enable Nx MCP in a repo without `nx.json`.

## 6. Safeguards (also in the path-scoped rule)

1. Language-native dependency management (pub / uv / npm). Nx does not replace them.
2. Independent app and service versions stay in each package manifest.
3. No unsolicited Nx. Human says yes; then `CC_NX_INIT=1`.
4. One affected-test owner per language.
5. Nx/remote cache **off** for `build_runner` / `*.g.dart`, Alembic, OpenAPI snapshots, Docker images, env-specific deploy artifacts.
6. Cross-language API contracts: committed snapshot + CI check (see `schema-contract` pattern), not `nx graph`.
7. Never Write/Edit lockfiles; never delete workspace members to “simplify.”

## Verify

```bash
python3 .claude/skills/polyglot-monorepo/scripts/discover_monorepo.py --selftest
python3 .claude/skills/writing-skills/scripts/check-skill-spec.py --dir .claude/skills \
  --prompt "Should this polyglot monorepo use Melos, uv workspaces, npm workspaces, or Nx for affected builds?" \
  --expect polyglot-monorepo --forbid java-spring-api
```

Exit 0 on both. Fixture matrix is in the discover script `--selftest` (Flutter-only, npm-only, uv-only, mixed, glob expansion, candidate-needs-approval, turbo, `--find-host`, JS+Nx).
