---
name: scaffold-genui-feature
description: Scaffold one generative-UI feature across the A2UI contract (v1.0 preferred, v0.9.x where a renderer is not proven on 1.0), backend adapter and Angular / React / Flutter renderers — contract-first, detects existing conventions, never overwrites without review, delegates platform code to the existing GenUI skills and commands
argument-hint: "<feature> <ComponentId> [angular|react|flutter|all] [shared-backend|standalone-backend] [langgraph|adk|other] [existing|new]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs
disable-model-invocation: true
---

# Scaffold a GenUI Feature (A2UI v1.0 / v0.9.x, contract-first)

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
- **Delegate platform code.** Angular → `/scaffold-a2ui` + `a2ui-angular` skill (`npm install --save-exact @a2ui/angular@0.16.0 @a2ui/web_core@0.16.1 @a2ui/markdown-it@0.2.4 zod@3.25.76`, Angular ^22.2.3. **1.0 (target):** `AngularCatalog`, `BASIC_COMPONENTS`, `BASIC_FUNCTIONS`, `provideA2Ui` and `A2uiRendererService` from the package root; `new AngularCatalog('<1.0 catalog id>', '1.0', [...BASIC_COMPONENTS, ...custom], BASIC_FUNCTIONS)` with `useUniversalComponents: true` and `processorOptions: { validationConfig: STRICT_VALIDATION, errorHandler, reportErrorsOnly: true, outboundListener }`, in a lazy route whose `providers` also list `A2uiRendererService`. Proven in the browser for ActionCard, EditableForm and ApprovalRequest. **v0.9 (compatibility path):** same root services; v0.9 `BASIC_COMPONENTS`/`BASIC_FUNCTIONS` from `@a2ui/angular/v0_9` and `AngularCatalog(id, '0.9', …)`. Add a contract gate in front of web_core: a byte cap, one version per stream, forbidden strings, and no `{path}` on 1.0. Add an action allowlist at dispatch: web_core and `@a2ui/agent` `validatePayload` accept `javascript:` URLs and non-allowlisted actions. Run `npm audit`: zod 3.25.76 is an unresolved HIGH with no in-range fix. CopilotKit Angular is v0.9 only); React → `.claude/skills/react-spa/reference/generative-ui-a2ui.md` + `react-spa` skill; Flutter → `/scaffold-genui` + `flutter-genui` skill (package pins and proven wire version as that skill records them); backend → `.claude/skills/genui-contract/` backend/topology references + `agentic-ai-dev` (LangGraph) or `google-adk` (ADK). Copy their verified templates; do not invent APIs.
- **One protocol version per stream, negotiated per client.** The backend serves the catalog once per wire version and streams 1.0 to a client that declares `a2uiRendererCapabilities` `{"1.0": …}`, v0.9 to a client that declares only `a2uiClientCapabilities` `{"v0.9": …}`, and `406` otherwise. A platform uses 1.0 only when its renderer skill records a passing 1.0 render test; otherwise it stays on v0.9.x. Never translate between versions (`.claude/skills/genui-contract/reference/ag-ui-transport.md`). CopilotKit and AG-UI are optional and only added if the project already uses them or the user asks; Flutter gets an app-owned transport adapter, never an assumed CopilotKit stream.
- **Docs first.** Verify each SDK identifier against the installed package (`node_modules/**/*.d.ts`, pub cache) or Context7 before use; mark anything unverified `UNVERIFIED` in the summary.

## Steps

0. **Pre-flight** — parse arguments; ask for any required one that is missing (feature, component, topology). Locate the catalog and declared platforms; list the files you plan to create or change and wait for approval if any exist.
1. **Contract entry** (`new` only) — add the component to the catalog JSON (typed props, required fields, `additionalProperties: false`, accessibility label prop) and any new actions to `x-genui.actions` (`sideEffect`, `risk`, `requiresIdempotencyKey`, `requiresHumanApproval`). Bump `x-genui.contractVersion` (minor for additive, major for breaking) and note it. `existing` → read and reuse the entry unchanged.
2. **Fixtures** — at least one valid message (`createSurface` (1.0 may carry `components` + `dataModel` inline) + `updateComponents` using the component, `"version": "1.0"` in `fixtures/valid-v1_0/`, plus a `"v0.9"` copy in `fixtures/valid/` while any declared platform is on the v0.9.x compatibility path), one valid action payload per new action, and invalid fixtures: unknown component, missing required prop, wrong prop type, unknown action, forbidden URL scheme. Run the contract validator (`uv run --python 3.14 .claude/skills/genui-contract/scripts/validate_a2ui_contract.py --root <contract dir>`): valid pass, invalid rejected with their expected codes, exit 0.
3. **Action contract** — server-side handler signature per action: authn + authz from the session (never from `context`), tenant check (another tenant's surface → 404), schema-validated context, idempotency-key dedupe for side-effecting actions, confirmation step for `requiresHumanApproval`. Catalog validation is not authorization: the SDK's `validatePayload` accepts off-allowlist action names, so the server allowlist is mandatory.
4. **Backend adapter** — for the chosen topology and framework: version + catalog negotiation, the agent step that emits the component as A2UI messages in the negotiated version (Node: `@a2ui/agent` 0.2.1, see `backend-emitters.md` §7), the action endpoint, and the stream (SSE or JSONL) with size limit, timeouts and cancel. `shared-backend`: one adapter, all clients. `standalone-backend`: one per app, same catalog files (referenced, not copied); no shared source code is required, the contract tests prove conformance.
5. **Angular renderer** (if requested) — map the catalog ID to an Angular component via the `a2ui-angular` skill; `STRICT_VALIDATION` + `errorHandler` (unknown component → visible error); contract gate; action allowlist at dispatch.
6. **React renderer** (if requested) — same mapping via the React GenUI reference.
7. **Flutter renderer** (if requested) — `ComponentImplementation` for the ID via `flutter-genui`; `Semantics` per control; action allowlist; `A2uiError` handled with an error state.
8. **Tests** — per platform: renders valid fixture; unknown/malformed fixture → placeholder or rejection + logged error; action dispatch sends the schema-valid payload; a11y assertions (web: `@axe-core/playwright` in a Playwright spec; Flutter: `meetsGuideline` widget test + `.maestro/<feature>.yaml` for device E2E). Backend: 401/403/404 (wrong tenant)/406 (undeclared version), unregistered action, idempotency dedupe, approval required, stream cap, cancel.
9. **Docs + verify + summary** — write the feature's integration notes next to the existing feature docs (component, actions and their risk, topology, how each declared platform registers the ID, how to run the contract and platform tests); then run `/audit-a2ui-parity` and `/validate-genui-feature <feature>`; print every check's status from its own exit code (`PASS` / `FAIL` / `BLOCKED` / `NOT RUN`). Then list created and changed files, detected conventions, contract version change, anything `UNVERIFIED`, and the next step (`genui-contract-reviewer` agent review).

## Related

- `.claude/rules/genui-a2ui.md` · `.claude/rules/testing-tool-selection.md` · `genui-contract-reviewer` agent
- `/scaffold-a2ui` (Angular) · `/scaffold-genui` (Flutter) · `/audit-a2ui-parity` · `/validate-genui-feature`

$ARGUMENTS
