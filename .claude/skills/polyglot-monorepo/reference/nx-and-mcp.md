# Nx, cache safety, and MCP (product repos only)

This kit is **not** an Nx workspace. Do not run `npx nx configure-ai-agents` here (it rewrites `CLAUDE.md` and MCP config). Do not register Melos MCP. Do not enable Nx MCP unless the **product** repo already has `nx.json`.

Official: [Nx AI setup](https://nx.dev/docs/getting-started/ai-setup) · [Nx MCP](https://nx.dev/docs/reference/nx-mcp) · [multi-language](https://nx.dev/docs/features/multi-language-support) · [Melos agents](https://melos.invertase.dev/agents) · [Melos MCP](https://melos.invertase.dev/mcp)

## When Nx is justified

All of:

1. Human approved (hook requires `CC_NX_INIT=1` for `nx init` / `create-nx-workspace`).
2. JS/TS is the bottleneck: many npm workspace members **and** measured CI cost for unaffected projects.
3. Flutter stays on Dart workspaces + Melos (Nx Flutter plugins are community; `@nxrocks/nx-flutter` is not Nx-23-safe).
4. Python stays on uv. Nx may wrap `uv run pytest` via `project.json`; it does not replace `uv.lock`.
5. Cross-language edges (OpenAPI → generated TS, Alembic → services) get **explicit** `implicitDependencies` or stay as snapshot gates.

Otherwise: npm workspaces + Makefile.

## Cache: never hit on these outputs

Nx restores outputs on a cache hit. That is wrong for:

| Output | Why |
|--------|-----|
| `build_runner` / `*.g.dart` / `*.freezed.dart` | Gitignored; environment and SDK skew; stale symbols |
| Alembic revisions | Not a compile cache; applied per environment |
| `openapi.json` / generated Zod/TS clients | Contract snapshots; must fail CI when stale, not restore |
| Docker images / Cloud Run digests | Digest promotion; env-specific |
| Gate results that depend on running containers | Content hash of source ≠ runtime |

Set `cache: false` on those targets, or do not model them in Nx. Prefer the repo’s content-addressed gate cache if it already exists.

## MCP — kit vs product

| Server | This onboarding kit | Product repo with `nx.json` | Product repo without `nx.json` |
|--------|---------------------|-----------------------------|--------------------------------|
| Nx MCP (`npx nx mcp`, Nx ≥ 21.4) | **Absent** | Optional, after human review | **Do not add** |
| Melos MCP | **Do not add** | **Do not add** | **Do not add** |
| `dart-mcp-server`, `angular-cli`, Context7 | Keep | Keep | Keep |

Melos MCP (official) is Invertase **docs.page** (`read_doc_page`, `list_doc_files`). It does not expose the repo graph. It duplicates Context7.

Nx MCP **default is `--minimal`**: Nx Cloud CI + running tasks. Workspace graph tools moved to Nx **skills**. Without Nx Cloud and without `nx.json`, the server has nothing useful to say and causes hallucinated `nx` commands.

### Enable Nx MCP only in a product repo that has `nx.json`

Add to **that repo’s** `.mcp.json` after a P0 scan (`skill-triggers.md`) and `session-mcp-governance.sh --approve`:

```json
"nx-mcp": {
  "type": "stdio",
  "command": "npx",
  "args": ["nx", "mcp"]
}
```

Prefer the workspace’s pinned `nx` binary over `nx-mcp@latest`. Do not pass `--no-minimal` unless the client has no skill support (token-heavy graph dumps).

`npx nx configure-ai-agents` writes `CLAUDE.md` / `AGENTS.md` and skills. Run it only in that product repo, with `CC_NX_INIT=1`, and review the diff. Never on this kit.

Invertase `dart run skills@ get` copies five Melos skills including **versioning**. Skip `melos-versioning` when apps ship independent store versions.
