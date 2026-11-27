# Nx + Melos Polyglot Monorepo Architecture Specification

**Document ID:** MONO-ARCH-001  
**Version:** 1.0 — Proposed  
**Date:** November 27, 2026  
**Intended use:** Architecture standard and implementation guidance for the `claude-code-onboarding` toolkit  
**Status:** Proposed design; no repository configuration or runtime performance validation is implied

## 1. Executive decision

**Adopt Nx + Melos as the *reference pattern for sufficiently complex polyglot monorepos that include Flutter/Dart*, not as a mandatory default for every repository.**

- **Melos** owns Flutter/Dart package-aware operations, operating over **native Dart Pub Workspaces**.
- **Nx** owns the non-Flutter project/task graph, affected-task selection, orchestration, and eligible task caching. In a full polyglot repository it also provides the **cross-stack coordination view**.
- **Native tooling** retains dependency resolution, compilation, testing, and artifact production: `dart pub`/Flutter, `pnpm` or npm, Gradle or Maven, and `uv`.
- **Explicit integration bridges** link API contracts and generated clients across technology boundaries. Neither graph is assumed to infer dependencies across all languages.
- Each executable task has **one owner**. Do not introduce two independent, competing Flutter task schedulers or release/versioning systems.

This is a recommended integration pattern assembled from the capabilities of Nx and Melos, **not an official Nx–Melos combined product or a guarantee of faster builds**. Adoption requires a verified project graph, correct task inputs and outputs, and benchmark evidence.

## 2. Goals, non-goals, and measurable benefits

### Goals

1. Identify and execute only impacted build, test, lint, and validation work, including dependent projects.
2. Reuse safe, reproducible results through Nx local/remote caching where configured.
3. Maintain accurate dependency and task graphs across JS/TS, Java, and optionally Python; preserve Melos's Dart-aware package graph.
4. Detect backend-to-client contract changes (OpenAPI, Protobuf, schemas) and trigger affected Flutter work.
5. Preserve native build optimizations, independent application releases, and reproducible lockfiles.
6. Supply reliable, inspectable project/task metadata to Claude Code and CI.

### Non-goals

- Replacing Flutter/pub, Java Gradle/Maven, Python uv, or JS package managers with Nx.
- Installing Nx for every single application, Python service, or Flutter package.
- Modeling every Flutter package as a separate Nx project by default.
- Applying unified versioning to independently deployed mobile apps and services.
- Treating cache hits as valid without verifying inputs, outputs, and environment dependencies.
- Claiming CI speedups before comparable baseline measurements.

### Expected benefits and how to measure them

| Benefit | Mechanism | Evidence required |
|---|---|---|
| Less unnecessary execution | Nx affected tasks, Melos package-aware filtering | Compare selected vs full-project tasks for representative diffs |
| Faster repeat builds | Nx task cache, native Gradle/JS caching | Cold/warm build time and cache hit correctness |
| Safer change impact | Explicit graph edges and API contract gates | Contract-change scenarios with no missed dependents |
| Better developer experience | Unified task discovery + native toolchains | Setup steps, command count, developer feedback |
| More reliable AI actions | Deterministic project/task queries | Agent uses real project names/targets instead of invented commands |

## 3. Architecture selection policy

| Repository topology | Default mode | Package/build tools | Decision criteria |
|---|---|---|---|
| Single app or small, tightly coupled services | **Native tools only** | Flutter/pub, pnpm/npm, Gradle/Maven, uv | Avoid orchestration overhead unless measured pain exists |
| Flutter/Dart multi-package | **Melos only** | Native Pub Workspaces, Flutter, `build_runner` | Dart package-aware scripts, ordered builds, dependent tests |
| JS/TS-heavy, Java, or mixed non-Flutter repository | **Nx only, if justified** | pnpm/npm; Gradle/Maven; optional uv | Multiple projects, shared libraries, affected tasks and CI/caching value |
| Flutter plus substantial JS/TS, Java, and/or Python | **Nx + Melos, if justified** | All relevant native tools | Genuine cross-stack dependencies and enough build/test scale to justify bridge maintenance |

**Selection guardrails:**

- Nx is a **preferred orchestration candidate**, not an automatic requirement for all Java or Python workspaces.
- Python requires deliberately configured projects and dependency edges; native JS/TS graph inference must not be assumed for `pyproject.toml` imports. Use explicit `implicitDependencies` or a verified plugin.
- For Java, prefer the supported **`@nx/gradle` integration** for Gradle repositories; preserve Maven in Maven-native projects and confirm the current maturity of `@nx/maven` before adoption.
- For Flutter, native Pub Workspaces own package resolution and the lockfile; Melos adds scoped orchestration. Verify Melos commands against the chosen major version. Do not assume legacy `melos bootstrap`, `melos.yaml`, or release workflows are required.
- A lightweight Makefile, `just`, or Taskfile remains appropriate for small polyglot repositories.

## 4. Reference architecture and ownership

```text
                            Developer / Claude Code / CI
                                        |
                               Nx (when adopted)
                   project graph | affected | task DAG | safe cache
                    /             |               |             \
          JS/TS projects    Java projects    Python projects    Flutter bridge
          pnpm/npm          Gradle/Maven      uv                 single Nx project
          Angular/React     Spring Boot       FastAPI/ADK/MCP         |
                                                              Melos (Dart package graph)
                                                                   |
                                                          Native Dart Pub Workspaces
                                                                   |
                                                        Flutter apps + shared packages

        Cross-stack contracts: OpenAPI / Protobuf / generated clients
        Explicit Nx dependency edges + deterministic contract validation
```

| Responsibility | Owner | Constraint |
|---|---|---|
| Dart dependencies and lockfile | Dart Pub Workspaces | One established source of truth |
| Flutter package selection, lint, test, codegen scripts | Melos | One Flutter task-selection owner |
| JavaScript/TypeScript package dependencies | pnpm/npm workspaces | Nx orchestrates, does not replace resolver |
| Java multi-module incremental compilation | Gradle/Maven | Avoid competing individual Gradle invocations/daemons |
| Python environments, packages, lockfiles | uv | Nx targets invoke uv when warranted |
| Non-Flutter project graph / affected / cache | Nx | Validate inferred and hand-configured edges |
| Flutter cross-stack coordination | Nx **bridge project** | Delegate work to Melos; do not duplicate the internal Dart graph |
| Cross-language compatibility | Schema/contract pipeline | Regenerate and compare artifacts; test consumers |
| Container images, deployments, credentials | Existing CI/CD and release tooling | Preserve environment boundaries and immutable artifacts |
| Independent app/service versions | Each product's release mechanism | No blanket Melos/Nx release train |

## 5. Cross-stack Flutter bridge design

### The dependency blind spot

An API service can change a schema consumed by a generated Dart client. Nx cannot infer all Dart-level impacts, and Melos cannot see the Java/Python service graph. A pure per-language `affected` check can therefore miss work.

### Recommended bridge

1. Represent the Flutter workspace as **one Nx project** (a leaf or boundary project) for cross-stack orchestration, rather than creating an Nx project for each Dart package.
2. Declare explicit project dependencies on contract-producing projects or a dedicated `api-contracts` project.
3. Nx selects the Flutter bridge when the relevant contract inputs change.
4. The bridge executes **one canonical Melos target**. Melos determines internal Flutter work using its supported package filters.
5. Contract CI validates schemas and generated clients, independent of Nx graph inference.
6. Test a backend contract change, a shared Dart-package change, and an unrelated documentation change to prove both inclusion and exclusion behavior.

**Important correctness rule:** `implicitDependencies` express project-level dependency relationships, but task-level affected selection also depends on configured inputs and target semantics. A graph edge by itself is **not proof** that every relevant contract change triggers every required task. Verify this with fixtures.

**Illustrative Nx bridge (adapt target names and inputs to the actual workspace):**

```json
{
  "name": "flutter-workspace",
  "root": "flutter",
  "implicitDependencies": ["api-contracts"],
  "targets": {
    "verify": {
      "command": "dart run melos run test:all",
      "options": { "cwd": "flutter" },
      "cache": false
    }
  }
}
```

The example assumes `flutter/pubspec.yaml` defines `melos.scripts.test:all`. The exact bridge must be checked against the installed Nx/Melos versions and tested; **`cache: false` is the conservative starting setting**, not a claim that all Flutter tasks can never be cached. The bridge's selection and Melos's internal filtering must use a consistent, valid Git comparison base. A whole-workspace test is a safe initial fallback while the affected-selection bridge is being proven.

## 6. Native stack integration

### 6.1 Flutter/Dart — Melos

- Use native Pub Workspaces for local package linking and a coherent lockfile.
- Use Melos scripts/filters for scoped format, analyze, tests, and ordered `build_runner` tasks.
- Retain independent mobile app/build-number lifecycles; do not enable monorepo-wide automatic version bumping by default.
- Keep generated Dart outputs and task inputs explicit; disable cross-stack cache until deterministic generation is proven.
- Verify script names, filter flags, and layout against the **installed Melos major version**, not legacy tutorials.

### 6.2 Angular, React, Node, and TypeScript MCP — Nx

- Keep pnpm/npm workspace resolution and JS build tooling intact.
- Use Nx's official supported plugins for the actual frameworks; rely on the project graph, affected-task selection, and cache only after auditing inputs/outputs.
- Preserve API contract and generated-client dependencies, including changes originating outside JS packages.

### 6.3 Java/Spring Boot — Nx + Gradle/Maven

- Gradle remains responsible for Java compilation, incremental work, and its internal task graph.
- Prefer `@nx/gradle` where compatible, avoiding manually spawning a Gradle daemon per Nx subproject target.
- Keep Maven when already established; verify `@nx/maven` maturity and supported Nx/Java versions before adoption.
- Validate cross-language dependencies separately from Java project relationships.

### 6.4 Python/FastAPI/ADK — Nx + uv (conditional)

- Keep `uv` as dependency manager and workspace/lockfile owner.
- Define Nx Python `project.json` tasks only when affected-project orchestration benefits justify configuration.
- Explicitly model shared-library and service dependencies, or validate any community plugin's actual graph output.
- Example task command: `uv run pytest` executed in the correct workspace context.
- Account for Python version islands, platform-specific wheels, native dependencies, and environment inputs.

## 7. Task scheduling, affected selection, and caching rules

### Affected correctness

1. Maintain a representative change-impact test matrix for source, shared packages, contracts, lockfiles, generated files, and root tool configuration.
2. Compare Nx-selected tasks and Melos-selected packages with an independent known-correct baseline.
3. Include a scheduled full-build/full-test sampling audit; selection must produce **zero known false negatives** before relying on affected-only CI gates.
4. Prefer conservative over-selection when graph completeness is uncertain.
5. Confirm Git base/head values are valid in shallow CI checkouts and merge-queue contexts.

### Caching correctness

**Cache eligibility is per task, not per language.** A task is eligible only when its inputs, environment/toolchain dependencies, side effects, and outputs are deterministic and completely represented.

| Task/artifact class | Initial policy | Upgrade condition |
|---|---|---|
| Pure unit tests, lint, reproducible JS builds | Evaluate caching | Correct inputs, lockfiles, toolchain versions, output semantics |
| Dart `build_runner` and generated `*.g.dart` | Disable Nx caching initially | Prove inputs and generated outputs complete and repeatable |
| OpenAPI/Protobuf generation and cross-language snapshots | Disable initially | Include producer contracts, generator version and outputs; gate diffs |
| Database migrations or schema mutation | **Do not cache execution** | Keep migrations as ordered, auditable side effects |
| Docker image creation and release promotion | Keep under supply-chain/release controls | Avoid treating env-specific or signed artifacts as ordinary cache outputs |
| Deployments, secrets, environment-specific tasks | **Never cache execution** | N/A: side-effectful operations |

- Pin versions and include `pnpm-lock.yaml`/`package-lock.json`, `uv.lock`, `pubspec.lock`, Gradle configuration/locks, code-generator versions, and relevant environment inputs.
- Separate local cache, remote cache, and CI artifacts; do not let caches bypass integrity checks or secrets boundaries.
- Configure `dependsOn`, target inputs, and outputs against the current Nx release and inspect the resulting task graph.

## 8. CI/CD reference workflow

1. **Discover** changed files against the correct base and read the project's graph/contract metadata.
2. **Plan** affected Nx tasks; evaluate the Flutter bridge and corresponding Melos package scope when applicable.
3. **Validate contracts** (OpenAPI/Protobuf/schema snapshots and generated clients).
4. **Execute** native tasks through Nx/Melos with bounded parallelism and validated cache policies.
5. **Test** security, integration, migration, and release gates that cannot be inferred safely from source imports.
6. **Publish** immutable build artifacts once; promote by verified digest rather than rebuilding for each environment.
7. **Audit** periodically by comparing affected-only selection against full validation.

Keep platform-specific Flutter/iOS builds on appropriate runners. A green `nx affected` result **cannot replace** contract compatibility, migration safety, secret scanning, integration tests, or deployment approval.

## 9. Claude Code onboarding integration specification

The public toolkit should provide an **on-demand monorepo decision capability**, not automatically install both orchestration products.

**Reuse or add the minimum assets:**

- **One architecture-selection skill** (or extend an existing equivalent): discover topology, compare four modes, produce a dependency/task graph plan, assess migration cost, and identify cross-stack edges.
- **Existing architecture/scaffolding commands:** invoke the decision skill, require approval before changing `nx.json`, `project.json`, `pubspec.yaml`, lockfiles, CI, or root instructions.
- **Existing Flutter, JS, Java, Python skills:** own language-specific setup and validation.
- **Existing review/security checks:** verify graph completeness, release boundaries, caching and credentials; avoid a large always-loaded rule or redundant agent.
- **Optional Nx MCP/AI setup:** enable only in actual Nx projects. Verify its current scope and review generated `CLAUDE.md`, `AGENTS.md`, and MCP files before accepting any changes.
- **Optional Melos documentation/agent references:** load on demand. Do not require a separate Melos MCP solely for docs if existing documentation integrations suffice.

**Agent workflow:** `Discover → Recommend mode → Map project/contract edges → Human approval → Scaffold or migrate → Graph/affected/cache tests → Review → Report`.

Claude Code must query actual Nx/Melos project and task metadata when those tools are present; it must not invent project names or assume a complete Python/Flutter dependency graph.

## 10. Adoption and migration plan

| Phase | Activities | Exit gate |
|---|---|---|
| 0. Baseline | Inventory toolchains, lockfiles, project graph, cross-language contracts; measure build/test timing | Baseline and ownership map documented |
| 1. Native workspaces | Ensure pub/Melos, JS workspace, uv, and Gradle/Maven builds work independently | Clean native builds/tests reproducible |
| 2. Nx non-Flutter | Introduce Nx where justified; configure JS/Java/Python projects and dependencies | Project graph reviewed; no missing known edges |
| 3. Flutter bridge | Add single Nx Flutter boundary project; map API contracts to Flutter verification | Backend contract changes reliably select Flutter checks |
| 4. Cache pilot | Enable cache only for deterministic tasks; test clean/warm and invalidation cases | No stale hit; reproducible outputs; measured improvement |
| 5. CI rollout | Run affected selection alongside full-validation sampling; tune runners | Zero false-negative gates over agreed pilot period |
| 6. Operate | Document ownership, upgrades, graph drift checks, rollback | Stable maintenance and improvement metrics |

**Rollback:** Keep native commands and lockfiles valid at every phase. Remove Nx integration or the Flutter bridge independently without losing Melos/Gradle/uv/pnpm functionality. Avoid bulk migrations, production deployments, or forced unified releases as part of tool introduction.

## 11. Acceptance criteria and required test scenarios

The architecture is **READY for a specific repository** only after executable checks demonstrate:

1. Changes to a JS shared library select all relevant JS consumers and skip unrelated projects.
2. Changes to a Python shared workspace library select dependent FastAPI/agent services using explicit verified graph edges.
3. Changes to a Java shared module select dependents without subverting Gradle's own incremental/task graph.
4. Changes to an OpenAPI/Protobuf contract select the generating service/contract gate, relevant JS clients, and Flutter bridge.
5. A shared Dart package change selects affected Flutter apps through Melos, without duplicate Nx Flutter scheduling.
6. An unrelated documentation change does not unnecessarily trigger an expensive full build unless documentation is an explicit task input.
7. A changed lockfile, generator/toolchain version, or environment dependency invalidates appropriate caches.
8. No cached result skips migration execution, deployment approval, secret scanning, or other mandatory safety gate.
9. Full-validation sampling detects no missing impacted tasks; failed graph checks block affected-only gating.
10. Individual applications and services retain independent versions and release controls.

**Decision states:** **ADOPT** (proved need and checks pass); **PILOT** (potential value, graph/caching not yet demonstrated); **NATIVE ONLY** (orchestration cost exceeds benefit); **BLOCKED** (known missed dependencies or unsafe caching).

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Nx/Melos separate graphs miss backend→Flutter clients | Explicit bridge project, contract inputs, contract CI and fixture tests |
| Python dependency graph is incomplete | Hand-written `implicitDependencies` or tested plugin; fail conservative |
| Nx duplicates Gradle/Melos scheduling | Native Gradle plugin; Nx single Melos boundary target |
| Stale cache of generated artifacts | Conservative initial exclusions; comprehensive hashes and reproducibility tests |
| Unplanned release coupling | Keep per-app versions and independent pipelines |
| Tool upgrades break commands | Lock versions; verify current docs, plugin compatibility, migration notes |
| AI setup overwrites project governance | Human review before `configure-ai-agents` and any generated config |
| Nx complexity exceeds benefit | Four-mode decision tree and benchmark-based adoption |

## 13. Official reference documentation

- **Nx multi-language:** https://nx.dev/docs/features/multi-language-support
- **Nx project/dependency configuration:** https://nx.dev/docs/reference/project-configuration
- **Nx affected selection:** https://nx.dev/docs/features/ci-features/affected
- **Nx inputs:** https://nx.dev/docs/reference/inputs
- **Nx caching:** https://nx.dev/docs/features/ci-features/remote-cache
- **Nx Gradle:** https://nx.dev/docs/technologies/java/gradle/introduction
- **Nx Maven:** https://nx.dev/docs/technologies/java/maven/introduction
- **Nx AI setup:** https://nx.dev/docs/getting-started/ai-setup
- **Melos:** https://melos.invertase.dev/
- **Melos commands and filters:** https://melos.invertase.dev/commands/run and https://melos.invertase.dev/filters
- **Melos migrations:** https://melos.invertase.dev/guides/migrations
- **Melos agent guidance:** https://melos.invertase.dev/agents
- **uv workspaces:** https://docs.astral.sh/uv/concepts/projects/workspaces/

> **Source and verification notes:** This specification consolidates three expert assessments and incorporates checks against official Nx/Melos documentation on November 27, 2026. Statements about the combined Nx–Melos boundary, Python dependency edges, cache policy, and adoption gates are **architecture recommendations** requiring verification in each target repository. Sample config is illustrative, not an executed reference implementation. Version-dependent flags, Nx Java integration maturity, and Melos configuration must be confirmed at implementation time.
