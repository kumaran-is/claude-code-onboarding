# MCP Design Patterns for Autonomous Agents — Core

This reference covers the 5 foundational design patterns that EVERY MCP server should implement. For advanced patterns (idempotency, context carryover, circuit breakers, audit trails) and domain-specific presets, read `agent-design-patterns-advanced.md`. For multi-agent orchestration (supervisor, parallel execution, reflection, debate, self-healing tiers), read `agent-orchestration-patterns.md`.

---

## Pattern Reference Matrix

| Pattern | Solves | When to Use | Complexity |
|---------|--------|-------------|------------|
| 1. Agent-Directive Response | Agent doesn't know next step | **ALWAYS** — Every tool response | Low |
| 2. Confidence-Gated Response | Preventing low-confidence actions | High-risk operations (payments, deletions) | Medium |
| 3. Structured Error Recovery | Agent retry loops, unclear failures | All error scenarios | Medium |
| 4. Progressive Disclosure | Large payloads, slow operations | Data-heavy APIs, multi-stage queries | Medium |
| 5. Resource Linking (HATEOAS) | Agent doesn't see related actions | REST APIs, workflow navigation | Low |
| 6. Idempotency & Safe Retry | Duplicate operations on retry | POST/PUT/DELETE operations | Medium |
| 7. Context Carryover | Lost context across tool calls | Multi-turn workflows, sessions | High |
| 8. Capability Advertisement | Agent uses tool incorrectly | Complex tools with limits | Low |
| 9. Circuit Breaker Status | Repeated failures to dead services | External API integrations | Medium |
| 10. Audit Trail | Debugging agent decisions | Compliance, debugging, production | Low |

Patterns 6-10 are in [agent-design-patterns-advanced.md](agent-design-patterns-advanced.md).

---

## Pattern 1: Agent-Directive Response (ALWAYS USE)

**Problem**: Agent receives data but doesn't know what to do next.

**Solution**: Every tool response includes `next_actions`, `suggestion`, and `context` to guide the agent's next move.

### TypeScript Interface

```typescript
interface AgentResponse<T> {
  data: T;
  next_actions: string[];           // Explicit next steps agent should consider
  suggestion: string;                // Natural language guidance
  context: Record<string, unknown>;  // Key-value pairs for follow-up tools
}
```

### Helper Function

```typescript
function formatAgentResponse<T>(
  data: T,
  nextActions: string[],
  suggestion: string,
  context: Record<string, unknown> = {}
): AgentResponse<T> {
  return {
    data,
    next_actions: nextActions,
    suggestion,
    context
  };
}
```

### Usage in Tool Handler (Modern MCP SDK)

```typescript
import { McpServer } from "@modelcontextprotocol/server";
import * as z from "zod/v4";

const server = new McpServer({ name: "example-server", version: "1.0.0" });

// Register tool with modern API
server.registerTool(
  "get_user",
  {
    title: "Get User",
    description: "Fetches user profile by ID",
    inputSchema: z.object({
      user_id: z.string().describe("The user ID to fetch")
    }),
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  async ({ user_id }) => {
    const user = await fetchUser(user_id);

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(formatAgentResponse(
            user,
            [
              "fetch_user_orders",
              "fetch_user_preferences",
              "update_user_profile"
            ],
            `User ${user.name} found. You can now fetch their orders or update their profile.`,
            {
              user_id: user.id,
              has_premium: user.subscription === "premium",
              last_login: user.last_login
            }
          ), null, 2)
        }
      ]
    };
  }
);
```

### Example JSON Output

```json
{
  "data": {
    "id": "usr_123",
    "name": "Alice",
    "email": "alice@example.com",
    "subscription": "premium"
  },
  "next_actions": [
    "fetch_user_orders",
    "fetch_user_preferences",
    "update_user_profile"
  ],
  "suggestion": "User Alice found. You can now fetch their orders or update their profile.",
  "context": {
    "user_id": "usr_123",
    "has_premium": true,
    "last_login": "2026-02-01T10:30:00Z"
  }
}
```

**Optional: `threshold_guidance` for numeric outputs**

When a tool returns a score, probability, or other numeric value, agents need to know what the number *means* before they can act. Add a `threshold_guidance` field alongside `next_actions`:

```json
{
  "data": { "risk_score": 73, "issues_found": 12 },
  "next_actions": ["get_issue_details", "review_critical_vulnerabilities"],
  "suggestion": "Risk score above 70. Investigate the 3 critical issues before deploying.",
  "threshold_guidance": {
    "low": "< 40",
    "medium": "40–70",
    "high": "> 70"
  }
}
```

Without `threshold_guidance`, the agent must infer meaning from context or ask for clarification. With it, the agent knows immediately that 73 is in the *high* tier and can branch without a follow-up call. Add this whenever the tool returns a dimensioned numeric result (scores, percentages, probabilities, confidence values).

### Typed Next-Intent Envelope (Advanced)

For complex workflows where agents need to know not just *what* to do next but *why* and *how*, extend `AgentResponse<T>` with a typed `next` object. This replaces the untyped `next_actions: string[]` with a discriminated union that the agent can branch on without parsing natural language.

```typescript
type NextIntent =
  | 'present'       // Show result to user — workflow step complete
  | 'ask_clarify'   // Agent must ask user before proceeding
  | 'retry'         // Retry same tool with corrected params (corrective_params provided)
  | 'escalate';     // Route to human — confidence below threshold or irreversible action

interface TypedNextDirective {
  intent: NextIntent;
  prompt_template?: string;            // Pre-built prompt for ask_clarify intent
  suggested_tool?: string;             // Next tool to call for present/retry intents
  suggested_params?: Record<string, unknown>;  // Pre-populated params for suggested_tool
}

interface TypedAgentResponse<T> extends Omit<AgentResponse<T>, 'next_actions'> {
  next: TypedNextDirective;
  schema_version: number;              // Increment on breaking next.intent changes
}
```

**When to use typed vs unstructured directives:**

| Response type | When to use |
|---|---|
| `next_actions: string[]` | Advisory flows — agent picks from options (low-stakes, multiple valid paths) |
| `next: TypedNextDirective` | Workflow-critical flows — agent must branch correctly (payments, deletions, auth) |

**Anti-pattern:** Using `ask_clarify` intent when the required information is already in context. Reserve it for genuinely missing user intent — overuse trains agents to interrupt unnecessarily.

---

### Directive Strength Calibration (Three Tiers)

Not every tool response needs the same directive strength. Over-directing trains agents to ignore suggestions; under-directing leaves agents lost.

| Tier | When to Use | `next_actions` | `suggestion` |
|------|------------|----------------|-------------|
| **Mandatory** | Agent MUST do this or the workflow breaks | Single action, imperative phrasing: "call X to proceed" | "You must call X next — the workflow cannot continue without it" |
| **Conditional** | Agent should do this IF a condition is true | 1-2 actions with condition: "if order_status is 'shipped', call track_shipment" | "If the status is 'shipped', call track_shipment to get delivery details" |
| **Advisory** | Agent MAY do this — it's optional context | 2-3 options, no imperative phrasing | "You can optionally fetch user preferences for a personalized response" |

**Anti-pattern:** Always-on suggestions with equal weight. If every tool response says "you should do X, Y, and Z", the agent learns to ignore suggestions entirely. Reserve Mandatory directives for genuine workflow requirements.

**Health signal:** Monitor suggestion override rate (see observability-patterns.md). Target 5-15%. If it drops below 5%, your suggestions are too obvious or always followed — they may be unnecessary. If it exceeds 25%, your suggestions are wrong and agents are correctly ignoring them.

### Typed `directive` Object (Structured Three-Tier Responses)

The three-tier table above describes calibration intent. For production servers where the agent must distinguish tier at runtime, use a typed `directive` object instead of bare `next_actions[]`:

```typescript
type DirectiveTier = 'mandatory' | 'conditional' | 'advisory';

interface MandatoryDirective {
  type: 'mandatory';
  next_action: string;
  params?: Record<string, unknown>;
  rationale: string;             // Required — always explain why
}

interface ConditionalDirective {
  type: 'conditional';
  conditions: Array<{
    if: string;                  // Evaluable condition string
    suggest: string;             // Tool to call if condition is true
    rationale: string;           // Why this condition maps to this action
  }>;
  agent_override_allowed: true;  // Always true — agent retains judgment
}

interface AdvisoryDirective {
  type: 'advisory';
  considerations: string[];      // Context for agent to reason with
  possible_actions: string[];    // Options — not ranked or recommended
  decision_owner: 'agent';       // Explicit: agent must decide
}
```

**Mandatory directive example** (transaction rollback after failure):
```json
{
  "directive": {
    "type": "mandatory",
    "next_action": "rollback_transaction",
    "params": { "transaction_id": "txn-123" },
    "rationale": "Partial transaction detected. Rollback required for data consistency."
  }
}
```

**Conditional directive example** (data freshness branch):
```json
{
  "directive": {
    "type": "conditional",
    "conditions": [
      {
        "if": "data_freshness == 'stale'",
        "suggest": "refresh_market_data",
        "rationale": "Sentiment score based on data >1hr old. Consider refreshing."
      },
      {
        "if": "data_freshness == 'fresh'",
        "suggest": "proceed_with_analysis",
        "rationale": "Data is current. Analysis can proceed."
      }
    ],
    "agent_override_allowed": true
  }
}
```

**Advisory directive example** (anomaly with ambiguous cause):
```json
{
  "directive": {
    "type": "advisory",
    "considerations": [
      "Anomaly could indicate data corruption OR genuine outlier",
      "Historical false positive rate for this detector: 23%",
      "Previous anomalies this week: 2 (both confirmed genuine)"
    ],
    "possible_actions": ["investigate_anomaly", "flag_for_review", "proceed_anyway"],
    "decision_owner": "agent"
  }
}
```

**Mandatory directive usage cap:** If more than ~10% of your tool responses use `type: "mandatory"`, you are building a workflow executor, not an agent. Mandatory directives are appropriate for regulatory compliance sequences, safety-critical rollbacks, and idempotency enforcement — not for routine workflow guidance. Exceed 10% and reconsider whether agent autonomy is needed at all.

**Rationale is required on every directive.** Omitting it trains agents to follow suggestions without understanding why, degrading their ability to handle novel situations where no directive is provided. Always explain: "Primary provider at 89% failure rate in last 5 minutes. Fallback recommended to maintain SLA."

### Directive Fallback Chain (Graceful Autonomy Degradation)

Design your directive logic to start with the least prescriptive tier and escalate only when response data indicates complexity:

```
Level 1: No directive — agent decides autonomously
    ↓ if agent uncertainty detected after reasoning
Level 2: Advisory directive — provide considerations, preserve agent judgment
    ↓ if still uncertain
Level 3: Conditional directive — provide if/then branches, allow override
    ↓ only if condition match fails or safety threshold crossed
Level 4: Mandatory directive or human escalation
```

Most tools default to Level 1 for routine cases. Reserve Level 3–4 for situations where the tool has domain-specific knowledge the agent doesn't (regulatory rules, partial-state detection, idempotency enforcement).

---

## Pattern 2: Confidence-Gated Response

**Problem**: Agent executes high-risk actions with low confidence, causing errors or unwanted operations.

**Solution**: Tools return confidence scores and guidance when confidence is below threshold.

### TypeScript Interface

```typescript
interface ConfidenceGatedResponse<T> {
  data: T | null;
  confidence: number;              // 0.0 - 1.0
  confidence_threshold: number;    // Minimum required confidence
  below_threshold_action: string;  // What agent should do if confidence too low
  reasoning: string;               // Why confidence is low/high
}
```

### Example JSON Output

```json
{
  "data": null,
  "confidence": 0.45,
  "confidence_threshold": 0.80,
  "below_threshold_action": "escalate_to_human",
  "reasoning": "Ambiguous deletion request - 'last order' could mean most recent or final. User has 3 orders from today. Recommend asking user to specify order ID explicitly."
}
```

**When confidence is high:**

```json
{
  "data": {
    "order_id": "ord_999",
    "status": "cancelled",
    "refund_amount": 49.99
  },
  "confidence": 0.95,
  "confidence_threshold": 0.80,
  "below_threshold_action": "proceed",
  "reasoning": "Clear order ID provided (ord_999), user confirmed cancellation intent, refund policy allows cancellation within 24 hours."
}
```

---

## Pattern 3: Structured Error Recovery

**Problem**: Agent receives generic error messages and enters retry loops without fixing the issue.

**Solution**: Errors include recovery actions, retry timing, fallback tools, and corrective parameters.

### TypeScript Interface

```typescript
interface StructuredError {
  code: string;                    // Machine-readable error code
  message: string;                 // Human-readable message
  retry_after_ms?: number;         // Wait time before retry (null = don't retry)
  recovery_actions: string[];      // Steps agent should take
  fallback_tool?: string;          // Alternative tool to try
  corrective_params?: Record<string, unknown>;  // Fixed parameters to use
}
```

### Example JSON Output (Rate Limit)

```json
{
  "code": "RATE_LIMIT_EXCEEDED",
  "message": "API rate limit exceeded: 100 requests/minute",
  "retry_after_ms": 12000,
  "recovery_actions": [
    "wait_12_seconds",
    "retry_with_same_params"
  ],
  "fallback_tool": null,
  "corrective_params": null
}
```

### Example JSON Output (Invalid Parameter)

```json
{
  "code": "INVALID_DATE_FORMAT",
  "message": "Date must be in ISO 8601 format (YYYY-MM-DD)",
  "retry_after_ms": null,
  "recovery_actions": [
    "reformat_date_to_iso8601",
    "retry_with_corrected_params"
  ],
  "fallback_tool": null,
  "corrective_params": {
    "date": "2026-02-02",
    "original_input": "2/2/2026"
  }
}
```

---

## Pattern 4: Progressive Disclosure

**Problem**: Large responses cause token overflow; agent needs summary first, details on demand.

**Solution**: Return summary with metadata about available details and how to fetch them.

### TypeScript Interface

```typescript
interface ProgressiveResponse<TSummary, TDetail> {
  summary: TSummary;
  detail_available: boolean;
  detail_tool: string;           // Tool to call for full details
  detail_params: Record<string, unknown>;  // Params to pass to detail_tool
}
```

### Example JSON Output

```json
{
  "summary": {
    "total_orders": 1247,
    "date_range": "2025-01-01 to 2026-02-02",
    "total_revenue": 98543.21,
    "top_product": "Widget Pro"
  },
  "detail_available": true,
  "detail_tool": "get_orders_detail",
  "detail_params": {
    "date_range": "2025-01-01/2026-02-02",
    "page_size": 100,
    "include_line_items": true
  }
}
```

---

## Pattern 5: Resource Linking (HATEOAS)

**Problem**: Agent doesn't discover related actions or navigate workflows.

**Solution**: Include hypermedia links and available actions in every response.

### TypeScript Interface

```typescript
interface LinkedResponse<T> {
  data: T;
  links: {
    self: string;
    related?: string[];
  };
  available_actions: Array<{
    name: string;
    tool: string;
    params: Record<string, unknown>;
  }>;
}
```

### Example JSON Output

```json
{
  "data": {
    "order_id": "ord_456",
    "status": "shipped",
    "tracking_number": "1Z999AA1234567890"
  },
  "links": {
    "self": "mcp://orders/ord_456",
    "related": [
      "mcp://users/usr_123",
      "mcp://shipments/shp_789"
    ]
  },
  "available_actions": [
    {
      "name": "Track shipment",
      "tool": "track_shipment",
      "params": { "tracking_number": "1Z999AA1234567890" }
    },
    {
      "name": "Cancel order",
      "tool": "cancel_order",
      "params": { "order_id": "ord_456" }
    },
    {
      "name": "Contact customer",
      "tool": "get_user",
      "params": { "user_id": "usr_123" }
    }
  ]
}
```
