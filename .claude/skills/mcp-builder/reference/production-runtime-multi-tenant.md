# Production Runtime — Multi-Tenant Support

Tenant context, quotas and audit for SaaS MCP servers. The tenant is a property of the **verified access token**, never of a header, a tool argument or the model's text. Token validation and per-tool scopes: [security-core.md](security-core.md). Graceful shutdown and health checks: [production-runtime-shutdown-health.md](production-runtime-shutdown-health.md). Code is copied from a tested sandbox (MCP TypeScript SDK v2, Node 24; 31 tests passing with both a 2026-07-28 and a 2025-11-25 client, 14 planted-defect controls).

## 1. Where the principal comes from

`requireBearerAuth` verifies the token and the verifier returns `AuthInfo` with the principal in `extra` (security-core §2). Tool handlers read it from `ctx.http.authInfo`; `principalFrom()` fails closed when it is absent. Passing the principal explicitly to the data layer is the simplest correct design:

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

Do **not** read `x-tenant-id` / `x-user-id` request headers or a `tenant_id` tool argument as identity: any caller can set them. The only exception is a trusted gateway that strips client-supplied identity headers and signs its own (for example a platform-verified identity token); then verify that signature, not the header's presence.

## 2. Optional ambient context with AsyncLocalStorage

When deep call chains make explicit passing awkward, wrap the handler body in `AsyncLocalStorage.run()`:

```ts
import { AsyncLocalStorage } from 'node:async_hooks';
import type { Principal } from './auth.ts';

const storage = new AsyncLocalStorage<Principal>();

/** Run `fn` with the verified principal as ambient context. Use run(), never enterWith():
 * enterWith leaks the store into whatever runs next on the same async resource (keep-alive sockets). */
export function withPrincipal<T>(principal: Principal, fn: () => Promise<T>): Promise<T> {
  return storage.run(principal, fn);
}

export function requirePrincipal(): Principal {
  const principal = storage.getStore();
  if (!principal) throw new Error('No principal in context');
  return principal;
}

/** Shared counter with an atomic increment-and-expire. Redis: MULTI; INCR key; EXPIRE key ttl NX; EXEC. */
export interface QuotaStore {
  incrementWithTtl(key: string, ttlSeconds: number): Promise<number>;
}

export class MemoryQuotaStore implements QuotaStore {
  private readonly counters = new Map<string, { count: number; resetAt: number }>();

  incrementWithTtl(key: string, ttlSeconds: number): Promise<number> {
    const now = Date.now();
    const current = this.counters.get(key);
    const next = !current || current.resetAt <= now ? { count: 1, resetAt: now + ttlSeconds * 1000 } : { count: current.count + 1, resetAt: current.resetAt };
    this.counters.set(key, next);
    return Promise.resolve(next.count);
  }
}

export class QuotaExceededError extends Error {
  override readonly name = 'QuotaExceededError';
}

/** Per-tenant and per-principal tool-call quota, keyed only by verified identity. */
export async function enforceToolQuota(store: QuotaStore, principal: Principal, limits: { perPrincipalPerMinute: number; perTenantPerHour: number }): Promise<void> {
  const [mine, tenant] = await Promise.all([
    store.incrementWithTtl(`quota:principal:${principal.tenantId}:${principal.subject}`, 60),
    store.incrementWithTtl(`quota:tenant:${principal.tenantId}`, 3600),
  ]);
  if (mine > limits.perPrincipalPerMinute || tenant > limits.perTenantPerHour) {
    throw new QuotaExceededError('Tool-call quota exceeded');
  }
}
```

- `run(store, fn)` scopes the principal to `fn` and everything it awaits; tested: concurrent requests keep their own principal and nothing remains after `run` returns.
- Never `enterWith()` in request handling: it leaks the store into the rest of the current async resource, which is how a keep-alive connection can carry one caller's context into the next request.
- The previous version of this page called `withTenantContext(context, async () => { return; })` with an empty callback, so the context existed only inside that no-op and every handler afterwards saw none (characterization test).

## 3. Quotas

`enforceToolQuota` above checks a per-principal and a per-tenant window, keyed only on verified identity. The store's increment and expiry must be atomic: with Redis use `MULTI; INCR key; EXPIRE key ttl NX; EXEC` (`NX` needs Redis 7.0+) (or a Lua script). Separate `INCR` then `EXPIRE` calls leave a counter without expiry if the process dies between them, and the tenant is blocked forever. Return a typed `RATE_LIMITED` / quota error to the model with a retry hint; do not fail open when the store is unreachable for write or expensive tools.

## 4. Tenant-scoped audit

Use the structured logger in [security-pii-compliance.md](security-pii-compliance.md) §3 (stderr, redacted). Each audit record carries tenant, subject, client id, tool, argument hash or ids, decision and result code. Raw tool arguments are not audit data: they can contain PII and secrets.

## 5. Data isolation checklist

- [ ] Every query includes the tenant from the principal (`WHERE tenant_id = $1 AND id = $2`); SQL stores also enforce row-level security from a per-transaction setting.
- [ ] Caches, vector-store filters, object-storage prefixes and handle stores are keyed by tenant (and subject where data is per user).
- [ ] Foreign and missing ids return the same error.
- [ ] Background work started by a tool carries the principal explicitly; it does not rely on ambient context surviving a queue.
- [ ] Tests: tenant A cannot read, list, update or delete tenant B's objects through any tool, and a negative control shows the test fails when the tenant filter is removed.
