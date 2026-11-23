# Angular SPA Performance Optimization

> **When to use**: Angular app scoring < 90 on Lighthouse, slow LCP/INP/CLS, large initial bundle, sluggish runtime change detection
> **Time estimate**: 2–4 hours for targeted fixes; 1–2 days for full Core Web Vitals remediation
> **Prerequisites**: Angular 22.x SPA running; `ng build --configuration=production` working; Chrome DevTools MCP configured

## Overview

Measure, diagnose, and fix performance issues in Angular 22.x SPAs — Core Web Vitals (LCP, INP, CLS), bundle size reduction, lazy loading, image optimization, and runtime change detection. Uses `browser-testing` agent for Lighthouse baseline, `angular-spa` agent for Angular-native fixes, and `code-reviewer` for correctness verification.

---

## Iron Law (from `skills/web-performance-optimization/SKILL.md`)

> **MEASURE FIRST. NEVER OPTIMIZE FROM INTUITION.**
> Profile with real data before changing code. Quantify every fix: "LCP 3.8s → 1.6s, -58%". Changes without measured improvement are noise.

---

## Phases

### Phase 1 — Load Skills and Query Docs

**Skills to load**:
- `web-performance-optimization` — Core Web Vitals thresholds, image optimization, caching strategies, bundle analysis (always load first)
- `angular-best-practices` — OnPush + Signals patterns, lazy routes, `@defer`, esbuild build budgets

**MCP**:
```
mcp__angular-cli__get_best_practices       → Angular 22.x performance patterns
mcp__angular-cli__onpush_zoneless_migration → migrate to OnPush + zoneless
mcp__context7__resolve-library-id          → @angular/core, @angular/common
mcp__context7__query-docs                  → NgOptimizedImage, @defer, signals
```

---

### Phase 2 — Measure Baseline

**Agent**: `browser-testing` via Chrome DevTools MCP

Run Lighthouse audit on the production build:
```
mcp__chrome-devtools__lighthouse_audit     → LCP, INP, CLS, TTI, TBT scores
mcp__chrome-devtools__performance_start_trace → start performance trace
mcp__chrome-devtools__performance_stop_trace  → capture long tasks
mcp__chrome-devtools__performance_analyze_insight → identify bottlenecks
```

Record bundle size from production build:
```bash
ng build --configuration=production --stats-json
npx webpack-bundle-analyzer dist/browser/stats.json
```

**Baseline record** (fill in before any changes):

| Metric | Threshold | Baseline |
|--------|-----------|---------|
| LCP | ≤ 2.5s | ___ |
| INP | ≤ 200ms | ___ |
| CLS | ≤ 0.1 | ___ |
| TTI | ≤ 3.8s | ___ |
| Initial bundle | ≤ 500KB | ___ |

---

### Phase 3 — Identify Bottlenecks

Analyze `dist/browser/stats.json` with bundle analyzer to find oversized chunks.

Check Chrome DevTools Performance tab for:
- Long tasks blocking the main thread (> 50ms)
- Unnecessary re-renders from `Default` change detection
- Large image payloads without lazy loading or modern formats

Common bottleneck patterns in Angular 22.x:

| Symptom | Likely Cause |
|---------|-------------|
| LCP > 2.5s | Hero image not preloaded; no `NgOptimizedImage` |
| Bundle > 500KB | Eager-loaded routes; large third-party libs |
| INP > 200ms | Zone.js-triggered re-renders; `Default` change detection |
| CLS > 0.1 | Images without `width`/`height`; late-loading fonts |

---

### Phase 4 — Prioritize Fixes

Rank by user impact — address in this order:

1. **LCP > 2.5s** — directly impacts perceived load speed; highest user-visible impact
2. **Bundle > 500KB** — delays TTI; affects all users on slow connections
3. **INP > 200ms** — interaction lag; degrades perceived responsiveness
4. **CLS > 0.1** — layout shifts; disorienting UX, especially on mobile

---

### Phase 5 — Implement

**Agent**: `angular-spa`

#### 5a — Image Optimization with `NgOptimizedImage`

```typescript
// app.config.ts — provide image loader
import { provideImgixLoader } from '@angular/common';

export const appConfig: ApplicationConfig = {
  providers: [
    provideImgixLoader('https://your-cdn.imgix.net'),
  ],
};
```

```html
<!-- Use NgOptimizedImage for all images -->
<img ngSrc="hero.jpg" width="1200" height="630" priority />
<img ngSrc="product.jpg" width="400" height="400" loading="lazy" />
```

#### 5b — Lazy Routes with `loadComponent` / `loadChildren`

```typescript
// app.routes.ts
export const routes: Routes = [
  {
    path: 'dashboard',
    loadComponent: () => import('./features/dashboard/dashboard.component')
      .then(m => m.DashboardComponent),
  },
  {
    path: 'orders',
    loadChildren: () => import('./features/orders/orders.routes')
      .then(m => m.ordersRoutes),
  },
];
```

#### 5c — Defer Below-Fold Content with `@defer`

```html
<!-- Defer any content not visible on initial load -->
@defer (on viewport) {
  <app-recommendations [userId]="userId()" />
} @placeholder {
  <div class="skeleton h-48 w-full"></div>
}

@defer (on idle) {
  <app-analytics-chart [data]="chartData()" />
} @loading {
  <div class="loading loading-spinner"></div>
}
```

#### 5d — OnPush + Signals for Runtime Performance

```typescript
// feature.component.ts
import { Component, signal, computed, inject } from '@angular/core';

@Component({
  selector: 'app-order-list',
  templateUrl: './order-list.component.html',
})
export class OrderListComponent {
  private orderService = inject(OrderService);

  orders = signal<Order[]>([]);
  loading = signal(true);

  // computed() only re-evaluates when orders() changes
  activeOrders = computed(() =>
    this.orders().filter(o => o.status !== 'CANCELLED')
  );
}
```

#### 5e — Build Budgets (esbuild)

```json
// angular.json — add/tighten budgets
{
  "configurations": {
    "production": {
      "budgets": [
        { "type": "initial", "maximumWarning": "400kb", "maximumError": "500kb" },
        { "type": "anyComponentStyle", "maximumWarning": "2kb", "maximumError": "4kb" }
      ]
    }
  }
}
```

---

### Phase 6 — Verify

**Agent**: `browser-testing` — re-run Lighthouse after each fix category.

**Agent**: `code-reviewer` — review optimized code for correctness before merging.

Report improvements with quantified before/after:

```
PERFORMANCE IMPROVEMENTS:
- LCP: 3.8s → 1.6s  (-58%)  [NgOptimizedImage + priority hint]
- Bundle: 620KB → 310KB  (-50%)  [lazy routes for /dashboard, /orders]
- INP: 340ms → 80ms  (-76%)  [OnPush + signals on OrderListComponent]
- CLS: 0.22 → 0.04  (-82%)  [explicit width/height on all images]
```

**Gate**: All four Core Web Vitals in "Good" range. Initial bundle ≤ 500KB. `ng build` passes all budgets with zero errors.

---

## Quick Reference

| Phase | Action | Agent / Command | Gate |
|-------|--------|----------------|------|
| 1 — Setup | Load skills + query Angular CLI MCP | MCP query | Current API confirmed |
| 2 — Measure | Lighthouse + bundle analysis | `browser-testing` + Chrome DevTools MCP | Baseline recorded |
| 3 — Diagnose | Identify bottlenecks by symptom | Bundle analyzer + Performance tab | Root cause named |
| 4 — Prioritize | Rank by user impact | Manual | Fix order decided |
| 5 — Implement | NgOptimizedImage, lazy routes, @defer, OnPush | `angular-spa` agent | Code changes complete |
| 6 — Verify | Re-run Lighthouse, quantify improvements | `browser-testing` + `code-reviewer` | All CWV in "Good" range |

---

## Common Pitfalls

- **Optimizing without a baseline** — you cannot claim improvement without a before measurement; always record Phase 2 numbers first
- **Skipping `priority` on LCP image** — `NgOptimizedImage` without `priority` on the hero image still loads lazily; the largest contentful paint image must have `priority`
- **`@defer` on above-fold content** — deferring content the user sees immediately increases LCP; `@defer` is for below-fold only
- **`Default` change detection with signals** — signals improve reactivity but do not reduce zone.js re-render cycles unless `OnPush` is also applied
- **No explicit `width`/`height` on images** — causes CLS as browser cannot reserve layout space; always set both attributes

## Related Workflows

- [`feature-angular-spa.md`](feature-angular-spa.md) — full Angular feature development workflow
- [`browser-e2e-testing.md`](browser-e2e-testing.md) — E2E and Lighthouse testing with Chrome DevTools MCP
- [`design-system-compliance.md`](design-system-compliance.md) — design token enforcement alongside performance work
