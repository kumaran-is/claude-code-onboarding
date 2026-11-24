## Tool Versioning and Breaking Changes

MCP tools have three types of breaking changes — each requires a different detection strategy.
Most teams only check for schema breaks. That catches roughly a third of actual failures.

| Break Type | What Changes | Agent Impact | Detection Method | Gate |
|------------|-------------|-------------|-----------------|------|
| **Schema break** | Field added/removed/renamed in input or output | Agent passes wrong params or fails to read output | Schema diff in CI/CD | Block deploy on incompatible changes |
| **Semantic break** | Schema unchanged, behavior different (e.g., fuzzy→exact match) | Agent makes correct call, gets wrong result | Replay harness with golden prompts | Fail if output semantics differ |
| **Language break** | Description or parameter name changed | Agent selects wrong tool or generates wrong arguments | Tool surface hash comparison | Require human review on hash change |

**Language break example** — the failure mode nobody expects:

> Changing a description from `"Search for users"` to `"Search for active users"` causes some
> agents to stop calling it for inactive user lookups. Same schema. Same behavior. The description
> change altered agent tool-selection behavior. Root cause takes 3 hours to find.

**Semantic break example:**

> `search_products({ query: "boots" })` returns fuzzy matches in v1, exact matches only in v2.
> Schema is identical. Every agent workflow that relied on fuzzy matching silently stops working.

### Explicit Tool Versioning

The MCP specification (revision 2026-07-28) defines no tool versioning. Choose one of three strategies:

**Option A — Version in `_meta`** (recommended for most servers):

```typescript
import { McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';

declare const server: McpServer;

server.registerTool(
  'orders_search',
  {
    title: 'Search Orders',
    description: 'Find orders by customer and status',
    inputSchema: z.object({ customer_id: z.string(), status: z.enum(['open', 'closed']).optional() }),
    annotations: { readOnlyHint: true, idempotentHint: true },
    // _meta is the spec's extension point; prefix custom keys with a domain you own.
    _meta: { 'com.example/tool-version': '2.0.0', 'com.example/deprecates': '1.0.0' },
  },
  async () => ({ content: [{ type: 'text', text: '[]' }] }),
);
```

Cleanest namespace. Do **not** put custom keys in `annotations`: `ToolAnnotations` is a closed type in SDK v2 and `tsc` rejects `annotations: { version: ... }`. Clients must read `_meta` to use the version.

**Option B — Version parameter in inputSchema** (best for backward compatibility):

```typescript
inputSchema: {
  query: z.string(),
  api_version: z.enum(["v1", "v2"]).default("v2").describe(
    "API version. v1: returns email inline. v2: email moved to separate endpoint."
  )
}
```

Single tool handles both versions. Keeps tool list clean. Increases handler complexity.

**Option C — Version in tool name** (`search_products_v2`):

Increases tool count and agent selection entropy — the agent must choose between versions.
Use only for external servers with diverse clients and long deprecation windows.

**Decision rule:**
- Internal server, controlled clients → Option A
- External server, need full backward compat → Option B
- External server, major behavioral change, long deprecation window → Option C

### Additive-Only Schema Evolution

Never remove or rename fields in tool schemas. Instead:

```typescript
// ❌ WRONG — removing a field breaks agents using it
inputSchema: {
  query: z.string(),
  // 'filters' removed — breaks existing agents
}

// ✅ CORRECT — mark as deprecated, keep for 2 release cycles
inputSchema: {
  query: z.string(),
  filters: z.record(z.string(), z.unknown()).optional().describe("DEPRECATED — use filter_v2 instead"),
  filter_v2: z.object({ ... }).optional(),
}
```

Safe vs breaking change classification:

| Change | Safe? |
|--------|-------|
| Add optional field | ✅ Safe |
| Add new response field | ✅ Safe |
| Remove field | ❌ Breaking |
| Change field type | ❌ Breaking |
| Make optional field required | ❌ Breaking |
| Change default value | ❌ Breaking (semantic break) |
| Change description wording | ⚠️ Language break — requires hash gate review |

### Deprecation Warning in Responses

When an agent uses a deprecated parameter, include a warning in the response:

```typescript
if (args.filters) {
  result.deprecation_warning = "Parameter 'filters' is deprecated and will be removed in v3.0. Use 'filter_v2' instead.";
}
```

### Versioned Response Envelope with Downgrade Path

For servers with multiple active versions, wrap responses in a versioned envelope:

```typescript
interface VersionedEnvelope<T> {
  _meta: {
    tool: string;
    version: string;                    // This response's version
    supported_versions: string[];        // All versions this server can serve
    downgrade_hint?: string;             // How to request an older format
    deprecation_warning?: {
      message: string;
      deadline: string;                  // ISO date when old version is removed
    };
  };
  data: T;
}
```

Example response:

```json
{
  "_meta": {
    "tool": "search_products",
    "version": "2.0.0",
    "supported_versions": ["1.0.0", "2.0.0"],
    "downgrade_hint": "Pass api_version='v1' for legacy format with email inline",
    "deprecation_warning": {
      "message": "v1 deprecated: email field moving to separate get_supplier_contact tool",
      "deadline": "2026-09-01"
    }
  },
  "data": { "products": [...], "total": 12 }
}
```

The `supported_versions` and `downgrade_hint` make the envelope actionable — clients can
programmatically adapt without human intervention.

### Tool Surface Hash Gate (CI/CD)

The tool surface hash catches all three break types in a single CI check. Compute a SHA256 hash
of the entire agent-visible surface (name + description + all parameter names, types, descriptions,
required flags). Block the deploy when it changes; require human review.

```typescript
// scripts/tool-surface-hash.ts — list tools through a real Client, in process (no port, no subprocess)
import { createHash } from 'node:crypto';
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { createMcpHandler } from '@modelcontextprotocol/server';
import { createServer } from '../src/server.js';

const handler = createMcpHandler(createServer);
const client = new Client({ name: 'surface-hash', version: '1.0.0' });
await client.connect(
  new StreamableHTTPClientTransport(new URL('http://surface.invalid/mcp'), {
    fetch: (input, init) => handler.fetch(new Request(input, init)),
  }),
);
const { tools } = await client.listTools();
const surface = tools
  .map(({ name, description, inputSchema, outputSchema, annotations }) => ({ name, description, inputSchema, outputSchema, annotations }))
  .sort((x, y) => x.name.localeCompare(y.name));
await client.close();
await handler.close();
process.stdout.write(`${createHash('sha256').update(JSON.stringify(surface)).digest('hex')}\n`);
```

```bash
# In CI: regenerate, then fail when it differs from the committed, human-reviewed baseline
npx tsx scripts/tool-surface-hash.ts > .tool-surface-hash
if ! git diff --exit-code -- .tool-surface-hash; then
  echo 'Tool surface changed: run the tool-selection eval, then commit the new hash after review' >&2
  exit 1
fi
```

`git diff` without `--exit-code` always exits 0, so a gate written that way never fails.

Commit `.tool-surface-hash` to the repository. The baseline is the last human-reviewed surface.

### Canary Rollouts with Instant Rollback

Never ship new tool versions to 100% of traffic immediately.

```typescript
// mcp/your-project-mcp/src/rollout.ts
interface RolloutConfig {
  [toolVersion: string]: {
    rollout_percentage: number;          // 0–100
    eligible_clients?: string[];          // Client ID prefixes; omit = all clients
    is_stable?: boolean;                  // Mark the current safe version
  };
}

const rolloutConfig: Record<string, RolloutConfig> = {
  search_products: {
    "2.1.0": { rollout_percentage: 5, eligible_clients: ["internal-"] },
    "2.0.0": { rollout_percentage: 95, is_stable: true }
  }
};

function resolveVersion(toolName: string, clientId: string): string {
  const config = rolloutConfig[toolName];
  if (!config) return "latest";

  // Check if client is eligible for canary
  for (const [version, settings] of Object.entries(config)) {
    if (settings.rollout_percentage === 100) continue;  // Skip stable
    const eligible = !settings.eligible_clients ||
      settings.eligible_clients.some(prefix => clientId.startsWith(prefix));
    if (eligible && Math.random() * 100 < settings.rollout_percentage) {
      return version;
    }
  }

  // Fall back to stable version
  return Object.entries(config).find(([, s]) => s.is_stable)?.[0] ?? "latest";
}
```

**Rollback procedure** — when canary metrics degrade:

```typescript
// Instant rollback: set canary percentage to 0
rolloutConfig.search_products["2.1.0"].rollout_percentage = 0;
logger.warn("Rollback executed", { tool: "search_products", version: "2.1.0", reason: "error_rate > 5%" });
// Alert on-call: page with rollback event + metrics snapshot
```

**Rollout stages (recommended):**

| Stage | Percentage | Eligible Clients | Hold Duration |
|-------|-----------|-----------------|--------------|
| Internal canary | 5% | `internal-*` only | 24 hours |
| Limited beta | 20% | All clients | 48 hours |
| Broad rollout | 50% | All clients | 24 hours |
| Full rollout | 100% | All clients | Stable |

Hold at each stage until all drift detection metrics stay green.

### Post-Deployment Monitoring Targets

After deploying a new tool version, verify these SLOs within 24 hours:

| Metric | Target | Alert Threshold | Break Type Detected |
|--------|--------|----------------|-------------------|
| Tool selection accuracy | > 90% (agent picks right tool) | < 85% → rollback | Language break |
| Schema validation error rate | < 0.5% | > 2% → rollback | Schema break |
| Tool call retry depth | < 1.5 avg retries | > 2.5 → investigate | Semantic break |
| Response parsing error rate | < 0.5% | > 2% → rollback | Schema break |
| Average token overhead per task | < 5,000 tokens | > 8,000 → investigate | — |
| Circuit breaker open rate | < 1% | > 3% → upstream issue | — |
| Multi-step task completion (≤3 calls) | > 80% | < 70% → tool design issue | — |
| Tool error rate | < 2% | > 5% → rollback | — |

**Alert rule**: A 5% error rate spike OR a 30% selection rate drop within 24 hours of a deploy
should page on-call immediately. Do not wait for the 24-hour SLO window when trend is clear.

These metrics are observable via the OTel metrics in `observability-patterns.md`.

### Pre-Deploy Versioning Checklist

Run before any PR that changes a tool's schema, description, or behavior:

```
□ Schema: No fields removed or renamed
□ Schema: New fields are optional with defaults
□ Schema: No type changes on existing fields
□ Behavior: Semantic behavior unchanged — OR version bumped
□ Language: Tool surface hash reviewed (git diff .tool-surface-hash)
□ Envelope: Response includes _meta.version and supported_versions
□ Rollout: Canary config updated (not shipping to 100% immediately)
□ Rollout: Rollback procedure documented and tested
□ Observability: Schema error alerting enabled for new version
□ Observability: Tool selection rate baseline recorded before deploy
```
