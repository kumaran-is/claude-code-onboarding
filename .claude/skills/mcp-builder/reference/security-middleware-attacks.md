# MCP Tool Execution Safety: Side Effects, Approvals, SSRF, Untrusted Output

What a tool may do once the caller is authenticated ([security-core.md](security-core.md)). Requirement levels and reviewer severities: [`security-reviewer/reference/mcp-security.md`](../../security-reviewer/reference/mcp-security.md). Code here is copied from the same tested sandbox (MCP SDK v2, revision 2026-07-28; 31 tests passing with both a 2026-07-28 and a 2025-11-25 client, 14 planted-defect controls).

## 1. Classify every tool before writing it

| Class | Examples | Required server-side controls |
|---|---|---|
| Read, closed world | `get_document` | scope, tenant filter from the token, output schema, result marked untrusted |
| Read, open world | `fetch_url`, web search | the above + SSRF guard (§4), size/time caps, result is untrusted data |
| Write, reversible | create draft, add comment | scope, idempotency key, audit before the effect |
| Destructive or external effect | delete, send, pay, publish | scope, **human approval bound to the exact call** (§2), idempotency key, audit, dry-run where possible |

Least privilege: one narrow tool per intent (`refund_order(order_id, amount ≤ captured)`), not `run_sql` or `http_request`. Allow/deny lists are per principal (security-core §4); a tool nobody needs is deleted, not hidden.

**Annotations are hints, not enforcement.** `readOnlyHint`, `destructiveHint`, `idempotentHint` and `openWorldHint` help a client render confirmations; the spec says clients MUST treat annotations as untrusted unless the server is trusted (Tools §Tool). A planted `destructiveHint: true` with no approval check deleted another tenant's document (negative control).

## 2. Human approval for destructive operations

The spec asks hosts to keep a human in the loop who can deny tool calls (Tools, SHOULD), but the host may auto-approve. When the effect matters, the **server** enforces approval: an approval service the model cannot reach (a UI confirm, a ticket, a second person) signs a short-lived, single-use grant bound to principal, tool and canonical arguments.

```ts
import { createHash, createHmac, timingSafeEqual } from 'node:crypto';

/** A human approval for one exact destructive call, issued by an approval service the
 * model cannot reach (UI confirm, ticket, second person). Bound to principal, tool,
 * canonical arguments and expiry; single use. */
export interface ApprovalClaims {
  subject: string;
  tenantId: string;
  tool: string;
  argsHash: string;
  expiresAt: number; // epoch seconds
  nonce: string;
}

export function hashArgs(args: Record<string, unknown>): string {
  const canonical = JSON.stringify(Object.keys(args).sort().map((key) => [key, args[key]]));
  return createHash('sha256').update(canonical).digest('base64url');
}

export class ApprovalVerifier {
  private readonly used = new Set<string>(); // production: shared store with TTL (Redis SET NX EX)

  private readonly key: Buffer;

  constructor(key: Buffer) {
    this.key = key;
    if (key.length < 32) throw new Error('Approval signing key must be at least 32 bytes');
  }

  sign(claims: ApprovalClaims): string {
    const body = Buffer.from(JSON.stringify(claims)).toString('base64url');
    const mac = createHmac('sha256', this.key).update(body).digest('base64url');
    return `${body}.${mac}`;
  }

  /** Returns null when valid; otherwise the refusal reason. Consumes the nonce on success. */
  verify(token: string | undefined, expected: Omit<ApprovalClaims, 'expiresAt' | 'nonce'>, nowSeconds: number): string | null {
    if (!token) return 'approval_required';
    const [body, mac] = token.split('.');
    if (!body || !mac) return 'approval_malformed';
    const expectedMac = createHmac('sha256', this.key).update(body).digest();
    const givenMac = Buffer.from(mac, 'base64url');
    if (givenMac.length !== expectedMac.length || !timingSafeEqual(givenMac, expectedMac)) return 'approval_invalid';
    const claims = JSON.parse(Buffer.from(body, 'base64url').toString('utf8')) as ApprovalClaims;
    if (claims.expiresAt < nowSeconds) return 'approval_expired';
    if (claims.subject !== expected.subject || claims.tenantId !== expected.tenantId || claims.tool !== expected.tool || claims.argsHash !== expected.argsHash) {
      return 'approval_mismatch';
    }
    if (this.used.has(claims.nonce)) return 'approval_replayed';
    this.used.add(claims.nonce);
    return null;
  }
}
```

```ts
server.registerTool(
  'delete_document',
  {
    description: 'Permanently delete one document. Requires a human approval token for this exact call.',
    inputSchema: z.object({ document_id: z.string().regex(/^[a-z0-9-]{1,64}$/), approval_token: z.string().max(2048).optional() }).strict(),
    annotations: { destructiveHint: true, idempotentHint: true, readOnlyHint: false, openWorldHint: false }, // hints for the client UI, not enforcement
    scopeChallenge: requireScopes('docs:delete'),
  },
  ({ document_id, approval_token }, ctx) => {
    const principal = principalFrom(ctx.http?.authInfo);
    if (!allow(principal)) return toolError('RATE_LIMITED', 'Too many calls; retry after 60s');
    const refusal = config.approvals.verify(
      approval_token,
      { subject: principal.subject, tenantId: principal.tenantId, tool: 'delete_document', argsHash: hashArgs({ document_id }) },
      Math.floor(Date.now() / 1000),
    );
    // Audit before the effect; the record carries ids and the decision, never the token.
    logger.info('audit.tool_call', { tool: 'delete_document', tenant: principal.tenantId, sub: principal.subject, document_id, decision: refusal ?? 'approved' });
    if (refusal) return toolError('APPROVAL_REQUIRED', `Refused: ${refusal}. Ask the user to approve this exact deletion.`);
    const deleted = config.documents.delete(principal.tenantId, document_id);
    return deleted ? { content: [{ type: 'text', text: JSON.stringify({ deleted: document_id }) }] } : toolError('NOT_FOUND', 'Document not found');
  },
);
```

Tested: no token → `approval_required`; approval for another document → `approval_mismatch`; the bound approval deletes once; the same approval again → `approval_replayed`. Planted defects (approval check skipped, replay check removed) each failed the suite.

- Form-mode elicitation MUST NOT request passwords, API keys, tokens or payment credentials (spec, Elicitation); use URL-mode elicitation, which sends the user to an out-of-band page, for credentials and third-party authorization.
- Elicitation (`ctx.mcpReq.elicitInput`) is a good way to *ask*; the answer comes from the client, so it is not proof that a human approved. Use it as UX in front of a server-verified grant.
- The used-nonce set must be shared and durable in production (for example Redis `SET nonce 1 NX EX <ttl>`), and the signing key comes from the secret store and rotates.
- Audit the decision **before** the effect; if the audit write fails, do not perform the effect.

## 3. Idempotency, timeouts, retries, circuit breakers

- Every write/destructive tool takes or derives an idempotency key; store `(principal, key) → result` and return the stored result on a repeat instead of acting twice.
- Every outbound call has a deadline (`AbortSignal.timeout`); the tool returns a typed error on timeout, never a fake empty result.
- Retry only idempotent operations, only on retryable failures (timeout, 429, 5xx, connection reset), with a bound and jittered backoff. Never retry a non-idempotent write without its idempotency key.
- Circuit breakers and bulkheads per upstream: [resilience-core.md](resilience-core.md). Durable execution of long multi-step effects (resume after crash without repeating side effects) belongs in a workflow engine or an outbox, not in the tool handler.

## 4. SSRF: URLs the model or a document can influence

Any tool that fetches a URL is an SSRF primitive: a prompt-injected document can ask the agent to fetch `http://169.254.169.254/` (cloud credentials) or an internal admin endpoint. The guard must hold for every hop and for the address actually connected to:

```ts
import { lookup as dnsLookup } from 'node:dns';
import type { LookupAddress } from 'node:dns';
import { request as httpRequest } from 'node:http';
import { request as httpsRequest } from 'node:https';
import type { IncomingMessage } from 'node:http';
import type { LookupFunction } from 'node:net';
import ipaddr from 'ipaddr.js';

export class SsrfBlockedError extends Error {
  override readonly name = 'SsrfBlockedError';
}

export interface SafeFetchPolicy {
  /** Schemes allowed for every hop. Production: ['https:']. */
  allowedProtocols: ReadonlySet<string>;
  /** Optional host allowlist (exact hostnames). Empty = any public host. */
  allowedHosts: ReadonlySet<string>;
  /** Decides per resolved address; default refuses everything that is not public unicast. */
  isAddressAllowed: (address: string, port: number) => boolean;
  maxRedirects: number;
  timeoutMs: number;
  maxBodyBytes: number;
}

/** Public unicast only: refuses loopback, RFC 1918, link-local (IMDS 169.254.169.254),
 * CGNAT, multicast, reserved, unspecified, ULA (fc00::/7) and IPv4-mapped forms of all of them. */
export function isPublicAddress(address: string): boolean {
  if (!ipaddr.isValid(address)) return false;
  let parsed = ipaddr.parse(address);
  if (parsed.kind() === 'ipv6' && (parsed as ipaddr.IPv6).isIPv4MappedAddress()) {
    parsed = (parsed as ipaddr.IPv6).toIPv4Address();
  }
  return parsed.range() === 'unicast';
}

export const defaultPolicy: SafeFetchPolicy = {
  allowedProtocols: new Set(['https:']),
  allowedHosts: new Set(),
  isAddressAllowed: (address) => isPublicAddress(address),
  maxRedirects: 3,
  timeoutMs: 5_000,
  maxBodyBytes: 1_000_000,
};

/** Resolve, check every address, then hand the checked address to the socket.
 * The connection can only go to an address that passed the check (no DNS-rebinding window). */
function pinnedLookup(policy: SafeFetchPolicy, port: number): LookupFunction {
  return (hostname, options, callback) => {
    dnsLookup(hostname, { all: true, family: options.family ?? 0 }, (error, addresses: LookupAddress[]) => {
      if (error) {
        callback(error, '', 0);
        return;
      }
      const first = addresses[0];
      if (!first || addresses.some((entry) => !policy.isAddressAllowed(entry.address, port))) {
        callback(new SsrfBlockedError(`Destination address not allowed for ${hostname}`), '', 0);
        return;
      }
      if (options.all) callback(null, addresses);
      else callback(null, first.address, first.family);
    });
  };
}

export interface SafeFetchResult {
  status: number;
  finalUrl: string;
  body: string;
}

function assertUrlAllowed(url: URL, policy: SafeFetchPolicy): number {
  if (!policy.allowedProtocols.has(url.protocol)) throw new SsrfBlockedError(`Scheme not allowed: ${url.protocol}`);
  if (url.username || url.password) throw new SsrfBlockedError('Credentials in URL are not allowed');
  if (policy.allowedHosts.size > 0 && !policy.allowedHosts.has(url.hostname)) {
    throw new SsrfBlockedError(`Host not on allowlist: ${url.hostname}`);
  }
  const port = url.port ? Number(url.port) : url.protocol === 'https:' ? 443 : 80;
  // A literal IP never goes through DNS lookup, so check it here as well.
  const literal = url.hostname.replace(/^\[|\]$/g, '');
  if (ipaddr.isValid(literal) && !policy.isAddressAllowed(literal, port)) {
    throw new SsrfBlockedError('Destination address not allowed');
  }
  return port;
}

function requestOnce(url: URL, policy: SafeFetchPolicy, port: number, signal: AbortSignal): Promise<{ response: IncomingMessage; body: string }> {
  const send = url.protocol === 'https:' ? httpsRequest : httpRequest;
  return new Promise((resolve, reject) => {
    const req = send(url, { method: 'GET', lookup: pinnedLookup(policy, port), signal, headers: { accept: 'application/json, text/plain' } }, (response) => {
      let size = 0;
      const chunks: Buffer[] = [];
      response.on('data', (chunk: Buffer) => {
        size += chunk.length;
        if (size > policy.maxBodyBytes) {
          req.destroy(new SsrfBlockedError('Response body too large'));
          return;
        }
        chunks.push(chunk);
      });
      response.on('end', () => { resolve({ response, body: Buffer.concat(chunks).toString('utf8') }); });
      response.on('error', reject);
    });
    req.on('error', reject);
    req.end();
  });
}

/** GET with SSRF protection: scheme/host allowlist, resolve-then-pin, manual redirects
 * re-validated on every hop, timeout and body cap. Never forwards the caller's credentials. */
export async function safeFetch(rawUrl: string, policy: SafeFetchPolicy = defaultPolicy): Promise<SafeFetchResult> {
  const signal = AbortSignal.timeout(policy.timeoutMs);
  let current = new URL(rawUrl);
  for (let hop = 0; hop <= policy.maxRedirects; hop += 1) {
    const port = assertUrlAllowed(current, policy);
    const { response, body } = await requestOnce(current, policy, port, signal);
    const status = response.statusCode ?? 0;
    const location = response.headers.location;
    if (status >= 300 && status < 400 && location) {
      current = new URL(location, current);
      continue;
    }
    return { status, finalUrl: current.href, body };
  }
  throw new SsrfBlockedError('Too many redirects');
}
```

- **Classify addresses with a library** (`ipaddr.js` `range() === 'unicast'`), never string prefixes: hand-written prefix lists miss `localhost`, `[::1]`, `[::ffff:7f00:1]`, `172.20.0.1`, `0.0.0.0` and attacker DNS names (characterization test against the old prefix guard). The spec's own advice: avoid manual IP parsing (Security Best Practices §SSRF).
- **Resolve then pin:** the custom `lookup` validates every resolved address and the socket connects only to a validated one, so a DNS answer cannot change between check and use (DNS rebinding / TOCTOU).
- **Redirects:** never auto-follow; re-validate scheme, host and address on every hop (tested: public host → 302 → metadata address is refused; with `fetch()` defaults the credential came back).
- **Caps:** timeout, body size, hop count; no credentials in URLs; never forward the caller's token or cookies to the fetched URL.
- **Defense in depth:** an egress proxy that blocks private ranges (the spec names Smokescreen as an example) and network policy on the workload, so a bug in the guard is not the last line.

Tests: blocked — `127.0.0.1`, `169.254.169.254`, `localhost`, `[::ffff:127.0.0.1]`, `2130706433` (decimal), redirect-to-private, `user:pass@` URLs; allowed — the stand-in public host. The sandbox lets one loopback port stand in for a public host; everything else uses the production rule.

## 5. Tool results and resources are untrusted data

Everything a tool returns (fetched pages, documents, tickets, emails, another server's output) may contain instructions aimed at the model. Controls are structural:

- Return data, not instructions: structured output with an `outputSchema`, fields such as `trust: 'untrusted'` and `source`; the client places it in tool-result content, never in the system prompt.
- Validate tool output against its schema on the client (spec: clients SHOULD validate structured results) and drop unknown fields before they reach code.
- Nothing read from a tool result grants authority: recipients, URLs, amounts and ids that drive a side effect come from verified state or an allowlist, and destructive follow-ups still need §2 approval.
- Regex "prompt injection detectors" are a signal for logging and review, not a boundary: the old pattern list missed paraphrases ("disregard what you were told earlier") and non-English text, and flagged benign text ("act as a liaison", `{"tool": "hammer"}`) (characterization tests). Do not reject or rewrite inputs on that signal alone.
- HTML stripping or DOMPurify on JSON-RPC arguments is not an injection defense; schema validation (types, enums, lengths, `.strict()`) is. Output encoding belongs to whichever UI renders the data.

## 6. Rate limits and quotas per principal

```ts
/** Fixed-window limiter keyed by verified principal. Production: shared store (Redis INCR + EXPIRE in one MULTI). */
function createLimiter(limit: number): (principal: Principal) => boolean {
  const windows = new Map<string, { start: number; count: number }>();
  return (principal) => {
    const key = `${principal.tenantId}:${principal.subject}`;
    const now = Date.now();
    const current = windows.get(key);
    if (!current || now - current.start >= 60_000) {
      windows.set(key, { start: now, count: 1 });
      return true;
    }
    current.count += 1;
    return current.count <= limit;
  };
}
```

Key limits on the verified principal (tenant + subject) and, separately, on the tenant; per-IP limits are only an outer layer. Multi-instance deployments need a shared counter: [production-runtime-multi-tenant.md](production-runtime-multi-tenant.md) §3. Budget expensive tools (fan-out, LLM calls, exports) separately from cheap reads.

## 7. Failed authentication

With OAuth access tokens the authorization server owns credential brute-force protection; the MCP server answers 401 and logs `auth.token_rejected` with the `jose` error code. For static API keys, add a per-key-prefix and per-IP failure limiter (429 with `Retry-After`), compare keys with `timingSafeEqual`, and plan their retirement in favour of OAuth or workload identity.
