# MCP Server Security: Authentication and Authorization

Remote (Streamable HTTP) MCP servers as OAuth resource servers: token validation, protected resource metadata, per-tool scopes and tenant isolation. Tool execution safety (SSRF, approvals, untrusted output) is in [security-middleware-attacks.md](security-middleware-attacks.md); secrets, errors, audit and PII in [security-pii-compliance.md](security-pii-compliance.md). Which controls the MCP specification requires and which are practice, with the reviewer severity table: [`security-reviewer/reference/mcp-security.md`](../../security-reviewer/reference/mcp-security.md).

**Versions:** MCP specification revision **2026-07-28** (current); TypeScript SDK v2: `@modelcontextprotocol/server` 2.4.0, `@modelcontextprotocol/fastify` 2.0.1, `@modelcontextprotocol/express` 2.0.2, `@modelcontextprotocol/node` 2.1.2, `@modelcontextprotocol/client` 2.4.0; `fastify` 5.12.8; `jose` 6.2.18; `zod` 4.6.7; `ipaddr.js` 2.5.0; Node 26.13.1; TypeScript 6.0.3. The v1 package `@modelcontextprotocol/sdk` (1.32.x) speaks up to revision 2025-11-25 only.

**Evidence:** Verified 2026-11-23 against the versions above. Every code block on this page is copied from a sandbox server that ran 114 `node:test` cases through the real SDK client over Streamable HTTP: Fastify and Express wiring, each with a client negotiating revision 2026-07-28 (`versionNegotiation: { mode: 'auto' }`; asserted with `getNegotiatedProtocolVersion()`) and with the default client, which stays on 2025-11-25. `tsc` strict with `exactOptionalPropertyTypes` and `typescript-eslint` strict-type-checked on the server code exited 0. 20 planted defects ran against copies of the code: 18 made the suite fail; the other 2 are layers that are redundant by design (§2). Attacks and their negative controls are listed in §8.

## 1. Request pipeline

```
HTTP request
  → Host + Origin validation        403 (spec: MUST validate Origin)
  → requireBearerAuth               401 + WWW-Authenticate: Bearer resource_metadata="…"
      verifier: signature, alg, typ, iss, aud (= this server), exp, required claims
  → per-tool scopeChallenge         403 insufficient_scope, scope="…" (before the handler runs)
  → handler: principal from ctx.http.authInfo (never from arguments)
      → per-principal rate limit → tenant-scoped data access → audit → result marked untrusted
```

Authorization is OPTIONAL in the protocol, but a remote server that has users or tenants needs it; when an HTTP server supports it, the specification's MUSTs apply (Protected Resource Metadata, audience validation, 401/403 semantics, no token passthrough). stdio servers do not use OAuth: they take credentials from the environment (spec, Authorization §Protocol Requirements).

## 2. Token verifier

`requireBearerAuth` delegates validation to an `OAuthTokenVerifier` you supply. This one validates a JWT access token locally with `jose`:

```ts
import { createRemoteJWKSet, errors, jwtVerify } from 'jose';
import type { JWTPayload } from 'jose';
import { OAuthError, OAuthErrorCode } from '@modelcontextprotocol/server';
import type { AuthInfo, OAuthTokenVerifier } from '@modelcontextprotocol/server';
import { logger } from './logger.ts';

export interface JwtVerifierConfig {
  /** Exact `iss` of the authorization server (from its validated metadata). */
  issuer: string;
  /** This MCP server's canonical URI (RFC 8707 resource), e.g. https://mcp.example.com/mcp */
  resource: URL;
  /** The AS `jwks_uri`. */
  jwksUri: URL;
  /** Asymmetric algorithms the AS signs with. Never include 'none' or HS* for a remote AS. */
  algorithms: Array<'ES256' | 'RS256' | 'PS256' | 'EdDSA'>;
}

/** The verified caller. Tenant and subject come only from here, never from tool arguments. */
export interface Principal {
  subject: string;
  tenantId: string;
  scopes: ReadonlySet<string>;
}

export function createJwtVerifier(config: JwtVerifierConfig): OAuthTokenVerifier {
  // jose caches keys and refetches on an unknown `kid` (rate-limited by cooldownDuration),
  // which is what makes signing-key rotation work without a restart.
  const jwks = createRemoteJWKSet(config.jwksUri, { timeoutDuration: 2_000, cooldownDuration: 30_000 });
  const audience = config.resource.href.replace(/\/$/, '');

  return {
    async verifyAccessToken(token: string): Promise<AuthInfo> {
      let payload: JWTPayload;
      try {
        ({ payload } = await jwtVerify(token, jwks, {
          issuer: config.issuer,
          audience,
          algorithms: config.algorithms,
          typ: 'at+jwt', // RFC 9068: refuse ID tokens and other JWT types presented as access tokens
          requiredClaims: ['exp', 'iat', 'sub', 'client_id', 'tenant_id'],
          clockTolerance: 30,
        }));
      } catch (error) {
        const reason = error instanceof errors.JOSEError ? error.code : 'unexpected';
        logger.warn('auth.token_rejected', { reason });
        throw new OAuthError(OAuthErrorCode.InvalidToken, 'Invalid or expired access token');
      }
      const tenantId = payload['tenant_id'];
      const clientId = payload['client_id'];
      const scope = payload['scope'];
      if (typeof tenantId !== 'string' || typeof clientId !== 'string' || payload.sub === undefined || payload.exp === undefined) {
        throw new OAuthError(OAuthErrorCode.InvalidToken, 'Token is missing required claims');
      }
      // Report the token's own audience so the gate's expectedResource check is independent of jwtVerify.
      const tokenAudience = typeof payload.aud === 'string' ? payload.aud : payload.aud?.length === 1 ? payload.aud[0] : undefined;
      if (tokenAudience === undefined || !URL.canParse(tokenAudience)) {
        throw new OAuthError(OAuthErrorCode.InvalidToken, 'Token must name exactly one resource');
      }
      const principal: Principal = {
        subject: payload.sub,
        tenantId,
        scopes: new Set(typeof scope === 'string' ? scope.split(' ').filter(Boolean) : []),
      };
      return {
        token,
        clientId,
        scopes: [...principal.scopes],
        expiresAt: payload.exp,
        resource: new URL(tokenAudience),
        extra: { principal },
      };
    },
  };
}

/** Read the verified principal inside a tool handler; fail closed when absent. */
export function principalFrom(authInfo: AuthInfo | undefined): Principal {
  const candidate = authInfo?.extra?.['principal'];
  if (
    typeof candidate !== 'object' || candidate === null ||
    typeof (candidate as Principal).tenantId !== 'string' ||
    typeof (candidate as Principal).subject !== 'string'
  ) {
    throw new Error('No verified principal on this request');
  }
  return candidate as Principal;
}
```

Why each option is there:

| Option | Attack it stops | Source |
|---|---|---|
| `algorithms` allowlist (asymmetric only) | `alg: none`, HS256-with-public-key confusion. Keep it, but know it is a second layer: with the option removed, `jose` still refused HS256 and `none` tokens against an EC JWKS (planted defect, suite stayed green) | RFC 8725 §3.1–3.2 |
| `typ: 'at+jwt'` | an ID token or other JWT replayed as an access token (test: `typ: JWT` → 401) | RFC 9068 §4 (resource server MUST check `typ`) |
| `issuer` exact match | tokens from another authorization server | OAuth 2.1 §5.2 |
| `audience` = canonical server URI | token passthrough / confused deputy: a token minted for another API (test: foreign `aud` → 401) | MCP Authorization §Token Handling (MUST) |
| `AuthInfo.resource` = the token's single `aud` | makes `expectedResource` (§3) a real second check; a token naming two audiences is refused (tested) | SDK `VerifyBearerTokenOptions.expectedResource` docs |
| `requiredClaims` incl. `exp`, `tenant_id` | tokens that cannot be scoped; the SDK also refuses an `AuthInfo` without `expiresAt` | SDK v2 docs |
| `createRemoteJWKSet` with `cooldownDuration` | signing-key rotation without restart; an unknown `kid` refetches at most once per cooldown | jose `RemoteJWKSetOptions` |
| `OAuthError(InvalidToken)` | every failure is a 401 with the challenge; only the `jose` error code is logged, never the token | SDK v2 docs |

Opaque tokens: implement `verifyAccessToken` with RFC 7662 introspection instead and still fill `resource` from the introspected `aud`; the gate is unchanged.

## 3. Wiring: metadata, bearer gate, transport guards

Both wirings below serve the same per-request factory (`buildServerFactory`, §4) and passed the same suite.

**Express** (`@modelcontextprotocol/express` ships the auth middleware):

```ts
export function buildExpressApp(config: ServerConfig): Express {
  const app = createMcpExpressApp({
    host: config.bindHost,
    ...(config.allowedHosts ? { allowedHosts: config.allowedHosts } : {}),
    ...(config.allowedOrigins ? { allowedOrigins: config.allowedOrigins } : {}),
    jsonLimit: '256kb',
  });
  app.use(mcpAuthMetadataRouter({
    oauthMetadata: config.oauthMetadata,
    resourceServerUrl: config.resource,
    scopesSupported: ['docs:read'],
    dangerouslyAllowInsecureIssuerUrl: config.allowInsecureIssuerUrl,
  }));
  const auth = requireBearerAuth({
    verifier: config.verifier,
    resourceMetadataUrl: getOAuthProtectedResourceMetadataUrl(config.resource),
    expectedResource: config.resource,
  });
  const node = toNodeHandler(createMcpHandler(buildServerFactory(config)));
  app.all(config.resource.pathname, auth, (req, res) => void node(req, res, req.body));
  return app;
}
```

**Fastify.** `@modelcontextprotocol/fastify` 2.0.1 exports only `createMcpFastifyApp` and the Host/Origin hooks: no bearer middleware and no metadata router (read from its `.d.ts`). Build the gate from the framework-neutral helpers in `@modelcontextprotocol/server`:

```ts
import { createMcpFastifyApp } from '@modelcontextprotocol/fastify';
import { toNodeHandler } from '@modelcontextprotocol/node';
import type { NodeIncomingMessageLike } from '@modelcontextprotocol/node';
import {
  bearerAuthChallengeResponse,
  buildOAuthProtectedResourceMetadata,
  createMcpHandler,
  getOAuthProtectedResourceMetadataUrl,
  verifyBearerToken,
} from '@modelcontextprotocol/server';
import type { AuthInfo } from '@modelcontextprotocol/server';
import type { FastifyInstance } from 'fastify';

declare module 'fastify' {
  interface FastifyRequest {
    authInfo: AuthInfo | null;
  }
}

export function buildFastifyApp(config: ServerConfig): FastifyInstance {
  // Host + Origin validation run as app-level onRequest hooks, before any route hook (403).
  const app = createMcpFastifyApp({
    host: config.bindHost,
    ...(config.allowedHosts ? { allowedHosts: config.allowedHosts } : {}),
    ...(config.allowedOrigins ? { allowedOrigins: config.allowedOrigins } : {}),
  });
  app.decorateRequest('authInfo', null);

  // RFC 9728 Protected Resource Metadata. Built once at startup: a bad issuer URL fails here, not per request.
  const metadata = buildOAuthProtectedResourceMetadata({
    oauthMetadata: config.oauthMetadata,
    resourceServerUrl: config.resource,
    scopesSupported: ['docs:read', 'docs:delete', 'web:fetch'],
    dangerouslyAllowInsecureIssuerUrl: config.allowInsecureIssuerUrl,
  });
  const resourceMetadataUrl = getOAuthProtectedResourceMetadataUrl(config.resource);
  app.get(new URL(resourceMetadataUrl).pathname, (_request, reply) => reply.send(metadata));

  const handler = createMcpHandler(buildServerFactory(config));
  const node = toNodeHandler(handler, { maxRequestBodySize: 262_144 });
  app.addHook('onClose', async () => { await handler.close(); });

  app.route({
    method: ['POST', 'GET', 'DELETE'],
    url: config.resource.pathname,
    bodyLimit: 262_144, // 413 before the JSON parser buffers more
    // Route-level onRequest: runs after Host/Origin checks and before the body is parsed.
    onRequest: async (request, reply) => {
      try {
        // Reads only the Authorization header (a token in the query string is never accepted),
        // runs the verifier, compares AuthInfo.resource with expectedResource, rejects tokens without exp.
        request.authInfo = await verifyBearerToken(request.headers.authorization, {
          verifier: config.verifier,
          resourceMetadataUrl,
          expectedResource: config.resource,
        });
      } catch (error) {
        // 401 invalid_token / 403 insufficient_scope with WWW-Authenticate: Bearer … resource_metadata="…"
        const challenge = bearerAuthChallengeResponse(error, { resourceMetadataUrl });
        return reply.code(challenge.status).headers(Object.fromEntries(challenge.headers)).send(await challenge.text());
      }
    },
    handler: async (request, reply) => {
      reply.hijack(); // the MCP handler writes the raw response (JSON or SSE)
      const auth = request.authInfo;
      if (!auth) throw new Error('bearer gate did not run');
      // Only the verified AuthInfo reaches the factory and handlers (ctx.http.authInfo).
      // Cast: IncomingMessage.method is `string | undefined`; NodeIncomingMessageLike.method is optional (TS2379 under exactOptionalPropertyTypes).
      await node(Object.assign(request.raw, { auth }) as NodeIncomingMessageLike, reply.raw, request.body);
    },
  });
  return app;
}
```

- **Body limit on Fastify is the route's `bodyLimit`.** Fastify parses JSON before the MCP handler runs, and the SDK's `maxRequestBodySize` (handler and `toNodeHandler`) skips a body passed as `parsedBody`. With `bodyLimit` removed, a 400 KB request was accepted (planted defect).
- **Gate placement.** A route-level `onRequest` hook runs after the app-level Host/Origin hooks and before body parsing, so unauthenticated callers never cost a JSON parse. Removing the hook made every unauthenticated test fail (planted defect).
- **`exactOptionalPropertyTypes` stays on.** It breaks one call, and it is not the Fastify adapter: `@modelcontextprotocol/fastify` only supplies hooks. The failing call is the handler returned by `toNodeHandler` from `@modelcontextprotocol/node` 2.1.2 when it gets a raw Node `IncomingMessage` (Fastify `request.raw`, or `req` in a plain `node:http` server). `@types/node` declares `method?: string | undefined`, while `NodeIncomingMessageLike` declares `method?: string`. Under the flag that is TS2379 and `tsc` exits 2. The flag-off build exits 0, and so does the flag-on build with a cast to `NodeIncomingMessageLike` at that one call site (above). The Express wiring passes `req` to the same handler and compiles either way, because Express's `Request` type redeclares `method: string`.

- **Protected Resource Metadata (RFC 9728) is a MUST.** `mcpAuthMetadataRouter` serves `/.well-known/oauth-protected-resource/<path>`; the 401 challenge carries `resource_metadata` pointing at it (tested).
- **`expectedResource`** makes the gate compare the verifier's `AuthInfo.resource` with this server's URI. It is a second audience check only if the verifier reports the **token's** `aud`. The previous version of this page set `resource` from configuration, so with `audience` removed from `jwtVerify` a token for another API was accepted (planted defect). With `resource` taken from `aud` (§2), the same defect was caught by `expectedResource`. `@modelcontextprotocol/express` 2.0.1 silently ignored this option (SDK docs); use 2.0.2 or later.
- **Origin and Host.** `createMcpExpressApp` validates both for loopback binds. Binding `0.0.0.0` turns the defaults off: pass `allowedHosts` and `allowedOrigins` (planted `host: '0.0.0.0'` → the Origin test failed). Matching is by hostname and ignores the port, so a page on another `localhost` port passes the Origin check (tested); authentication must still stop it.
- **`allowInsecureIssuerUrl`** exists only for a loopback test issuer; production config sets `false`.
- **Body size:** `jsonLimit` caps the request body before parsing.
- **Without a framework adapter:** `createMcpHandler` itself does no authentication and no Host/Origin checks (its docs: `authInfo` is pass-through, never derived from headers). Put the bearer gate (`requireBearerAuth` from `@modelcontextprotocol/server` for fetch hosts, `verifyBearerToken` for any other framework, as in the Fastify example) and Host/Origin validation in front of it, and pass only the verified `AuthInfo` to the handler. Request headers and `requestInfo` are client input, never identity.
- **Python SDK (`mcp` 2.3.0; verified by the protocol workstream's sandbox, not this one):** pass `transport_security=TransportSecuritySettings(allowed_hosts=[...])` to `streamable_http_app`; a non-localhost `host=` alone turns DNS-rebinding protection off.

## 4. Per-tool authorization and scopes

Endpoint-wide `requiredScopes` is coarse. Put the scope on each primitive with `scopeChallenge` (tool, resource or prompt registration): the SDK answers `403 insufficient_scope` with the exact scope set before the handler runs, and the SDK client surfaces it as `InsufficientScopeError` with `requiredScope` (tested).

- Return **all** scopes the operation needs in one challenge (spec SHOULD); account for hierarchies yourself (spec MUST; the SDK does not infer that `docs:admin` implies `docs:read`).
- `scopeChallenge` runs **before** input-schema validation; a callback that reads arguments must validate them itself.
- Map scopes to capabilities per **principal**, not per client: the verified `sub` + tenant decide what data a permitted tool may touch (§5).
- Filter what each caller can see as well as call: the per-request factory receives `ctx.authInfo`, so register only that principal's allowlisted tools, and still refuse and log a call outside the allowlist at execution time. Keep the allowlist in one checked-in file and fail the build when an agent's tool filter and the server allowlist drift apart (source-proven pattern).

```ts
/** Per-request factory: the verified principal decides which tools exist for this request. */
export function buildServerFactory(config: ServerConfig): McpServerFactory {
  const allow = createLimiter(30);
  return ({ authInfo }) => {
    const server = new McpServer({ name: 'docs-mcp', version: '1.0.0' });
    // No verified principal → no tools (the bearer gate should already have answered 401).
    if (authInfo) registerTools(server, config, principalFrom(authInfo), allow);
    return server;
  };
}
```

`registerTools` registers a tool only when the allowlist entry for `<tenant>:<subject>` contains its name, and each handler re-checks that set and returns `TOOL_NOT_ALLOWED` before doing any work. Tested: a reader principal lists only `get_document`; its `delete_document` call fails and the handler body never runs (a run counter stays unchanged). Removing the registration filter alone failed the suite because the tool became visible (planted defect).
- An LLM never decides authorization. A tool description that says "only call this for admins" is not a control.

## 5. Tenant isolation from the verified token

```ts
server.registerTool(
  'get_document',
  {
    description: 'Read one document of the caller’s own tenant by id. Returns title and body as untrusted data.',
    inputSchema: z.object({ document_id: z.string().regex(/^[a-z0-9-]{1,64}$/) }).strict(),
    outputSchema: z.object({ id: z.string(), title: z.string(), body: z.string(), trust: z.literal('untrusted') }),
    annotations: { readOnlyHint: true, openWorldHint: false },
    scopeChallenge: requireScopes('docs:read'),
  },
  ({ document_id }, ctx) => {
    const principal = principalFrom(ctx.http?.authInfo);
    if (!permitted('get_document', principal)) return toolError('TOOL_NOT_ALLOWED', 'Tool not allowed for this caller');
    if (!allow(principal)) return toolError('RATE_LIMITED', 'Too many calls; retry after 60s');
    const doc = config.documents.get(principal.tenantId, document_id);
    // Missing and foreign documents answer identically (no existence oracle across tenants).
    if (!doc) return toolError('NOT_FOUND', 'Document not found');
    const structuredContent = { ...doc, trust: 'untrusted' as const };
    return { structuredContent, content: [{ type: 'text', text: JSON.stringify(structuredContent) }] };
  },
);
```

- The tenant and subject come only from `ctx.http.authInfo` (`principalFrom` fails closed when absent). The schema is `.strict()`, so a smuggled `tenant_id` argument is a validation error, not a hint (tested).
- A foreign id answers exactly like a missing id: no cross-tenant existence oracle (tested).
- Push the tenant into the query (`WHERE tenant_id = $1 AND id = $2`) and, for SQL stores, back it with row-level security keyed by a session variable set from the principal.
- Cross-call state uses server-minted handles (revision 2026-07-28 removed protocol sessions): random, expiring, stored as `<tenant>:<subject>:<handle>`, and checked against the caller on every call. Possessing a handle is never authentication (spec Security Best Practices, State Handle Hijacking).

## 6. Service-to-service callers (no end user)

For agents calling an internal MCP gateway, a platform workload identity token works as well as user OAuth (source-proven, generalized):

- Verify the platform ID token's signature, `iss`, `exp` and `aud` = this server's URL; require a verified service-account email; map email → principal from a checked-in allowlist; unknown principal → 403.
- Fail startup when half-configured (audience without principal map or the reverse) and refuse to start in production with auth disabled.
- Legacy shared API keys: compare with `timingSafeEqual` over equal-length buffers, keep them on a retirement path, and record the auth mode per request so you can see when the last key caller is gone.
- For 2025-11-25 servers that still issue `Mcp-Session-Id`: bind each session to the identity that opened it and answer 403 when a different identity presents it.

**Agent callers and delegation (cross-agent trust).** Another agent's request or output is untrusted input. The tool server, not the calling agent, decides:

- **Authenticated agent identity:** the calling agent presents its own workload token; an agent name in arguments, `_meta` or a prompt is not identity.
- **Delegation scope:** when an agent acts for a user or another agent, the effective permission is the **intersection** of the delegator's grant and the agent's own allowlist, carried in a verified token (for example an RFC 8693 token-exchange token with `act`); an agent cannot delegate a permission it does not hold.
- **Maximum delegation depth:** count the `act` chain (or the equivalent claim) and refuse beyond the configured depth.
- **Schema validation and provenance:** messages from agents pass the same strict schemas as any caller; record the originating principal and each hop in the audit record.
- **Explicit tool authority and independent downstream authorization:** every hop re-checks the per-tool scope and the object's tenant; nothing is authorized because an upstream agent "already checked".
- **Restricted context sharing:** return only the fields the caller's scope permits; never forward another principal's context or tokens (no token passthrough).

These are implementation patterns for the tool side; who approves agent identities and delegation policies is an organisational control.

## 7. stdio servers

The client launches the server and owns its environment. Take credentials from environment variables or the platform secret store (spec: stdio implementations SHOULD NOT follow the OAuth flow). Never accept a secret as a command-line argument: argv is visible to other processes (`ps -o args`, `/proc/<pid>/cmdline`). Write logs to stderr, never stdout.

## 8. Tests that prove it

| Attack | Expected | Negative control (guard removed → attack succeeds) |
|---|---|---|
| No token | SDK `UnauthorizedError`; raw 401 with `WWW-Authenticate: Bearer … resource_metadata="…"` → PRM lists the issuer | Fastify gate hook removed → test fails |
| Token in query string | 401 (spec: MUST NOT be in the URI) | — |
| Token for another resource; token with two audiences | 401 each | `jwtVerify` without `audience` and no `expectedResource` → test fails |
| Expired / `typ: JWT` / HS256 / `alg: none` / unknown key / foreign `iss` / no `tenant_id` | 401 each, `invalid_token` | `typ`, `issuer` or `tenant_id` check removed → its test fails |
| Valid token, missing tool scope | 403 `insufficient_scope`, `requiredScope: docs:delete`; handler not run | `scopeChallenge` removed → test fails |
| Tool outside the principal allowlist | not listed; call refused; handler not run | registration filter removed → test fails |
| Tenant A reads tenant B id; smuggled `tenant_id` arg | `NOT_FOUND`, same text as a missing id; strict-schema error | tenant filter removed → tenant B secret returned, test fails |
| Browser `Origin: https://evil.example`; `Host: attacker.example` | 403 before auth | Fastify bound to `0.0.0.0` without allowlists → test fails |
| 400 KB body | 413 | Fastify route `bodyLimit` removed → test fails |
| Over quota | `RATE_LIMITED` tool error | — |

A cross-tenant id answers `NOT_FOUND`, not 403, on purpose: a 403 would confirm that the id exists in another tenant. HTTP 403 is for a missing scope and for a bad Origin or Host.

Run: `npx tsc -p .` (`noEmit`), `npx eslint src`, `node --test 'test/*.test.ts'` (Node 26 runs `.ts` files natively). Run every case with a client in `versionNegotiation: { mode: 'auto' }` and with the default client, so both protocol eras are covered. Assert each attack and its negative control in the same suite: a guard test that passes with the guard removed proves nothing.
