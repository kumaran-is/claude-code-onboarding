---
name: angular-ui-patterns
description: "Angular 22.x UI/UX state patterns — canonical load-state union derived from resources (error → hasValue → value), typed API error model, 401 vs 403 UX, error hierarchy (inline→toast→banner→full-screen), empty states, button in-flight guards, typed reactive forms with server errors, confirmation dialogs that stay open while a mutation runs. Load when building any Angular UI component that handles async data or user actions."
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs
metadata:
  triggers: Angular loading state, Angular error state, Angular empty state, Angular skeleton, Angular spinner, Angular form validation, Angular button loading, Angular dialog, Angular async UI, Angular UX patterns
  related-skills: angular-spa, angular, angular-best-practices
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-22"
---

## Iron Law

**LOAD `angular-spa` FIRST for the workspace UI mode's component classes (daisyUI, Spartan or hybrid: `angular-spa/reference/ui-mode-selection.md`) and Tailwind CSS 4.3.5 tokens. This skill provides UI state doctrine — use `angular-spa` reference files for the actual component HTML/CSS.**

## When to Use This Skill

Load this skill when:
- Building any Angular component that fetches async data
- Adding loading, error, or empty states to a list or page
- Implementing form validation with inline field errors
- Adding button loading states or disabling during async operations
- Building confirmation dialogs or modals
- Reviewing a component for missing UI state coverage

## Five Non-Negotiable Principles

1. **One derived load state** — derive loading / empty / ready / error with `computed()` from the resource (check `error()` before `value()`); never hand-sync flags. Loading indicators only when there is no data to show
2. **Always surface errors** — log through `Logger` AND show the user; never swallow, never `console.*`, never fallback or mock data
3. **401 ≠ 403** — 401: sign in again without a loop; 403: "not authorised". Client guards are UX; the server authorizes
4. **Guard every mutation** — in-flight early return + disabled trigger; read with resources, mutate with `HttpClient`, then `reload()`
5. **Progressive disclosure** — use `@defer` for non-critical content; partial data beats a blank page, but never fake data

> `resource` / `rxResource` / `httpResource` are stable in Angular 22 (`@publicApi 22.0`). Signal Forms are stable and the default for new forms; existing typed reactive forms stay supported.

---

## Pattern Selector

What are you building?
- Async list/page → load `reference/loading-control-flow.md` (canonical load-state union)
- Error handling, 401/403 → load `reference/error-handling.md` (canonical `ApiError` / `toApiError`)
- Button with loading → load `reference/button-empty-states.md`
- Form with validation → load `reference/form-dialog-patterns.md`
- Reviewing for mistakes → load `reference/anti-patterns.md`

## Reference Files

| Reference | Load When |
|-----------|-----------|
| [reference/index.md](reference/index.md) | Any time — navigation |
| [reference/loading-control-flow.md](reference/loading-control-flow.md) | Building async list or page |
| [reference/error-handling.md](reference/error-handling.md) | Adding error handling |
| [reference/button-empty-states.md](reference/button-empty-states.md) | Buttons or collections |
| [reference/form-dialog-patterns.md](reference/form-dialog-patterns.md) | Forms or confirmation dialogs |
| [reference/anti-patterns.md](reference/anti-patterns.md) | Reviewing a component |

---

## UI State Checklist

Before completing any UI component:

### UI States

- [ ] Load state derived with `computed()`: `error()` checked before `value()` (or `hasValue()` guard)
- [ ] Error state shown to user; 403 rendered as "not authorised", 401 as "sign in again"
- [ ] Loading state shown only when no data exists (`'reloading'` keeps data)
- [ ] Empty state provided for collections (`@empty` block)
- [ ] Mutation handlers return early while in flight; trigger disabled and shows progress

### Data & Mutations

- [ ] Every catch logs via `Logger` and shows feedback (no `console.*`, no fallback data)
- [ ] Reads via resource; mutations via `HttpClient` then `reload()`; 409 → reload and say so
- [ ] Optimistic updates roll back on failure

### Accessibility (WCAG 2.2 AA — checklist owned by the `accessibility-audit` skill)

- [ ] Loading states announced (`role="status"`), failures announced (`role="alert"`)
- [ ] Error messages linked to fields (`aria-describedby`, `aria-invalid`)
- [ ] Focus moved deliberately after state changes; dialogs focus their first control after render

---

## UI library integration (per workspace mode)

This skill provides the doctrine; the markup comes from the workspace UI mode (`ui-mode-selection.md` §4). In
`daisyui` and `hybrid` (where daisyUI owns loading, alerts and toasts) use these daisyUI classes; in `spartan` use
the Helm equivalents (`hlmSpinner`/`hlmSkeleton`, `hlmAlert`, `hlm-toaster`):
- Loading: `<span class="loading loading-spinner loading-lg" aria-hidden="true"></span>` inside a `role="status"` container with visible or `sr-only` text
- Alert: `class="alert alert-error"` / `class="alert alert-success"`
- Button loading: `<span class="loading loading-spinner loading-sm">` inside a disabled `btn`
- Skeleton: `class="skeleton h-4 w-full"`
- Empty state: a `card` or plain `div` with a heading, one sentence and the primary action (no `hero` layout needed)

Render order, timing thresholds (skeleton delay, minimum display), stale-while-error and offline
states follow the framework-neutral standard: `../design-system/reference/interaction-contracts.md`
§6b. Error with data keeps the content and adds an inline error; "empty" only after a settled load;
skeletons carry `aria-hidden="true"` inside an `aria-busy="true"` region. Optimistic updates only for
reversible, low-risk actions.

---

## Documentation Sources

Verify Angular APIs with the `angular-cli` MCP: `search_documentation` with `version: 22`, and
`get_best_practices` **with the workspace path** (without it the tool returns the latest-major guide —
the bundled generic guide). Context7 remains a fallback for other libraries.

## Related Skills

- `angular-spa` — workspace skill: daisyUI components, TailwindCSS tokens, conventions; `reference/web-security.md` (interceptor, refresh, guards, returnUrl); `reference/testing-vitest.md` (testing these states)
- `angular` — API reference: `references/signals-core.md` (resource options and stability), `references/signal-forms.md`
- `angular-best-practices` — review checklist and performance priorities
- `design-system` — framework-neutral async-state contract ([interaction-contracts.md §6b](../design-system/reference/interaction-contracts.md#6b-async-state-contract-loading--empty--error--refresh): loading / empty / error / refresh); this skill is its Angular implementation
- `accessibility-audit` — WCAG 2.2 AA checklist and automated checks
