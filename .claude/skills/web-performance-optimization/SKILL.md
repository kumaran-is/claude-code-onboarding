---
name: web-performance-optimization
description: "Optimize Angular 21.x web application performance including Core Web Vitals (LCP, INP, CLS), field measurement with web-vitals RUM, bundle size, lazy loading with @defer, NgOptimizedImage, OnPush+Signals, SSR/prerender with the HttpClient hydration cache, and SEO for public sites. Use when diagnosing slow Angular apps, preparing for Lighthouse audits, or reducing bundle size — always measure with profiling tools before making changes."
risk: low
source: community (adapted for Angular 21.x)
date_added: "2026-02-27"
updated: "2026-11-22"
last-reviewed: "2026-11-22"
allowed-tools: "Read, Grep, Glob, Bash, Edit, Write"
metadata:
  triggers: web performance, Core Web Vitals, LCP, INP, CLS, Lighthouse, bundle size, stats.json, NgOptimizedImage, defer, hydration, prerender, SEO, web-vitals, RUM
  related-skills: angular, angular-best-practices, browser-testing, deployment-ci-cd
---

## Iron Law

**NO PERFORMANCE OPTIMIZATION WITHOUT MEASURING FIRST — run Lighthouse (lab), check field data (CrUX / web-vitals RUM) and `ng build --stats-json` before writing a single optimization**

Profile before optimizing. Every change must have a before/after metric. Do not optimize based on guesswork.

# Web Performance Optimization — Angular 21.x

## Overview

Help developers optimize Angular 21.x SPA performance to improve user experience and Core Web Vitals. This skill provides systematic approaches to measure, analyze, and improve loading speed, runtime performance, and bundle size — grounded in Angular-native patterns (signals, `@defer`, `NgOptimizedImage`, lazy routes, hydration).

**Evidence (2026-11-22, Angular 21.2.26, TypeScript 5.9.3, Chromium via Playwright 1.58.2):** the SSR/hydration,
SEO and RUM snippets below compile with `ngc`; the web-vitals beacon, the image-space claim and the
critical-CSS/CSP interaction were measured in Chromium. Canonical SSR/hydration setup lives in
`angular/references/ssr-hydration.md`; this skill covers the performance angle only.

## When to Use This Skill

- Angular SPA loads slowly or scores poorly on Lighthouse
- Optimizing for Core Web Vitals (LCP, INP, CLS) — INP replaced FID in March 2024; `onFID` no longer exists in `web-vitals` 6.x (compile error verified)
- Reducing JavaScript bundle size output by `ng build`
- Improving Time to Interactive (TTI) or First Contentful Paint (FCP)
- Optimizing images and assets inside Angular templates
- Implementing lazy loading via routes or `@defer` blocks
- Debugging Angular change detection performance
- Preparing for performance audits on an Angular production build

## How It Works

### Step 1: Measure Current Performance

Establish baseline metrics before touching any code:

- Run Lighthouse audit (Chrome DevTools → Lighthouse tab) — lab data; INP needs real interactions, so lab runs show TBT instead
- Read field data: PageSpeed Insights / Search Console (CrUX) for public sites, your own RUM (below) for any app
- Build with stats: `ng build --stats-json` (production is the default configuration; `--prod` no longer exists).
  The application builder writes an **esbuild metafile** to `dist/<project>/stats.json` (keys `inputs`/`outputs`, verified).
  Open it at https://esbuild.github.io/analyze/ — `webpack-bundle-analyzer` does not read this format.
  Byte-level view of emitted JS: build with `sourceMap` on, then `npx -y source-map-explorer@2.5.3 dist/<project>/browser/main-*.js`
- Check network waterfall in Chrome DevTools → Network tab
- Profile change detection with Angular DevTools browser extension

### Step 2: Identify Issues

Angular-specific performance bottlenecks to look for:

- Large initial bundle — missing lazy routes or barrel file imports pulling everything in
- Default change detection (`ChangeDetectionStrategy.Default`) triggering excessive re-renders
- `BehaviorSubject` + `async` pipe causing unnecessary subscriptions instead of signals
- Images without `ngSrc` (NgOptimizedImage) missing auto-sizing and LCP hints
- Below-fold heavy components not wrapped in `@defer` blocks
- Double HTTP fetches in SSR — usually `provideClientHydration()` missing, the request carries `Authorization`, or server and client use different API origins (see Pitfalls)
- Third-party scripts loaded synchronously in `index.html`

### Step 3: Prioritize Optimizations

Focus on highest-impact Angular improvements first:

1. **Critical rendering path** — `NgOptimizedImage` with `priority` on LCP image, `<link rel="preload">` for fonts
2. **Bundle size** — lazy routes (`loadComponent`/`loadChildren`), `@defer` for below-fold components
3. **Runtime rendering** — `OnPush` + signals on all components, eliminate `Default` change detection
4. **Image pipeline** — convert to AVIF/WebP, serve responsive srcsets via `NgOptimizedImage`
5. **SSR double-fetch** — `provideClientHydration()` reuses server HttpClient responses; no manual TransferState for HttpClient

### Step 4: Implement Optimizations

Apply improvements in priority order — measure after each step.

### Step 5: Verify Improvements

- Re-run Lighthouse — compare scores before/after
- Re-run `ng build --stats-json` — compare bundle sizes (the CLI prints initial/lazy chunk sizes; budgets fail the build)
- Verify no layout shifts introduced (Chrome DevTools → Rendering → Layout Shift Regions)
- Test on throttled mobile: Chrome DevTools → Network 3G + CPU 4x slowdown
- Monitor LCP/INP/CLS from real users after deploy (RUM snippet below; CrUX for public sites)

---

## Examples

> See [references/optimization-checklists.md](references/optimization-checklists.md) for full worked examples with before/after code and measured results.

- **Example 1:** Fixing Core Web Vitals (LCP, INP, CLS) — NgOptimizedImage, OnPush+Signals, skeleton loaders
- **Example 2:** Reducing bundle size 59% — dependency replacement, lazy routes, `@defer`, build budgets
- **Example 3:** Image pipeline (AVIF/WebP with `sharp`) + CDN loader configuration

---

## Best Practices

### Do This

- **Measure First** — always run Lighthouse, check field data and `ng build --stats-json` before any optimization
- **OnPush Everywhere** — every component must declare `ChangeDetectionStrategy.OnPush`
- **Signals for State** — use `signal()` and `computed()` instead of `BehaviorSubject` + `async` pipe
- **Lazy Routes** — use `loadComponent`/`loadChildren` for every feature — nothing should be eagerly imported in `app.routes.ts`
- **@defer for Below-Fold** — any component not visible on first paint belongs in an `@defer (on viewport)` block
- **NgOptimizedImage** — replace every `<img>` in Angular templates with `ngSrc`; never bypass it
- **Build Budgets** — set `maximumWarning: 500kb` / `maximumError: 1mb` in `angular.json` so CI fails before a bloated build ships
- **Preload Critical Resources** — `<link rel="preload">` for critical fonts; `priority` attribute on LCP image
- **Hydration cache in SSR** — `provideClientHydration()` transfers HttpClient GET/HEAD responses automatically; use `TransferState` only for non-HttpClient data
- **Use CDN** — serve `dist/<project>/browser/` from a CDN; `immutable` only for content-hashed bundle files, `no-cache` for `index.html`, `config.json` and anything copied from `public/` unhashed (`firebase-hosting-basics/references/configuration.md`)

### Do Not Do This

- **Do not use `ChangeDetectionStrategy.Default`** — this is the single largest Angular runtime performance killer
- **Do not import side-effectful barrel files** — esbuild tree-shakes ESM barrels whose packages are side-effect free; barrels with top-level side effects or CommonJS re-exports pull in everything. Check the metafile before banning
- **Do not lazy-load too granularly** — chunks under 10KB create more HTTP overhead than they save; colocate small components
- **Do not block rendering** — no synchronous `<script>` in `index.html`; use `defer` or post-bootstrap dynamic injection
- **Do not skip `width`/`height`** on `ngSrc` images (or use `fill`) — NgOptimizedImage reports it as a runtime error in dev mode, and CLS will spike in prod
- **Do not optimize without evidence** — profile first with Chrome DevTools and Angular DevTools; fix the proven bottleneck

---

## Common Pitfalls

### Problem: Good Desktop Score, Poor Mobile Score
**Symptoms:** Lighthouse passes on desktop, fails on mobile throttling
**Solution:**
- Test with CPU 4x slowdown + 3G in Chrome DevTools
- Check INP: Angular Default change detection collapses on slow CPUs — switch all components to OnPush + signals
- Remove `@defer` triggers that never fire on mobile (e.g., hover-based triggers on touch devices)
```bash
# Lighthouse 13.6.0 CLI defaults to the mobile form factor (desktop needs --preset=desktop); keep the default for a mobile problem
npx -y lighthouse@13.6.0 https://example.com --only-categories=performance --view
```

### Problem: Bundle Size Exceeds angular.json Budget
**Symptoms:** `ng build` exits with "ERROR: bundle initial exceeded maximum budget"
**Solution:**
- Build with `ng build --stats-json` and load `dist/<project>/stats.json` into https://esbuild.github.io/analyze/
- Convert eager feature imports to lazy routes
- Replace heavy libraries (moment → date-fns, full lodash → lodash-es cherry-picks)
- Wrap heavy components in `@defer`
```bash
ng build --stats-json            # writes dist/<project>/stats.json (esbuild metafile)
```

### Problem: Images Cause Layout Shifts (High CLS)
**Symptoms:** CLS > 0.1 in Lighthouse, content jumps on load
**Solution:**
- Use `ngSrc` with `width`/`height` (or `fill` inside a sized container)
- Plain `<img>`: set the `width` and `height` **attributes** and `height: auto` in CSS — browsers derive the aspect ratio from the attributes
- Do **not** add `aspect-ratio: attr(width) / attr(height)`: in Chromium it parses but computes to `auto`, discarding the attribute-derived ratio. Measured before the image loads, a 400px-wide 800×400 image reserved 200px without that rule and **0px** with it — the rule causes the shift it claims to prevent
- For dynamic image lists, render skeleton placeholders at the correct height before data arrives
```css
img { max-width: 100%; height: auto; }   /* with width="800" height="400" attributes on the element */
```

### Problem: Slow TTFB with Angular SSR
**Symptoms:** Time to First Byte > 600ms, server HTML arrives late
**Solution:** TTFB is server and data latency — hydration settings do not change it.
- Prerender (`RenderMode.Prerender`) every route whose HTML does not depend on the request
- Cache slow upstream API responses server-side; cache SSR HTML at the CDN only for anonymous, non-personalised pages
- Measure the server: time spent awaiting data vs rendering
- Incremental hydration (`withIncrementalHydration()`, opt-in in v21) reduces **client** JS work after the HTML arrives (helps INP/TBT), not TTFB

### Problem: SSR Double HTTP Fetch
**Symptoms:** Network tab shows the same API call twice (once server, once client)
**Solution:** `provideClientHydration()` already caches HttpClient GET/HEAD responses made during server render and
replays them on the client — hand-written `TransferState` around `HttpClient` is redundant. When you still see two
fetches, check, in order:
1. `provideClientHydration()` is missing from the browser `appConfig`
2. The request carries `Authorization`/`Proxy-Authorization` — excluded from the cache by default
   (`withHttpTransferCacheOptions({ includeRequestsWithAuthHeaders: true })` only for non-user-specific data)
3. Server and browser call different origins (internal vs public URL) — map them with `HTTP_TRANSFER_CACHE_ORIGIN_MAP`,
   provided on the server only
4. The request is not GET/HEAD, or it is issued outside the initial render

```typescript
// app.config.ts — browser
import { ApplicationConfig } from '@angular/core';
import { provideHttpClient, withFetch } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { provideClientHydration, withIncrementalHydration } from '@angular/platform-browser';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes),
    provideHttpClient(withFetch()),
    provideClientHydration(withIncrementalHydration()), // HttpClient transfer cache is on by default
  ],
};

// app.config.server.ts — server (provideServerRendering comes from @angular/ssr, not @angular/platform-server)
import { mergeApplicationConfig } from '@angular/core';
import { provideServerRendering, withRoutes } from '@angular/ssr';
import { appConfig } from './app.config';
import { serverRoutes } from './app.routes.server';

export const config = mergeApplicationConfig(appConfig, {
  providers: [provideServerRendering(withRoutes(serverRoutes))],
});
```

---

## Performance Checklist

> See [references/optimization-checklists.md](references/optimization-checklists.md) for the full checklist (Angular Architecture, Bundle Size, Images, CSS, Core Web Vitals targets, SSR).

**Critical items:**
- [ ] `ChangeDetectionStrategy.OnPush` on ALL components — no exceptions
- [ ] All feature routes use `loadComponent` or `loadChildren`
- [ ] LCP image has `priority` attribute; all other `ngSrc` images do not
- [ ] SSR/prerender: `provideClientHydration()` present; no hand-written TransferState around HttpClient
- [ ] Field LCP/INP/CLS reported from real users (RUM below) and reviewed after each release

---

## Performance Tools

> See [references/optimization-checklists.md](references/optimization-checklists.md) for full tool list (Measurement, Bundle Analysis, Image Optimization, Monitoring).

- **Lighthouse** — Chrome DevTools → Lighthouse tab
- **Angular DevTools** — Component tree profiler, change detection inspector
- `ng build --stats-json` → `dist/<project>/stats.json` → https://esbuild.github.io/analyze/
- `web-vitals` 6.x RUM (below) for field LCP/INP/CLS

---

## Field Measurement (RUM) with web-vitals

Lab scores do not contain INP from real input. Report field metrics from every production app — public or not.
Pin `web-vitals@6.2.3` (`npm install -E web-vitals@6.2.3`). Verified: this exact snippet compiled on TS 5.9 and, in
Chromium, sent one beacon each for LCP, INP and CLS after a click and a page hide, carrying only the route template
(a `?secret=` query parameter on the page URL did not appear in any beacon).

```typescript
// core/telemetry/rum.ts — call once after bootstrap, in the browser only
import { onCLS, onINP, onLCP, type Metric } from 'web-vitals';

export function reportWebVitals(endpoint: string, release: string, routeTemplate: () => string): void {
  const send = (metric: Metric): void => {
    const body = JSON.stringify({
      name: metric.name, value: metric.value, rating: metric.rating, id: metric.id,
      navigationType: metric.navigationType, route: routeTemplate(), release, // route template, never the raw URL
    });
    if (!navigator.sendBeacon(endpoint, new Blob([body], { type: 'application/json' }))) {
      void fetch(endpoint, { method: 'POST', body, keepalive: true, headers: { 'content-type': 'application/json' } });
    }
  };
  onCLS(send);
  onINP(send);
  onLCP(send);
}
```

- Thresholds (good, p75): LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1. Aggregate by route template and release.
- Debug a poor INP/LCP with the attribution build (`web-vitals/attribution`) in a sampled subset.
- The endpoint is same-origin or listed in CSP `connect-src`; no user ids, emails or query strings in the payload.
- Tracing/OTel and error monitoring: `deployment-ci-cd/reference/web-frontend-delivery.md`.

## SEO — public, indexable pages only

Applies to marketing pages, docs and other content that must appear in search. **Authenticated apps and admin consoles
are not SEO targets**: send `X-Robots-Tag: noindex` from the host (or `<meta name="robots" content="noindex">`), keep
them out of sitemaps, and skip everything below.

- Crawlers and link-preview scrapers often do not run JavaScript. A CSR-only page that sets tags with `Meta`/`Title`
  after boot shows the `index.html` defaults to them. Public pages need **prerender** (static hosting:
  `ng add @angular/ssr`, `"outputMode": "static"`, `RenderMode.Prerender`) or SSR.
- No soft 404s: a catch-all `{ path: '**', redirectTo: '' }` serves the home page with 200 for every URL. Route `**` to a
  real not-found page. On an SSR host give the server route `status: 404`; `RenderMode.Prerender` routes **cannot** set
  `status` (type error on 21.2, verified) — on static hosting add `noindex` on the not-found page.
- Unique `<title>` and `description` per route; canonical URL, Open Graph tags, sitemap and `robots.txt` all on the serving
  domain and changed together.
- Structured data (JSON-LD) states only verifiable facts — no ratings, reviews, offers or `sameAs` profiles that do not
  exist.

```typescript
// app.routes.ts
export const routes: Routes = [
  { path: '', loadComponent: () => import('./home.page').then((m) => m.HomePage) },
  { path: '**', loadComponent: () => import('./not-found.page').then((m) => m.NotFoundPage) }, // not redirectTo ''
];

// app.routes.server.ts
import { RenderMode, ServerRoute } from '@angular/ssr';
export const serverRoutes: ServerRoute[] = [
  { path: '', renderMode: RenderMode.Prerender },
  { path: '**', renderMode: RenderMode.Server, status: 404 }, // SSR host only
];

// home.page.ts (constructor) — tags are in the prerendered HTML
inject(Title).setTitle('Example — Home');
inject(Meta).updateTag({ name: 'description', content: 'What this public page offers, in one sentence.' });

// not-found.page.ts (constructor)
inject(Meta).updateTag({ name: 'robots', content: 'noindex' });
```

---

## Related Skills

- `angular-spa` — Angular component scaffolding, lazy routing, and daisyUI styling
- `angular-best-practices` — OnPush, signals, rendering performance, and SSR hydration patterns
- `angular` — Angular 21.x core API reference: Signals, `@defer`, TransferState, incremental hydration
- `browser-testing` — Chrome DevTools performance profiling via MCP; record traces, inspect long tasks (web targets; tool choice per `.claude/rules/testing-tool-selection.md`)
- `security-reviewer/reference/web-frontend-security.md` — CSP vs critical-CSS inlining trade-off
- `systematic-debugging` — Root-cause methodology for performance regressions

---

## Additional Resources

- [NgOptimizedImage Guide](https://angular.dev/guide/image-optimization) — official directive reference
- [@defer Blocks](https://angular.dev/guide/defer) — all trigger types (`on viewport`, `on idle`, `on interaction`, `when`)
- [Angular SSR](https://angular.dev/guide/ssr) — render modes, HttpClient caching, incremental hydration
- [web-vitals](https://github.com/GoogleChrome/web-vitals) — field measurement library
- [Core Web Vitals](https://web.dev/vitals/) — LCP, INP, CLS definitions and thresholds
- [Web.dev Performance](https://web.dev/performance/) — General web performance techniques

---

**Key principle:** Measure before optimizing. `ng build --stats-json` + the esbuild analyzer shows where the bundle weight is, and field RUM shows what users feel — every other optimization is guesswork without them.
