# Angular 21.2 SSR and Hydration — Canonical Reference

Snippets compiled against `@angular/*@21.2.26` + `@angular/ssr@21.2.x`, TypeScript 5.9.3,
`strictTemplates`.

## Setup

```bash
ng add @angular/ssr   # adds @angular/ssr, server.ts, app.config.server.ts, app.routes.server.ts
```

## Client config

```typescript
import { provideHttpClient, withFetch } from '@angular/common/http';
import { ApplicationConfig } from '@angular/core';
import { provideClientHydration, withEventReplay, withIncrementalHydration } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes),
    provideHttpClient(withFetch()), // fetch backend: recommended for SSR
    // withEventReplay: replays clicks made before hydration finished.
    // withIncrementalHydration: REQUIRED for any `hydrate on …` trigger below.
    provideClientHydration(withEventReplay(), withIncrementalHydration()),
  ],
};
```

## Server config and render modes

```typescript
import { mergeApplicationConfig } from '@angular/core';
import { RenderMode, ServerRoute, provideServerRendering, withRoutes } from '@angular/ssr';
import { appConfig } from './app.config';

export const serverRoutes: ServerRoute[] = [
  { path: 'account/**', renderMode: RenderMode.Client },   // per-user pages: no SSR
  { path: 'about', renderMode: RenderMode.Prerender },      // static at build time
  { path: '**', renderMode: RenderMode.Server },
];

export const config = mergeApplicationConfig(appConfig, {
  providers: [provideServerRendering(withRoutes(serverRoutes))],
});
```

`provideServerRendering` is imported from **`@angular/ssr`** (with `withRoutes`). The argument-less
`provideServerRendering()` in `@angular/platform-server` is the old entry point; do not mix them.

### Security: `allowedHosts` (SSRF)

The SSR engine builds absolute URLs from the request `Host`. Configure the hosts you serve in
`angular.json` → `projects.<name>.architect.build.options.security.allowedHosts` (or the
`NG_ALLOWED_HOSTS` env var, or `AngularNodeAppEngine({ allowedHosts })`). Unknown hosts get a
client-rendered page or a 400 (from the `@angular/ssr` 21.2 `.d.ts` remarks). Never render
per-user data on prerendered routes, and never put secrets in `TransferState` — it is serialized
into the HTML.

## Incremental hydration

```typescript
@Component({
  selector: 'app-page',
  imports: [ProductList, ChatWidget],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @defer (hydrate on viewport) { <app-product-list /> }
    @defer (on idle; hydrate on interaction) { <app-chat-widget /> }
    @defer (hydrate never) { <footer>Static footer</footer> }
  `,
})
export class Page {}
```

| Trigger | Hydrates when |
|---|---|
| `hydrate on idle` | Browser is idle |
| `hydrate on viewport` | Block enters the viewport |
| `hydrate on interaction` | User clicks/focuses inside it |
| `hydrate on hover` | Pointer hovers it |
| `hydrate on timer(2s)` | After the delay |
| `hydrate when expr` | Expression becomes truthy (only checked once a parent is hydrated) |
| `hydrate never` | Stays static HTML |

Regular `on …` triggers control client-side loading; `hydrate on …` controls when server-rendered
content becomes interactive. Without `withIncrementalHydration()` the `hydrate` triggers are ignored.

## Avoiding duplicate requests

- **HttpClient GET/HEAD** responses made during SSR are cached into the page and reused on the
  client automatically when `provideClientHydration()` is present (tune with
  `withHttpTransferCacheOptions`). This covers `httpResource` and `HttpClient`-based `rxResource`.
- Requests with an `Authorization` header are not cached by default — keep it that way for
  per-user data.
- Use `TransferState` manually only for non-HttpClient data:

```typescript
const CONFIG_KEY = makeStateKey<{ region: string }>('runtime-config');

@Component({ selector: 'app-browser-only', changeDetection: ChangeDetectionStrategy.OnPush, template: `{{ width() }}` })
export class BrowserOnly {
  private readonly isBrowser = isPlatformBrowser(inject(PLATFORM_ID));
  private readonly state = inject(TransferState);
  readonly width = signal(0);
  readonly region = this.state.get(CONFIG_KEY, { region: 'unknown' }).region;

  constructor() {
    // Browser-only APIs belong in render hooks: they never run on the server.
    afterNextRender(() => this.width.set(window.innerWidth));
    if (!this.isBrowser) this.state.set(CONFIG_KEY, { region: 'eu' });
  }
}
```

## Common SSR issues

| Issue | Fix |
|---|---|
| `window`/`document`/`localStorage` is not defined | Move the code into `afterNextRender`, or guard with `isPlatformBrowser` |
| Hydration mismatch (NG0500-series) | Server and client must render the same DOM: no random ids/dates in templates, no DOM manipulation outside Angular, valid HTML nesting |
| `hydrate on …` has no effect | Add `withIncrementalHydration()` |
| Request rendered with wrong host / 400 | Add the host to `security.allowedHosts` |
| Data fetched twice | Use `HttpClient` (the transfer cache is on by default with `provideClientHydration()`; `withFetch()` does not enable it) |
| `status` on a Prerender route does not compile (TS2353) | Only `RenderMode.Server` routes accept `status`/`headers`; prerendered pages cannot set an HTTP status |
| Server and browser call the API on different origins | `HTTP_TRANSFER_CACHE_ORIGIN_MAP` — provide it on the **server** only (internal → public origin) |
