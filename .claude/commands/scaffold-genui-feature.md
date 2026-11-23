---
name: scaffold-genui-feature
description: Scaffold one generative-UI feature across the A2UI v0.9 contract, backend adapter and Angular / React / Flutter renderers — contract-first, detects existing conventions, never overwrites without review, delegates platform code to the existing GenUI skills and commands
argument-hint: "<feature> <ComponentId> [angular|react|flutter|all] [shared-backend|standalone-backend] [langgraph|adk|other] [existing|new]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs
disable-model-invocation: true
---

# Scaffold a GenUI Feature (A2UI v0.9, contract-first)

Adds one generative-UI feature to an **existing** project: the catalog entry, fixtures, action contract, backend adapter and the renderer mapping on each requested platform. It never creates a new app (use `/scaffold-angular-app`, `/scaffold-react-app`, `/scaffold-flutter-app` first).

**Arguments:** $ARGUMENTS

| Arg | Values | Default / when missing |
|---|---|---|
| feature | kebab-case name, e.g. `order-approval` | required — ask |
| component | a catalog ID: `ActionCard`, `DataSummaryTable`, `ApprovalForm`, `SelectionList`, `DetailPanel`, `StatusIndicator`, `InputForm`, `ConfirmationDialog`, or a new PascalCase ID | required — ask |
| platforms | `angular` \| `react` \| `flutter` \| `all` (comma list allowed) | the platforms in `x-genui.platforms`; none declared → ask |
| topology | `shared-backend` (one agent service for every client) \| `standalone-backend` (one per app) | ask; never guess |
| agent framework | `langgraph` \| `adk` \| `other` | detect from the backend's dependencies; ask if none |
| catalog component | `existing` (reuse the catalog ID) \| `new` (add it to the contract) | `existing` if the ID is already in the catalog |

## Rules

- **Contract first.** No renderer code before the catalog entry, its schema and its fixtures validate.
- **Detect, don't impose.** Before writing, find the existing catalog (`*catalog*.json` with `x-genui`), GenUI folders (`**/a2ui/**`, `**/genui/**`), state management, test runners and naming. Follow them; report what you detected.
- **Never overwrite without review.** If a target file exists, show the diff you would apply and wait for approval. Never delete files.
- **Delegate platform code.** Angular → `/scaffold-a2ui` + `a2ui-angular` skill (SDK path, `@a2ui/angular@0.14.0` + `@a2ui/web_core@0.15.0` from `/v0_9`); React → `.claude/skills/react-spa/reference/generative-ui-a2ui.md` + `react-spa` skill; Flutter → `/scaffold-genui` + `flutter-genui` skill (`a2ui_flutter 0.4.0` + `a2ui_core 0.8.0`); backend → `.claude/skills/genui-contract/` backend/topology references + `agentic-ai-dev` (LangGraph) or `google-adk` (ADK). Copy their verified templates; do not invent APIs.
- **One protocol version.** A2UI v0.9 everywhere (`.claude/rules/genui-a2ui.md`). CopilotKit and AG-UI are optional and only added if the project already uses them or the user asks.
- **Docs first.** Verify each SDK identifier against the installed package (`node_modules/**/*.d.ts`, pub cache) or Context7 before use; mark anything unverified `UNVERIFIED` in the summary.

## Steps

0. **Pre-flight** — parse arguments; ask for any required one that is missing (feature, component, topology). Locate the catalog and declared platforms; list the files you plan to create or change and wait for approval if any exist.
1. **Contract entry** (`new` only) — add the component to the catalog JSON (typed props, required fields, `additionalProperties: false`, accessibility label prop) and any new actions to `x-genui.actions` (`sideEffect`, `risk`, `requiresIdempotencyKey`, `requiresHumanApproval`). Bump `x-genui.contractVersion` (minor for additive, major for breaking) and note it. `existing` → read and reuse the entry unchanged.
2. **Fixtures** — at least one valid message (`createSurface` + `updateComponents` using the component, `"version": "v0.9"`), one valid action payload per new action, and invalid fixtures: unknown component, missing required prop, wrong prop type, unknown action, forbidden URL scheme. Run the contract validator (`uv run --python 3.14 .claude/skills/genui-contract/scripts/validate_a2ui_contract.py --root <contract dir>`): valid pass, invalid rejected with their expected codes, exit 0.
3. **Action contract** — server-side handler signature per action: authn + authz from the session (never from `context`), schema-validated context, idempotency-key dedupe for side-effecting actions, confirmation step for `requiresHumanApproval`.
4. **Backend adapter** — for the chosen topology and framework: the agent step that emits the component as A2UI v0.9 messages, the action endpoint, and the stream (SSE or JSONL) with size limit, timeouts and cancel. `shared-backend`: one adapter, all clients. `standalone-backend`: one per app, same catalog file (referenced, not copied).
5. **Angular renderer** (if requested) — map the catalog ID to an Angular component via the `a2ui-angular` skill; strict validation; action allowlist; unknown-component placeholder.
6. **React renderer** (if requested) — same mapping via the React GenUI reference.
7. **Flutter renderer** (if requested) — `ComponentImplementation` for the ID via `flutter-genui`; `Semantics` per control; action allowlist; `A2uiError` handled with an error state.
8. **Tests** — per platform: renders valid fixture; unknown/malformed fixture → placeholder or rejection + logged error; action dispatch sends the schema-valid payload; a11y assertions (web: `@axe-core/playwright` in a Playwright spec; Flutter: `meetsGuideline` widget test + `.maestro/<feature>.yaml` for device E2E). Backend: 401/403, idempotency dedupe, approval required.
9. **Docs + verify + summary** — write the feature's integration notes next to the existing feature docs (component, actions and their risk, topology, how each declared platform registers the ID, how to run the contract and platform tests); then run `/audit-a2ui-parity` and `/validate-genui-feature <feature>`; print every check's status from its own exit code (`PASS` / `FAIL` / `BLOCKED` / `NOT RUN`). Then list created and changed files, detected conventions, contract version change, anything `UNVERIFIED`, and the next step (`genui-contract-reviewer` agent review).

## Related

- `.claude/rules/genui-a2ui.md` · `.claude/rules/testing-tool-selection.md` · `genui-contract-reviewer` agent
- `/scaffold-a2ui` (Angular) · `/scaffold-genui` (Flutter) · `/audit-a2ui-parity` · `/validate-genui-feature`

$ARGUMENTS
