## Domain-Based Pattern Selection Presets

### Weather / Public Data APIs
```yaml
required_patterns: [1, 3, 8]
Pattern 1: Always guide next actions
Pattern 3: Handle API errors gracefully
Pattern 8: Advertise rate limits and coverage
```

### Payment / Financial APIs
```yaml
required_patterns: [1, 2, 3, 6, 9, 10]
Pattern 1: Guide agent through payment flow
Pattern 2: Confidence gates for high-value transactions
Pattern 3: Structured error recovery for payment failures
Pattern 6: Idempotency for duplicate payment prevention
Pattern 9: Circuit breaker for payment gateway outages
Pattern 10: Audit trail for compliance and fraud investigation
```

### Healthcare APIs
```yaml
required_patterns: [1, 2, 3, 4, 6, 7, 9, 10]
Pattern 1: Guide clinical workflows
Pattern 2: Confidence gates for diagnoses and prescriptions
Pattern 3: Structured error recovery for critical failures
Pattern 4: Progressive disclosure for large patient records
Pattern 6: Idempotency for medication orders
Pattern 7: Session context for multi-step appointments
Pattern 9: Circuit breaker for EHR system outages
Pattern 10: Audit trail for HIPAA compliance
escalate_to_human: MANDATORY for prescriptions, diagnoses, life-safety
```

### E-Commerce APIs
```yaml
required_patterns: [1, 3, 4, 5, 6, 7, 10]
Pattern 1: Guide shopping workflows
Pattern 3: Structured error recovery for checkout failures
Pattern 4: Progressive disclosure for large product catalogs
Pattern 5: Resource linking for product discovery
Pattern 6: Idempotency for order creation
Pattern 7: Session context for multi-step checkout
Pattern 10: Audit trail for fraud detection
```

### Trading / Autonomous Trading Agents
```yaml
required_patterns: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
ALL_PATTERNS: Maximum safety and auditability
escalate_to_human: MANDATORY for trades >$10k, margin calls, unusual volatility
```

---

## Tool Design: Intent-Based Consolidation

### Anti-Pattern: CRUD Explosion (6+ Tools)

```typescript
// BAD: 6 tools for basic user operations
server.registerTool("create_user", ...);
server.registerTool("get_user", ...);
server.registerTool("update_user", ...);
server.registerTool("delete_user", ...);
server.registerTool("list_users", ...);
server.registerTool("search_users", ...);
```

**Problems:**
- Agent confused about which tool to use
- Increased prompt size (all tools sent to model)
- Redundant parameter validation
- Hard to maintain consistent error handling

### Correct Pattern: Intent-Based Consolidation (2 Tools)

```typescript
// GOOD: 2 intent-based tools
server.registerTool(
  "manage_user",
  {
    title: "Manage User",
    description: "Create, update, or delete a user",
    inputSchema: {
      action: z.enum(["create", "update", "delete"]).describe("The action to perform"),
      user_id: z.string().optional().describe("Required for update/delete"),
      user_data: z.object({
        name: z.string().optional(),
        email: z.string().email().optional(),
        role: z.enum(["user", "admin"]).optional()
      }).optional().describe("Required for create/update")
    },
    annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: false }
  },
  async ({ action, user_id, user_data }) => {
    // Single handler with consolidated logic
    switch (action) {
      case "create":
        return createUser(user_data);
      case "update":
        return updateUser(user_id, user_data);
      case "delete":
        return deleteUser(user_id);
    }
  }
);

server.registerTool(
  "query_users",
  {
    title: "Query Users",
    description: "Search or list users with filters",
    inputSchema: {
      search_term: z.string().optional(),
      role: z.enum(["user", "admin"]).optional(),
      limit: z.number().default(50),
      offset: z.number().default(0)
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  async ({ search_term, role, limit, offset }) => {
    return queryUsers({ search_term, role, limit, offset });
  }
);
```

### Tool Count Guidelines

| Tool Count | Status | Action |
|------------|--------|--------|
| 10-15 | Ideal | Proceed |
| 16-25 | Acceptable | Review for consolidation opportunities |
| 26-30 | Warning | Consolidate or split into multiple MCP servers |
| 31+ | Critical | MUST consolidate — agent performance will degrade |

**Rule of Thumb:**
- **Write operations** (create, update, delete): 1-2 tools per entity
- **Read operations** (get, list, search): 1 tool per entity
- **Workflow tools** (checkout, submit_form, process_order): 1 tool per workflow
- **Utility tools** (calculate, validate, format): Consolidate into domain-specific tools

---

## `escalate_to_human` Tool Requirement

For high-risk domains, MCP servers SHOULD implement an `escalate_to_human` tool.

### When Required

- Life-safety decisions (healthcare, autonomous vehicles)
- Fraud detection and account security
- High-value financial transactions (>$1000 or domain threshold)
- Legal/compliance decisions
- Ambiguous user intent with confidence < threshold

### Implementation Example

```typescript
server.registerTool(
  "escalate_to_human",
  {
    title: "Escalate to Human",
    description: "Escalate decision to human operator",
    inputSchema: {
      reason: z.string().describe("Why escalation is needed"),
      context: z.record(z.string(), z.unknown()).describe("Relevant context for human reviewer"),
      urgency: z.enum(["low", "medium", "high", "critical"]),
      suggested_action: z.string().optional()
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false }
  },
  async ({ reason, context, urgency, suggested_action }) => {
    const ticket = await createEscalationTicket({
      reason,
      context,
      urgency,
      suggested_action,
      timestamp: new Date().toISOString()
    });

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({
            escalation_id: ticket.id,
            status: "escalated",
            estimated_response_time_minutes: urgency === "critical" ? 5 : 30,
            message: "Request escalated to human operator. Do not proceed until human review is complete.",
            next_actions: ["wait_for_human_response"],
            context: {
              escalation_id: ticket.id,
              check_tool: "check_escalation_status"
            }
          }, null, 2)
        }
      ]
    };
  }
);
```

---

## Summary: Pattern Adoption Hierarchy

Implement patterns in this order. Each tier's patterns are prerequisites for the next.

### Day 1 — Eliminates most agent confusion
- [ ] **Pattern 1 (Agent-Directive)** — Add `next_actions` + `suggestion` to EVERY tool response. Solves "what do I do next?" which is the most common agent stall point.
- [ ] **Pattern 3 (Structured Error Recovery)** — Add `recovery_actions` + `fallback_tool` + `retry_after_ms` to ALL error responses. Silent failures kill workflows.

### Week 1 — Adds judgment and efficiency
- [ ] **Pattern 2 (Confidence-Gated)** — Once agents make classification or prediction calls, gate actions on `confidence_threshold`. Prevents low-confidence decisions from proceeding unquestioned.
- [ ] **Pattern 4 (Progressive Disclosure)** — Once token costs become visible in billing, add `summary` + `detail_tool` + `detail_params` to data-heavy tools. Agents get summaries by default; load detail only when needed.

### Month 1 — Production maturity
- [ ] **Pattern 6 (Idempotency)** — Before ANY payment or state mutation goes live. Retries will happen; `already_processed` + `original_result` prevents duplicates.
- [ ] **Pattern 9 (Circuit Breaker Status)** — Before external dependencies can cause cascading failures. Expose `circuit_state` + `fallback_tool` + `expected_recovery`.
- [ ] **Pattern 10 (Audit Trail)** — Before compliance or debugging requires "how did this happen?" Include `correlation_id`, `tool_chain`, `data_sources`, `model_version`.

### Sophisticated agents
- [ ] **Pattern 5 (Resource Linking)** — When agents navigate entity graphs. Embed `links` + `available_actions` so agents discover relationships without hardcoded schema knowledge.
- [ ] **Pattern 7 (Context Carryover)** — When multi-turn state matters. Pass `session_id` + `carry_forward` + `next_tool_hint` to eliminate re-fetching across turns.
- [ ] **Pattern 8 (Capability Advertisement)** — When agents select from many similar tools. Surface `capabilities`, `limitations`, `max_file_size_mb`, `cost_estimate` so agents can self-plan.
- [ ] **`escalate_to_human`** — Implemented for high-risk domains (financial, irreversible, low-confidence critical decisions).
- [ ] **Tool count** — Between 10-25 tools (consolidate if >25 — see mcp-design-principles.md)

**Next Steps:**
1. Read [node-mcp-setup.md](node-mcp-setup.md) or [python-mcp-setup.md](python-mcp-setup.md) for current SDK v2 implementation examples
2. Use `server.registerTool()` (TypeScript) or `@mcp.tool()` on `MCPServer` (Python) — never the deprecated v1 `server.tool()`. The low-level `server.setRequestHandler(...)` is not deprecated; use it only for what `McpServer` does not cover (e.g. paginated `resources/list`)
3. Return `structuredContent` (matching `outputSchema`) plus a `content` text block: `{ content: [{ type: "text", text: JSON.stringify(output) }], structuredContent: output }`
4. Test with autonomous agent workflows, not just single tool calls
