# Discover, join, migrate

Load from `polyglot-monorepo` after the decision tree. Implementation details stay in stack skills.

## Join an existing workspace (scaffolds)

Resolve the host with `discover_monorepo.py --find-host <path>` (prints the host directory, exit 1 if none). Then `discover_monorepo.py --root <host>`:

### Dart / Melos

Already in `/scaffold-flutter-app` step 12 and `/scaffold-flutter-package`. Host is root `pubspec.yaml` with `workspace:`.

1. Add the new path to root `workspace:`.
2. Set `resolution: workspace` on the member.
3. Depend on sibling packages **by name** (version constraint the local version satisfies), not `path:`.
4. `dart run melos bootstrap` at the root (Melos is a root `dev_dependency`; Melos 7+ has no `melos.yaml`). Affected Dart tests: `melos exec --diff=<ref> --include-dependents` (or the repo's `flutter-test-changed` script).
5. Do **not** `flutter pub get` only inside the new app as the workspace convention.

Details: `flutter-mobile/reference/flutter-build-and-workspace.md`.

### uv / Python

`/scaffold-python-api` and `/scaffold-python-worker` join when the ancestor `pyproject.toml` has `[tool.uv.workspace]`.

1. Create the service **as a directory under the host**, not a second git root with its own `uv.lock`, unless `requires-python` conflicts.
2. Append the path to `[tool.uv.workspace].members` only if it is not already listed.
3. In the member: `[tool.uv.sources] <host-lib> = { workspace = true }` for shared packages.
4. `uv lock` then `uv sync --locked --all-packages` at the **host**.
5. A member that cannot resolve on the host Python (e.g. wheels only to 3.13) stays **excluded**, with its own `.python-version` and `uv.lock` (`uv-package-manager`).

### npm / Angular / MCP

`/scaffold-angular-app` and `/scaffold-mcp-server` join when an ancestor `package.json` has `workspaces`.

1. Scaffold the app/server in a path the host already lists, or add the path to `workspaces`.
2. Shared libraries use `"@scope/name": "*"` (npm workspaces). Do **not** write yarn `workspace:` protocol.
3. Scaffold with `--skip-install` (Angular) or skip nested `npm install` (MCP). `npm install` at the **host**, then `npm ci -w <name>` if you need a workspace-scoped install. One `package-lock.json`. Do not commit a nested lockfile.
4. Root scripts that test only one app are not “affected”; add a path-filtered script or run the workspace that changed. Nx is not required for five npm members.

## Greenfield mixed repo (no Nx)

```
/
  pubspec.yaml          # Dart workspace + melos:
  package.json          # npm workspaces
  pyproject.toml        # [tool.uv.workspace]
  Makefile              # compose, gates, release
  apps/                 # Flutter
  packages/             # Dart shared
  web/                  # Angular
  services/             # Python
  mcp/                  # TypeScript MCP
```

Do not add `nx.json`. Do not add `melos.yaml`. Independent `version:` / npm `version` / Python `version` per deployable.

## Safe migration of an existing repo

| Change | Allowed without extra approval | Needs explicit human yes |
|--------|--------------------------------|--------------------------|
| Add a member to an existing Dart/uv/npm workspace | Yes (scaffold join steps) | — |
| Add Melos scripts to an existing Dart workspace | Yes | — |
| Introduce `nx.json` / `nx init` / `create-nx-workspace` | No | `CC_NX_INIT=1` after the human agrees |
| `nx configure-ai-agents` (rewrites `CLAUDE.md` / MCP) | No | Same marker; never on this onboarding kit |
| Replace `uv.lock` / `package-lock.json` / `pubspec.lock` via Write | Never | Package manager via Bash only |
| Split a uv member out because of `requires-python` | Yes (document why) | — |
| Run `melos version` across independently shipped apps | No | Product policy; default is per-app pubspec |
| Delete workspace members or lockfiles to “simplify” | No | — |

Rollback: git revert the host manifest + lockfile together. Never restore a lockfile by hand.

## Affected tests (one owner per language)

| Language | Owner | Fallback |
|----------|--------|----------|
| Dart | `melos exec --diff=<ref> --include-dependents` (or the repo’s `flutter-test-changed` script) | Full `melos run test:*` when the change is outside a package |
| Python | Makefile / pytest path selection / CI `paths:` | `uv run pytest` at the host |
| JS/TS | npm `--workspace=` on changed workspaces; Nx `affected` **only if** `nx.json` exists | Root `npm test` is not dependents-aware |
| Cross-language contract | Snapshot gate (OpenAPI JSON + generated client) | Always run when either side changes |

Unknown blast radius → full suite for that language, never skip.

## Makefile / Taskfile

Use for compose profiles, env files, release, and grep gates that are not a package graph. Do not rewrite a working Makefile into Nx targets. Do not add Taskfile **and** Nx **and** Melos as three parallel CLIs for the same job.
