// Contract suite over a real SDK v2 Client and Streamable HTTP. Every test runs against a fresh server.
import { after, before, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import type { CallToolResult } from '@modelcontextprotocol/client';
import { newState, start, type Running } from './server.ts';

// One port per suite: undici keeps sockets alive, so restarting on the same port resets reused connections.
let nextPort = Number(process.env['TEST_PORT'] ?? '56510');
let srv: Running;

async function client(token: string | null, era: 'modern' | 'legacy' = 'modern'): Promise<Client> {
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  // The 2.4.0 client defaults to the 2025 (legacy) era; pin 2026-07-28 so cancellation reaches the handler.
  const c = new Client({ name: 'contract-tests', version: '1.0.0' },
    era === 'modern' ? { versionNegotiation: { mode: { pin: '2026-07-28' } } } : {});
  await c.connect(new StreamableHTTPClientTransport(srv.url, { requestInit: { headers } }));
  return c;
}
const code = (r: CallToolResult): string | undefined => (r.structuredContent as { error_code?: string } | undefined)?.error_code;
const refund = (over: Record<string, unknown> = {}): Record<string, unknown> => ({
  schema_version: '1.0', order_id: 'ord_001', amount_cents: 1000, reason: 'damaged', expected_order_version: 1,
  idempotency_key: 'key-0000000000000001', ...over,
});

describe('L1 protocol contract', () => {
  before(async () => { srv = await start(nextPort++, newState()); });
  after(async () => { await srv.close(); });
  it('lists exactly the expected tools for a clerk (no surprise tools)', async () => {
    const c = await client('tok-clerk-t1');
    const names = (await c.listTools()).tools.map((t) => t.name).sort();
    assert.deepEqual(names, ['inventory_check', 'orders_export', 'orders_get', 'refunds_create']);
  });
  it('unknown tool is a protocol error, not a result', async () => {
    const c = await client('tok-clerk-t1');
    await assert.rejects(c.callTool({ name: 'orders_delete_all', arguments: {} }));
  });
});

describe('L2 schema validity (G3)', () => {
  before(async () => { srv = await start(nextPort++, newState()); });
  after(async () => { await srv.close(); });
  it('rejects an unknown field (smuggled tenant_id) without executing', async () => {
    const c = await client('tok-clerk-t1');
    const r = await c.callTool({ name: 'refunds_create', arguments: refund({ tenant_id: 't2' }) });
    assert.equal(r.isError, true);
    assert.equal(srv.state.refunds.size, 0);
  });
  it('rejects a missing required field and a bad enum', async () => {
    const c = await client('tok-clerk-t1');
    const { idempotency_key: _drop, ...noKey } = refund();
    assert.equal((await c.callTool({ name: 'refunds_create', arguments: noKey })).isError, true);
    assert.equal((await c.callTool({ name: 'refunds_create', arguments: refund({ reason: 'because' }) })).isError, true);
    assert.equal(srv.state.refunds.size, 0);
  });
  it('unsupported schema major → SCHEMA_VERSION_MISMATCH, nothing executed', async () => {
    const c = await client('tok-clerk-t1');
    const r = await c.callTool({ name: 'refunds_create', arguments: refund({ schema_version: '2.0' }) });
    assert.equal(code(r), 'SCHEMA_VERSION_MISMATCH');
    assert.equal(srv.state.refunds.size, 0);
  });
});

describe('L3 authorization + isolation', () => {
  before(async () => { srv = await start(nextPort++, newState()); });
  after(async () => { await srv.close(); });
  it('no token → connection refused with 401', async () => {
    await assert.rejects(client(null));
  });
  it('unknown token → 401', async () => {
    await assert.rejects(client('tok-forged'));
  });
  it('reader lacks refunds:write → refused before the handler, no side effect', async () => {
    const c = await client('tok-reader-t1');
    await assert.rejects(c.callTool({ name: 'refunds_create', arguments: refund() }));
    assert.equal(srv.state.refunds.size, 0);
  });
  it('tenant t2 cannot read or refund a t1 order (same answer as missing)', async () => {
    const c = await client('tok-clerk-t2');
    const read = await c.callTool({ name: 'orders_get', arguments: { schema_version: '1.0', order_id: 'ord_001' } });
    const missing = await c.callTool({ name: 'orders_get', arguments: { schema_version: '1.0', order_id: 'ord_999' } });
    assert.equal(code(read), 'NOT_FOUND');
    assert.deepEqual(read.content, missing.content);
    const write = await c.callTool({ name: 'refunds_create', arguments: refund() });
    assert.equal(code(write), 'NOT_FOUND');
    assert.equal(srv.state.refunds.size, 0);
  });
});

describe('G4 idempotency + G5 stale intent + §10.3 audit', () => {
  before(async () => { srv = await start(nextPort++, newState()); });
  after(async () => { await srv.close(); });
  it('same key + same payload → first result, one side effect', async () => {
    const c = await client('tok-clerk-t1');
    const first = await c.callTool({ name: 'refunds_create', arguments: refund() });
    const again = await c.callTool({ name: 'refunds_create', arguments: refund() });
    assert.equal(first.isError, undefined);
    assert.equal((again.structuredContent as { replayed: boolean }).replayed, true);
    assert.equal((again.structuredContent as { refund_id: string }).refund_id, (first.structuredContent as { refund_id: string }).refund_id);
    assert.equal(srv.state.refunds.size, 1);
  });
  it('same key + changed amount → IDEMPOTENCY_PAYLOAD_MISMATCH, no second side effect', async () => {
    const c = await client('tok-clerk-t1');
    const r = await c.callTool({ name: 'refunds_create', arguments: refund({ amount_cents: 2000 }) });
    assert.equal(code(r), 'IDEMPOTENCY_PAYLOAD_MISMATCH');
    assert.equal(srv.state.refunds.size, 1);
  });
  it('late AI retry after a human changed the order → STALE_INTENT', async () => {
    const c = await client('tok-clerk-t1');
    const r = await c.callTool({ name: 'refunds_create', arguments: refund({ idempotency_key: 'key-0000000000000002', expected_order_version: 1 }) });
    assert.equal(code(r), 'STALE_INTENT');
    assert.equal(srv.state.refunds.size, 1);
  });
  it('every write decision has an audit record with the §10.3 fields', async () => {
    const required = ['tool_name', 'caller_role', 'caller_id_hash', 'scope_id_hash', 'request_id', 'session_id', 'input_schema_valid',
      'authorization_result', 'side_effect_type', 'prompt_version', 'model_name', 'audit_log_id', 'latency_ms', 'error_code'];
    const c = await client('tok-clerk-t1');
    const before = srv.state.audit.length;
    await c.callTool({ name: 'refunds_create', arguments: refund({ idempotency_key: 'key-0000000000000003', expected_order_version: 2, amount_cents: 500 }),
      _meta: { 'app/session_id': 'conv-42', 'app/prompt_version': 'refund-agent@3', 'app/model_name': 'fixture-model' } });
    const rec = srv.state.audit.at(-1);
    assert.equal(srv.state.audit.length, before + 1);
    assert.ok(rec);
    for (const f of required) assert.ok(f in rec, `missing ${f}`);
    assert.equal(rec.authorization_result, 'allowed');
    assert.equal(rec.prompt_version, 'refund-agent@3');
    assert.notEqual(rec.caller_id_hash, 'alice'); // hashed, not raw
    assert.equal(srv.state.audit.filter((a) => a.error_code === 'IDEMPOTENCY_PAYLOAD_MISMATCH').length, 1);
  });
  it('audit store down → no side effect (audit before effect)', async () => {
    const c = await client('tok-clerk-t1');
    srv.state.faults.auditStoreDown = true;
    const n = srv.state.refunds.size;
    const r = await c.callTool({ name: 'refunds_create', arguments: refund({ idempotency_key: 'key-0000000000000004', expected_order_version: 3, amount_cents: 100 }) });
    srv.state.faults.auditStoreDown = false;
    assert.equal(code(r), 'AUDIT_UNAVAILABLE');
    assert.equal(srv.state.refunds.size, n);
  });
  it('§10.4 metrics recorded (calls by result, auth denials, audit writes)', () => {
    const keys = [...srv.state.metrics.keys()];
    assert.ok(keys.some((k) => k.startsWith('tool_calls_total') && k.includes('IDEMPOTENCY_PAYLOAD_MISMATCH')));
    assert.ok(keys.some((k) => k.startsWith('audit_writes_total')));
  });
});

describe('cancellation + failure injection (dimension 13)', () => {
  before(async () => { srv = await start(nextPort++, newState()); });
  after(async () => { await srv.close(); });
  it('client abort stops the long tool between batches', async () => {
    const c = await client('tok-clerk-t1');
    const ac = new AbortController();
    const call = c.callTool({ name: 'orders_export', arguments: { schema_version: '1.0', batches: 40 } }, { signal: ac.signal });
    setTimeout(() => ac.abort(), 180);
    await assert.rejects(call);
    await new Promise((r) => setTimeout(r, 200));
    assert.equal(srv.state.exportCancelled, true);
    assert.ok(srv.state.exportBatchesDone < 40, `ran ${srv.state.exportBatchesDone} batches`);
    assert.equal(c.getProtocolEra(), 'modern');
  });
  it('documented limit: a 2025-era client on stateless HTTP cannot cancel (handler runs to completion)', async () => {
    srv.state.exportCancelled = false; srv.state.exportBatchesDone = 0;
    const c = await client('tok-clerk-t1', 'legacy');
    const ac = new AbortController();
    const call = c.callTool({ name: 'orders_export', arguments: { schema_version: '1.0', batches: 10 } }, { signal: ac.signal });
    setTimeout(() => ac.abort(), 120);
    await assert.rejects(call);
    await new Promise((r) => setTimeout(r, 700));
    assert.equal(c.getProtocolEra(), 'legacy');
    assert.equal(srv.state.exportCancelled, false);
    assert.equal(srv.state.exportBatchesDone, 10);
  });
  it('upstream down → typed visible error, never fabricated data', async () => {
    const c = await client('tok-clerk-t1');
    srv.state.faults.upstreamDown = true;
    const r = await c.callTool({ name: 'inventory_check', arguments: { schema_version: '1.0', sku: 'SKU-1' } });
    srv.state.faults.upstreamDown = false;
    assert.equal(code(r), 'UPSTREAM_UNAVAILABLE');
    assert.equal(JSON.stringify(r).includes('in_stock'), false);
  });
});
