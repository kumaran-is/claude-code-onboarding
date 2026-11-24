---
name: mcp-builder
description: Use when building, testing, or designing MCP (Model Context Protocol) servers to
  integrate external APIs and services. Covers tool design, schema validation, error handling,
  security, resilience patterns, and production evaluations for Python (MCP SDK v2 `MCPServer`,
  formerly FastMCP) and Node/TypeScript (MCP SDK v2) on protocol revision 2026-07-28 over stdio
  or Streamable HTTP.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch, WebSearch
metadata:
  triggers: MCP server, Model Context Protocol, MCP integration, FastMCP, MCP tool, MCP resource, build MCP
  related-skills: agentic-ai-dev, python-dev
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-23"
---

## Iron Law

Never publish an MCP server without testing all tool schemas against the MCP spec; always validate tool descriptions are >= 10 words and parameters are fully typed.

# MCP Server Development Guide

Create MCP servers that enable LLMs to interact with external services through well-designed tools.

## High-Level Workflow

### Phase 1: Research and Plan

- Spec: current revision **2026-07-28** — `https://modelcontextprotocol.io/specification/2026-07-28` (changelog: `.../2026-07-28/changelog`; append `.md` to any page for markdown)
- TypeScript SDK v2 docs: `https://ts.sdk.modelcontextprotocol.io/v2/` (`llms.txt` available) — packages `@modelcontextprotocol/server` / `client` 2.x; `@modelcontextprotocol/sdk` 1.x is legacy
- Python SDK v2 docs: `https://py.sdk.modelcontextprotocol.io/` — `mcp` 2.x, `from mcp.server import MCPServer`
- Load design principles, agent patterns, and error taxonomy from reference files (see table below)

### Protocol facts that change designs (2026-07-28)

| Topic | Current rule |
|---|---|
| Transports | stdio and Streamable HTTP only. HTTP+SSE (2024-11-05) is Deprecated: migration only |
| Handshake / sessions | No `initialize`, no `Mcp-Session-Id`: every request carries version + capabilities in `_meta`; servers implement `server/discover`. Cross-call state = explicit, authorized, expiring handles in tool arguments |
| Versions | Mismatch → HTTP 400 + `-32022` with `data.supported`. SDKs serve 2025-era clients too; decide and document which eras you accept |
| Asking the user mid-call | Return `input_required` (Multi Round-Trip Requests) and handle decline; no server-pushed `elicitation/create` |
| Deprecated | Sampling, Roots, protocol Logging (SEP-2577), HTTP+SSE, Dynamic Client Registration |
| Errors | Tool failures → `isError: true` result the model reads; malformed requests / unknown resources → JSON-RPC error (resource not found is `-32602`) |
| Annotations | Hints for the host UI, never security |
| Cancellation | stdio: `notifications/cancelled`; Streamable HTTP: closing the request's stream. Check the abort signal after every await |

### Phase 2: Implement

- Set up project structure using language-specific reference files (see table below)
- Create shared utilities: API client, error handling, response formatting, pagination
- For each tool: define input schema (Zod/Pydantic), output schema, description, annotations, and async implementation
- **Recommended stack**: TypeScript SDK v2 (`serveStdio` locally, `createMcpHandler` behind Host/Origin validation and auth remotely) or Python SDK v2 `MCPServer`

### Phase 3: Review and Test

- Review for: no duplication, consistent error handling, full type coverage, clear tool descriptions
- TypeScript: `tsc --noEmit` (strict), tests through a real `Client` in both eras, then `npx @modelcontextprotocol/inspector@2.16.0 --cli ...`
- Python: `uv run pytest` driving the server through `mcp.Client` (in memory + stdio), then `uv run mcp dev server.py`
- Every gate needs a negative control: break the handler and watch the test fail

### Phase 4: Create Evaluations

- Create 10 complex, realistic evaluation questions requiring multiple tool calls
- Each question must be: independent, read-only, complex, realistic, verifiable, stable
- Output as XML with `<evaluation>` root containing `<qa_pair>` elements

## Tool Implementation Checklist

For each tool, define:
- **Input schema** — Zod (TypeScript) or Pydantic (Python) with constraints and descriptions
- **Output schema** — Use `outputSchema` and `structuredContent` where possible
- **Description** — Concise summary, parameter docs, return type
- **Annotations** — `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`
- **Implementation** — Async/await, proper error handling, pagination support
- **Agent directive** — Include `next_actions` and `suggestion` in every response
- **Error taxonomy** — Use `MCPErrorCode` enum with recovery actions

### Adding a tool to an existing server

1. Keep the tool a thin adapter: validate input, call the existing service or client, map the result and errors. No business rule lives only in the tool handler; if the logic is new, it goes into the service with its own unit tests.
2. Classify it first (read-only, write, destructive, egress) and set the annotations to match; a write needs an idempotency key, a destructive tool needs the confirmation path (`reference/security-middleware-attacks.md` §1).
3. Authorize in the server from the caller's verified identity and scope, never from a model-supplied id.
4. Contract parity (one case per tool, `scripts/contract-test/contract.test.ts` is the model): add the name to the exact tool-set assertion ("no surprise tools"), plus at least one allowed call, one denied call (wrong role or scope) and one invalid-input call asserting the error code. A tool with no contract case, or a case with no tool, is a FAIL in review.
5. Run `/verify full` (the Node block's MCP gate lists tools and compiles every schema) and the contract suite; quote both exit codes.

## Reference Files

| Resource | When to Load |
|----------|-------------|
| [MCP Design Principles](reference/mcp-design-principles.md) | Phase 1 — intent-first design, tool count limits, naming, anti-patterns |
| [MCP Design Server Patterns](reference/mcp-design-server-patterns.md) | Phase 1/2 — naming, response formats, pagination, transport, 3-layer architecture |
| [MCP Design Context Efficiency](reference/mcp-design-context-efficiency.md) | Phase 2 — tool description budget (180-token template), context efficiency, filesystem discovery |
| [MCP Quality Standards](reference/mcp-quality-standards.md) | Phase 1 — security, annotations, testing, audit logging, MCP primitives |
| [MCP Quality Compliance](reference/mcp-quality-compliance.md) | Phase 2 — SOC2/GDPR/PCI compliance flags, canonical scorer delegation |
| [MCP Quality Versioning](reference/mcp-quality-versioning.md) | Phase 2 — tool versioning, breaking changes, canary rollouts |
| [Agent Design Patterns — Core](reference/agent-design-patterns.md) | Phase 1 — patterns 1-5: directive, confidence, error, disclosure, linking |
| [Agent Design Patterns — Advanced](reference/agent-design-patterns-advanced.md) | Phase 2 — patterns 6-10: idempotency, context carryover, circuit breaker, audit trail |
| [Agent Design Patterns — Domain](reference/agent-design-patterns-domain.md) | Phase 2 — domain presets (payment, healthcare, e-commerce), tool consolidation |
| [Error Taxonomy](reference/error-taxonomy.md) | Phase 1 — error codes, recovery hints, no-fake-empty-data |
| [Branded Types & Audit](reference/error-branded-types-audit.md) | Phase 2 — type-safe IDs, Zod integration, audit logging |
| [TypeScript Setup](reference/node-mcp-setup.md) | Phase 2 — project structure, package config, build; registering a server in Claude Code (`claude mcp add`, `.mcp.json`) |
| [Scaffold templates — core](assets/scaffold-templates-core.md), [HTTP + ops](assets/scaffold-templates-http-ops.md) | New TypeScript server: `/scaffold-mcp-server` writes these verified templates (config, tool registry, stdio, tests, CI; Streamable HTTP on Fastify, bearer auth, Docker, OpenTelemetry) |
| [TypeScript Patterns](reference/node-mcp-patterns.md) | Phase 2 — tool naming, Zod schemas, tool structure |
| [TypeScript Patterns Advanced](reference/node-mcp-patterns-advanced.md) | Phase 2 — response formats, pagination, error handling, utilities |
| [TypeScript Advanced](reference/node-mcp-advanced.md) | Phase 2 — complete example, resources, transport |
| [Python Setup](reference/python-mcp-setup.md) | Phase 2 — Python SDK, tool structure, Pydantic |
| [Python Patterns](reference/python-mcp-patterns.md) | Phase 2 — pagination, errors, complete example |
| [Python Advanced](reference/python-mcp-advanced.md) | Phase 2 — context, resources, lifespan, quality |
| [Resilience Core](reference/resilience-core.md) | Phase 2 — error classes, timeout budgets, bulkheads, retries only for idempotent calls, opossum circuit breaker (tested) |
| [Resilience Caching & Pool](reference/resilience-retry-cache.md) | Phase 2 — rate limiter, retry, LRU caching |
| [Resilience Production](reference/resilience-production.md) | Phase 2 — connection pool, composing patterns, loop detection |
| [Security Core](reference/security-core.md) | Phase 2 — OAuth resource server: token verifier, Protected Resource Metadata, bearer gate, Host/Origin guards, per-tool scopes, tenant isolation from the verified token (tested) |
| [Security Middleware & Attacks](reference/security-middleware-attacks.md) | Phase 2 — tool side-effect classes, human approval, idempotency/timeouts, SSRF guard, untrusted tool output, per-principal rate limits (tested) |
| [Security PII & Compliance](reference/security-pii-compliance.md) | Phase 2 — secrets and no token passthrough, secure errors, redacted audit logs, PII tokenization, CI gates, security checklist |
| [Observability Tracing](reference/observability-tracing.md) | Phase 2 — request and tool spans, semantic conventions, trace propagation via `params._meta`, sampling, what never to record (tested) |
| [Observability Metrics](reference/observability-metrics.md) | Phase 2 — metrics collection, sampling strategies |
| [Observability Monitoring](reference/observability-monitoring.md) | Phase 2 — integration example, post-deployment health targets, alert tiers, cost reduction |
| [Production Runtime — Shutdown & Health](reference/production-runtime-shutdown-health.md) | Phase 2 — readiness vs liveness, in-flight drain, signal handling and shutdown budgets (tested) |
| [Production Runtime — Multi-Tenant](reference/production-runtime-multi-tenant.md) | Phase 2 — principal from the verified token, AsyncLocalStorage `run()`, atomic quotas, tenant-scoped audit |
| [Production Infrastructure Docker](reference/production-deployment-docker.md) | Phase 2 — Docker multi-stage build, docker-compose, Kubernetes manifests |
| [Production Infrastructure Structure](reference/production-deployment-structure.md) | Phase 2 — 3-layer folder structure, layer responsibilities |
| [Evaluation Criteria](reference/evaluation-criteria.md) | Phase 4 — question/answer design |
| [Evaluation Running](reference/evaluation-running.md) | Phase 4 — CLI, setup, troubleshooting |

## Common Mistakes

- **Scoring/ranking logic in MCP layer** — MCP tools are API entry points only. All business logic (scoring, filtering, matching) belongs in an upstream service. See [reference/mcp-quality-compliance.md](reference/mcp-quality-compliance.md).
- **Exceeding 25 tools** — Agent decision accuracy degrades sharply past 25 tools. Consolidate by user intent, not by API endpoint. See [reference/mcp-design-principles.md](reference/mcp-design-principles.md).
- **Missing `next_actions` in responses** — Every tool response must include `next_actions` (machine-readable) and `suggestion` (human-readable) or agents stall. No exceptions.
- **Returning empty list/null on error** — Never return `[]` or `null` as a silent fallback. Return a structured `MCPErrorCode` error so the agent knows what failed and how to recover.
- **Tool descriptions written for developers** — "Executes POST /api/v1/orders" tells an LLM nothing. Write for the agent: "USE WHEN: Finding a customer's recent orders. EXAMPLES: ..."
- **v1-era APIs in new code** — `server.tool()`, `SSEServerTransport`, `McpError`, `mcp.server.fastmcp`, protocol sessions as state. See the setup files for the v2 equivalents.
- **Returning `"Error: ..."` as a normal result** — without `isError: true` (TS) or `raise ToolError` (Python) the model treats the failure as success.

## Error Handling

> For the full error taxonomy and circuit breaker patterns, Read [reference/error-taxonomy.md](reference/error-taxonomy.md)

**Server startup failures**: Validate all required environment variables at startup. Fail fast with a clear error message — never silently fall back to defaults.

**Tool execution errors**: Return structured MCP error responses with error codes. Never let unhandled exceptions crash the server.

```typescript
import { McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';
import { pino } from 'pino';

const logger = pino({}, pino.destination(2)); // stderr: stdout is the protocol on stdio
declare const ordersClient: { search(customerId: string, signal: AbortSignal): Promise<{ id: string }[]> };

export function registerOrdersSearch(server: McpServer): void {
  server.registerTool(
    'orders_search',
    {
      description: "Find a customer's recent orders by customer id. Use before orders_get for details.",
      inputSchema: z.object({ customer_id: z.string().min(1).max(64) }),
      annotations: { readOnlyHint: true },
    },
    async ({ customer_id }, ctx) => {
      try {
        const orders = await ordersClient.search(customer_id, ctx.mcpReq.signal);
        const output = {
          data: orders,
          next_actions: ['orders_get'],
          suggestion: `Found ${orders.length} orders. Call orders_get for one order's details.`,
        };
        return { content: [{ type: 'text', text: JSON.stringify(output) }], structuredContent: output };
      } catch (error: unknown) {
        logger.error({ tool: 'orders_search', err: error }, 'orders search failed');
        return {
          isError: true,
          content: [{ type: 'text', text: JSON.stringify({
            code: 'SERVICE_UNAVAILABLE',
            message: 'The orders service did not answer. Retry once in a few seconds.',
            retry_after_ms: 5000,
            recovery_actions: ['retry'],
          }) }],
        };
      }
    },
  );
}
```

## Verify

Before publishing any MCP server:

- [ ] `npx tsc --noEmit` exits 0 (TypeScript, strict) or `uv run pytest` exits 0 with the server driven through `mcp.Client` (Python)
- [ ] `npx @modelcontextprotocol/inspector@2.16.0 --cli <entrypoint> --method tools/list` — all tools listed with correct schemas; `--method tools/call` with a bad argument exits non-zero
- [ ] HTTP servers: Host/Origin validation in front of the handler; `npx @modelcontextprotocol/conformance@0.1.16 server --url <url> --scenario dns-rebinding-protection` passes
- [ ] All tool descriptions are ≥ 10 words
- [ ] All input parameters are fully typed (no `any` in TypeScript, no untyped `dict` in Python)
- [ ] Every tool response includes `next_actions` and `suggestion` fields
- [ ] `npm test` (or `uv run pytest`) exits 0 with coverage thresholds met
- [ ] No unhandled exceptions — all errors return structured `MCPErrorCode` responses
- [ ] Security checklist in [reference/security-pii-compliance.md §6](reference/security-pii-compliance.md#6-checklist) reviewed
