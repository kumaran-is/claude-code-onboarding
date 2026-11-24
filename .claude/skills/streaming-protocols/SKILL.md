---
name: streaming-protocols
description: "Use when designing or debugging streaming in AI systems — SSE, NDJSON, HTTP Streaming, WebSocket, MCP transport, or A2UI transport. Covers the three-layer mental model, bidirectionality, real-world wire formats (OpenAI, Anthropic, MCP), production pitfalls (proxy buffering, compression, reconnection), the server-side stream lifecycle (disconnect cancels the model call, one terminal frame, no action on partial output, WebSocket auth before accept), and the decision guide for which protocol to use when."
allowed-tools: Read, Grep, Glob, Bash, WebFetch
metadata:
  triggers: SSE, server-sent events, client disconnect, stream cancellation, terminal frame, NDJSON, HTTP streaming, WebSocket, streaming protocol, MCP transport, streamable HTTP, bidirectional streaming, traceparent, streaming AI, token streaming
  related-skills: a2ui-angular, mcp-builder, agentic-ai-dev, ai-chat, voice-ai-development
  domain: infrastructure
  role: reference
  scope: architecture
  output-format: guidance
last-reviewed: "2026-11-22"
---

# Streaming Protocols for AI Systems

> **OPTIONAL extension.** Streaming is not required for an AI feature: a one-shot JSON response is simpler and is the default. Load this skill only when you stream model output, push live updates, or proxy a realtime (voice) session. Lifecycle stage router: `ai-playbook/SKILL.md`.

## Iron Law

**Pick one option from each of the three layers (Transport / Framing / Message). The "which protocol?" question answers itself.**

Most streaming confusion comes from treating options at different layers as alternatives. They compose — they are not competitors.

---

## 1. The Three-Layer Mental Model

```
┌─────────────────────────────────────────────────────────┐
│  MESSAGE LAYER — what each message means                │
│  JSON-RPC · A2UI envelope · OpenAI delta · plain JSON   │
├─────────────────────────────────────────────────────────┤
│  FRAMING LAYER — how messages are delimited             │
│  SSE events · NDJSON lines · HTTP chunks · WS frames    │
├─────────────────────────────────────────────────────────┤
│  TRANSPORT LAYER — the connection itself                │
│  HTTP · HTTP Streaming · WebSocket · stdio              │
└─────────────────────────────────────────────────────────┘
```

```
Transport opens the pipe.
Framing chops the pipe into messages.
Message format gives each message meaning.
```

**The most common real-world stack:**

```
HTTP Streaming (transport)
  └── SSE (framing)
        └── JSON-RPC or provider-specific JSON (message)
```

**For tool/agent IPC:**

```
stdio (transport)
  └── newline-delimited JSON (framing)
        └── JSON-RPC 2.0 (message)
```

---

## 2. SSE vs HTTP Streaming — The Core Confusion

**SSE is not a competitor to HTTP Streaming. SSE is one *kind* of HTTP Streaming.**

```
HTTP Streaming  (the behavior: server sends response gradually)
    │
    ├── SSE                 ← text/event-stream, blank-line framed
    ├── NDJSON              ← one JSON object per line
    ├── Chunked HTML        ← progressive page rendering
    ├── Raw binary chunks   ← video/audio, file downloads
    └── Custom formats      ← gRPC-Web, protobuf streams
```

Asking "SSE vs HTTP Streaming" is like asking "JSON vs HTTP body" — JSON is *one of the things* you can put in a body.

**Why people conflate them:**

1. In browsers, `EventSource` is the only ergonomic way to consume HTTP streams. Everything else requires `fetch()` + `ReadableStream` + manual byte parsing.
2. ChatGPT, Claude, Perplexity all use SSE — so "streaming response" colloquially means "SSE response."
3. MCP's transport naming confused everyone: the old transport was "HTTP+SSE"; the new one is "Streamable HTTP" — these sound like alternatives when they're not.

**When to pick which framing:**

| Scenario | Best framing | Why |
|----------|-------------|-----|
| Browser receives live updates | **SSE** | Native `EventSource`, auto-reconnect, simple to parse |
| AI agent token streaming to a UI | **SSE** | Browser-friendly, typed event names for tool use |
| Server-to-server streaming | NDJSON | No event-name overhead, easy to log/replay |
| Batch processing pipelines | NDJSON | Line-addressable, replayable, strong tooling |
| stdio IPC (MCP local) | NDJSON | OS-pipe-friendly newline framing |
| Binary data (video, files) | Raw chunks | No text encoding overhead |
| gRPC internal ML platforms | gRPC frames | Strong types, multiplexing, codegen |

---

## 3. Bidirectionality — Half-Duplex vs Full-Duplex

| | HTTP/1.1 Streaming | HTTP/2 Streaming | WebSocket |
|--|-------------------|-----------------|-----------|
| Direction per stream | Half-duplex | Half-duplex within a stream | **Full-duplex** |
| Bidirectional in practice? | Only by opening 2+ requests | Yes, via separate streams | Yes, natively |
| Auto-reconnect? | Native `EventSource` GET only (`Last-Event-ID`); fetch-based streams: no | Per protocol | No — implement yourself |
| Works through corporate proxies? | Almost always | Almost always | Often blocked or buggy |
| Good for AI token streaming? | **Yes** (standard choice) | Yes | Overkill |
| Good for voice / collab editing? | No | Marginal | **Yes** |
| Server can initiate? | No (only respond) | Server push (limited) | Yes, anytime |

**The crisp distinction:**

```
HTTP Streaming = one-direction-at-a-time per request (walkie-talkie)
WebSocket      = both-directions-simultaneously on one connection (phone call)
```

**Why ChatGPT's "stop generating" button closes the connection:** once the POST is sent, the client is in receive-only mode. There's no upstream channel to send a "stop" message on. The only option is to drop the connection — so the SERVER must notice the disconnect and cancel the model call, or it keeps generating (and billing) tokens nobody reads. See §6a.

**Pick HTTP Streaming (SSE) when:**
- Data flow is dominantly server → client
- You need to traverse corporate proxies and CDNs reliably
- You want browser auto-reconnect (native `EventSource`, GET only); resumability still needs event ids plus a server-side buffer
- You're streaming LLM tokens, agent progress, A2UI updates

**Pick WebSocket when:**
- Genuinely simultaneous bidirectional flow (voice, multiplayer, collab editing)
- Frequent small messages in both directions
- Server initiates messages as often as the client does

**Practical reality for AI apps:** 95% of the time, SSE is the right choice. WebSocket earns its weight for voice and collaborative editing — not for token streaming.

---

## 4. MCP over Streamable HTTP (revision 2026-07-28)

One endpoint, one `POST` per JSON-RPC request; the server answers each with either a single JSON body or an SSE stream that carries that request's progress notifications and then its result. There is no protocol session, no long-lived `GET` stream and no server-initiated request:

```
CLIENT                                         MCP SERVER
  │── POST /mcp  tools/call  (id 1) ────────────►│  headers: MCP-Protocol-Version, Mcp-Method, Mcp-Name
  │◄── 200 text/event-stream ───────────────────│  stream for request 1 only
  │◄── data: {notifications/progress}           │
  │◄── data: {result, resultType:"input_required"}│  server needs a user answer (MRTR)
  │                                              │
  │── POST /mcp  tools/call  (id 2) ────────────►│  same call again + inputResponses
  │◄── 200 application/json {result} ───────────│
  │                                              │
  │── POST /mcp  subscriptions/listen ──────────►│  opt-in stream for list_changed / resource updates
  │◄── 200 text/event-stream (stays open) ──────│
```

| Concern | 2026-07-28 rule |
|---|---|
| Version | every request carries `_meta` `io.modelcontextprotocol/protocolVersion`; the `MCP-Protocol-Version` header must match it (mismatch → `400`, `-32020`); unsupported version → `400`, `-32022` with `data.supported` |
| State | no `Mcp-Session-Id`; any replica can serve any request. Cross-call state = explicit handles the server returns as tool results |
| Cancellation | close the request's SSE stream (stdio still uses `notifications/cancelled`). Servers must stop work and send nothing more |
| Broken stream | **no resumption**: `Last-Event-ID` replay was removed; the client re-issues the request with a new id. Make side-effecting tools idempotent |
| Server → client asks | only as an `input_required` result the client answers by retrying (sampling and roots are Deprecated) |
| Security | validate `Origin` and `Host` against allow-lists (`403`; Host blocks DNS rebinding), cap the body size (`413`), bind `127.0.0.1` for local servers, authenticate remote ones |
| Proxies | send `X-Accel-Buffering: no` and never compress the SSE response |

**2025-era servers (≤ 2025-11-25)** still use the older shape: `initialize` handshake, optional `Mcp-Session-Id` echoed on every request, a standalone `GET` SSE stream for server-initiated requests, and `Last-Event-ID` resumption. Treat these as backward-compatibility behaviour, not a design to copy. A client that must talk to both probes with `server/discover` and falls back to `initialize` when the reply is not a recognised 2026 error.

**SSE deprecation note:** the HTTP+SSE *MCP transport* (2024-11-05: separate `GET /sse` + `POST /messages`) is Deprecated since 2025-03-26, replaced by Streamable HTTP. SSE as a response format is alive and well: Streamable HTTP uses it, and so do LLM streaming, dashboards and browser-facing live updates.

---

## 5. Real-World Wire Formats

### OpenAI / Compatible APIs (SSE, bare JSON)

```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","choices":[{"delta":{"content":"The"},"index":0}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","choices":[{"delta":{"content":" answer"},"index":0}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","choices":[{"delta":{},"finish_reason":"stop","index":0}]}

data: [DONE]
```

- Bare JSON (not JSON-RPC) — request/response pairing is implicit in the HTTP exchange
- `[DONE]` sentinel is OpenAI's convention, not part of the SSE spec
- Client extracts `choices[0].delta.content` and appends to rendered message

### Anthropic (SSE, typed events)

```
event: message_start
data: {"type":"message_start","message":{"id":"msg_01...","role":"assistant"}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"The answer"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_stop
data: {"type":"message_stop"}
```

- `event:` field carries semantic type — clients dispatch on type rather than inspecting payload shape
- Makes tool use, thinking blocks, and multi-modal content cleaner to handle
- Mid-stream errors arrive as `event: error` with HTTP status still 200

### MCP (JSON-RPC over SSE or newline-delimited)

```
event: message
data: {"jsonrpc":"2.0","method":"notifications/progress","params":{"progressToken":"t1","progress":30}}

event: message
data: {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"done"}]}}
```

### A2UI over SSE

One A2UI message per default `message` event (no `event:` name, so `EventSource.onmessage` receives it), an
`id` of `<streamId>:<seq>` for resume, and a terminal `done` event. Canonical framing, resume and error codes:
`genui-contract/reference/runtime-lifecycle.md`.

```
id: 45d261f755a91c43:1
data: {"version":"v0.9","createSurface":{"surfaceId":"case_1","catalogId":"..."}}

id: 45d261f755a91c43:2
data: {"version":"v0.9","updateDataModel":{"surfaceId":"case_1","path":"/status","value":"Open"}}

event: done
data: {}
```

The frames above are the v0.9 wire form. A 1.0 stream carries `"version":"1.0"` and may create a surface with its components in one `createSurface`. The version is negotiated per client, never mixed in one stream.

### A2UI over AG-UI

AG-UI HTTP SSE (`POST`, `Accept: text/event-stream`) carries A2UI inside `ACTIVITY_SNAPSHOT` events with
`activityType: "a2ui-surface"`, `content.a2ui_operations` and `replace: true` (constants from `@ag-ui/a2ui-middleware`
0.0.16). Mapping, negotiation keys and the verified transport per platform:
`genui-contract/reference/ag-ui-transport.md`. Server lifecycle rules (disconnect cancels, one terminal frame):
`reference/server-stream-lifecycle.md`.

### A2UI over NDJSON (replay / eval / debugging)

```jsonl
{"version":"v0.9","createSurface":{"surfaceId":"case_1","catalogId":"..."}}
{"version":"v0.9","updateDataModel":{"surfaceId":"case_1","path":"/status","value":"Open"}}
{"version":"v0.9","updateComponents":{"surfaceId":"case_1","components":[...]}}
```

---

## 6. Production Pitfalls Checklist

### ❌ Proxy Buffering (Silent Stream Killer)
Nginx, CloudFront, and most CDNs buffer responses by default. Your "streaming" tokens arrive in one batch.

**Fix:**
```nginx
location /stream {
  proxy_buffering off;
  add_header X-Accel-Buffering no;
}
```
Also set `X-Accel-Buffering: no` as a response header from your app server.

### ❌ gzip / Brotli Breaks SSE
Compression middleware accumulates bytes before compressing — turns smooth token flow into chunky bursts.

**Fix:** Disable compression for `text/event-stream` responses. The bandwidth saving is not worth the latency cost. (Starlette 1.10's `GZipMiddleware` already excludes `text/event-stream` by default; CDNs, other compressors and older pinned versions may not — check yours.)

```ts
// Express example
app.use(compression({
  filter: (req, res) => {
    if (res.getHeader('Content-Type') === 'text/event-stream') return false;
    return compression.filter(req, res);
  },
}));
```

### ❌ SSE Connection Timeouts on Long Agent Runs
Long agent runs exceed default proxy timeouts (often 60s). Connection drops mid-stream.

**Fix:** Send periodic keepalive comments every ≤ 15 s, below the tightest proxy idle timeout (`sse-starlette` pings every 15 s by default):
```
: keepalive

```
(A colon-prefixed line is an SSE comment — ignored by clients, but prevents timeout.) Keepalives do not lift the platform's hard request timeout (Cloud Run: 300 s default, 3600 s max): give the stream its own budget below it and end with a terminal frame.

### ❌ Mobile Reconnection Without `Last-Event-ID`
iOS kills HTTP connections when the app backgrounds. Without `Last-Event-ID`, the stream restarts from scratch on reconnect.

**Fix:**
1. Include `id:` field on every SSE event
2. Buffer events server-side for ≥60 seconds after sending
3. On reconnect, client sends `Last-Event-ID` header; server replays from that point

Native `EventSource` already reconnects by itself (WHATWG HTML spec): after a network error AND after the server ends the body normally, it waits the reconnection time (server sets it with a `retry:` field) and re-sends `Last-Event-ID`. It does not reconnect after `close()`, a non-200 status or a wrong `Content-Type`; a server stops it with `204`.

```ts
// ❌ WRONG — the browser is already reconnecting; this opens a SECOND stream
es.onerror = () => setTimeout(() => reconnect(), retryDelay);

// ✅ RIGHT — let the browser retry; close on the terminal frame so a finished
// stream is not re-requested (which would re-run generation and bill twice)
const es = new EventSource(`/stream/${generationId}`);
es.addEventListener('done', () => es.close());
es.addEventListener('error', () => {
  if (es.readyState === EventSource.CLOSED) showFailed();   // fatal: no retry
  else showReconnecting();                                   // transient: browser retries
});
```
(Server tunes the delay with `retry: 5000`.)

4. `EventSource` cannot POST or set headers. A `fetch()` + `ReadableStream` chat stream gets no automatic reconnect and no `Last-Event-ID`: resuming needs a server-side event buffer keyed by generation id; otherwise a reconnect re-runs generation. Prefer "fetch the final answer by id" after a drop.
5. Surface "reconnecting..." state to the user — silent staleness is worse than a visible indicator
6. For long agent runs (>10 min backgrounded): provide a polling fallback that returns current state

### ❌ Missing `traceparent` Propagation
A single user action may generate 30+ network calls. Without a correlation ID, cross-service debugging is impossible.

**Fix:** Generate `traceparent` (W3C Trace Context) at the edge; forward it on every outbound call.

```
User action
  └─► Backend generates traceparent: 00-{trace_id}-{span_id}-01
        ├─► POST to LLM API — Header: traceparent
        ├─► POST to MCP server — traceparent in the request's params._meta (MCP reserves traceparent/tracestate/baggage there)
        └─► SSE response to client — echo traceparent back
```

Every modern observability tool (Langfuse, Datadog, Honeycomb, Grafana Tempo) understands `traceparent`. Include it in NDJSON logs so you can join logs across services after the fact.

### ❌ Conflating JSON-RPC `id` and SSE `id`
They are unrelated and live at different layers.

| Field | Layer | Purpose |
|-------|-------|---------|
| JSON-RPC `id` | Message | Correlates request to response within a JSON-RPC session |
| SSE `id` | Framing | Enables reconnection via `Last-Event-ID` header (generic SSE; MCP 2026-07-28 removed resumption) |

### ❌ Treating Streamable HTTP and SSE as Competitors
Streamable HTTP (MCP) is a *transport pattern*. SSE is *one of the response formats* Streamable HTTP can return. They compose.

### ❌ WebSocket "Because It's Realtime"
If data flow is server→client only (which most LLM streaming is), WebSocket adds operational complexity without benefit. SSE is simpler, proxy-friendly, and auto-reconnecting. Reach for WebSocket only when you genuinely need bidirectional realtime.

---

## 6a. Server-Side Stream Lifecycle (the agent / model SSE contract)

This is the canonical stream contract for agent and model endpoints in this toolkit; framework templates (LangGraph, ADK) link here. Executed code, test evidence and the WebSocket admission pattern: `reference/server-stream-lifecycle.md`.

| ❌ Wrong | ✅ Right |
|---------|---------|
| Stop button closes the socket; server keeps generating | Client disconnect cancels the upstream model call in `finally` on every exit path |
| Upstream call in a detached task / queue pump | Upstream owned by the stream (executed: a detached pump kept producing tokens after disconnect) |
| `except BaseException` / swallowed `CancelledError` | Catch `Exception` at the stream boundary; cancellation propagates |
| `data: {text}` raw, `data: {e}` on error | JSON-encode every `data:`; typed events `content` / `done` / `error` |
| `[ERROR]` then `[DONE]`, or no terminal frame | Exactly ONE terminal frame: `done` OR `error` with a fixed code; never `str(exc)` |
| Auth / safety / kill-switch inside the generator | Decide and log in the route before returning the response (the generator may never run) |
| Persist or execute tool calls from partial deltas | Act only on the final, schema-validated message; a stopped answer is stored `incomplete`, never acted on |
| `await db.save(...)` in `finally` during cancellation | Shield it (`anyio.CancelScope(shield=True)`); executed: unshielded write was lost |
| No budget; platform timeout cuts the stream | Stream budget below the platform request timeout, then a terminal frame |
| WebSocket `accept()` then authenticate | Subprotocol + auth before `accept()`; one stream per actor; frame/byte/time/idle caps; bounded queue → `BACKPRESSURE` |

A BFF / proxy hop maps ANY upstream connect, read or non-200 failure to one terminal `error` frame, derives identity server-side and propagates the request id.

---

## 7. Decision Guide

| Your need | Transport | Framing | Message |
|-----------|-----------|---------|---------|
| Chat UI with token streaming | HTTP Streaming | SSE | Provider JSON (OpenAI/Anthropic) |
| Local AI app calling tools | stdio | newline-delimited | JSON-RPC (MCP) |
| Remote AI app calling tools | HTTP Streaming | JSON or SSE | JSON-RPC (MCP) |
| Agent pushing UI updates (A2UI) | HTTP Streaming | SSE | A2UI envelope |
| Recording agent runs (eval/replay) | File / HTTP POST | NDJSON | App-specific trace |
| Bulk LLM inference | HTTP | NDJSON | Provider JSON (Batch API) |
| Voice / collaborative editing | WebSocket | WS frames | App-specific |
| High-perf server-to-server AI | HTTP/2 | gRPC frames | Protobuf |
| Simple one-shot answer | HTTP | — | Plain JSON |

---

## 8. NDJSON's Real-World Niche

NDJSON rarely appears in the live request path (SSE wins there). It dominates in three places:

1. **stdio IPC** — MCP local servers, language servers, CLI tools. Newline framing is OS-pipe-friendly.
2. **Batch / bulk APIs** — OpenAI Batch API, Anthropic Batch API return NDJSON. Common Crawl, eval traces, log shipping (Vector, Fluent Bit) all favor NDJSON.
3. **Replay and eval** — Recording an agent run as NDJSON gives a perfect, line-addressable trace. Langfuse, Braintrust, W&B Weave ingest these directly.

```
SSE        → live, server→client, browser-facing
NDJSON     → batch, logs, replay, stdio, server-to-server
WebSocket  → genuinely bidirectional realtime (voice, collab editing)
Plain JSON → one-shot response, no streaming needed
```

---

## Cheat Sheet

**Rules that catch most bugs:**

1. Don't compress SSE responses — it buffers your stream into chunky bursts.
2. MCP 2026-07-28 has no sessions or stream resumption: keep `MCP-Protocol-Version` equal to the `_meta` version, and re-issue a request whose stream broke (idempotent tools make that safe).
3. Propagate `traceparent` across every layer, or you'll never debug a multi-hop agent failure.
4. Client disconnect cancels the model call; every stream ends with exactly one `done` or `error` frame (§6a).
5. Never act on partial output; never open a second stream from `onerror`.

**The four real-world stacks:**

| Stack | Transport | Framing | Message |
|-------|-----------|---------|---------|
| Chat token streaming | HTTP Streaming | SSE | Provider JSON |
| MCP (local) | stdio | newline-delimited | JSON-RPC |
| MCP (remote) | HTTP Streaming | JSON or SSE | JSON-RPC |
| Generative UI (A2UI) | HTTP Streaming | SSE | A2UI envelope |
