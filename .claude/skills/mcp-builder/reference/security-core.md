# MCP Server Security: Authentication and Authorization

Remote (Streamable HTTP) MCP servers as OAuth resource servers: token validation, protected resource metadata, per-tool scopes and tenant isolation. Tool execution safety (SSRF, approvals, untrusted output) is in [security-middleware-attacks.md](security-middleware-attacks.md); secrets, errors, audit and PII in [security-pii-compliance.md](security-pii-compliance.md). Which controls the MCP specification requires and which are practice, with the reviewer severity table: [`security-reviewer/reference/mcp-security.md`](../../security-reviewer/reference/mcp-security.md).

**Versions (checked 2026-11-23):** MCP specification revision **2026-07-28** (current); TypeScript SDK v2: `@modelcontextprotocol/server` 2.4.0, `@modelcontextprotocol/express` 2.0.2, `@modelcontextprotocol/node` 2.1.2, `@modelcontextprotocol/client` 2.4.0; `jose` 6.2.18; `zod` 4.6.7; `ipaddr.js` 2.5.0; Node 24. The v1 package `@modelcontextprotocol/sdk` (1.32.x) speaks up to revision 2025-11-25 only.

**Evidence:** every code block on this page is copied from a sandbox server that ran 31 `node:test` cases through the real SDK client over Streamable HTTP, once with a client negotiating revision 2026-07-28 (`versionNegotiation: { mode: 'auto' }`; the v2 `Client` defaults to the 2025-11-25 era) and once with the default client (strict `tsc`, `typescript-eslint` strict-type-checked, zero errors), and 14 planted defects (scope check removed, SSRF allow-all, `typ` check removed, approval skipped, ...) each made the suite fail. Attacks and their negative controls are listed in §8.

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
        resource: new URL(audience),
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
| `algorithms` allowlist (asymmetric only) | `alg: none`, HS256-with-public-key confusion | RFC 8725 §3.1–3.2 |
| `typ: 'at+jwt'` | an ID token or other JWT replayed as an access token (test: `typ: JWT` → 401) | RFC 9068 §4 (resource server MUST check `typ`) |
| `issuer` exact match | tokens from another authorization server | OAuth 2.1 §5.2 |
| `audience` = canonical server URI | token passthrough / confused deputy: a token minted for another API (test: foreign `aud` → 401) | MCP Authorization §Token Handling (MUST) |
| `requiredClaims` incl. `exp`, `tenant_id` | tokens that cannot be scoped; the SDK also refuses an `AuthInfo` without `expiresAt` | SDK v2 docs |
| `createRemoteJWKSet` with `cooldownDuration` | signing-key rotation without restart; an unknown `kid` refetches at most once per cooldown | jose `RemoteJWKSetOptions` |
| `OAuthError(InvalidToken)` | every failure is a 401 with the challenge; only the `jose` error code is logged, never the token | SDK v2 docs |

Opaque tokens: implement `verifyAccessToken` with RFC 7662 introspection instead and still fill `resource` from the introspected `aud`; the gate is unchanged.

## 3. Wiring: metadata, bearer gate, transport guards

```ts
export function buildApp(config: ServerConfig): Express {
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

- **Protected Resource Metadata (RFC 9728) is a MUST.** `mcpAuthMetadataRouter` serves `/.well-known/oauth-protected-resource/<path>`; the 401 challenge carries `resource_metadata` pointing at it (tested).
- **`expectedResource`** makes the gate compare the verifier's `AuthInfo.resource` with this server's URI, a second audience check that held even with `audience` removed from `jwtVerify` (tested). `@modelcontextprotocol/express` 2.0.1 silently ignored this option (SDK docs); use 2.0.2 or later.
- **Origin and Host.** `createMcpExpressApp` validates both for loopback binds. Binding `0.0.0.0` turns the defaults off: pass `allowedHosts` and `allowedOrigins` (planted `host: '0.0.0.0'` → the Origin test failed). Matching is by hostname and ignores the port, so a page on another `localhost` port passes the Origin check (tested); authentication must still stop it.
- **`allowInsecureIssuerUrl`** exists only for a loopback test issuer; production config sets `false`.
- **Body size:** `jsonLimit` caps the request body before parsing.
- **Without the Express adapter:** `createMcpHandler` itself does no authentication and no Host/Origin checks. Put the bearer gate (`requireBearerAuth` from `@modelcontextprotocol/server` for fetch hosts) and Host/Origin validation in front of it, and pass only the verified `AuthInfo` to the handler. Request headers and `requestInfo` are client input, never identity.
- **Python SDK (`mcp` 2.3.0; verified by the protocol workstream's sandbox, not this one):** pass `transport_security=TransportSecuritySettings(allowed_hosts=[...])` to `streamable_http_app`; a non-localhost `host=` alone turns DNS-rebinding protection off.

## 4. Per-tool authorization and scopes

Endpoint-wide `requiredScopes` is coarse. Put the scope on each primitive with `scopeChallenge` (tool, resource or prompt registration): the SDK answers `403 insufficient_scope` with the exact scope set before the handler runs, and the SDK client surfaces it as `InsufficientScopeError` with `requiredScope` (tested).

- Return **all** scopes the operation needs in one challenge (spec SHOULD); account for hierarchies yourself (spec MUST; the SDK does not infer that `docs:admin` implies `docs:read`).
- `scopeChallenge` runs **before** input-schema validation; a callback that reads arguments must validate them itself.
- Map scopes to capabilities per **principal**, not per client: the verified `sub` + tenant decide what data a permitted tool may touch (§5).
- Filter what each caller can see as well as call: the per-request factory receives `ctx.authInfo`, so register only that principal's allowlisted tools, and still refuse and log a call outside the allowlist at execution time. Keep the allowlist in one checked-in file and fail the build when an agent's tool filter and the server allowlist drift apart (source-proven pattern).
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

## 7. stdio servers

The client launches the server and owns its environment. Take credentials from environment variables or the platform secret store (spec: stdio implementations SHOULD NOT follow the OAuth flow). Never accept a secret as a command-line argument: argv is visible to other processes (`ps -o args`, `/proc/<pid>/cmdline`). Write logs to stderr, never stdout.

## 8. Tests that prove it

| Attack | Expected | Negative control (guard removed → attack succeeds) |
|---|---|---|
| No token | SDK `UnauthorizedError`; raw 401 with `resource_metadata` → PRM lists the issuer | — |
| Token in query string | 401 (spec: MUST NOT be in the URI) | — |
| Token for another resource | 401 | `jwtVerify` without `audience` and no `expectedResource` → tenant data returned |
| Expired / `typ: JWT` / unknown key / no `tenant_id` | 401 each | planted: `typ` check removed → ID-token test fails |
| Valid token, missing tool scope | 403 `insufficient_scope`, `requiredScope: docs:delete` | planted: `scopeChallenge` removed → test fails |
| Tenant A reads tenant B id; smuggled `tenant_id` arg | `NOT_FOUND`, same text as a missing id; strict-schema error | tool takes `tenant_id` from arguments → tenant B secret returned |
| Browser `Origin: https://evil.example` | 403 before auth | plain `express.json()` app → `tools/list` served |
| Over quota | `RATE_LIMITED` tool error | — |

Run: `npx tsc --noEmit -p .`, `npx eslint .`, `node --test 'test/*.test.ts'` (Node 24 strips types natively). Assert the attack and its negative control in the same suite: a guard test that passes with the guard removed proves nothing.
