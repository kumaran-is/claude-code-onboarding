## Server Naming Conventions

Follow these standardized naming patterns:

**Python**: Use format `{service}_mcp` (lowercase with underscores)
- Examples: `slack_mcp`, `github_mcp`, `jira_mcp`

**Node/TypeScript**: Use format `{service}-mcp-server` (lowercase with hyphens)
- Examples: `slack-mcp-server`, `github-mcp-server`, `jira-mcp-server`

The name should be general, descriptive of the service being integrated, easy to infer from the task description, and without version numbers.

---

## Tool Naming and Design

### Tool Naming

1. **Use snake_case**: `search_users`, `create_project`, `get_channel_info`
2. **Include service prefix**: Anticipate that your MCP server may be used alongside other MCP servers
   - Use `slack_send_message` instead of just `send_message`
   - Use `github_create_issue` instead of just `create_issue`
3. **Use precise verb prefixes** — naming accuracy directly affects tool selection accuracy:
   - `fetch_*` — get by identifier: `fetch_order(order_id)`, `fetch_user(user_id)`
   - `lookup_*` — get by attribute: `lookup_customer_by_email(email)`, `lookup_order_by_tracking(code)`
   - `search_*` — query / multi-result: `search_vendors(query, filters)`, `search_orders(date_range)`
   - `create_*` — new resource: never `add_*` or `new_*`
   - `cancel_*` / `submit_*` / `send_*` — action verbs for workflow operations
4. **Avoid generic names**: `process_data()`, `handle_request()`, `get_*` for everything — agents distinguish tools by verb precision

### Tool Design

- Tool descriptions must narrowly and unambiguously describe functionality
- Descriptions must precisely match actual functionality
- Provide tool annotations (readOnlyHint, destructiveHint, idempotentHint, openWorldHint)
- Keep tool operations focused and atomic

### Intent-Based Tool Consolidation

Consolidate CRUD operations into intent-based tools to reduce agent cognitive load:

```typescript
// WRONG: 6 separate tools (decision paralysis for agents)
tools: ["createUser", "readUser", "updateUser", "deleteUser", "getUserById", "searchUsers"]

// RIGHT: 2 intent-based tools (clear purpose)
tools: ["manageUser", "searchUsers"]

// manageUser tool definition
{
  name: "manageUser",
  description: "Unified user management (create/read/update/delete)",
  inputSchema: z.object({
    action: z.enum(["create", "read", "update", "delete"]),
    userId: z.string().optional(),
    data: z.record(z.string(), z.unknown()).optional(),
  }),
}
```

### escalate_to_human Tool

MCP servers SHOULD include an `escalate_to_human` tool for high-risk domains:

**Required for:**
- Life-safety decisions (healthcare, autonomous systems)
- Fraud detection and account security
- Financial operations >$1,000 (or domain-specific threshold)
- Legal/compliance decisions

**Not required for:**
- Read-only or public-data servers (weather, documentation, search)
- Low-risk CRUD operations with no financial or safety impact
- Development/testing tools

```typescript
server.registerTool(
  "escalate_to_human",
  {
    title: "Escalate to Human",
    description: "Escalate to human operator for review. MUST be used for life-safety, fraud, or high-value decisions.",
    inputSchema: {
      reason: z.string().describe("Why human review is needed"),
      severity: z.enum(["low", "medium", "high", "critical"]),
      context: z.record(z.string(), z.unknown()).describe("Relevant context for the human reviewer"),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false }
  },
  async ({ reason, severity, context }) => {
    // Log escalation and notify human operator
    return {
      content: [{ type: "text", text: JSON.stringify({
        success: true,
        data: { escalation_id: generateId(), status: "pending_review" },
        next_actions: ["check_escalation_status"],
        suggestion: "Escalation submitted. Wait for human review before proceeding.",
      })}]
    };
  }
);
```

---

## Response Formats

All tools that return data should support multiple formats:

### JSON Format (`response_format="json"`)
- Machine-readable structured data
- Include all available fields and metadata
- Consistent field names and types
- Use for programmatic processing

### Markdown Format (`response_format="markdown"`, typically default)
- Human-readable formatted text
- Use headers, lists, and formatting for clarity
- Convert timestamps to human-readable format
- Show display names with IDs in parentheses
- Omit verbose metadata

---

## Pagination

For tools that list resources:

- **Always respect the `limit` parameter**
- **Implement pagination**: Use `offset` or cursor-based pagination
- **Return pagination metadata**: Include `has_more`, `next_offset`/`next_cursor`, `total_count`
- **Never load all results into memory**: Especially important for large datasets
- **Default to reasonable limits**: 20-50 items is typical

Example pagination response:
```json
{
  "total": 150,
  "count": 20,
  "offset": 0,
  "items": [...],
  "has_more": true,
  "next_offset": 20
}
```

---

## Transport Options

### Streamable HTTP

**Best for**: Remote servers, web services, multi-client scenarios

**Characteristics**:
- Bidirectional communication over HTTP
- Supports multiple simultaneous clients
- Can be deployed as a web service
- Enables server-to-client notifications

**Use when**:
- Serving multiple clients simultaneously
- Deploying as a cloud service
- Integration with web applications

### stdio

**Best for**: Local integrations, command-line tools

**Characteristics**:
- Standard input/output stream communication
- Simple setup, no network configuration needed
- Runs as a subprocess of the client

**Use when**:
- Building tools for local development environments
- Integrating with desktop applications
- Single-user, single-session scenarios

**Note**: stdio servers should NOT log to stdout (use stderr for logging)

### Transport Selection

| Criterion | stdio | Streamable HTTP |
|-----------|-------|-----------------|
| **Deployment** | Local | Remote |
| **Clients** | Single | Multiple |
| **Complexity** | Low | Medium |
| **Real-time** | No | Yes |

The 2024-11-05 HTTP+SSE transport (separate `/sse` + `/messages` endpoints) is Deprecated; never pick it for new work.

### Dual Transport Pattern (Production)

One `createServer()` factory, two thin entry points (TypeScript SDK v2; full code in [node-mcp-setup.md](node-mcp-setup.md)):

```typescript
// src/stdio.ts — local
import { serveStdio } from '@modelcontextprotocol/server/stdio';
import { createServer } from './server.js';

serveStdio(createServer);
```

```typescript
// src/http.ts — remote: the handler calls the factory per request; put Host/Origin checks and auth in front of it
import { createMcpHandler } from '@modelcontextprotocol/server';
import { createServer } from './server.js';

export const mcpHandler = createMcpHandler(createServer);
```

**Critical constraint:** Business logic (tools, resources, prompts) MUST NOT know which transport is active. Transport selection is infrastructure configuration — not business logic. Mixing them means you can't switch transports without rewriting tool handlers.

**stdio lifecycle warning:** The server process dies when the client disconnects. All in-memory state is lost. Design tool handlers to be stateless or use an external store (Redis, DB) for persistence.

**No protocol sessions (2026-07-28):** Streamable HTTP has no `Mcp-Session-Id` in the current revision; each request carries its own version and capabilities, so any replica can serve it. Keep state that must survive between calls in an external store behind an explicit handle the tool returns (owner-checked, expiring) — see [node-mcp-patterns.md](node-mcp-patterns.md). Sessionful serving with idle-timeout cleanup exists only for 2025-era clients ([node-mcp-advanced.md](node-mcp-advanced.md#legacy-sessions-2025-era-only)).

---

## Three-Layer Architecture (Production Standard)

Single-file MCP servers (tutorial style) fail in production because:
- You can't switch transports without rewriting tools
- External API schema changes blast every tool handler
- Business logic can't be unit tested independently
- 3 AM debugging is slow when everything is entangled

**The fix:** Separate into 3 layers with strict one-way dependencies:

```
┌─────────────────────────────────┐
│  Layer 3: Transport             │  stdio / Streamable HTTP
│  (server.ts)                    │  ← Changes when deployment changes
├─────────────────────────────────┤
│  Layer 2: Protocol              │  Tool registration, Zod validation,
│  (tools/*.ts)                   │  agent-directive formatting, error codes
│                                 │  ← Changes when MCP patterns change
├─────────────────────────────────┤
│  Layer 1: Business Logic        │  API clients, scoring, data transform
│  (services/*.ts)                │  ← Changes when domain logic changes
└─────────────────────────────────┘
```

**Dependency rule:** Layer 3 imports Layer 2. Layer 2 imports Layer 1. Layer 1 imports nothing from Layer 2 or 3.

**Testing implication:** Layer 1 (business logic) is pure unit-testable — no MCP SDK, no transport in scope. Layer 2 (tools) tests mock Layer 1. Layer 3 (server.ts) is excluded from coverage — it's glue code.

**Anti-pattern: returning mock/empty data on API failure.** If the upstream API is down and you return `[]` or fake data, the LLM learns to expect data even when reality has none. For life-safety or decision-making tools, this is dangerous. Always return a structured error (see error-taxonomy.md).

---
