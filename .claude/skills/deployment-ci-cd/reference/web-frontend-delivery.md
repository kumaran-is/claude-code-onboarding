# Web Frontend Delivery (static SPA: Angular 22, React)

Release, configuration, caching, verification and client telemetry for browser apps served from static hosting
(Firebase Hosting, a bucket + CDN, or similar). Host-specific commands: `firebase-hosting-basics`. Security rules for
headers, tokens and CSP: `security-reviewer/reference/web-frontend-security.md`. Angular content was compiled and run on
Angular 21.2.26 / TS 5.9.3 / Node 24.13.1 / Chromium (Playwright 1.58.2) on 2026-11-22; the `ng build` output shape and
hash format were re-checked on Angular 22.3.0 / TS 6.0.3 / Node 26.13.1 on 2026-11-23. React notes are RECOMMENDED
PRACTICE.

## 1. Reproducible builds

- Build from a clean checkout of one commit, never a developer working tree: `git worktree add --detach <dir> <sha>` locally,
  or the CI checkout.
- `npm ci` (lockfile-exact; fails when `package.json` and the lockfile disagree). Never `npm install` in a release job.
- Pin Node: `.nvmrc` (e.g. `26.13.1`, the Active LTS; Angular 22 accepts `^22.22.3 || ^24.15.0 || ^26.0.0`) + `"engines": { "node": ">=26.13 <27" }` + `actions/setup-node` with
  `node-version-file: .nvmrc`. Pin GitHub Actions to commit SHAs (`firebase-hosting-basics/references/ci-cd-github-actions.md`).
- Angular: `ng build` (production is the default configuration; `--prod` no longer exists). Budgets fail the build only
  if a CI job runs it on every PR. React/Vite: `vite build`.
- Build once, promote the same artifact: preview → live by cloning/copying the tested files, not by rebuilding.
- A monorepo workspace member's own `version` can drift from the lockfile without `npm ci` failing — compare them in CI
  if you publish workspace packages (UNVERIFIED in this workspace).

## 2. Runtime config, not build-time environments

`environment.ts`, `fileReplacements`, `define`, `import.meta.env`/`VITE_*` are compiled into the bundle: one build per
environment, and every value is public. Prefer **one build** + a served `config.json` that is fetched before bootstrap,
validated, frozen, and failed **closed** with a visible message.

Verified: unit run (2 valid + 8 rejected inputs: http in production, local emulator host in production, relative URL,
credentials in URL, unknown key, missing release, bad environment, array) and Chromium runs of the built app — valid
config boots; an emulator host in a production config and a **missing** `config.json` both show the alert and no app.
The missing-file case matters: an SPA catch-all rewrite answers `/config.json` with `index.html` and HTTP 200, so a bare
`response.json()` fails with an opaque parse error.

```typescript
// core/config/runtime-config.ts — per-environment values fetched at boot, validated, then frozen
import { InjectionToken } from '@angular/core';

export interface RuntimeConfig {
  readonly environment: 'dev' | 'staging' | 'production';
  readonly apiBaseUrl: string;          // absolute, no trailing slash
  readonly release: string;             // build/release id for error and RUM reports
  readonly telemetryEndpoint?: string;  // optional, absolute
}

export const RUNTIME_CONFIG = new InjectionToken<RuntimeConfig>('RUNTIME_CONFIG');

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

function absoluteUrl(value: unknown, field: string, environment: string, problems: string[]): string | undefined {
  if (typeof value !== 'string' || value.length === 0) { problems.push(`${field}: required string`); return undefined; }
  let url: URL;
  try { url = new URL(value); } catch { problems.push(`${field}: not an absolute URL`); return undefined; }
  const local = LOCAL_HOSTS.has(url.hostname);
  if (url.protocol !== 'https:' && !(local && environment === 'dev')) problems.push(`${field}: must be https`);
  if (local && environment !== 'dev') problems.push(`${field}: local host in ${environment}`);
  if (url.username || url.password || url.search || url.hash) problems.push(`${field}: no credentials, query or fragment`);
  return value.replace(/\/+$/, '');
}

/** Throws with every problem listed; never returns a half-valid config. Values are public — no secrets here. */
export function parseRuntimeConfig(raw: unknown): RuntimeConfig {
  const problems: string[] = [];
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) throw new Error('config.json: expected an object');
  const input = raw as Record<string, unknown>;
  const allowed = new Set(['environment', 'apiBaseUrl', 'release', 'telemetryEndpoint']);
  for (const key of Object.keys(input)) if (!allowed.has(key)) problems.push(`${key}: unknown key`);
  const environment = input['environment'];
  if (environment !== 'dev' && environment !== 'staging' && environment !== 'production') problems.push('environment: dev | staging | production');
  const env = typeof environment === 'string' ? environment : 'production';
  const apiBaseUrl = absoluteUrl(input['apiBaseUrl'], 'apiBaseUrl', env, problems);
  const release = input['release'];
  if (typeof release !== 'string' || !/^[\w.-]{1,64}$/.test(release)) problems.push('release: 1-64 chars [A-Za-z0-9_.-]');
  const telemetryEndpoint = input['telemetryEndpoint'] === undefined ? undefined : absoluteUrl(input['telemetryEndpoint'], 'telemetryEndpoint', env, problems);
  if (problems.length > 0) throw new Error(`config.json invalid: ${problems.join('; ')}`);
  return Object.freeze({ environment: env as RuntimeConfig['environment'], apiBaseUrl: apiBaseUrl!, release: release as string, telemetryEndpoint });
}

export async function loadRuntimeConfig(path = '/config.json'): Promise<RuntimeConfig> {
  const response = await fetch(path, { cache: 'no-store', credentials: 'same-origin' });
  if (!response.ok) throw new Error(`config.json: HTTP ${response.status}`);
  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    // A missing file behind an SPA catch-all rewrite comes back as index.html with HTTP 200
    throw new Error('config.json: response is not JSON (missing file served as index.html?)');
  }
  return parseRuntimeConfig(raw);
}
```

```typescript
// main.ts — no config, no app: fail closed with a visible message
// API_CONFIG and the interceptor are the canonical ones in angular-spa/reference/web-security.md.
import { bootstrapApplication } from '@angular/platform-browser';
import { App } from './app/app';
import { appConfig } from './app/app.config';
import { API_CONFIG } from './app/core/config/api-config';
import { RUNTIME_CONFIG, loadRuntimeConfig } from './app/core/config/runtime-config';

loadRuntimeConfig()
  .then((config) =>
    bootstrapApplication(App, {
      providers: [
        ...appConfig.providers, // keep router, HttpClient + interceptors; replacing them fails with NG0201
        { provide: RUNTIME_CONFIG, useValue: config },
        // The token allowlist follows the validated config (the later provider wins over any API_CONFIG in appConfig).
        // The refresh path is your API's; adjust it.
        { provide: API_CONFIG, useValue: { apiRoots: [config.apiBaseUrl], refreshUrl: `${config.apiBaseUrl}/auth/refresh` } },
      ],
    }),
  )
  .catch((err: unknown) => {
    const message = document.createElement('p');
    message.setAttribute('role', 'alert');
    message.textContent = 'This app could not start. Please reload, or try again later.';
    document.body.replaceChildren(message);
    throw err; // keep it visible to the error monitor / console; no half-configured app
  });
```

- `config.json` holds **public** values only (API origin, release id, publishable ids). Unknown keys are rejected so a
  secret pasted into it fails the boot instead of shipping.
- Serve it with `Cache-Control: no-cache` so a config change or rollback applies on next load.
- The deploy job validates the same file before upload (reuse `parseRuntimeConfig` in a Node script) and refuses a
  production config that names `localhost`/emulator hosts.
- React: same shape — fetch and validate before `createRoot(...).render(...)` — RECOMMENDED.

## 3. Caching and CDN

| Path | Cache-Control | Why |
|---|---|---|
| `index.html`, SPA fallbacks, `config.json`, service-worker script | `no-cache` | Clients revalidate, so a deploy or rollback is seen on next load |
| Content-hashed bundles (`main-XXXXXXXX.js`, `chunk-*.js`, `styles-*.css`) | `public, max-age=31536000, immutable` | Name changes when content changes |
| Unhashed files copied from `public/`/`assets/` | `no-cache` (or version the file name) | An `immutable` glob that also matches `logo.png` or a theme script pins a stale file for a year |

- Check the real `dist/` listing before writing the hashed-file glob. Angular 21.2 and 22.3 emit uppercase base32 hashes
  (`main-43LP34PO.js` on 21.2, `main-WYLVDS3Y.js` on 22.3, verified); a Firebase Hosting rule for that is in `firebase-hosting-basics/references/configuration.md`
  (emulator-verified).
- Deploys must keep the **previous** release's hashed chunks reachable for a while: a tab opened before the deploy
  lazy-loads old chunk names. Hosts that publish immutable versions (Firebase Hosting) do this per version only while the
  old `index.html` is cached; handle a failed dynamic import by reloading once (`ChunkLoadError`/`Failed to fetch
  dynamically imported module`) — UNVERIFIED behaviour per host, test it.
- CDN invalidation: Firebase Hosting clears its CDN cache on each release (host-managed). On a bucket + CDN, upload hashed
  files first, then `index.html`/`config.json`, then invalidate only those two paths.
- Preview environments: one per PR, auto-expiring, `X-Robots-Tag: noindex`, never wired to production data with write
  access; each preview origin must be registered as an OAuth/Auth redirect origin or sign-in fails there.

## 4. Canary and rollback for static hosting

Static hosts usually cannot split traffic by percentage. The practical sequence:

1. Deploy the build to a preview channel/URL; run smoke E2E (Playwright — web targets, per
   `.claude/rules/testing-tool-selection.md`) and the header check (§6) against it.
2. Promote the **same files** (Firebase: `hosting:clone <site>:<channel> <site>:live`).
3. Run the header check against live; on failure roll back immediately (Firebase: release history *Rollback*, or clone the
   previous version) and alert.
4. Watch error rate and RUM (LCP/INP/CLS by release) for the first hour; compare with the previous release.

Percentage canaries need a server or edge layer (Cloud Run traffic splitting serving the SPA, an edge worker choosing
between two versions by cookie) — `gcp-cloud-run`.

## 5. Source maps stay private

- Build with `"sourceMap": { "scripts": true, "styles": false, "hidden": true }` in the production configuration: maps are
  generated, but bundles carry no `sourceMappingURL` comment.
- `hidden` does not stop the host from **serving** `*.map` files that sit in the deploy directory. Upload maps to the error
  tracker in CI, then delete them (`find dist -name '*.map' -delete`) or exclude them (`"ignore": ["**/*.map"]` on Firebase
  Hosting).
- CI asserts no map is deployed: `test -z "$(find dist -name '*.map' -print -quit)"`.

## 6. Post-deploy header check (live response)

Run after every deploy and fail the release on mismatch. Node ≥ 20, no dependencies. Retries cover CDN propagation.

Verified 2026-11-22 (each command's own exit code):

| Case | Exit |
|---|---|
| Correct headers + `--config` (static server) | 0 |
| Correct headers + `--config` (Firebase Hosting emulator, `firebase-tools@15.37.0`) | 0 |
| NEGATIVE: `'unsafe-inline'` in `script-src`, no `nosniff`, `index.html` immutable, `config.json` immutable | 1 (4 problems listed, 2 attempts) |
| NEGATIVE: `config.json` missing → SPA fallback HTML (Firebase emulator) | 1 |
| `--auto-csp` on an Angular `autoCsp` build with a header that omits `default-src`/`script-src` | 0 |
| NEGATIVE: `--auto-csp` with `default-src 'self'` in the header (blocks the loader) | 1 |
| NEGATIVE: `--auto-csp` on a build without the meta CSP | 1 |
| NEGATIVE: header without `script-src`/`default-src`, no flag | 1 |
| No URL argument | 2 |

```javascript
#!/usr/bin/env node
// scripts/check-headers.mjs — post-deploy check of the LIVE response. Node >= 20, no dependencies.
// Usage: node scripts/check-headers.mjs <origin-url> [--auto-csp] [--config] [--attempts N] [--delay-ms MS]
// Exit 0 = all checks pass, 1 = a check failed after all attempts, 2 = usage error.
const args = process.argv.slice(2);
const target = args.find((a) => !a.startsWith('--'));
const flag = (name) => args.includes(name);
const option = (name, fallback) => { const i = args.indexOf(name); return i >= 0 ? Number(args[i + 1]) : fallback; };
if (!target) { console.error('usage: check-headers.mjs <origin-url> [--auto-csp] [--config] [--attempts N] [--delay-ms MS]'); process.exit(2); }
const attempts = option('--attempts', 5);
const delayMs = option('--delay-ms', 5000);

function parseCsp(value) {
  const directives = new Map();
  for (const part of value.split(';')) {
    const [name, ...sources] = part.trim().split(/\s+/);
    if (name) directives.set(name.toLowerCase(), sources);
  }
  return directives;
}

async function check() {
  const problems = [];
  const page = await fetch(target, { redirect: 'manual', cache: 'no-store' });
  if (page.status !== 200) problems.push(`GET ${target}: HTTP ${page.status}`);
  const h = page.headers;
  const html = await page.text();

  const cspHeader = h.get('content-security-policy');
  if (!cspHeader) problems.push('Content-Security-Policy header missing');
  else {
    const csp = parseCsp(cspHeader);
    for (const required of ['object-src', 'base-uri', 'frame-ancestors']) if (!csp.has(required)) problems.push(`CSP lacks ${required}`);
    if (!(csp.get('object-src') ?? []).includes("'none'")) problems.push("CSP object-src is not 'none'");
    const scriptSources = csp.get('script-src') ?? csp.get('default-src');
    if (scriptSources) {
      for (const bad of ["'unsafe-inline'", "'unsafe-eval'", '*', 'http:', 'https:', 'data:']) {
        if (scriptSources.includes(bad)) problems.push(`CSP script-src/default-src allows ${bad}`);
      }
    } else if (!flag('--auto-csp')) problems.push('CSP has neither script-src nor default-src (pass --auto-csp only for an autoCsp build)');
    if (flag('--auto-csp')) {
      const meta = html.match(/<meta http-equiv="Content-Security-Policy" content="([^"]+)"/i);
      if (!meta || !meta[1].includes("'strict-dynamic'")) problems.push("--auto-csp: index.html has no hash-based meta CSP with 'strict-dynamic'");
      if (csp.has('default-src') || csp.has('script-src')) problems.push('--auto-csp: header must not set default-src/script-src (it would block the autoCsp loader)');
    }
  }
  const hsts = h.get('strict-transport-security') ?? '';
  const maxAge = Number(/max-age=(\d+)/i.exec(hsts)?.[1] ?? 0);
  if (maxAge < 31536000) problems.push(`Strict-Transport-Security max-age ${maxAge} < 31536000`);
  if ((h.get('x-content-type-options') ?? '').toLowerCase() !== 'nosniff') problems.push('X-Content-Type-Options is not nosniff');
  if (!h.get('referrer-policy')) problems.push('Referrer-Policy missing');
  const cache = (h.get('cache-control') ?? '').toLowerCase();
  if (!/no-cache|no-store|max-age=0\b/.test(cache)) problems.push(`index.html Cache-Control "${cache}" lets clients keep an old release`);

  if (flag('--config')) {
    const url = new URL('/config.json', target);
    const res = await fetch(url, { cache: 'no-store' });
    const type = res.headers.get('content-type') ?? '';
    if (res.status !== 200 || !type.includes('application/json')) problems.push(`${url}: HTTP ${res.status} ${type} (SPA fallback serving index.html?)`);
    else {
      try { await res.json(); } catch { problems.push(`${url}: not valid JSON`); }
      if (!/no-cache|no-store|max-age=0\b/.test((res.headers.get('cache-control') ?? '').toLowerCase())) problems.push(`${url}: must be no-cache`);
    }
  }
  return problems;
}

for (let attempt = 1; attempt <= attempts; attempt++) {
  let problems;
  try { problems = await check(); } catch (err) { problems = [`request failed: ${err instanceof Error ? err.message : String(err)}`]; }
  if (problems.length === 0) { console.log(`PASS ${target} (attempt ${attempt}/${attempts})`); process.exit(0); }
  console.error(`attempt ${attempt}/${attempts} FAIL ${target}\n  - ${problems.join('\n  - ')}`);
  if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, delayMs)); // CDN may still serve the previous release
}
process.exit(1);
```

Extend the required list with your own policy (`connect-src` origins, `X-Robots-Tag: noindex` for authenticated apps,
`Permissions-Policy`). Keep the negative cases in CI by running the script once against a deliberately weakened local
server — a check that has never failed proves nothing.

## 7. Error monitoring (browser)

A global `ErrorHandler` that only writes to `console` is not monitoring. Send errors to a service (self-hosted or vendor):

- Payload: error name, message, stack (symbolicated server-side with the private maps), release id, route **template**
  (`/orders/:id`), browser/OS. Not: tokens, cookies, `Authorization` headers, form values, emails, query strings or ids in
  URLs, and not `HttpErrorResponse.message`/server error bodies verbatim (servers echo submitted input).
- Sample and rate-limit client-side; deduplicate by fingerprint.
- Keep the dev-mode rethrow so errors stay visible locally; production still logs to the console for support sessions.
- Unhandled promise rejections and failed lazy chunks are errors too.
- The ingest endpoint is listed in CSP `connect-src`; its CORS allows only your app origins.

## 8. OpenTelemetry in the browser (EXPERIMENTAL upstream)

OpenTelemetry describes browser instrumentation as experimental; use it only if you already run a collector and need
frontend→backend traces. Package versions (`npm view`, 2026-11-22) are **not** a coherent set at their `latest` tags:
`@opentelemetry/sdk-trace-web@2.12.0` peers on `@opentelemetry/api <1.10.0`, while `instrumentation-fetch@0.301.2`
depends on `core@3.1.1` (peer `api >=1.10.0`). The set below installs cleanly and was tested:

`npm install -E @opentelemetry/api@1.9.1 @opentelemetry/sdk-trace-web@2.12.1 @opentelemetry/resources@2.12.1 @opentelemetry/instrumentation@0.223.2 @opentelemetry/instrumentation-fetch@0.223.2 @opentelemetry/exporter-trace-otlp-http@0.223.2 @opentelemetry/semantic-conventions@1.45.0`

Verified: compiles on TS 5.9.3 (`skipLibCheck: true`, the Angular default — the packages ship Node-only typings), bundled
with esbuild and run in Chromium: `traceparent` (`00-<32 hex>-<16 hex>-01`) was sent to `https://api.example.com/v1/orders`
and **not** to `https://api.example.com.evil.net/x` or a CDN URL. NEGATIVE control: the demo setting
`propagateTraceHeaderCorsUrls: [/.*/]` sent `traceparent` to all three origins.

```typescript
// core/telemetry/tracing.ts — OpenTelemetry for the browser. EXPERIMENTAL upstream: pin versions, sample, keep it optional.
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { BatchSpanProcessor, TraceIdRatioBasedSampler, WebTracerProvider } from '@opentelemetry/sdk-trace-web';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';

const escape = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export function startTracing(opts: { collectorUrl: string; apiOrigins: readonly string[]; release: string; sampleRatio: number }): void {
  const provider = new WebTracerProvider({
    resource: resourceFromAttributes({ [ATTR_SERVICE_NAME]: 'web-app', [ATTR_SERVICE_VERSION]: opts.release }),
    sampler: new TraceIdRatioBasedSampler(opts.sampleRatio),
    spanProcessors: [new BatchSpanProcessor(new OTLPTraceExporter({ url: opts.collectorUrl }))],
  });
  provider.register();
  registerInstrumentations({
    instrumentations: [
      new FetchInstrumentation({
        // traceparent only to YOUR API origins, never /.*/ — it is sent cross-origin and needs CORS allow-listing there
        propagateTraceHeaderCorsUrls: opts.apiOrigins.map((origin) => new RegExp(`^${escape(origin)}(/|$)`)),
        ignoreUrls: [new RegExp(`^${escape(opts.collectorUrl)}`)],
        applyCustomAttributesOnSpan: (span) => { span.setAttribute('http.url', '[redacted]'); }, // full URLs carry ids/query strings
      }),
    ],
  });
}
```

- CORS: every API origin that receives `traceparent`/`tracestate` must list them in `Access-Control-Allow-Headers`, or
  preflights fail and the request breaks — add them deliberately, not with `*` plus credentials.
- The collector endpoint needs its own CORS allowlist (your app origins only) and is listed in CSP `connect-src`.
- Correlate: backend spans continue the browser trace id; log the trace id with server errors so a user report can be
  joined to the backend trace.
- Sample (`TraceIdRatioBasedSampler`), and keep URLs/query strings out of span attributes.
- Without OTel, a simpler correlation path: the backend returns a request id header; the error report includes it.
