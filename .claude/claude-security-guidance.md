# Security Guidance — claude-code-onboarding

Loaded by the `security-guidance` plugin into its model-backed diff review (user → project →
`.local.md`, 8 KB combined; keep this file short so user-wide rules are not truncated).
Project-specific rules on top of the plugin's built-in checklist. Full review method:
`.claude/skills/security-reviewer/reference/security-review-checklist.md`.

## Stack

Java 21 / Spring Boot 3.5 WebFlux (R2DBC) · NestJS 11 / Fastify / Prisma · Python 3.14 / FastAPI /
SQLAlchemy async · Angular 21 and React 19 SPAs · Flutter 3.41 (Firebase Auth, Firestore) ·
PostgreSQL with RLS · LangChain/LangGraph and Google ADK agents · MCP servers.

## Authorization (server-side, every stack)

- Authentication is not authorization. Every read and write is scoped to the caller: tenant and
  user ids come from the verified token, never the request body, path, tool arguments or model
  output. Foreign objects return 404. Client route guards and hidden buttons are UX only.
- Spring WebFlux: every route outside `/actuator/health` and `/actuator/info` is covered by a
  `SecurityWebFilterChain` rule or `@PreAuthorize`; the full actuator never sits on the public port.
- NestJS: authentication is a global `APP_GUARD`; routes opt out with `@Public()`. `@Public()` on a
  route that writes state or returns user data IS a finding. Per-route opt-in guards are a finding.
- FastAPI: protected routes depend on the auth dependency; admin routes add
  `Depends(require_role(Role.ADMIN))` before any database access.
- Firestore rules: `request.auth != null` alone is not authorization. Writes check ownership or a
  role claim (`request.auth.uid == resource.data.ownerId`, custom claims); a rule that lets a user
  read another user's document by guessing its id is an IDOR.

## AI, agents and MCP

- Model output, retrieved documents and tool results are untrusted data. They never decide
  authorization, never reach `eval`/`exec`/`new Function`/a shell, and are never concatenated into
  system instructions.
- Side-effecting tools need a deterministic server-side check (and human approval when
  destructive); LLM guardrails and classifiers are signals, not the authorization decision.
- Retrieval filters by tenant and permission inside the query, not after it.
- MCP servers: validate token audience; never pass the client's token upstream; tenant from the
  token, never tool arguments. Secrets never go in `.mcp.json` `args`.

## Logging and PII

- Never log tokens, passwords, API keys, `Authorization` headers, raw prompts/completions or
  `str(exc)` built from request data. Email, phone and account numbers are not logged at INFO or
  above; log an opaque internal id instead.
- Spring WebFlux: an MDC value put in a reactive chain is removed in `doFinally`; a missing
  removal leaks one request's context into another on the shared event-loop thread.
- Flutter: no user profile fields or `exception.toString()` in release-build logs or Crashlytics.

## Cryptography

- Token/HMAC comparison: `crypto.timingSafeEqual` (Node), `hmac.compare_digest` (Python),
  `MessageDigest.isEqual` (Java); never `===`/`==`/`equals`.
- No `AES/ECB`; use AES-GCM. No `crypto.createCipher` (removed in Node 22) — `createCipheriv`.
- Passwords: argon2id or bcrypt cost ≥ 12; never `bcrypt.compareSync`/`hashSync` on a request path.
- Flutter: JWTs and keys in `flutter_secure_storage`, never `SharedPreferences`.

## Injection and unsafe sinks

- NestJS: `$queryRaw` as a tagged template binds values; `$queryRawUnsafe` or `Prisma.raw` with
  user input is SQL injection. DTOs carry `class-validator` decorators.
- Spring: `DatabaseClient.sql(...)` built by string concatenation is SQL injection — use `.bind`.
- FastAPI: SQLAlchemy `text()` with f-string or `+` interpolation is SQL injection.
- Angular `bypassSecurityTrust*`, React `dangerouslySetInnerHTML`, `[innerHTML]`/`innerHTML =` on
  user, CMS or model content without DOMPurify are XSS sinks. Rules and severities:
  `security-reviewer/reference/web-frontend-security.md`.
- Flutter `WebViewController.runJavaScript*` (legacy `evaluateJavascript`) with interpolated user or
  agent content is script injection.

## SSRF

Spring `WebClient`, FastAPI `httpx`/`requests`, NestJS `fetch`/`axios` on a URL derived from user,
tool or model input need a scheme + host allowlist, resolved-address checks and redirect
re-validation.

## Flutter mobile

- `badCertificateCallback` returning `true` disables TLS verification — HIGH.
- A dio `onError` interceptor that calls `handler.resolve(...)` with a fallback response for
  401/403/5xx swallows the error — flag it (`handler.next(e)` and `handler.reject(e)` propagate).
- No service, HMAC or private keys in Dart code or `--dart-define`.

## Supply chain

- Packages only from the official registries, exact versions pinned, lockfiles committed.
- `npm audit --audit-level=high` / `pip-audit` / dependency-check failures block a merge.
- `pip install git+https://...` in production requirements is elevated risk.
