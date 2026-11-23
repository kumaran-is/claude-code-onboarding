# Angular SPA Feature Development

> **When to use**: Building a new Angular 22.x page, component, service, or full feature end-to-end
> **Time estimate**: 2–4 hours per screen; 1–2 days for a full feature with multiple views
> **Prerequisites**: Angular workspace created by `/scaffold-angular-app` (or an existing 22.x workspace); Tailwind CSS 4.3.5 + daisyUI 5.8.2 are the toolkit default (opt-out)

## Overview

Angular feature development using the `angular-spa` skill, Angular CLI MCP, and `angular-spa` agent. Follows standalone component architecture, signals-based state management, lazy routing, and daisyUI design tokens. Ends with `ui-standards-expert` + `accessibility-auditor` review.

---

## Iron Law (from `skills/angular-spa/SKILL.md`)

> **QUERY ANGULAR CLI MCP FOR CURRENT API BEFORE WRITING COMPONENT CODE**
> Angular 22.x: standalone, zoneless and OnPush are the defaults; no `@NgModule`, no zone.js. Scaffolding is CLI-first (`.claude/rules/web-frontend.md`).

---

## Phases

### Phase 1 — Load Skill and Query Docs

**Skills to load**:
- `angular-spa` — workspace conventions, Tailwind CSS 4.3.5, daisyUI 5.8.2 (always load first)
- `angular` — load when working with SSR, hydration, signal testing, or complex DI patterns
- `angular-best-practices` — load when reviewing code or optimizing performance
- `angular-ui-patterns` — load when building components with async data (loading/error/empty states)
**MCP**: Angular CLI MCP → query for current patterns before writing

```
mcp__angular-cli__list_projects         → find workspace path
mcp__angular-cli__get_best_practices    → pass workspacePath (the angular.json folder) for version-matched guidance
mcp__angular-cli__search_documentation  → version: 22
```

---

### Phase 2 — Scaffold the Feature

Three cases:
- **New workspace:** `/scaffold-angular-app <name>` (`ng new` 22.3.0, `ng add` for lint and Tailwind, `ng generate` for the structure).
- **Existing 22.x workspace:** generate every file with the workspace's local CLI — never hand-write a skeleton. Check the
  target paths do not exist first (a generation over an existing file fails with "A merge conflicted" and exit 1; never `--force`).
- **Older major:** do not scaffold; `ng update @angular/core@22 @angular/cli@22`, then `ng generate @angular/core:<migration> --dry-run` (list: `ng generate @angular/core: --help`).

```bash
npm exec --no -- ng generate component features/orders/order-list --defaults --interactive=false;   echo "exit=$?"
npm exec --no -- ng generate component features/orders/order-detail --defaults --interactive=false; echo "exit=$?"
npm exec --no -- ng generate service features/orders/orders-api --defaults --interactive=false;     echo "exit=$?"
npm exec --no -- ng generate interface features/orders/order --defaults --interactive=false;        echo "exit=$?"
```

```
src/app/features/orders/
├── order-list/order-list.ts / .html / .css / .spec.ts   # page (smart) component, class OrderList
├── order-detail/order-detail.ts …
├── orders-api.ts / .spec.ts            # @Service() typed HttpClient service
├── order.ts                            # interface (fill in; the generated one is empty)
└── orders.routes.ts                    # lazy routes (hand-written: no schematic)
```

---

### Phase 3 — Page Component with Signals

Follow `angular-spa/reference/angular-templates.md` §Page component and the canonical load-state
union in `angular-ui-patterns/reference/loading-control-flow.md`:

- OnPush is the v22 default (the generated component has no `changeDetection`; keep it that way); no `CommonModule`/`NgIf`/`NgFor` imports.
- Read with `httpResource`/`rxResource` (stable in v22) or `toSignal`; derive one
  `computed()` state in the order `error()` → `hasValue()` → `value()`.
- Render loading (`role="status"`), empty (only after a settled load), error (`role="alert"`, 401 →
  sign in again, 403 → not authorised, no retry), success; keep stale data on a failed refresh.
- Never fallback or mock data on failure; log via the central `Logger`.

---

### Phase 4 — HTTP Service

Fill the generated `@Service()` class: typed `HttpClient` service that returns observables and lets errors propagate
(`angular-templates.md` §Service). Encode path segments, build queries with `HttpParams`. Mutations
use `HttpClient` then `resource.reload()`; guard against double submit
(`angular-ui-patterns/reference/form-dialog-patterns.md`).

---

### Phase 5 — Lazy Routing and Auth

```typescript
// orders.routes.ts
import { Routes } from '@angular/router';

export const ORDER_ROUTES: Routes = [
  { path: '', title: 'Orders', loadComponent: () => import('./order-list/order-list').then((m) => m.OrderList) },
  { path: ':id', title: 'Order', loadComponent: () => import('./order-detail/order-detail').then((m) => m.OrderDetail) },
];

// app.routes.ts
// { path: 'orders', canActivate: [signedInGuard], loadChildren: () => import('./features/orders/orders.routes').then((m) => m.ORDER_ROUTES) }
```

`signedInGuard`, the credential allow-list interceptor and safe `returnUrl` come from
`angular-spa/reference/web-security.md`. Guards are UX; the API authorizes every request.
`withComponentInputBinding()` binds `:id` to an `input()`.

---

### Phase 6 — Unit Tests (Vitest)

A CLI 22.3 workspace uses `@angular/build:unit-test` with Vitest — not Karma/Jasmine. Patterns in
`angular-spa/reference/testing-vitest.md`:

- `HttpTestingController`: flush each request **before** `await fixture.whenStable()`.
- One spec per UI state (loading, empty, 401, 403, 5xx with retry, success); harnesses for DOM access.
- Mocks with `vi.fn()`; timers with `vi.useFakeTimers()` — `fakeAsync` fails without zone.js.

```bash
npm exec --no -- ng test --watch=false; echo "test exit=$?"
npm exec --no -- ng build; echo "build exit=$?"
npm exec --no -- ng lint; echo "lint exit=$?"
```

E2E (optional): Playwright via the `browser-testing` skill.

---

### Phase 7 — Design System Review

**Command**: `/lint-design-system`

**Agent 1**: `ui-standards-expert`
- No hardcoded colors (only daisyUI semantic: `bg-primary`, `text-base-content`)
- No raw spacing values (use Tailwind scale: `p-4`, not `p-[16px]`)
- Target size ≥ 24×24 CSS px (WCAG 2.2 AA); house standard ≥ 44px

**Agent 2**: `accessibility-auditor`
- Semantic HTML (`<button>` not `<div>` for interactive elements)
- ARIA labels on icon-only buttons
- Color contrast ≥ 4.5:1 for normal text
- Keyboard navigation for all interactive elements

**Step 3**: `web-design-guidelines` skill
- Load skill and fetch guidelines from source URL
- Run against all changed component files
- Verify: loading states present, error states present, empty states present, focus management correct

**Gate**: `/lint-design-system` returns zero violations. Both agents pass.

---

### Phase 8 — Code Review and PR

```
/review-code        → dispatch angular-spa reviewer (ui-standards-expert + code-reviewer)
/validate-changes   → output-evaluator agent: APPROVE / NEEDS_REVIEW / REJECT
/ship               → comprehensive pre-deploy check
```

---

## Quick Reference

| Phase | Action | Agent / Command | Gate |
|-------|--------|----------------|------|
| 1 — Setup | Load skill + query Angular CLI MCP | MCP query | Current API confirmed |
| 2 — Scaffold | `/scaffold-angular-app` or `ng generate` | Angular CLI | Every generate exits 0 |
| 3 — Component | Fill generated component: signals + states | Manual (logic only) | Component renders |
| 4 — Service | Fill generated `@Service()` | Manual (logic only) | API calls work |
| 5 — Routing | Lazy routes | Manual | Navigation works |
| 6 — Tests | Vitest unit tests | `ng test --watch=false` | All tests pass |
| 7 — Design | `/lint-design-system` | `ui-standards-expert` + `accessibility-auditor` | Zero violations |
| 8 — Review | `/review-code` + `/ship` | Multiple agents | Zero CRITICAL findings |

---

## Common Pitfalls

- **Hand-writing a component/service skeleton** — use `ng generate`; it applies the 22.3 conventions (file names, `@Service`, OnPush default)
- **Leaving generated placeholders** — a guard that returns `true` or an empty interface fails `ng lint`; implement them
- **Using `NgModule`** — use standalone components only
- **Plain fields updated from async callbacks** — zoneless + OnPush do not re-render them; hold state in signals
- **Hardcoded colors** — always daisyUI semantic tokens; never `#FF5733` or `text-blue-500`
- **`async pipe` without loading state** — users see blank screen during load; always show loading indicator
- **No error state** — errors that produce an empty screen look like empty data; show `role="alert"` with retry (and never fallback data)
- **Credentials on every request** — attach tokens only to allow-listed API origins (`web-security.md`)

## Related Workflows

- [`feature-a2ui-renderer.md`](feature-a2ui-renderer.md) — agent-driven UI in Angular
- [`design-system-compliance.md`](design-system-compliance.md) — enforcing design tokens
- [`browser-e2e-testing.md`](browser-e2e-testing.md) — E2E testing the Angular app
- [`angular-best-practices`](../../.claude/skills/angular-best-practices/SKILL.md) — performance-ranked rules for PR review
- [`web-design-guidelines`](../../.claude/skills/web-design-guidelines/SKILL.md) — run after Phase 3 to audit component against Vercel Web Interface Guidelines (third review layer after `/lint-design-system` and `accessibility-auditor`)
- [`angular-ui-patterns`](../../.claude/skills/angular-ui-patterns/SKILL.md) — loading/error/empty state doctrine
