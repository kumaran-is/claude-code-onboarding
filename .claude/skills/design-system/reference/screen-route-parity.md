# Screen ↔ route parity

Same-PR contract: a named screen in the project's design SSOT and a route in the app stay aligned. Do not generate HTML frames from Dart. Do not invent a second map file when DESIGN.md or a screen inventory already lists routes.

## Source of truth (first that yields routes wins)

1. Canonical `DESIGN.md` / `docs/DESIGN.md` / `design/DESIGN.md` — the `## Screens` section (table with a `route`/`path` column, or `route: /x` / `` `/x` `` in that section only).
2. `docs/screen-inventory.md` (or `docs/design/screen-inventory.md`) — a table with a `Route` or `Path` column.
3. Legacy fallback only: `app-screen-map.json` if the repo already has one.

`id` is the DESIGN.md / inventory screen id. `route` is the GoRoute path, Angular `path`, or React Router `path`.

## Iron Law

**No screen add / remove / rename without updating the existing SSOT in the same PR.** App-first work still updates DESIGN.md (or the inventory) before the PR. Do not add `app-screen-map.json` as a parallel contract.

No design-side routes → the gate is `NOT APPLICABLE` (exit 2). `--require-map` makes absence a FAIL for repos that have adopted screens.

## Gate

```bash
python3 .claude/scripts/check-design-route-parity.py --selftest
python3 .claude/scripts/check-design-route-parity.py --root .
# after the project has named screens:
python3 .claude/scripts/check-design-route-parity.py --root . --require-map
```

Callers: `/lint-design-system`, `/verify` (full / pre-pr). Do not inline a second route grep in CI when this script exists.
