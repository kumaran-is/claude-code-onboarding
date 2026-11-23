# Web Performance Optimization — Checklists, Examples & Tools

Extended reference content moved from `../SKILL.md`.

---

## Example 1: Fixing Core Web Vitals on Angular SPA

```markdown
## Performance Audit Results

### Current Metrics (Before Optimization)
- **LCP (Largest Contentful Paint):** 4.2s (target: < 2.5s)
- **INP (Interaction to Next Paint):** 320ms (target: < 200ms)
- **CLS (Cumulative Layout Shift):** 0.25 (target: < 0.1)
- **Lighthouse Score:** 58/100

### Issues Identified

1. **LCP:** Hero image (2.5MB JPEG) loads without priority hint — browser discovers it late
2. **INP:** All components use `ChangeDetectionStrategy.Default` — full tree re-renders on every event
3. **CLS:** Product images have no width/height — browser cannot reserve layout space
```

### Fix LCP — NgOptimizedImage with priority

**Before:**
```html
<img src="/hero.jpg" alt="Hero banner">
```

**After (app.component.ts):**
```typescript
import { NgOptimizedImage } from '@angular/common';

@Component({
  imports: [NgOptimizedImage],
  template: `
    <!-- priority: fetchpriority="high", eager loading, and a preconnect check; a preload link is added when server-rendered -->
    <img ngSrc="/hero.jpg"
         width="1200"
         height="600"
         priority
         alt="Hero banner" />
  `
})
export class AppComponent {}
```

`NgOptimizedImage` automatically:
- Adds `fetchpriority="high"` for the `priority` image (preload link only in server-rendered output — UNVERIFIED for CSR, check the emitted HTML)
- Requires `width`/`height` (or `fill`) — a dev-mode runtime error otherwise — eliminating CLS from that image
- Lazy-loads all non-priority images by default

**Additional LCP steps:**
- Compress hero image to < 200KB (use `sharp` pipeline — see Example 3)
- Serve from a CDN; `Cache-Control: public, max-age=31536000, immutable` only when the file name contains a content hash (files in `public/` are copied unhashed — give them `no-cache` or version the name)
- Preload critical font: `<link rel="preload" as="font" href="/fonts/inter.woff2" crossorigin>`

### Fix INP — OnPush + Signals

**Before:**
```typescript
@Component({
  // Default strategy: checked whenever any change detection runs above it
  template: `<div>{{ user.name }}</div>`
})
export class ProfileComponent {
  @Input() user!: User;
}
```

**After** (compiled on Angular 21.2.26):
```typescript
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export interface User { firstName: string; lastName: string; }

@Component({
  selector: 'app-profile',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div>{{ fullName() }}</div>`,
})
export class ProfileComponent {
  readonly user = input.required<User>();
  // Re-evaluates only when the user input changes; the view is checked only when a signal it reads changes
  readonly fullName = computed(() => `${this.user().firstName} ${this.user().lastName}`);
}
```

**Rule:** Every component declares `ChangeDetectionStrategy.OnPush` and reads state through signals. v21 apps are zoneless by default, so checks are scheduled by signal and event notifications; `Default` components are still re-checked on every pass that reaches them.

### Fix CLS — NgOptimizedImage dimensions + skeleton loaders

NgOptimizedImage enforces `width` and `height` on every `ngSrc` image — this eliminates image-induced CLS at the framework level.

For dynamically-loaded content (lists, cards that appear after API response):

```html
<!-- Reserve space before data arrives — prevents layout jump -->
@if (products()) {
  @for (product of products(); track product.id) {
    <app-product-card [product]="product" />
  }
} @else {
  @for (i of skeletonCount; track i) {
    <div class="skeleton h-48 w-full rounded-lg"></div>
  }
}
```

```css
/* Always specify aspect ratio so the browser reserves exact space */
.product-image {
  aspect-ratio: 4 / 3;
  width: 100%;
  height: auto;
}
```

### Results After Optimization
- **LCP:** 1.7s (improved by 60%)
- **INP:** 80ms (improved by 75%)
- **CLS:** 0.04 (improved by 84%)
- **Lighthouse Score:** 93/100

---

## Example 2: Reducing Angular Bundle Size

### Current State
- **Initial Bundle:** 820KB (gzipped: 265KB) — exceeds angular.json 500KB warning budget
- **Load Time (3G):** 9.1s
- **ng build output:** WARNING: budget exceeded by 320KB

### Step 1: Diagnose with Stats JSON

```bash
# Production is the default configuration; writes the esbuild metafile dist/<project>/stats.json
ng build --stats-json
# Open dist/<project>/stats.json at https://esbuild.github.io/analyze/ (webpack-bundle-analyzer cannot read it)
```

**Findings from analyzer:**
1. `moment.js` — 67KB (only `format()` used — replace with `date-fns`)
2. `lodash` — 72KB (full import, only 3 functions needed)
3. Admin feature loaded eagerly — 180KB that 95% of users never need
4. No `@defer` on heavy chart component — 95KB loaded on every page visit

### Step 2: Replace Heavy Dependencies

```bash
# Remove moment.js (67KB) → date-fns (tree-shakable, 12KB for format())
npm uninstall moment
npm install date-fns
```

```typescript
// Before
import moment from 'moment';
const formatted = moment(date).format('YYYY-MM-DD');

// After — only imports the format function (~2KB)
import { format } from 'date-fns';
const formatted = format(date, 'yyyy-MM-dd');
```

**Savings: ~55KB**

```typescript
// Before — full lodash (72KB)
import _ from 'lodash';
const unique = _.uniq(array);

// After — named cherry-pick (4KB) or native
import { uniq } from 'lodash-es';
// or just:
const unique = [...new Set(array)];
```

**Savings: ~68KB**

### Step 3: Lazy-Load Feature Routes

```typescript
// app.routes.ts — BEFORE: eager imports
import { AdminComponent } from './admin/admin.component';    // 180KB loaded upfront
import { DashboardComponent } from './dashboard/dashboard.component';

export const routes: Routes = [
  { path: 'admin', component: AdminComponent },
  { path: 'dashboard', component: DashboardComponent }
];

// AFTER: lazy-loaded routes — each chunk only fetches when the user navigates there
export const routes: Routes = [
  {
    path: 'admin',
    loadComponent: () => import('./admin/admin.component')
      .then(m => m.AdminComponent)
  },
  {
    path: 'dashboard',
    loadChildren: () => import('./dashboard/dashboard.routes')
      .then(m => m.DASHBOARD_ROUTES)
  }
];
```

**Savings: ~180KB removed from initial bundle**

### Step 4: @defer for Below-Fold Components

```html
<!-- Before: HeavyChartComponent (95KB) loaded at startup even if user never scrolls -->
<app-heavy-chart [data]="chartData()" />

<!-- After: deferred until the element enters the viewport -->
@defer (on viewport) {
  <app-heavy-chart [data]="chartData()" />
} @loading (minimum 300ms) {
  <div class="skeleton h-64 w-full rounded-lg"></div>
} @placeholder {
  <div class="h-64 w-full bg-base-200 rounded-lg flex items-center justify-center">
    <span class="text-base-content/50">Chart</span>
  </div>
} @error {
  <div class="alert alert-error">Failed to load chart</div>
}
```

**Savings: ~95KB removed from initial bundle**

### Step 5: Configure Build Budgets in angular.json

Budgets fail the build before a bloated bundle reaches production — only if CI runs `ng build`. Values are examples; set them from your measured baseline:

```json
"configurations": {
  "production": {
    "budgets": [
      {
        "type": "initial",
        "maximumWarning": "500kb",
        "maximumError": "1mb"
      },
      {
        "type": "anyComponentStyle",
        "maximumWarning": "4kb",
        "maximumError": "8kb"
      }
    ]
  }
}
```

### Step 6: Defer Third-Party Analytics

```typescript
// core/telemetry/analytics-loader.ts — load a third-party script after first render, without blocking it
import { DOCUMENT, Injectable, afterNextRender, inject } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class AnalyticsLoader {
  private readonly document = inject(DOCUMENT);

  /** Call from the root component's constructor. afterNextRender never runs on the server. */
  scheduleLoad(src: string, integrity: string): void {
    afterNextRender(() => {
      const append = (): void => {
        const script = this.document.createElement('script');
        script.src = src;               // exact, versioned URL — also listed in CSP script-src
        script.integrity = integrity;   // SRI hash of that exact file
        script.crossOrigin = 'anonymous';
        script.async = true;
        this.document.head.appendChild(script);
      };
      // The window 'load' event may already have fired by the time the app renders
      if (this.document.readyState === 'complete') append();
      else this.document.defaultView?.addEventListener('load', append, { once: true });
    });
  }
}
```

The old pattern (`ngAfterViewInit` + `window.addEventListener('load', …)`) never loads the script when `load` has already fired before the app renders. The script is also third-party code with full page access: pin the version, add SRI and list its origin in CSP (`security-reviewer/reference/web-frontend-security.md` §2).

### Results

- **Initial Bundle:** 340KB (reduced by 59%)
- **Gzipped:** 108KB
- **Load Time (3G):** 3.4s (improved by 63%)
- **ng build:** No budget warnings

---

## Example 3: Image Optimization with NgOptimizedImage + AVIF/WebP Pipeline

### Current Issues
- 18 images totaling 14MB — all uncompressed JPEG
- No modern formats (WebP, AVIF)
- No responsive srcsets
- No dimensions — causing CLS
- Hero image not marked as LCP priority

### Step 1: Build AVIF/WebP Pipeline with sharp

```bash
npm install --save-dev sharp
```

```javascript
// scripts/optimize-images.mjs
import sharp from 'sharp';
import { readdirSync } from 'fs';
import { join, basename, extname } from 'path';

const INPUT_DIR = './src/assets/images/raw';
const OUTPUT_DIR = './src/assets/images/optimized';

async function optimizeImage(inputPath) {
  const name = basename(inputPath, extname(inputPath));

  // AVIF — best compression (~50% smaller than WebP)
  await sharp(inputPath)
    .avif({ quality: 70 })
    .toFile(join(OUTPUT_DIR, `${name}.avif`));

  // WebP — broad browser support
  await sharp(inputPath)
    .webp({ quality: 80 })
    .toFile(join(OUTPUT_DIR, `${name}.webp`));

  // JPEG fallback — progressive for perceived speed
  await sharp(inputPath)
    .jpeg({ quality: 80, progressive: true })
    .toFile(join(OUTPUT_DIR, `${name}.jpg`));

  // Responsive sizes
  for (const width of [400, 800, 1200]) {
    await sharp(inputPath)
      .resize({ width })
      .avif({ quality: 70 })
      .toFile(join(OUTPUT_DIR, `${name}-${width}.avif`));

    await sharp(inputPath)
      .resize({ width })
      .webp({ quality: 80 })
      .toFile(join(OUTPUT_DIR, `${name}-${width}.webp`));
  }
}

const images = readdirSync(INPUT_DIR).filter(f => /\.(jpg|jpeg|png)$/i.test(f));
await Promise.all(images.map(img => optimizeImage(join(INPUT_DIR, img))));
console.log(`Optimized ${images.length} images`);
```

```bash
node scripts/optimize-images.mjs
```

### Step 2: NgOptimizedImage — Above-fold (LCP) Images

```typescript
// hero.component.ts
import { Component } from '@angular/core';
import { NgOptimizedImage } from '@angular/common';

@Component({
  imports: [NgOptimizedImage],
  template: `
    <!-- priority = fetchpriority="high" + <link rel="preload"> automatically injected -->
    <img ngSrc="/assets/images/optimized/hero.avif"
         width="1200"
         height="600"
         sizes="(max-width: 768px) 100vw, 50vw"
         priority
         alt="Hero banner" />
  `
})
export class HeroComponent {}
```

Format negotiation needs a server: an image CDN loader (below) reads the `Accept` header and returns AVIF/WebP. A static `.avif` file referenced directly has **no** fallback — browsers without AVIF support show a broken image. Without a loader, serve WebP (or JPEG) from `ngSrc`, or use a plain `<picture>` with `<source type="image/avif">` + a JPEG/WebP `<img>` fallback.

### Step 3: NgOptimizedImage — Below-fold (Lazy) Images

```typescript
// product-list.component.ts
import { Component, inject } from '@angular/core';
import { NgOptimizedImage } from '@angular/common';
import { ProductService } from './product.service';

@Component({
  imports: [NgOptimizedImage],
  template: `
    @for (product of products(); track product.id) {
      <!-- No priority attribute = loading="lazy" applied automatically -->
      <img ngSrc="/assets/images/optimized/{{ product.imageSlug }}.avif"
           width="400"
           height="300"
           sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
           [alt]="product.name" />
    }
  `
})
export class ProductListComponent {
  private productService = inject(ProductService);
  products = this.productService.products;
}
```

### Step 4: Configure Image CDN Loader (Optional — for automatic format negotiation)

```typescript
// app.config.ts
import { provideImgixLoader } from '@angular/common';

export const appConfig: ApplicationConfig = {
  providers: [
    // Imgix, Cloudinary, Cloudflare Images, or custom loader
    provideImgixLoader('https://your-subdomain.imgix.net')
  ]
};
```

With a CDN loader, you only set `ngSrc="/hero.jpg"` — the loader appends format/width parameters automatically, serving AVIF to supporting browsers with no manual file variants needed.

### Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Total Image Size | 14MB | 1.9MB | 86% reduction |
| LCP | 4.8s | 1.6s | 67% faster |
| CLS (images) | 0.22 | 0.00 | 100% eliminated |
| Page Load (3G) | 21s | 4.8s | 77% faster |

---

## Performance Checklist

### Angular Architecture
- [ ] `ChangeDetectionStrategy.OnPush` on ALL components — no exceptions
- [ ] Signals (`signal()`, `computed()`) used for all reactive state — no `BehaviorSubject` for component state
- [ ] No side-effectful or CommonJS barrel imports (check the metafile; side-effect-free ESM barrels tree-shake)
- [ ] Every `@for` has a stable `track` expression (an id, not `$index` for mutable lists); no legacy `*ngFor`

### Bundle Size
- [ ] All feature routes use `loadComponent` or `loadChildren` — zero eagerly imported feature components in `app.routes.ts`
- [ ] `@defer` blocks wrapping all below-fold heavy components
- [ ] `ng build` (production is the default configuration; `--prod` no longer exists) run in CI from `npm ci`
- [ ] Budgets for `initial` and `anyComponentStyle` in `angular.json`, and a CI job that runs `ng build` so the error threshold actually gates merges
- [ ] Bundle analyzed with `ng build --stats-json` → esbuild analyzer — no unexpected large chunks
- [ ] Heavy libraries replaced: `moment` → `date-fns`, full `lodash` → cherry-picked `lodash-es`

### Images
- [ ] Every `<img>` uses `ngSrc` (NgOptimizedImage directive) — no raw `src` on images
- [ ] All `ngSrc` images have explicit `width` and `height` attributes
- [ ] LCP image has `priority` attribute
- [ ] Non-LCP images have NO `priority` attribute (browser lazy-loads automatically)
- [ ] AVIF/WebP via a negotiating loader or `<picture>` with a fallback — never a bare `.avif` with no fallback
- [ ] `immutable` caching only for content-hashed image URLs

### CSS
- [ ] Critical CSS inlining (`optimization.styles.inlineCritical`, default **true** for every production build, CSR included) is compatible with your CSP: under `script-src 'self'` it leaves the global stylesheet at `media="print"` (unstyled app, verified in Chromium). Either set `inlineCritical: false` (measure the LCP cost) or use `autoCsp` — `security-reviewer/reference/web-frontend-security.md` §2
- [ ] No unused CSS (TailwindCSS emits only used utilities at build time)
- [ ] Component styles stay under the `anyComponentStyle` budget you set

### Core Web Vitals Targets
- [ ] LCP < 2.5s
- [ ] INP < 200ms
- [ ] CLS < 0.1
- [ ] TTFB < 800ms (diagnostic, not a Core Web Vital)
- [ ] Field data (CrUX or RUM at p75), not only a Lighthouse run

### SSR (if using @angular/ssr)
- [ ] `provideClientHydration()` in the browser config — it caches HttpClient GET/HEAD responses from the server render; no manual `TransferState` around HttpClient
- [ ] `withIncrementalHydration()` (opt-in in v21) with `hydrate on …` triggers for below-fold sections
- [ ] Browser-only work in `afterNextRender`; never branch rendered template content on `isPlatformBrowser` (hydration mismatch, CLS)

---

## Performance Tools

### Measurement
- **Lighthouse** — Comprehensive audit; run in Chrome DevTools → Lighthouse tab
- **PageSpeed Insights** — Real user metrics (CrUX data) + lab data: https://pagespeed.web.dev
- **Chrome DevTools Performance tab** — Frame-level profiling and long task identification
- **Angular DevTools** — Component tree profiler, change detection cycle inspector
- **Web Vitals Chrome Extension** — Overlay CWV metrics on any live page

### Bundle Analysis
- `ng build --stats-json` — esbuild metafile at `dist/<project>/stats.json`; open at https://esbuild.github.io/analyze/
- **Bundlephobia** (https://bundlephobia.com) — check npm package size before installing
- **source-map-explorer** — build with source maps, then `npx -y source-map-explorer@2.5.3 dist/<project>/browser/main-*.js` — byte-level breakdown (do not deploy the maps)

### Image Optimization
- **sharp** (`npm install --save-dev sharp`) — Node.js image conversion pipeline
- **Squoosh** (https://squoosh.app) — browser-based manual AVIF/WebP conversion
- **ImageOptim** — macOS GUI for batch compression

### Monitoring (Post-Deploy)
- **Google Search Console** — Core Web Vitals report from real users
- **web-vitals 6.x** — self-hosted field LCP/INP/CLS (`../SKILL.md` § Field Measurement)
- Hosted RUM/error vendors are examples, not requirements; whichever you use, apply the redaction rules in `deployment-ci-cd/reference/web-frontend-delivery.md`
