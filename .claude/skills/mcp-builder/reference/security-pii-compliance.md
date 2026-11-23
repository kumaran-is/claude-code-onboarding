# MCP Server Security: Secrets, Errors, Audit Logging and PII

Credentials, what leaves the server in errors and logs, and keeping PII out of model context. Authentication: [security-core.md](security-core.md). Tool execution: [security-middleware-attacks.md](security-middleware-attacks.md). Requirement levels: [`security-reviewer/reference/mcp-security.md`](../../security-reviewer/reference/mcp-security.md). Code is copied from the tested sandbox (31 tests passing with both a 2026-07-28 and a 2025-11-25 client, 14 planted-defect controls).

## 1. Secrets and credential forwarding

- **No token passthrough (spec MUST NOT).** The token the client sent is for *this* server. To call an upstream API, the server uses its own credential: a service account, OAuth client credentials, or a token obtained by token exchange (RFC 8693) for that upstream audience. Never forward the inbound `Authorization` header (Authorization §Access Token Privilege Restriction).
- **Proxy servers with a static client ID** that forward users to a third-party authorization server MUST obtain user consent for each dynamically registered client (confused deputy; Authorization Security Considerations).
- Never collect a secret through form-mode elicitation (spec MUST NOT); credentials and third-party OAuth go through URL-mode elicitation so they never pass through the MCP client or the model.
- Secrets come from the platform secret store or injected environment variables, are validated at startup (missing → refuse to start), and never appear in argv, tool arguments, tool results, resource contents, prompts, logs or traces. A secret in argv is visible to every process that can list processes (`ps -o args` showed a `--api-key=…` argument in a local check).
- Upstream credentials are scoped to what the tools need (restricted keys, read-only database roles) so a tool bug cannot exceed them. A read-only *transaction* is not a read-only *role*: a server that runs the model's SQL as one simple-protocol query inside `BEGIN READ ONLY` can be escaped with `COMMIT;` followed by a write (read from a published server's code; not executed here). Enforce read-only with the role's grants.
- Rotate signing keys and API keys without restart: JWKS refetch on unknown `kid` (security-core §2), dual-key windows for HMAC approval keys.

## 2. Secure error responses

- HTTP layer: 401 for missing/invalid/expired tokens, 403 for valid tokens without the scope or permission, 400 for malformed requests (spec MUST); 401/403 carry `WWW-Authenticate: Bearer …` with `resource_metadata`.
- Tool layer: a tool failure is a successful JSON-RPC result with `isError: true` and a stable code plus a safe message (`NOT_FOUND`, `APPROVAL_REQUIRED`, `DESTINATION_NOT_ALLOWED`, `UPSTREAM_UNAVAILABLE`, `RATE_LIMITED`). Never return `error.message` from an upstream, a stack trace, SQL, a connection string or an internal hostname: validation and driver errors echo submitted values.
- Missing and forbidden answer identically where existence is itself sensitive (cross-tenant ids).
- Log the error *type* and correlation id server-side; the client gets the code.

## 3. Structured audit logging with redaction

```ts
// Structured JSON logger to stderr (stdout is reserved for stdio transports).
// Redacts credential-shaped keys before anything is serialized.
const REDACTED_KEYS = /^(authorization|token|access_token|refresh_token|id_token|password|secret|api_key|apikey|cookie|set-cookie|approval_token)$/i;

export type LogFields = Record<string, unknown>;

export function redact(value: unknown, depth = 0): unknown {
  if (depth > 6 || value === null || typeof value !== 'object') return value;
  if (Array.isArray(value)) return value.map((item) => redact(item, depth + 1));
  const out: Record<string, unknown> = {};
  for (const [key, inner] of Object.entries(value)) {
    out[key] = REDACTED_KEYS.test(key) ? '[REDACTED]' : redact(inner, depth + 1);
  }
  return out;
}

function write(level: 'info' | 'warn' | 'error', event: string, fields: LogFields): void {
  const record = { ts: new Date().toISOString(), level, event, ...(redact(fields) as LogFields) };
  process.stderr.write(`${JSON.stringify(record)}\n`);
}

export const logger = {
  info: (event: string, fields: LogFields = {}) => { write('info', event, fields); },
  warn: (event: string, fields: LogFields = {}) => { write('warn', event, fields); },
  error: (event: string, fields: LogFields = {}) => { write('error', event, fields); },
};
```

- Write logs to **stderr**: stdout carries JSON-RPC for stdio servers. The protocol's `notifications/message` logging is deprecated in revision 2026-07-28 (migration: stderr for stdio, OpenTelemetry for observability).
- Audit every authorization decision and every write/destructive tool call: timestamp, tenant, subject, client id, tool, argument **hash** or ids (not raw arguments), decision, result code, correlation id. Write the audit record before the effect; a failed audit write blocks the effect.
- Never log tokens, approval grants, cookies, raw prompts or tool payloads containing user content. Redaction by key is a backstop; the primary control is not passing secrets to the logger.
- Ship audit records to an append-only store with retention and access control; alert on spikes of 401/403, `insufficient_scope`, `ssrf_blocked` and `approval_*` refusals.

## 4. PII tokenization: keep raw PII out of model context

When a tool returns records with PII the model does not need to read, return opaque tokens and resolve them server-side when the model passes one back to an action tool.

```ts
import { randomBytes } from 'node:crypto';
import type { Principal } from './auth.ts';

/** Replaces PII values with opaque tokens before a result reaches the model. The mapping is
 * keyed by the verified principal, expires, and an unknown or foreign token is an error. */
export class PiiTokenizer {
  private readonly store = new Map<string, { value: string; expiresAt: number }>();
  private readonly ttlMs: number;

  constructor(ttlMs: number) {
    this.ttlMs = ttlMs;
  }

  private key(principal: Principal, token: string): string {
    return `${principal.tenantId}:${principal.subject}:${token}`;
  }

  tokenize<T extends Record<string, unknown>>(principal: Principal, record: T, fields: ReadonlyArray<keyof T & string>): Record<string, unknown> {
    const safe: Record<string, unknown> = { ...record };
    for (const field of fields) {
      const value = record[field];
      if (typeof value !== 'string') continue;
      const token = `pii_${randomBytes(12).toString('base64url')}`;
      this.store.set(this.key(principal, token), { value, expiresAt: Date.now() + this.ttlMs });
      safe[field] = token;
    }
    return safe;
  }

  /** Resolve a token the model passed back. Throws instead of passing an unknown value through. */
  resolve(principal: Principal, token: string): string {
    const entry = this.store.get(this.key(principal, token));
    if (!entry || entry.expiresAt < Date.now()) throw new Error('Unknown or expired PII token');
    return entry.value;
  }
}
```

Tested: the owner resolves its token; another principal presenting the same token, an unknown value and an expired token all fail. The previous version of this page keyed the store on `extra.sessionId ?? 'default'` (every sessionless caller shared one map; revision 2026-07-28 has no protocol sessions) and passed unknown tokens through as literal values, so a model could address any email it invented.

- Store the mapping server-side with a TTL (shared store when multi-instance), never in tool results or on disk unencrypted.
- Tokenization limits what the model sees; it does not replace authorization on the action tool (scope, tenant, approval).
- Approved data classes per model provider still apply: if a field must never reach the provider, tokenization must run before every tool result, not only some.

## 5. CI gates for an MCP server repository

- Type check (`tsc --noEmit`, strict) and lint (`no-console`, `no-explicit-any`) exit 0.
- The security test suite (attacks plus negative controls) runs on every PR.
- `npm audit --audit-level=high` (judged by its own exit code), secret scanning, and container scanning if you ship an image.
- Third-party GitHub Actions pinned to a full commit SHA; MCP SDK and `jose` pinned to exact versions and upgraded deliberately (an adapter minor version changed whether `expectedResource` was enforced).

## 6. Checklist

- [ ] HTTP transport: Protected Resource Metadata served; 401 challenge carries `resource_metadata`; tokens validated for `alg`, `typ`, `iss`, `aud` = this server, `exp`
- [ ] No token passthrough; upstream calls use the server's own scoped credential
- [ ] Origin validated (403 on a bad Origin); local servers bind `127.0.0.1`; remote binds list `allowedHosts` and `allowedOrigins`
- [ ] Per-tool scopes via `scopeChallenge`; tool allowlist per principal; tenant and subject only from the verified token
- [ ] Destructive tools need a server-verified approval bound to the exact call; annotations are hints only
- [ ] Every URL-fetching path uses the SSRF guard (library IP classification, resolve-then-pin, per-hop redirect checks, caps)
- [ ] Tool results marked untrusted and schema-validated; no authority derived from tool output
- [ ] Per-principal and per-tenant rate limits and quotas in a shared store
- [ ] Errors return stable codes, no upstream messages; logs on stderr, redacted, audit before effect
- [ ] Secrets from the secret store or environment, never argv; startup fails when one is missing
- [ ] Security tests include a negative control for each guard
