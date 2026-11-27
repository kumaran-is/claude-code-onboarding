# Four modes, Flutter bridge, Git baseline

Load from `polyglot-monorepo` after discover. Architecture: `docs/Nx_Melos_Polyglot_Monorepo_Architecture_Spec.md` (MONO-ARCH-001).

## Mode selection (do not skip approval)

| Discover signals | Mode | `mode_status` |
|------------------|------|----------------|
| Single package / small mixed (Flutter + few npm/uv members, no Java multi-module) | `native-only` | `recommend` |
| Dart workspace with Melos (or 2+ Dart packages), no substantial non-Flutter | `melos-only` | `recommend` |
| `nx.json` present, no Dart workspace | `nx-only` | `keep` (`justified` if npm members ≥ 8 or 2+ Java modules) |
| npm members ≥ 8 **or** 2+ Java modules, no Dart, no `nx.json` | `nx-only` | `candidate-needs-approval` |
| `nx.json` + Dart/Melos | `nx-plus-melos` | `keep` |
| Dart/Melos **and** substantial JS/Java/Python, no `nx.json` | `nx-plus-melos` | `candidate-needs-approval` |
| `turbo.json` present, no `nx.json` | keep Turbo; mode `native-only` | `do-not-add` Nx |

**Substantial** (toolkit heuristic, overridable by the human): expanded npm members ≥ 8, **or** Gradle/Maven with ≥ 2 included modules, **or** (npm members ≥ 3 **and** uv members ≥ 2 **and** Dart). Small mixed repos stay **native-only** with a Makefile.

`candidate-needs-approval` is a recommendation only. Do not run `nx init` until the human approves.

## Native tooling (all modes)

| Stack | Resolver / compiler | Orchestration allowed |
|-------|---------------------|------------------------|
| Flutter/Dart | Dart Pub Workspaces + `pubspec.lock` | Melos 8.x (`dart run melos`); kit pin 8.10.1; no `melos.yaml` |
| Angular / React / Nest / MCP | pnpm or npm workspaces + lockfile | Nx **if** mode is NX ONLY or NX + MELOS |
| Java | Gradle (preferred for Nx) or Maven | `@nx/gradle` when Java ≥ 17 and Gradle ≥ 8; keep Maven if already used — confirm `@nx/maven` maturity first |
| Python | uv workspaces + `uv.lock` | Nx `project.json` that runs `uv run …` **and** explicit edges |

Nx does not replace any row.

## Flutter as one Nx bridge (NX + MELOS only)

Do **not** create an Nx project per Dart package. One boundary project:

```json
{
  "name": "flutter-workspace",
  "root": "flutter",
  "implicitDependencies": ["api-contracts"],
  "targets": {
    "verify": {
      "command": "dart run melos run test:all",
      "options": { "cwd": "flutter" },
      "cache": false,
      "inputs": [
        "default",
        "^default",
        "{workspaceRoot}/contracts/**/*",
        "{workspaceRoot}/flutter/pubspec.lock"
      ]
    }
  }
}
```

Adapt names to the repo. The example assumes `flutter/pubspec.yaml` defines `melos.scripts.test:all`.

Nx 24 uses **task-based affected**: a project edge without matching `inputs` (especially `^default` / `^production` and the contract glob) will **not** select `flutter-workspace:verify` when OpenAPI/Protobuf changes. Verify with `nx affected -t verify --base=<git-baseline> --head=HEAD --explain`.

Melos owns internal Dart `--diff` / `--include-dependents` using the **same Git baseline**.

## Git baseline (never assume `main`)

Resolve in this order, in the **target repo**:

1. `git symbolic-ref refs/remotes/origin/HEAD` (upstream default)
2. `git rev-parse --abbrev-ref origin/HEAD`
3. First existing of `main`, `master`, `develop` **that this repo actually has**
4. Current branch if this is a new fixture with a single commit

Write that value into `nx.json` `defaultBase` and into Melos `--diff`. Shallow CI clones need `fetch-depth: 0` (Nx affected docs). Do not copy `defaultBase: "main"` from a tutorial if the repo default is `develop`.

Discover prints `detected.git_baseline`.

## Cache and contracts

| Class | Initial policy |
|-------|----------------|
| Unit test / lint / reproducible JS build | Cache only with complete `inputs` + lockfiles + toolchain |
| `build_runner` / `*.g.dart` / OpenAPI / Protobuf generation | `cache: false` until inputs, generator version, and outputs are proven |
| `migrate` / Alembic / schema mutation | **Never cache** |
| `deploy` / `release` / `docker-push` | **Never cache** |

Pin lockfiles as inputs: `package-lock.json` / `pnpm-lock.yaml`, `uv.lock`, `pubspec.lock`, Gradle lock/configuration.

## Independent releases

Each shipped app keeps its own `version` / build number. Do not `melos version` or Nx release across independently deployed units. CI images stay environment-isolated; promote by digest.

## Rollback

Native `dart` / `npm` / `uv` / `gradle` commands and lockfiles stay valid at every phase. Removing `nx.json` or `flutter-workspace/project.json` must not break Melos or Gradle. Revert the host manifests + lockfiles together.
