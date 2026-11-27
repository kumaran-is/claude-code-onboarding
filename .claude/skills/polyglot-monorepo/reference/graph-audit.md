# Dependency-graph audit (fail closed)

Script: `scripts/audit_monorepo_graph.py`. Uses official Nx/Melos CLI output when `--root` has `nx.json` / Melos; `--graph-file` is for fixtures and `--selftest`.

Nx 24: `nx graph --file=<path>` writes the project graph; `nx affected -t <target> --base=<sha> --head=<sha>` / `nx show projects --affected -t <target>` select **tasks from inputs**. `nx graph --affected` still lists projects. Confirm flags on the **installed** Nx before teaching them.

## Expect JSON

```json
{
  "projects": ["web", "ui", "api-contracts", "flutter-workspace", "py-api", "py-lib"],
  "edges": [
    ["web", "ui"],
    ["flutter-workspace", "api-contracts"],
    ["py-api", "py-lib"]
  ],
  "flutter_bridge": "flutter-workspace",
  "python_projects": ["py-api", "py-lib"],
  "required_inputs": {
    "flutter-workspace:verify": ["^default", "{workspaceRoot}/contracts/**/*"]
  },
  "required_outputs": {},
  "never_cache": ["deploy", "migrate", "release", "docker-push"],
  "generated_targets": ["codegen", "openapi", "generate", "build_runner"]
}
```

`edges` are `[consumer, dependency]` — the consumer is selected when the dependency changes.

## Checks (any failure → exit 2, `verdict: FAIL`)

1. Every `projects` name exists in the Nx graph.
2. Every expected edge exists (static or implicit). Missing Python edges fail even if JS inference looks healthy.
3. At most one Flutter bridge (`flutter_bridge` or projects named `flutter-workspace`). It must depend on listed contract projects.
4. `never_cache` target names must have `cache` explicitly `false` (targetDefaults or project). Missing `cache: false` fails — Nx may cache by default.
5. `generated_targets` default to `cache: false`. `cache: true` or omitted cache on those names fails.
6. `required_inputs` / `required_outputs` substrings must appear on that `project:target`.
7. If `python_projects` is non-empty and no matching edges exist and `nx.json` plugins do not include a **verified** Python plugin whose graph was inspected in this repo, fail closed.
8. If `nx graph` / Melos CLI cannot be parsed, fail closed (do not skip).

A clean discover `nx_cache_unsafe` list is **advisory only** and does not replace this audit.

## Affected-task comparison (fixtures / CI)

After a Git baseline commit:

```bash
BASE=$(python3 -c "import json,sys; print(json.load(sys.stdin)['detected']['git_baseline'])" < discover.json)
npx nx show projects --affected -t verify --base="$BASE" --head=HEAD
```

Compare the printed project set to the **independent expected set** for that diff. Record:

- **False negative:** expected consumer missing → FAIL (blocks affected-only CI)
- **False positive:** extra cheap `verify` echo is a warning; extra `deploy`/`migrate` is FAIL

Unrelated docs-only diffs must not select expensive app/Flutter verify unless docs are declared inputs.

## Melos

When Melos is present:

```bash
dart run melos list --diff="$BASE"
```

Use the same `$BASE` as Nx. Do not treat Melos package names as Nx project names except the single bridge.

## CLI probe (before implementing new checks)

```bash
npx nx graph --help
npx nx affected --help
npx nx show projects --help
dart run melos list --help
```

Do not invent `--print-affected` (removed) or assume `@nx/maven` infers everything. `@nx/gradle` infers Gradle project relationships when the plugin **and** the `dev.nx.gradle.project-graph` companion plugin are installed and compatible; still declare cross-language contract edges by hand. Python/uv workspace members are **not** inferred from `pyproject.toml` imports — prove the graph: missing `implicitDependencies` must fail closed.

`scripts/run_fixture_matrix.py` exercises Melos `--diff` + `--include-dependents`, Nx Flutter-bridge selection, lockfile/toolchain cache invalidation, `@nx/gradle` inferred vs explicit edges, uv explicit vs inferred edges, and native rollback.
