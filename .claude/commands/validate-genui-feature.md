---
description: Validate a generative-UI (A2UI 1.0 target or v0.9.x compatibility) feature end to end — contract schema and fixtures, per-platform type checks and tests routed by target (Playwright for web, Maestro only for Flutter mobile), action/interaction contracts, accessibility, streaming and cancel — with per-check evidence
argument-hint: "[feature name or path] [platforms: angular|react|flutter|all, default: declared in the contract]"
allowed-tools: Bash, Read, Glob, Grep
---

# /validate-genui-feature — GenUI evidence gate

Runs the checks that prove a GenUI feature works on every platform it targets, and prints one line per check: `PASS`, `FAIL`, `BLOCKED` (could not run: say what is missing) or `NOT RUN` (skipped by choice: say why), each from the command's own exit code. Read-only: it never edits source, installs packages or regenerates files. Only `PASS` counts as a pass.

**Target:** $ARGUMENTS

## Tool routing (authoritative: `.claude/rules/testing-tool-selection.md`)

| Target | Static + unit | UI / E2E / a11y |
|---|---|---|
| Contract (catalog, schema, fixtures) | `genui-contract` validator | — |
| Angular web | `/verify` **Web apps** block (`tsc -p tsconfig.app.json --noEmit`, `ng test --watch=false`) | Playwright (`playwright test`) + `@axe-core/playwright` |
| React web | `/verify` **Web apps** block (`tsc -b` / `tsc --noEmit`, `vitest run`) | Playwright + `@axe-core/playwright` |
| Flutter Android/iOS | `/verify` **Flutter** block (`dart format`, `flutter analyze`, `flutter test`) | **Maestro CLI / MCP only**; no device or Maestro → `BLOCKED`, never a browser substitute |
| Backend adapter | `/verify` Python or Node block for the service that emits A2UI and handles actions | — |

Do not copy the `/verify` scripts: run its Web apps and Flutter blocks (`.claude/commands/verify.md`) for the roots this feature touches, with `MODE=full`.

## Checks

1. **Scope** — find the catalog documents (`*catalog*.json` with `x-genui` for v0.9.x, or `metadata.extensions.genui_contract` for 1.0), its fixtures, the declared platforms (`platforms` in that policy), the wire version each platform is proven on (`compatibility-matrix.md`) and topology, and the feature's files on each platform. A platform the contract does not declare is `NOT RUN (not declared)`.
2. **Contract schema** — `uv run --python 3.14 .claude/skills/genui-contract/scripts/validate_a2ui_contract.py --root <dir with catalog/ and fixtures/>` (exit 0 = catalog valid, every valid fixture accepted, every invalid fixture rejected with its code, golden actions reproduced, streams replayed), plus `--selftest` to prove it can fail. Last line must read `scanned N items: PASS`. Each message is checked against the version it declares (`1.0` or `v0.9`/`v0.9.1`); a feature that claims 1.0 needs `valid-v1_0/` fixtures, and a platform claiming 1.0 needs a test where its real package renders them (else `FAIL (1.0 claimed without renderer proof)`). Validator missing → `BLOCKED`.
3. **Parity + protocol** — run `/audit-a2ui-parity` and copy its per-platform lines.
4. **Per-platform static + unit** — the `/verify` blocks above, per touched root. Required unit cases (each is a named test; absent → `FAIL (missing test: <case>)`):
   - unknown component type → placeholder or rejected surface + logged error, no crash
   - malformed payload (missing required prop, wrong type, oversize, cycle/depth) → rejected + error state
   - action allowlist: unknown action name is not dispatched
   - action payload matches the catalog's action schema (name, typed context)
5. **Interaction contract (backend)** — tests that the server: rejects an action from an unauthenticated or unauthorized caller (401/403), ignores model-supplied role/owner/tenant fields, deduplicates a repeated idempotency key on a side-effecting action, and requires confirmation for actions marked `requiresHumanApproval`. Absent → `FAIL (missing test: <case>)`; no backend in this repo → `NOT RUN (backend not in repo)`.
6. **Streaming and cancel** — tests (unit or E2E) that: a partial stream renders incrementally or is held until valid per the chosen validation mode; an over-limit event is rejected; cancel/abort stops rendering and the request; a reconnect does not replay a side-effecting action. Use the fixtures under the contract's `streams/` folder when present.
7. **Accessibility** — web: Playwright + `@axe-core/playwright` on a page that renders every catalog component (zero violations = "no automated violations; manual checks required", never "compliant"). Flutter: `flutter test` with `meetsGuideline` (`androidTapTargetGuideline`, `iOSTapTargetGuideline`, `labeledTapTargetGuideline`, `textContrastGuideline`) on the surface host; device a11y via Maestro or `BLOCKED`.
8. **Web E2E** — `playwright test` for the feature spec (missing browser/server → `BLOCKED`).
9. **Flutter device E2E** — `maestro test .maestro/<feature>.yaml` (or Maestro MCP `list_devices` → `run`). No device/simulator or Maestro → `BLOCKED (no device | maestro missing)`.

Capture each command like this (never pipe the tool into `tail` before reading its status):

```bash
log=$(mktemp); <command> > "$log" 2>&1; rc=$?; echo "<CHECK> EXIT:$rc"; [ "$rc" -eq 0 ] || tail -20 "$log"
```

## Output

```
## GenUI validation — <feature> — <date>
Contract: <catalog path(s)> · protocol <1.0 | v0.9.x per platform> · platforms: <declared> · topology: <shared-backend|standalone-backend>
| # | Check | Angular | React | Flutter | Backend | Evidence |
|---|---|---|---|---|---|---|
| 2 | Contract schema | — | — | — | — | <command> → exit n; invalid fixtures rejected N/N |
| 3 | Parity + protocol | PASS | NOT RUN (not declared) | PASS | — | /audit-a2ui-parity |
| 4 | Static + unit | ... | | | | |
| 5 | Interaction contract | | | | ... | |
| 6 | Streaming + cancel | | | | | |
| 7 | Accessibility | | | | | |
| 8–9 | E2E (Playwright / Maestro) | | | BLOCKED (no simulator) | | |
Verdict: PASS only if every applicable cell is PASS. Any FAIL → FAIL. Otherwise any BLOCKED → BLOCKED.
```

## Related

- `.claude/rules/genui-a2ui.md` · `genui-contract-reviewer` agent (review depth) · `/audit-a2ui-parity` · `/verify`
- `.claude/skills/accessibility-audit/` · `.claude/skills/browser-testing/` (web) · `.claude/skills/flutter-mobile/reference/flutter-e2e-maestro.md` (Flutter mobile)

$ARGUMENTS
