---
name: polyglot-monorepo
description: "Use when choosing or migrating polyglot monorepo tooling per MONO-ARCH-001: native-only, Melos-only, Nx-only, or Nx + Melos. Triggers when: set up a monorepo, Melos vs Nx, Flutter bridge, uv workspace, npm workspaces, affected builds, graph audit, implicitDependencies, join a workspace, do not add Nx."
allowed-tools: Read, Bash, Glob, Grep
metadata:
  triggers: polyglot monorepo, Melos vs Nx, native-only, Melos-only, Nx-only, Nx + Melos, Flutter bridge, uv workspace, npm workspaces, affected builds, graph audit, join a workspace, do not add Nx
  related-skills: flutter-mobile, uv-package-manager, architecture-design, python-dev, angular-spa, java-spring-api, mcp-builder
  domain: architecture
  role: architect
  scope: design
  output-format: document
last-reviewed: "2026-11-27"
---

## Iron Law

**Language-native package managers first. Pick one of four modes, then stop for human approval before setup or migration. Never add Nx, `melos.yaml`, or a second orchestrator without that approval. Fail closed if the dependency graph cannot prove affected-task correctness. Never cache deploy, migrate, release, docker-push, or unverified generated-code tasks.**

# Polyglot Monorepo (MONO-ARCH-001)

On-demand decision skill. It does **not** replace Melos, uv, npm, Gradle/Maven, or Nx docs. Discover topology, recommend a mode, map edges, get approval, then load the stack skill that owns implementation.

Architecture: [docs/Nx_Melos_Polyglot_Monorepo_Architecture_Spec.md](../../../docs/Nx_Melos_Polyglot_Monorepo_Architecture_Spec.md) (MONO-ARCH-001).

Official docs (re-check before pinning): [Nx multi-language](https://nx.dev/docs/features/multi-language-support) · [Nx project configuration](https://nx.dev/docs/reference/project-configuration) · [Nx affected](https://nx.dev/docs/features/ci-features/affected) · [Nx AI](https://nx.dev/docs/getting-started/ai-setup) · [Nx MCP](https://nx.dev/docs/reference/nx-mcp) · [Melos](https://melos.invertase.dev/) · [Melos agents](https://melos.invertase.dev/agents) · [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/) · [npm workspaces](https://docs.npmjs.com/cli/using-npm/workspaces)

Nx **24** selects **tasks from declared inputs**, not from project edges alone (`implicitDependencies` is not proof). New workspaces must not set `affected.legacy`. Resolve Git `base` from the actual repository; do not assume `main`.

## 1. Discover (do this first)

```bash
python3 .claude/skills/polyglot-monorepo/scripts/discover_monorepo.py --root <repo>
python3 .claude/skills/polyglot-monorepo/scripts/discover_monorepo.py --find-host <path>
```

Treat the JSON as the inventory. Do not invent a fourth package manager. Do not rewrite lockfiles.

| Signal | Means |
|--------|--------|
| Root `pubspec.yaml` `workspace:` | Dart pub workspace |
| Root `dev_dependencies.melos` + `melos:` | Melos 7+/8 (no `melos.yaml`). Default when **two or more** Dart packages. Kit pin **8.10.1**. |
| `melos.yaml` | Legacy Melos 6 — migrate, do not extend |
| `[tool.uv.workspace]` | uv workspace |
| `package.json` `workspaces` | npm workspaces (`"*"` for members; not yarn `workspace:`) |
| `settings.gradle*` / `pom.xml` | Java — Gradle preferred for Nx; keep Maven if already used |
| `nx.json` | Nx **already** in use — keep; do not rip out |
| `turbo.json` | Keep Turbo for JS; do **not** add Nx |
| `Makefile` / `Taskfile.y*ml` / `Taskfile.dist.yml` | Lightweight polyglot orchestrator |

`recommendation.mode` is one of `native-only` · `melos-only` · `nx-only` · `nx-plus-melos`. `mode_status` `candidate-needs-approval` is **not** permission to add Nx.

## 2. Four architecture modes

| Mode | When | Package/build tools | Orchestration |
|------|------|---------------------|---------------|
| **NATIVE ONLY** | Single app or small tightly coupled repo | Flutter/pub, pnpm/npm, Gradle/Maven, uv | Makefile/Taskfile only if cross-language tasks exist |
| **MELOS ONLY** | Flutter/Dart multi-package, no substantial JS/Java/Python | Dart Pub Workspaces + Melos | Melos owns Dart selection; no Nx |
| **NX ONLY** | Angular/React/Node/NestJS, Java/Spring Boot, optional Python — **if justified** | pnpm/npm; Gradle/Maven; uv | Nx owns non-Flutter graph/affected/cache |
| **NX + MELOS** | Flutter **plus** substantial JS/TS, Java, and/or Python — **if justified** | All relevant native tools | Nx non-Flutter + **one** Flutter bridge project; Melos owns Dart |

Nx + Melos is the **reference pattern for complex polyglot repos that include Flutter**, not a mandatory default. Python and Java are **not** auto-discovered as JS imports are. Use explicit `implicitDependencies` or a verified plugin (`@nx/gradle` for Gradle; `@nxlv/python` is community — prove its graph before trusting it). Details: [reference/modes-and-bridge.md](reference/modes-and-bridge.md).

## 3. Agent workflow (required)

`Discover → Recommend mode → Map project/contract edges → Human approval → Scaffold or migrate → Graph/affected/cache tests → Review → Report`

1. Run discover. Record `mode`, `mode_status`, package managers, Git baseline (`detected.git_baseline`).
2. If the mode would add `nx.json` or a Flutter bridge: **stop**. Show the recommendation. Do not run `nx init` until the human approves and the command carries `CC_NX_INIT=1`.
3. Map OpenAPI, Protobuf, generated clients, and shared libraries as **explicit** edges plus task `inputs`/`outputs`.
4. Scaffold with existing `/scaffold-*` (join steps). There is **no** `/scaffold-monorepo`.
5. After Nx or a bridge exists, run the graph audit. Fail closed on missing projects, missing Python/Java edges, duplicate Flutter bridges, cached side-effect tasks, or undeclared generated-code cache.

```bash
python3 .claude/skills/polyglot-monorepo/scripts/audit_monorepo_graph.py --root <repo> --expect <expect.json>
```

Expect schema and fail-closed rules: [reference/graph-audit.md](reference/graph-audit.md).

## 4. Nx + Melos ownership (when NX + MELOS is approved)

| Responsibility | Owner |
|----------------|-------|
| Dart lockfile | Dart Pub Workspaces |
| Flutter package selection, lint, test, codegen | **Melos only** |
| JS/TS dependencies | pnpm/npm workspaces |
| Java incremental compile | Gradle/Maven (`@nx/gradle` when compatible) |
| Python envs/lockfiles | uv (`uv run pytest` from Nx targets) |
| Non-Flutter graph / affected / cache | Nx |
| Flutter cross-stack coordination | **One** Nx project (`flutter-workspace`) that **delegates** to Melos |
| Independent app versions and deploy pipelines | Each product — no monorepo-wide `melos version` / Nx release train |

Do not model every Dart package as an Nx project. Do not run Melos affected **and** Nx affected on the same Dart tests.

Nx 24: declare `inputs` (including `^default` / `^production` for dependents) or a contract change will **not** select the Flutter `verify` task. `cache: false` on the bridge until generation is proven deterministic.

## 5. Greenfield vs migration

**Greenfield:** language workspace first (`/scaffold-flutter-app`, `/scaffold-python-api`, `/scaffold-angular-app`, `/scaffold-spring-api`, `/scaffold-mcp-server`). Then join — [reference/discover-and-migrate.md](reference/discover-and-migrate.md). Mode approval happens in `/design-architecture` and `/new-project` before any `nx init`.

**Migration:** additive. Keep lockfiles. Phases 0–6 and rollback in MONO-ARCH-001 §10. Native commands must keep working after Nx or the bridge is removed.

Hook: `block-raw-scaffold.sh` blocks raw Nx init unless `CC_NX_INIT=1`, and blocks **new** `nx.json` / `melos.yaml`. Never run `nx configure-ai-agents` on this kit (it rewrites `CLAUDE.md` / MCP). Never overwrite this kit's `CLAUDE.md`, `AGENTS.md`, or `.mcp.json`.

## 6. Route implementation (do not copy it here)

| Need | Load |
|------|------|
| Melos scripts, `resolution: workspace`, `dart run melos` | `flutter-mobile` → `reference/flutter-build-and-workspace.md` |
| uv members, `--all-packages`, version islands | `uv-package-manager` |
| FastAPI service as a member | `python-dev` + `/scaffold-python-api` |
| Angular CLI + npm workspaces | `angular-spa` + `/scaffold-angular-app` |
| Java/Spring | `java-spring-api` + `/scaffold-spring-api` |
| MCP as an npm member | `mcp-builder` + `/scaffold-mcp-server` |
| System C4 / ADR | `architecture-design` + `/design-architecture` |
| Nx cache, MCP, `configure-ai-agents` | [reference/nx-and-mcp.md](reference/nx-and-mcp.md) — product repo only |

Do **not** copy Invertase Melos skills or Nrwl Nx skills into this kit. Do **not** register Melos MCP. Do **not** enable Nx MCP in a repo without `nx.json`.

## 7. Safeguards

1. Native PMs: pub / uv / npm / Gradle / Maven. Nx orchestrates; it does not replace them.
2. Independent app and service versions stay in each package manifest.
3. No unsolicited Nx. Human says yes; then `CC_NX_INIT=1`.
4. One affected-test owner per language. Unique Flutter bridge when Nx + Melos.
5. Never cache `deploy` / `migrate` / `release` / `docker-push`. Generated/codegen/OpenAPI start at `cache: false`.
6. Cross-language contracts: committed snapshot **and** explicit graph edges **and** task inputs. Snapshot CI still runs.
7. Git `base` from the repo (`origin/HEAD`, then existing local default), never a hardcoded `main`.
8. Never Write/Edit lockfiles; never delete workspace members to “simplify.”
9. Graph audit fail-closed → do not enable affected-only CI gates.

## Verify

```bash
python3 .claude/skills/polyglot-monorepo/scripts/discover_monorepo.py --selftest
python3 .claude/skills/polyglot-monorepo/scripts/audit_monorepo_graph.py --selftest
python3 .claude/skills/writing-skills/scripts/check-skill-spec.py --dir .claude/skills \
  --prompt "Should this polyglot monorepo use native-only, Melos-only, Nx-only, or Nx + Melos?" \
  --expect polyglot-monorepo --forbid java-spring-api
```

Live Nx/Melos fixture matrix (writes under `$TMPDIR`, never the toolkit). Do **not** pass `--offline` when claiming affected-task PASS (`--offline` exits non-zero):

```bash
python3 .claude/skills/polyglot-monorepo/scripts/run_fixture_matrix.py
```

Exit 0 on the selftests **and** the live fixture matrix. If `detected.git_baseline_status` is `unresolved`, do not set `defaultBase` to the current branch.

**READY checklist (product repo):** map MONO-ARCH-001 §11.1–10 to executed evidence or NOT RUN. ADOPT only after zero known false negatives; otherwise PILOT, NATIVE ONLY, or BLOCKED.
