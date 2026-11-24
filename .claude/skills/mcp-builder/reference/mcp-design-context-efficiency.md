## Tool Description Budget (180-Token Template)

Every tool description MUST fit within ~180 tokens and follow this structure:

```
USE WHEN: [One sentence describing the exact scenario that triggers this tool]

EXAMPLES:
- "[concrete example 1]"
- "[concrete example 2]"

NEXT STEPS: After calling this tool, the agent should call [tool_name] to [reason].

RETURNS: [Key fields in the response and what they mean]
```

**Why 180 tokens:** LLMs use tool descriptions to select which tool to call. Descriptions over ~200 tokens get truncated or ignored in context-constrained agents. Under ~50 tokens, agents lack enough context for accurate selection.

**Example — well-formed description:**

```typescript
server.registerTool('catalog_search_products', {
  title: 'Search Products',
  description: `USE WHEN: Finding products in the catalog by keyword, category, price or availability.

EXAMPLES:
- "Find waterproof hiking boots under $150 that ship this week"
- "Search wireless headphones with rating > 4.0 in stock"

NEXT STEPS: After getting results, call catalog_get_product to fetch the full product record, or orders_create_quote to price a basket.

RETURNS: products[] with id, name, price, rating, in_stock; plus next_actions and suggestion.`,
  inputSchema: { ... }
});
```

**Anti-pattern:** "Executes a semantic search against the product ranking engine using the provided query string and filters." — This is developer documentation, not agent guidance. It tells the LLM nothing about WHEN to use this tool.

---

## Context Efficiency Architecture

### The Token Ceiling Problem

Traditional MCP has an architectural ceiling: every intermediate result from a tool call enters the LLM's context window. Three sequential tool calls processing 50,000 rows of data each means 150,000+ tokens consumed before any reasoning output is generated.

Response-size optimization (pagination, selective fields, compression) addresses symptoms. The architectural fix is preventing intermediate data from entering context at all — through code execution or server-side aggregation.

**Break-even point:** For 1–3 sequential tool calls with small responses, traditional MCP is simpler and lower-risk. At 4+ calls with data-intensive responses, server-side aggregation or code execution architecture becomes a better design choice.

### Design Your Server for Context-Efficient Clients

When building MCP servers, design them to support context-efficient consumption patterns:

**1. Expose aggregation tools alongside raw data tools**

```typescript
// Verbose — returns full list, client aggregates in LLM context
server.registerTool('get_all_orders', { ... }, async ({ customer_id }) => {
  return db.query('SELECT * FROM orders WHERE customer_id = $1', [customer_id]);
  // Returns 500 rows → 40,000 tokens in agent context
});

// Context-efficient — aggregation happens server-side
server.registerTool('get_order_summary', { ... }, async ({ customer_id }) => {
  const [row] = await db.query(
    'SELECT COUNT(*) as count, SUM(amount) as total, MAX(created_at) as latest FROM orders WHERE customer_id = $1',
    [customer_id]
  );
  return row;
  // Returns 3 fields → ~50 tokens in agent context
});
```

Expose BOTH. The agent calls the summary by default; the detail tool when full data is needed. Never force the agent to choose between "all or nothing."

**2. Filtering belongs on the server**

Never return unfiltered data and expect the agent to select relevant rows. Agents that filter in context consume tokens for every discarded row. Push all filter logic server-side:

```typescript
// ❌ Agent filters in context — O(N) token cost
{ users: [all 10,000 users] }

// ✅ Server filters — O(1) token cost
server.registerTool('get_active_users_since', { ... }, async ({ since_date }) => {
  return db.query('SELECT id, email FROM users WHERE status = $1 AND last_login > $2', ['active', since_date]);
});
```

**3. Design for composability with code execution clients**

Some clients will use code execution architecture (agent writes code, sandbox calls your server, only summaries return to LLM). Design your server to support this without changes:
- Stateless tools that accept explicit parameters (not session-derived context)
- Idempotent reads so retries are safe
- Clear error codes so sandbox error handlers can branch without LLM involvement

---

## Filesystem Tool Discovery (Large API Surface)

When an MCP server exposes >30 tools, upfront tool definition loading consumes significant context before any work begins. A 50-tool server at 180 tokens/definition = 9,000 tokens of definitions loaded even if only 2 tools are used.

The Filesystem Tool Discovery pattern stores tool definitions as browsable resources rather than pre-loading all definitions at registration time.

### Server-Side Implementation

```typescript
// Register a directory of tool metadata files as a resource
server.registerResource(
  'tool_index',
  'tool-index://registry',
  { title: 'Available Tools', description: 'Browse available tools by category' },
  async () => {
    const categories = await fs.readdir(TOOLS_DIR);
    const index = await Promise.all(
      categories.map(async cat => ({
        category: cat,
        tools: await fs.readdir(path.join(TOOLS_DIR, cat)),
      }))
    );
    return {
      contents: [{ uri: 'tool-index://registry', text: JSON.stringify(index) }]
    };
  }
);

// Register individual tool metadata as resources
server.registerResource(
  'tool_definition',
  new ResourceTemplate('tool-def://{category}/{name}', { list: undefined }),
  { title: 'Tool Definition', description: 'Get full definition for a specific tool' },
  async (uri, { category, name }) => {
    // Template variables are client-controlled `string | string[]`: allowlist before building a path.
    const safe = /^[a-z0-9_-]+$/;
    if (typeof category !== 'string' || typeof name !== 'string' || !safe.test(category) || !safe.test(name)) {
      throw new ResourceNotFoundError(uri.href);
    }
    const defPath = path.join(TOOLS_DIR, category, `${name}.json`);
    const def = await fs.readFile(defPath, 'utf8');
    return { contents: [{ uri: uri.href, text: def }] };
  }
);
```

### Agent Usage Pattern

The agent reads the index resource (~200 tokens) and loads individual tool definitions only when needed (~150 tokens each), rather than receiving all 9,000 tokens at session start.

**When to use filesystem discovery:**
- Server exposes 30+ tools
- Many tools are domain-specific and rarely used together
- Context budget is a known constraint for target agents

**When NOT to use:**
- Server exposes <15 tools — overhead of discovery pattern adds latency without meaningful token savings
- All tools are used in nearly every session — pre-loading all is simpler
