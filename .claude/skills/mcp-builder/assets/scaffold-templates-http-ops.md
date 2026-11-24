# MCP Server Scaffold Templates: HTTP and Operations

Verbatim files for `/scaffold-mcp-server` when the transport is `http` or `both`: bearer auth, the Streamable HTTP app on Fastify, its tests and the container. OpenTelemetry is in the command itself. Project files, the tool registry and CI are in `scaffold-templates-core.md`. Plain `node:http` instead of Fastify: `../reference/node-mcp-setup.md`; auth background: `../reference/security-core.md` §3. Verified 2026-11-23 against Node 26.13.1, TypeScript 6.0.3, `@modelcontextprotocol/server` 2.4.0, `node` 2.1.2, `fastify` adapter 2.0.1, Fastify 5.12.8, jose 6.2.18, Docker 29.8.0 (see `scaffold-templates-core.md` for the full run).

## 1. Auth

**`src/auth.ts`**: The bearer gate is always on: there is no unauthenticated HTTP mode. Use stdio for local development. Tokens must be RFC 9068 access tokens (`typ: at+jwt`) from your issuer with `exp`, `iat`, `sub`, a string `client_id`, exactly one `aud` = the canonical `/mcp` URL (RFC 8707), and a `scope` that covers each tool's entry in `TOOL_SCOPES`. The verifier reports the token's own `aud` as `resource`, so the SDK's `expectedResource` check is independent of `jwtVerify`.

```typescript
import { createRemoteJWKSet, errors, jwtVerify } from 'jose';
import type { JWTPayload, JWTVerifyGetKey } from 'jose';
import { OAuthError, OAuthErrorCode } from '@modelcontextprotocol/server';
import type { AuthInfo, OAuthTokenVerifier } from '@modelcontextprotocol/server';
import { logger } from './logger.js';
import type { Principal } from './tools.js';

export interface JwtVerifierConfig {
  issuer: string;
  /** This server's canonical URI (RFC 8707 resource), e.g. https://mcp.example.com/mcp */
  resource: URL;
  /** Remote JWKS URL in production; a local key set in tests. */
  keys: URL | JWTVerifyGetKey;
  algorithms: Array<'ES256' | 'RS256' | 'PS256' | 'EdDSA'>;
}

export function createJwtVerifier(config: JwtVerifierConfig): OAuthTokenVerifier {
  const keys = config.keys instanceof URL ? createRemoteJWKSet(config.keys, { timeoutDuration: 2_000 }) : config.keys;
  const audience = config.resource.href;
  return {
    async verifyAccessToken(token: string): Promise<AuthInfo> {
      let payload: JWTPayload;
      try {
        ({ payload } = await jwtVerify(token, keys, {
          issuer: config.issuer,
          audience,
          algorithms: config.algorithms,
          typ: 'at+jwt', // RFC 9068: refuse ID tokens and other JWT types presented as access tokens
          requiredClaims: ['exp', 'iat', 'sub', 'client_id'],
          clockTolerance: 30,
        }));
      } catch (error) {
        logger.warn({ reason: error instanceof errors.JOSEError ? error.code : 'unexpected' }, 'auth.token_rejected');
        throw new OAuthError(OAuthErrorCode.InvalidToken, 'Invalid or expired access token');
      }
      const clientId = payload['client_id'];
      if (typeof clientId !== 'string' || payload.sub === undefined || payload.exp === undefined) {
        throw new OAuthError(OAuthErrorCode.InvalidToken, 'Token is missing required claims');
      }
      // Report the token's OWN audience, so the gate's expectedResource check does not depend on jwtVerify.
      const aud = payload.aud;
      const tokenAudience = typeof aud === 'string' ? aud : aud?.length === 1 ? aud[0] : undefined;
      if (tokenAudience === undefined || !URL.canParse(tokenAudience)) {
        throw new OAuthError(OAuthErrorCode.InvalidToken, 'Token must name exactly one resource');
      }
      const scopes = typeof payload['scope'] === 'string' ? payload['scope'].split(' ').filter(Boolean) : [];
      return {
        token,
        clientId,
        scopes,
        expiresAt: payload.exp,
        resource: new URL(tokenAudience),
        extra: { principal: { subject: payload.sub, scopes: new Set(scopes) } satisfies Principal },
      };
    },
  };
}

export function principalFromAuth(authInfo: AuthInfo | undefined): Principal | undefined {
  const candidate = authInfo?.extra?.['principal'];
  if (typeof candidate !== 'object' || candidate === null) return undefined;
  const { subject, scopes } = candidate as Partial<Principal>;
  return typeof subject === 'string' && scopes instanceof Set ? { subject, scopes } : undefined;
}
```

## 2. Streamable HTTP app

**`src/app.ts`**: Order per request: Host/Origin guard (app-level hooks, 403) → route `bodyLimit` (413) → bearer gate (401 `invalid_token` with `WWW-Authenticate: Bearer … resource_metadata=`; scope is enforced per tool, not here) → stateless MCP handler → per-tool allowlist. `/health/live` and the protected-resource metadata need no token. The single cast in the route handler: `IncomingMessage.method` is `string | undefined` while `NodeIncomingMessageLike.method` is optional, which is TS2379 under `exactOptionalPropertyTypes`.

```typescript
import { createMcpFastifyApp } from '@modelcontextprotocol/fastify';
import { toNodeHandler, type NodeIncomingMessageLike } from '@modelcontextprotocol/node';
import {
  bearerAuthChallengeResponse,
  buildOAuthProtectedResourceMetadata,
  createMcpHandler,
  getOAuthProtectedResourceMetadataUrl,
  McpServer,
  verifyBearerToken,
} from '@modelcontextprotocol/server';
import type { AuthInfo, OAuthMetadata, OAuthTokenVerifier } from '@modelcontextprotocol/server';
import type { FastifyInstance } from 'fastify';
import { principalFromAuth } from './auth.js';
import { logger } from './logger.js';
import { registerTools, TOOL_SCOPES, type ToolDeps } from './tools.js';

export interface HttpConfig {
  /** Canonical URI of the MCP endpoint; its pathname is the route. */
  resource: URL;
  bindHost: string;
  allowedHosts?: string[];
  allowedOrigins?: string[];
  oauthMetadata: OAuthMetadata;
  verifier: OAuthTokenVerifier;
  /** Loopback test issuer only. */
  allowInsecureIssuerUrl?: boolean;
  bodyLimitBytes?: number;
  notes: ToolDeps['notes'];
}

export function buildHttpApp(config: HttpConfig): FastifyInstance {
  // Host + Origin validation (DNS rebinding) run as app-level onRequest hooks: 403 before any route code.
  const app = createMcpFastifyApp({
    host: config.bindHost,
    ...(config.allowedHosts ? { allowedHosts: config.allowedHosts } : {}),
    ...(config.allowedOrigins ? { allowedOrigins: config.allowedOrigins } : {}),
  });
  const resourceMetadataUrl = getOAuthProtectedResourceMetadataUrl(config.resource);
  const metadata = buildOAuthProtectedResourceMetadata({
    oauthMetadata: config.oauthMetadata,
    resourceServerUrl: config.resource,
    scopesSupported: [...new Set(Object.values(TOOL_SCOPES))],
    dangerouslyAllowInsecureIssuerUrl: config.allowInsecureIssuerUrl ?? false,
  });
  app.get(new URL(resourceMetadataUrl).pathname, () => metadata);
  app.get('/health/live', () => ({ status: 'ok' }));

  // Stateless: one McpServer per request, built from the verified AuthInfo only.
  const handler = createMcpHandler(({ authInfo }) =>
    registerTools(new McpServer({ name: 'notes-mcp', version: '0.1.0' }), {
      principal: () => principalFromAuth(authInfo),
      notes: config.notes,
    }),
  );
  const bodyLimit = config.bodyLimitBytes ?? 262_144;
  const node = toNodeHandler(handler, {
    maxRequestBodySize: bodyLimit,
    onerror: (err) => {
      logger.error({ err }, 'mcp_adapter_error');
    },
  });
  app.addHook('onClose', async () => {
    await handler.close();
  });

  const authenticated = new WeakMap<object, AuthInfo>();
  app.route({
    method: ['POST', 'GET', 'DELETE'],
    url: config.resource.pathname,
    bodyLimit, // 413 before the JSON parser buffers more
    onRequest: async (request, reply) => {
      try {
        const auth = await verifyBearerToken(request.headers.authorization, {
          verifier: config.verifier,
          resourceMetadataUrl,
          expectedResource: config.resource,
        });
        authenticated.set(request, auth);
      } catch (error) {
        // 401 invalid_token / 403 insufficient_scope with WWW-Authenticate: Bearer … resource_metadata="…"
        const challenge = bearerAuthChallengeResponse(error, { resourceMetadataUrl });
        return reply
          .code(challenge.status)
          .headers(Object.fromEntries(challenge.headers))
          .send(await challenge.text());
      }
    },
    handler: async (request, reply) => {
      const auth = authenticated.get(request);
      if (!auth) throw new Error('bearer gate did not run');
      reply.hijack(); // the MCP handler writes the raw response (JSON or SSE)
      await node(Object.assign(request.raw, { auth }) as NodeIncomingMessageLike, reply.raw, request.body);
    },
  });
  return app;
}
```

**`src/http.ts`** (env validated at startup, exit 1 on: a missing `MCP_RESOURCE`; a non-https issuer or JWKS URL, except a loopback http URL outside production; a non-loopback `HOST` without both `ALLOWED_HOSTS` and `ALLOWED_ORIGINS`. Both lists take hostnames without port. Never list `localhost` in `ALLOWED_ORIGINS`: Origin matching ignores the port)

```typescript
import * as z from 'zod';
import { buildHttpApp } from './app.js';
import { createJwtVerifier } from './auth.js';
import { logger } from './logger.js';
import { SAMPLE_NOTES } from './notes.js';

const list = z.string().transform((v) =>
  v
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean),
);
const LOOPBACK = ['127.0.0.1', 'localhost', '::1'];
// Issuer and JWKS must be https; plain http only for a loopback issuer outside production.
const httpsUrl = z.url({ protocol: /^https$/ });
const oauthUrl =
  process.env['NODE_ENV'] === 'production'
    ? httpsUrl
    : z.union([httpsUrl, z.url({ protocol: /^http$/, hostname: /^(127\.0\.0\.1|localhost|\[::1\])$/ })]);
const env = z
  .object({
    HOST: z.string().default('127.0.0.1'),
    PORT: z.coerce.number().int().min(1).max(65_535).default(3000),
    MCP_RESOURCE: z.url(), // canonical public URL of /mcp; tokens must carry it as `aud`
    OAUTH_ISSUER: oauthUrl,
    OAUTH_JWKS_URI: oauthUrl,
    // Hostnames without port (the SDK compares URL.hostname). In a container add 127.0.0.1: /health/live is behind this guard.
    ALLOWED_HOSTS: list.optional(),
    // Origin hostnames (port ignored). Set but empty (`ALLOWED_ORIGINS=`) = reject any request that carries an Origin.
    ALLOWED_ORIGINS: list.optional(),
  })
  .parse(process.env);

// Bound beyond loopback, the Host/Origin guards are mandatory (DNS rebinding): refuse to start without them.
if (!LOOPBACK.includes(env.HOST) && (!env.ALLOWED_HOSTS?.length || env.ALLOWED_ORIGINS === undefined)) {
  logger.error({ host: env.HOST }, 'config.allowlists_required: set ALLOWED_HOSTS and ALLOWED_ORIGINS');
  process.exit(1);
}

const resource = new URL(env.MCP_RESOURCE);
const app = buildHttpApp({
  resource,
  bindHost: env.HOST,
  ...(env.ALLOWED_HOSTS ? { allowedHosts: env.ALLOWED_HOSTS } : {}),
  ...(env.ALLOWED_ORIGINS ? { allowedOrigins: env.ALLOWED_ORIGINS } : {}),
  oauthMetadata: {
    issuer: env.OAUTH_ISSUER,
    authorization_endpoint: new URL('/authorize', env.OAUTH_ISSUER).href,
    token_endpoint: new URL('/token', env.OAUTH_ISSUER).href,
    response_types_supported: ['code'],
  },
  verifier: createJwtVerifier({
    issuer: env.OAUTH_ISSUER,
    resource,
    keys: new URL(env.OAUTH_JWKS_URI),
    algorithms: ['ES256', 'RS256'],
  }),
  notes: SAMPLE_NOTES,
});

const address = await app.listen({ host: env.HOST, port: env.PORT });
logger.info({ address }, 'listening');
for (const signal of ['SIGTERM', 'SIGINT'] as const) {
  process.once(signal, () => {
    app.close().then(
      () => process.exit(0),
      (err: unknown) => {
        logger.error({ err }, 'http_shutdown_failed');
        process.exit(1);
      },
    );
  });
}
```

## 3. HTTP tests

**`test/http.test.ts`**: Signing keys are generated per run, so nothing secret is committed. `test/config.test.ts` (startup refusals) is in `scaffold-templates-core.md` §3. Covered here: valid token, no token (401 + `resource_metadata`), wrong audience, expired, foreign key, `typ: JWT`, missing scope (allowlist denies), foreign Host and foreign Origin (403), oversize body (413).

```typescript
import { createServer } from 'node:http';
import type { AddressInfo } from 'node:net';
import { Client, StreamableHTTPClientTransport, UnauthorizedError } from '@modelcontextprotocol/client';
import type { FastifyInstance } from 'fastify';
import { createLocalJWKSet, exportJWK, generateKeyPair, SignJWT } from 'jose';
import type { CryptoKey, JWTPayload } from 'jose';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildHttpApp } from '../src/app.js';
import { createJwtVerifier } from '../src/auth.js';

const issuer = 'http://127.0.0.1:9/issuer'; // never contacted: keys are local
let app: FastifyInstance;
let resource: URL;
let signingKey: CryptoKey;
let otherKey: CryptoKey;
const clients: Client[] = [];

async function mint(claims: JWTPayload = {}, key: CryptoKey = signingKey, typ = 'at+jwt'): Promise<string> {
  return new SignJWT({ scope: 'notes:read', client_id: 'test-client', ...claims })
    .setProtectedHeader({ alg: 'ES256', kid: 'k1', typ })
    .setIssuer(issuer)
    .setAudience(typeof claims.aud === 'string' ? claims.aud : resource.href)
    .setSubject('alice')
    .setIssuedAt()
    .setExpirationTime(typeof claims.exp === 'number' ? claims.exp : '5m')
    .sign(key);
}

async function connect(token: string | undefined): Promise<Client> {
  const client = new Client({ name: 'http-test', version: '1.0.0' }, { versionNegotiation: { mode: 'auto' } });
  clients.push(client);
  await client.connect(
    new StreamableHTTPClientTransport(resource, { authProvider: { token: () => Promise.resolve(token) } }),
  );
  return client;
}

async function freePort(): Promise<number> {
  const probe = createServer();
  await new Promise<void>((resolve) => {
    probe.listen(0, '127.0.0.1', resolve);
  });
  const { port } = probe.address() as AddressInfo;
  await new Promise<void>((resolve) => {
    probe.close(() => {
      resolve();
    });
  });
  return port;
}

beforeAll(async () => {
  // Keys are generated per run; nothing is committed.
  const pair = await generateKeyPair('ES256');
  signingKey = pair.privateKey;
  otherKey = (await generateKeyPair('ES256')).privateKey;
  const keys = createLocalJWKSet({ keys: [{ ...(await exportJWK(pair.publicKey)), kid: 'k1', alg: 'ES256' }] });
  const port = await freePort();
  resource = new URL(`http://127.0.0.1:${String(port)}/mcp`);
  app = buildHttpApp({
    resource,
    bindHost: '127.0.0.1',
    oauthMetadata: {
      issuer,
      authorization_endpoint: `${issuer}/authorize`,
      token_endpoint: `${issuer}/token`,
      response_types_supported: ['code'],
    },
    verifier: createJwtVerifier({ issuer, resource, keys, algorithms: ['ES256'] }),
    allowInsecureIssuerUrl: true,
    notes: [{ id: 'n1', title: 'Release checklist' }],
  });
  await app.listen({ host: '127.0.0.1', port });
});

afterAll(async () => {
  await Promise.allSettled(clients.map((c) => c.close()));
  await app.close();
});

describe('Streamable HTTP transport (real Client)', () => {
  it('valid token: lists and calls the tool', async () => {
    const client = await connect(await mint());
    const { tools } = await client.listTools();
    expect(tools.map((t) => t.name)).toEqual(['notes_search']);
    const res = await client.callTool({ name: 'notes_search', arguments: { query: 'release' } });
    expect(res.structuredContent).toEqual({ notes: [{ id: 'n1', title: 'Release checklist' }] });
  });

  it('no token: 401 with a WWW-Authenticate resource_metadata challenge', async () => {
    await expect(connect(undefined)).rejects.toBeInstanceOf(UnauthorizedError);
    const raw = await fetch(resource, { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' });
    expect(raw.status).toBe(401);
    expect(raw.headers.get('www-authenticate')).toContain('resource_metadata=');
  });

  it.each([
    ['wrong audience', () => mint({ aud: 'https://other.example/mcp' })],
    ['expired', () => mint({ exp: Math.floor(Date.now() / 1000) - 120 })],
    ['foreign signing key', () => mint({}, otherKey)],
    ['typ JWT (not an access token)', () => mint({}, signingKey, 'JWT')],
  ])('%s: 401', async (_label, token) => {
    const raw = await fetch(resource, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${await token()}` },
      body: '{}',
    });
    expect(raw.status).toBe(401);
  });

  it('token without the tool scope: the allowlist denies before the handler runs', async () => {
    const client = await connect(await mint({ scope: 'other:read' }));
    const res = await client.callTool({ name: 'notes_search', arguments: { query: 'release' } });
    expect(res.isError).toBe(true);
    expect(JSON.stringify(res.content)).toContain('TOOL_NOT_ALLOWED');
  });

  it('foreign Host header: 403 (DNS rebinding guard)', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/mcp',
      headers: { host: 'evil.example', authorization: `Bearer ${await mint()}` },
      payload: {},
    });
    expect(res.statusCode).toBe(403);
  });

  it('foreign Origin: 403', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/mcp',
      headers: { host: resource.host, origin: 'https://evil.example', authorization: `Bearer ${await mint()}` },
      payload: {},
    });
    expect(res.statusCode).toBe(403);
  });

  it('oversize body: 413', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/mcp',
      headers: { host: resource.host, 'content-type': 'application/json', authorization: `Bearer ${await mint()}` },
      payload: JSON.stringify({ pad: 'x'.repeat(300_000) }),
    });
    expect(res.statusCode).toBe(413);
  });
});
```

## 4. Container

**`Dockerfile`**: Resolve the current digest with `docker buildx imagetools inspect node:26.13.1-trixie-slim`. Run it as `docker run --read-only --cap-drop ALL --security-opt no-new-privileges --memory 512m -e ALLOWED_HOSTS=<public hostname>,127.0.0.1,localhost -e ALLOWED_ORIGINS=<browser client hostnames, or empty> …`. `ALLOWED_HOSTS` entries are hostnames without port (a `host:port` entry makes every request 403). An empty `ALLOWED_ORIGINS=` rejects every request that carries an Origin header (server-to-server clients send none). The Host check guards `/health/*` too. Without `127.0.0.1`, the in-container HEALTHCHECK gets 403 and the container never becomes healthy. Kubernetes probes send the pod IP as Host (403), so give them `httpHeaders: [{name: Host, value: localhost}]` and keep `localhost` in the list.

```dockerfile
# syntax=docker/dockerfile:1
# Base image pinned by multi-arch index digest (node:26.13.1-trixie-slim, resolved 2026-11-23); let Renovate/Dependabot bump it.
ARG NODE_IMAGE=node:26.13.1-trixie-slim@sha256:e6bedef217677b276c591795e169840edd9096dbf13f29df8ef8d1856b8820bc

FROM ${NODE_IMAGE} AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --ignore-scripts
COPY tsconfig.json tsconfig.build.json ./
COPY src ./src
RUN npm run build

FROM ${NODE_IMAGE} AS prod-deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev --ignore-scripts

FROM ${NODE_IMAGE} AS runtime
# 512 MiB container: old space 320 MiB (heap_size_limit measured 332 MiB on 26.13.1) leaves room for buffers and native memory.
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000 NODE_OPTIONS=--max-old-space-size=320
WORKDIR /app
COPY --from=prod-deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY package.json ./
USER node
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/health/live').then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
CMD ["node", "dist/http.js"]
```

**`.dockerignore`**

```text
*
!package.json
!package-lock.json
!tsconfig.json
!tsconfig.build.json
!src
```
