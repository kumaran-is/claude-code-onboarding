# firebase.json Hosting Configuration (static SPA)

Verified 2026-11-22 with `firebase-tools@15.37.0` and the local Hosting emulator: every header and cache rule below
was read back with `curl -sI` from `emulators:start --only hosting` (SPA deep link, `index.html`, hashed asset).
The emulator serves `firebase.json` headers and rewrites; it does not prove CDN behaviour or a custom domain.

```json
{
  "hosting": {
    "public": "public",
    "ignore": ["firebase.json", "**/.*", "**/node_modules/**", "**/*.map"],
    "cleanUrls": true,
    "trailingSlash": false,
    "rewrites": [{ "source": "**", "destination": "/index.html" }],
    "headers": [
      { "source": "**", "headers": [
        { "key": "Content-Security-Policy", "value": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'" },
        { "key": "Strict-Transport-Security", "value": "max-age=63072000; includeSubDomains" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" },
        { "key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()" },
        { "key": "Cache-Control", "value": "no-cache" } ] },
      { "source": "**/*-+([A-Z0-9]).@(js|css)", "headers": [ { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" } ] }
    ]
  }
}
```

| Setting | Why |
|---|---|
| `public` | Must equal the build output. Angular application builder: `dist/<project>/browser` |
| `ignore` `**/*.map` | Source maps are not served publicly; upload them to your error tracker instead (`deployment-ci-cd/reference/web-frontend-delivery.md`) |
| `rewrites` `**` → `/index.html` | SPA deep links return the app shell. Put API/function rewrites **before** it (first match wins) |
| `Cache-Control: no-cache` on `**` | `index.html` and `config.json` are revalidated on every load, so a deploy or rollback takes effect immediately |
| immutable rule on hashed names | Later header rules override earlier ones for the same key. Matches the builder's `name-HASH.js/css` (uppercase base32 hash, `outputHashing: "all"`). Check the emitted names before copying the glob; a wrong glob silently caches nothing as immutable — or, worse, caches un-hashed files for a year |
| CSP | Matches the Angular CSP guidance in `security-reviewer/reference/web-frontend-security.md` §2: with the default `inlineCritical: true`, `script-src 'self'` blocks the stylesheet `onload` and the app renders unstyled — set `inlineCritical: false` or use `autoCsp` and drop `default-src`/`script-src` from this header. Add your API, auth and telemetry origins to `connect-src` |
| HSTS | Only once every subdomain serves HTTPS; `*.web.app` already enforces HTTPS |

Authenticated apps also add `{ "key": "X-Robots-Tag", "value": "noindex" }`. Validate the **live** headers after each
deploy with the header check in `web-frontend-delivery.md`.

Runtime config: serve `config.json` from `public` (no-cache via the `**` rule) and validate it at boot — it is public, like
everything else in `public`.
