---
name: scaffold-a2ui
description: Scaffold an A2UI (Agent-to-User Interface) renderer feature module in an existing Angular 21.x app with component catalog, recursive renderer, agent service, and chat page
argument-hint: "[feature name, default: a2ui-chat]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs
disable-model-invocation: true
---

# Scaffold A2UI Angular Renderer

Create an A2UI renderer feature module in an existing Angular 21.x project.

**Feature name:** $ARGUMENTS (default to "a2ui-chat" if not provided)

## Pre-requisites

> **Official SDK first (A2UI v0.9):** `npm install -E @a2ui/angular@0.14.0 @a2ui/web_core@0.15.0`, then follow
> `reference/a2ui-renderer-services.md` (`provideA2uiStrict()` with `STRICT_VALIDATION`, sanitizing `MarkdownRenderer`,
> `<a2ui-v09-surface>`). For the shared GenUI catalog (`genui-contract` skill), follow
> `reference/canonical-catalog-angular.md` instead: `AngularCatalog` with the canonical IDs, ingest guard, action gateway
> (allowlist, `Idempotency-Key` header, server-held approval) and `/genui-config.json` for `shared-backend` /
> `standalone-backend`; optional AG-UI or CopilotKit (`reference/copilotkit-angular.md`: 0.3.1 is the last Angular 21 line).
> Then gate it with `/validate-genui-feature` and `/audit-a2ui-parity`. The steps below scaffold the hand-built LEGACY v0.8 renderer — use them only when the agent
> still emits v0.8. A custom design system does not rule out the SDK: register your own components in a v0.9 custom
> catalog with `AngularCatalog` from `@a2ui/angular@0.14.0` (`.claude/skills/a2ui-angular/reference/canonical-catalog-angular.md`). Never mix protocol versions.

1. Read the `a2ui-angular` skill (`SKILL.md` and all `reference/*.md` files) for protocol spec, security rules, component catalog, and renderer patterns.
2. Read the `angular-spa` skill's `reference/angular-conventions.md` for Angular coding standards.
3. Verify Angular APIs with the `angular-cli` MCP (`search_documentation`, version 21) and A2UI APIs against the installed package `.d.ts` files.

## Steps

1. **Create feature folder structure**
   ```
   src/app/features/<name>/
   +-- models/a2ui.model.ts
   +-- services/a2ui-catalog.service.ts
   +-- services/a2ui-agent.service.ts
   +-- services/a2ui-sanitizer.service.ts
   +-- components/a2ui-renderer/a2ui-renderer.component.ts
   +-- components/a2ui-renderer/a2ui-renderer.component.spec.ts
   +-- components/a2ui-chat/a2ui-chat.component.ts
   +-- components/a2ui-chat/a2ui-chat.component.spec.ts
   +-- <name>.routes.ts
   ```

2. **Create A2UI models** — `A2UIValue`, `A2UIChildren`, `A2UIComponent`, `SurfaceUpdate`, `DataModelUpdate`, `A2UIMessage`, `SurfaceState`, `UserAction`, `ChatMessage` interfaces. `UserAction` is the client→agent message type: `{ name, surfaceId, sourceComponentId, timestamp, context }`. Follow `reference/a2ui-renderer-patterns.md` models section.

3. **Create catalog service** — Allowlist of official A2UI v0.8 component types: `Row`, `Column`, `Text`, `Image`, `Icon`, `Button`, `TextField`, `Checkbox`, `DateTimeInput`, `Card`, `Modal`, `Tabs`, `List`, `Divider`. Follow `reference/a2ui-security.md`.

4. **Create sanitizer service** — one URL policy (`https:` only AND a host allowlist via `A2UI_ALLOWED_URL_HOSTS`, provided in `app.config.ts`), text length limits. Copy it from `reference/a2ui-renderer-patterns.md` § Sanitizer Service.

5. **Create recursive renderer component** — Maps official A2UI v0.8 types (Row, Column, Text, Image, Icon, Button, TextField, Checkbox, DateTimeInput, Card, Modal, Tabs, List, Divider) to Angular/daisyUI components via `@switch`. Uses signal inputs, `computed()` for child filtering, validates against catalog, and carries the cycle/depth guard (`depth` + `ancestors` inputs, placeholder + `ErrorHandler`, no `console.*`). Copy `reference/a2ui-renderer-template.md`. Note: Card uses `child` (single id string); layout components use `children.explicitList`. Follow `reference/a2ui-renderer-patterns.md`.

6. **Create agent service** — REST endpoints for `sendMessage` (text → agent) and `sendUserAction(action: UserAction): Observable<SurfaceState>` (button/form actions → agent). `sendUserAction` sends a `UserAction` message and builds `SurfaceState` from the JSONL messages in the response. Optional SSE streaming support. Follow `reference/a2ui-renderer-patterns.md`.

7. **Create chat page component** — Message history with chat bubbles, A2UI renderer for agent responses, text input, loading state, action handling. Follow `reference/a2ui-renderer-patterns.md`.

8. **Create lazy-loaded route** — Add route config in `<name>.routes.ts`, wire into `app.routes.ts` with `loadChildren`.

9. **Write tests** — catalog (allow known, reject unknown), renderer (valid card renders; unknown type, self-reference cycle and depth > 32 each render the placeholder; `http:` / non-allowlisted / `javascript:` image URLs render no `<img>`), action dispatch (emits correct data). Run them in a real browser (Playwright) for the cycle case — a missing guard crashes the tab.

10. **Verify build** — Run `npx ng build` and the tests; report each command with its own exit code (PASS / FAIL / NOT RUN).

11. **Print summary** — List created files, how to run, next steps (connect to real agent backend).

## Reference

- `a2ui-angular` skill: `reference/canonical-catalog-angular.md`, `reference/copilotkit-angular.md`, `reference/a2ui-protocol.md`, `reference/a2ui-security.md`, `reference/a2ui-component-catalog.md`, `reference/a2ui-renderer-patterns.md`
- `genui-contract` skill: canonical catalog, action table, fixtures, backend topologies
- `angular-spa` skill: `reference/angular-conventions.md`, `reference/angular-templates.md`

$ARGUMENTS
