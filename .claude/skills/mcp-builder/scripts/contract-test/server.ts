// Reference MCP contract-test server (TypeScript SDK v2 2.4.0, protocol 2026-07-28). Fixture data and
// test-only opaque tokens: copy the patterns, not the token table. Exercised by contract.test.ts:
// strict schemas + schema_version, bearer gate, per-tool scopes, tenant isolation, payload-hash-bound
// idempotency, stale-intent rejection, audit-before-effect with the eval-standard audit fields,
// tool metrics, cancellation and failure injection. `DRIFT=1` edits one description (surface-lock control).
import { createHash, randomUUID } from 'node:crypto';
import { createServer, type Server as HttpServer } from 'node:http';
import { toNodeHandler, type NodeIncomingMessageLike } from '@modelcontextprotocol/node';
import {
  McpServer,
  OAuthError,
  OAuthErrorCode,
  bearerAuthChallengeResponse,
  createMcpHandler,
  getOAuthProtectedResourceMetadataUrl,
  requireScopes,
  verifyBearerToken,
  type AuthInfo,
  type CallToolResult,
  type OAuthTokenVerifier,
} from '@modelcontextprotocol/server';
import * as z from 'zod/v4';

export const SUPPORTED_SCHEMA_MAJOR = 1;

export interface Principal { subject: string; tenantId: string; role: string; scopes: string[] }

/** Test verifier: opaque token → principal. Production verifies a JWT/introspection result. */
const TOKENS: Record<string, Principal> = {
  'tok-clerk-t1': { subject: 'alice', tenantId: 't1', role: 'clerk', scopes: ['orders:read', 'refunds:write'] },
  'tok-reader-t1': { subject: 'carol', tenantId: 't1', role: 'reader', scopes: ['orders:read'] },
  'tok-clerk-t2': { subject: 'bob', tenantId: 't2', role: 'clerk', scopes: ['orders:read', 'refunds:write'] },
};
/** Per-role tool allowlist, checked again inside every handler. */
const ALLOWED_TOOLS: Record<string, readonly string[]> = {
  clerk: ['orders_get', 'refunds_create', 'orders_export', 'inventory_check'],
  reader: ['orders_get', 'orders_export', 'inventory_check'],
};

export interface AuditRecord {
  tool_name: string; caller_role: string; caller_id_hash: string; scope_id_hash: string;
  request_id: string; session_id: string | null; input_schema_valid: boolean;
  authorization_result: 'allowed' | 'denied'; side_effect_type: string;
  prompt_version: string | null; model_name: string | null; audit_log_id: string;
  latency_ms: number; error_code: string | null;
}

export interface State {
  orders: Map<string, { tenantId: string; capturedCents: number; version: number }>;
  refunds: Map<string, { refundId: string; amountCents: number }>; // side effects actually performed
  idempotency: Map<string, { payloadHash: string; result: { refund_id: string; amount_cents: number } }>;
  audit: AuditRecord[];
  metrics: Map<string, number>;
  faults: { auditStoreDown: boolean; upstreamDown: boolean; driftDescription: boolean };
  exportBatchesDone: number;
  exportCancelled: boolean;
}

export function newState(): State {
  return {
    orders: new Map([
      ['ord_001', { tenantId: 't1', capturedCents: 5000, version: 1 }],
      ['ord_002', { tenantId: 't2', capturedCents: 9000, version: 1 }],
    ]),
    refunds: new Map(), idempotency: new Map(), audit: [], metrics: new Map(),
    faults: { auditStoreDown: false, upstreamDown: false, driftDescription: false },
    exportBatchesDone: 0, exportCancelled: false,
  };
}

const sha256 = (text: string): string => createHash('sha256').update(text).digest('hex');

/** Canonical JSON: sorted object keys, no whitespace, so equal payloads hash equally. */
export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function count(state: State, name: string, labels: Record<string, string>): void {
  const key = `${name}${canonicalJson(labels)}`;
  state.metrics.set(key, (state.metrics.get(key) ?? 0) + 1);
}

function toolError(code: string, message: string): CallToolResult {
  return { isError: true, content: [{ type: 'text', text: `${code}: ${message}` }], structuredContent: { error_code: code } };
}

function ok(payload: Record<string, unknown>): CallToolResult {
  return { content: [{ type: 'text', text: JSON.stringify(payload) }], structuredContent: payload };
}

/** schema_version is "<major>.<minor>"; only the supported major executes (G3 compatibility policy). */
const SchemaVersion = z.string().regex(/^[0-9]+\.[0-9]+$/).describe('Contract version of this tool input, e.g. "1.0"');
const schemaMajorOk = (version: string): boolean => Number(version.split('.')[0]) === SUPPORTED_SCHEMA_MAJOR;

function buildTools(server: McpServer, state: State, p: Principal): void {
  const permitted = (tool: string): boolean => (ALLOWED_TOOLS[p.role] ?? []).includes(tool);
  const finish = (tool: string, result: CallToolResult): CallToolResult => {
    const code = result.isError ? String((result.structuredContent as { error_code?: string } | undefined)?.error_code) : 'ok';
    count(state, 'tool_calls_total', { tool, role: p.role, result: code });
    return result;
  };
  const deny = (tool: string, reason: string): CallToolResult => {
    count(state, 'tool_auth_denials_total', { tool, reason });
    return finish(tool, toolError(reason, 'Not allowed for this caller'));
  };

  server.registerTool('orders_get', {
    description: 'Read one order of the caller\'s own tenant by id: captured amount in cents and current version. Read-only.',
    inputSchema: z.strictObject({ schema_version: SchemaVersion, order_id: z.string().regex(/^ord_[0-9]{3}$/) }),
    annotations: { readOnlyHint: true, openWorldHint: false },
    scopeChallenge: requireScopes('orders:read'),
  }, ({ schema_version, order_id }) => {
    if (!schemaMajorOk(schema_version)) return finish('orders_get', toolError('SCHEMA_VERSION_MISMATCH', `supported major ${SUPPORTED_SCHEMA_MAJOR}`));
    if (!permitted('orders_get')) return deny('orders_get', 'TOOL_NOT_ALLOWED');
    const order = state.orders.get(order_id);
    // Foreign and missing ids answer identically: no cross-tenant existence oracle.
    if (!order || order.tenantId !== p.tenantId) return finish('orders_get', toolError('NOT_FOUND', 'Order not found'));
    return finish('orders_get', ok({ order_id, captured_cents: order.capturedCents, version: order.version }));
  });

  const refundDescription = state.faults.driftDescription
    ? 'Refund an order. (silently changed description)'
    : 'Refund part or all of a captured order in the caller\'s tenant. Requires an idempotency key; a retry with the same key and the same payload returns the first result.';
  server.registerTool('refunds_create', {
    description: refundDescription,
    inputSchema: z.strictObject({
      schema_version: SchemaVersion,
      order_id: z.string().regex(/^ord_[0-9]{3}$/),
      amount_cents: z.number().int().positive().max(100_000),
      reason: z.enum(['damaged', 'late', 'other']),
      expected_order_version: z.number().int().positive().describe('Order version read before deciding; stale versions are rejected'),
      idempotency_key: z.string().regex(/^[A-Za-z0-9_-]{16,64}$/),
    }),
    annotations: { destructiveHint: true, idempotentHint: true, openWorldHint: false },
    scopeChallenge: requireScopes('refunds:write'),
  }, (args, ctx) => {
    const started = performance.now();
    const tool = 'refunds_create';
    if (!schemaMajorOk(args.schema_version)) return finish(tool, toolError('SCHEMA_VERSION_MISMATCH', `supported major ${SUPPORTED_SCHEMA_MAJOR}`));
    const meta = (ctx.mcpReq._meta ?? {}) as Record<string, unknown>;
    const audit = (authorization_result: AuditRecord['authorization_result'], error_code: string | null): void => {
      if (state.faults.auditStoreDown) throw new Error('audit store unavailable');
      state.audit.push({
        tool_name: tool, caller_role: p.role, caller_id_hash: sha256(p.subject), scope_id_hash: sha256(p.tenantId),
        request_id: String(ctx.mcpReq.id), session_id: typeof meta['app/session_id'] === 'string' ? meta['app/session_id'] : null,
        input_schema_valid: true, authorization_result, side_effect_type: 'financial',
        prompt_version: typeof meta['app/prompt_version'] === 'string' ? meta['app/prompt_version'] : null,
        model_name: typeof meta['app/model_name'] === 'string' ? meta['app/model_name'] : null,
        audit_log_id: randomUUID(), latency_ms: Math.round(performance.now() - started), error_code,
      });
      count(state, 'audit_writes_total', { tool });
    };
    try {
      if (!permitted(tool)) { audit('denied', 'TOOL_NOT_ALLOWED'); return deny(tool, 'TOOL_NOT_ALLOWED'); }
      const order = state.orders.get(args.order_id);
      if (!order || order.tenantId !== p.tenantId) { audit('denied', 'NOT_FOUND'); return finish(tool, toolError('NOT_FOUND', 'Order not found')); }
      const payloadHash = sha256(canonicalJson({ order_id: args.order_id, amount_cents: args.amount_cents, reason: args.reason }));
      const key = sha256(`${p.tenantId}|${args.idempotency_key}`); // keys are tenant-scoped
      const prior = state.idempotency.get(key);
      if (prior) {
        if (prior.payloadHash !== payloadHash) { audit('denied', 'IDEMPOTENCY_PAYLOAD_MISMATCH'); return finish(tool, toolError('IDEMPOTENCY_PAYLOAD_MISMATCH', 'Key reused with a different payload; nothing executed')); }
        return finish(tool, ok({ ...prior.result, replayed: true }));
      }
      // A human resolved or changed the order since the agent read it: the late AI intent is stale.
      if (order.version !== args.expected_order_version) { audit('denied', 'STALE_INTENT'); return finish(tool, toolError('STALE_INTENT', 'Order changed since it was read; re-read and decide again')); }
      if (args.amount_cents > order.capturedCents) { audit('denied', 'AMOUNT_EXCEEDS_CAPTURE'); return finish(tool, toolError('AMOUNT_EXCEEDS_CAPTURE', 'Amount exceeds captured total')); }
      audit('allowed', null); // audit before effect: a failed audit write throws and nothing executes
      const result = { refund_id: `rf_${randomUUID()}`, amount_cents: args.amount_cents };
      state.refunds.set(result.refund_id, { refundId: result.refund_id, amountCents: args.amount_cents });
      order.capturedCents -= args.amount_cents;
      order.version += 1;
      state.idempotency.set(key, { payloadHash, result });
      return finish(tool, ok({ ...result, replayed: false }));
    } catch (error) {
      process.stderr.write(`${JSON.stringify({ level: 'error', event: 'refund_blocked', error_type: error instanceof Error ? error.name : 'unknown' })}\n`);
      return finish(tool, toolError('AUDIT_UNAVAILABLE', 'Audit store unavailable; nothing executed, retry later'));
    }
  });

  server.registerTool('orders_export', {
    description: 'Export the caller\'s tenant orders in batches. Long-running; honours cancellation between batches. Read-only.',
    inputSchema: z.strictObject({ schema_version: SchemaVersion, batches: z.number().int().min(1).max(50) }),
    annotations: { readOnlyHint: true },
    scopeChallenge: requireScopes('orders:read'),
  }, async ({ schema_version, batches }, ctx) => {
    if (!schemaMajorOk(schema_version)) return finish('orders_export', toolError('SCHEMA_VERSION_MISMATCH', `supported major ${SUPPORTED_SCHEMA_MAJOR}`));
    const signal = ctx.mcpReq.signal;
    try {
      for (let i = 0; i < batches; i += 1) {
        await new Promise<void>((resolve, reject) => {
          const timer = setTimeout(resolve, 50);
          signal.addEventListener('abort', () => { clearTimeout(timer); reject(signal.reason); }, { once: true });
        });
        state.exportBatchesDone += 1;
      }
    } catch (error) {
      if (signal.aborted) { state.exportCancelled = true; }
      throw error;
    }
    return finish('orders_export', ok({ batches_done: batches }));
  });

  server.registerTool('inventory_check', {
    description: 'Check stock for a SKU from the upstream inventory service. Returns a typed error when the upstream is unavailable.',
    inputSchema: z.strictObject({ schema_version: SchemaVersion, sku: z.string().regex(/^[A-Z0-9-]{3,32}$/) }),
    annotations: { readOnlyHint: true, openWorldHint: true },
    scopeChallenge: requireScopes('orders:read'),
  }, ({ schema_version, sku }) => {
    if (!schemaMajorOk(schema_version)) return finish('inventory_check', toolError('SCHEMA_VERSION_MISMATCH', `supported major ${SUPPORTED_SCHEMA_MAJOR}`));
    // Failure path: never a fabricated "0 in stock" (graceful degradation is a visible typed error).
    if (state.faults.upstreamDown) return finish('inventory_check', toolError('UPSTREAM_UNAVAILABLE', 'Inventory service unavailable; retry later or ask a human'));
    return finish('inventory_check', ok({ sku, in_stock: 3 }));
  });
}

export interface Running { url: URL; state: State; close: () => Promise<void> }

export async function start(port: number, state: State = newState()): Promise<Running> {
  const resource = new URL(`http://127.0.0.1:${port}/mcp`);
  const resourceMetadataUrl = getOAuthProtectedResourceMetadataUrl(resource);
  const verifier: OAuthTokenVerifier = {
    verifyAccessToken: (token) => {
      const p = TOKENS[token];
      if (!p) return Promise.reject(new OAuthError(OAuthErrorCode.InvalidToken, 'unknown token'));
      const info: AuthInfo = { token, clientId: 'test-client', scopes: p.scopes, expiresAt: Math.floor(Date.now() / 1000) + 600, resource, extra: { principal: p } };
      return Promise.resolve(info);
    },
  };
  const handler = createMcpHandler(({ authInfo }) => {
    const server = new McpServer({ name: 'contract-test-mcp', version: '1.0.0' });
    const principal = authInfo?.extra?.['principal'] as Principal | undefined;
    if (principal) buildTools(server, state, principal); // no verified principal → no tools
    return server;
  });
  const node = toNodeHandler(handler, { maxRequestBodySize: 262_144 });
  const http: HttpServer = createServer((req, res) => {
    void (async () => {
      try {
        const auth = await verifyBearerToken(req.headers.authorization, { verifier, resourceMetadataUrl, expectedResource: resource });
        await node(Object.assign(req, { auth }) as NodeIncomingMessageLike, res);
      } catch (error) {
        const challenge = bearerAuthChallengeResponse(error, { resourceMetadataUrl });
        res.writeHead(challenge.status, Object.fromEntries(challenge.headers));
        res.end(await challenge.text());
      }
    })();
  });
  await new Promise<void>((resolve) => http.listen(port, '127.0.0.1', resolve));
  return { url: resource, state, close: async () => { await handler.close(); await new Promise<void>((r) => http.close(() => r())); } };
}

if (import.meta.main) {
  const port = Number(process.env['PORT'] ?? '56501');
  const state = newState();
  state.faults.driftDescription = process.env['DRIFT'] === '1';
  await start(port, state);
  process.stderr.write(`${JSON.stringify({ level: 'info', event: 'listening', port })}\n`);
}
