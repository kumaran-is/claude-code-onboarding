# MCP Quality Standards

## Security Best Practices

### Authentication and Authorization

**OAuth 2.1 with PKCE** (Production Auth):
- Use OAuth 2.1 with PKCE (Proof Key for Code Exchange) — required for all clients
- Validate access tokens before processing requests
- Only accept tokens specifically intended for your server
- Implement token refresh with `refresh_token` grant type
- Use Redis-backed token storage for production (TTL-based expiry)
- Require `code_challenge` with S256 method for all authorization requests
- See [security-core.md](security-core.md) for full OAuth implementation

**API Keys**:
- Store API keys in environment variables, never in code
- Validate keys on server startup
- Provide clear error messages when authentication fails

### Input Validation

- Sanitize file paths to prevent directory traversal
- Validate URLs and external identifiers
- Check parameter sizes and ranges
- Prevent command injection in system calls
- Use schema validation (Pydantic/Zod) for all inputs
- Strict objects (`z.strictObject`, Pydantic `extra="forbid"`): an unknown field such as a smuggled `tenant_id` is a validation error, not silently stripped. With `z.object` (strip) the smuggled call executed (planted defect)

**Tool boundary order, every call:** tool exists → schema version supported → payload conforms to the pinned schema → authorization permits the action. Any failure: return a stable code and do **not** execute.

- Version the contract: a `schema_version` (`"<major>.<minor>"`) argument or a versioned tool name. Unsupported major → `SCHEMA_VERSION_MISMATCH`; minor bumps are additive only; enum changes and new required fields need a compatibility review.
- TypeScript SDK v2 validates the whole `inputSchema` before the handler runs and answers with `isError` and the text `Input validation error: …` (not a custom code). That still meets the control (nothing executes); map it to `SCHEMA_VALIDATION_FAILED` in clients or traces if you need one code. Check the major version first thing in the handler.
- Tested (SDK v2 2.4.0, 2026-11-23): unknown field, missing required field, bad enum and `schema_version: "2.0"` were each rejected with no side effect; removing the major-version check failed the suite.
- The advertised tool surface (name, description, input schema) is locked in CI so prompts, tool declarations and backend schemas cannot drift apart unnoticed: `eval-guide/reference/mcp-eval-patterns.md` (tool-surface lock).

### Error Handling

- Don't expose internal errors to clients
- Log security-relevant errors server-side
- Provide helpful but not revealing error messages
- Clean up resources after errors

### DNS Rebinding Protection

For streamable HTTP servers running locally:
- Enable DNS rebinding protection
- Validate the `Origin` header on all incoming connections
- Bind to `127.0.0.1` rather than `0.0.0.0`

---

## Tool Annotations

Provide annotations to help clients understand tool behavior:

| Annotation | Type | Default | Description |
|-----------|------|---------|-------------|
| `readOnlyHint` | boolean | false | Tool does not modify its environment |
| `destructiveHint` | boolean | true | Tool may perform destructive updates |
| `idempotentHint` | boolean | false | Repeated calls with same args have no additional effect |
| `openWorldHint` | boolean | true | Tool interacts with external entities |

**Important**: Annotations are hints, not security guarantees. Clients should not make security-critical decisions based solely on annotations.

---

## Error Handling

- Use standard JSON-RPC error codes
- Report tool errors within result objects (not protocol-level errors)
- Provide helpful, specific error messages with suggested next steps
- Don't expose internal implementation details
- Clean up resources properly on errors

Example error handling:
```typescript
try {
  const result = performOperation();
  return { content: [{ type: "text", text: result }] };
} catch (error) {
  return {
    isError: true,
    content: [{
      type: "text",
      text: `Error: ${error.message}. Try using filter='active_only' to reduce results.`
    }]
  };
}
```

---

## Testing Requirements

### Coverage Thresholds (Non-Negotiable)

Configure these in `vitest.config.ts` under `coverage.thresholds`. These are the minimum bars — CI must fail if any threshold is not met:

```typescript
// vitest.config.ts
export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'html'],
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.d.ts', 'src/server.ts'], // exclude wire-up entry point
      thresholds: {
        statements: 90, // ← hard minimum
        branches: 80,   // ← hard minimum (lower: branch paths harder to reach)
        functions: 90,  // ← hard minimum
        lines: 90,      // ← hard minimum
      },
    },
  },
});
```

**Why these numbers:** Statements/functions/lines at 90% catches the majority of dead or untested code paths. Branches at 80% acknowledges that some error branches (e.g. OS-level failures) are impractical to trigger in tests.

**What to exclude:** Only exclude `server.ts` (the transport wire-up entry point) — this is pure glue code (instantiates classes, binds ports) that cannot be meaningfully unit tested. Every other file must hit the threshold.

Comprehensive testing should cover:

- **Functional testing**: Verify correct execution with valid/invalid inputs
- **Integration testing**: Test interaction with external systems
- **Security testing**: Validate auth, input sanitization, rate limiting
- **Performance testing**: Check behavior under load, timeouts
- **Error handling**: Ensure proper error reporting and cleanup

### Testing Patterns

#### Unit Testing Tools (Vitest)

Test tool handlers with mocked API clients:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { handleSearchUsers } from './tools/users.js';

describe('search_users tool', () => {
  const mockApiClient = {
    searchUsers: vi.fn(),
  };

  it('should return formatted results for valid query', async () => {
    mockApiClient.searchUsers.mockResolvedValue({
      users: [{ id: 'usr_1', name: 'Alice', email: 'alice@example.com' }],
      total: 1,
    });

    const result = await handleSearchUsers(
      { query: 'Alice', limit: 10, offset: 0 },
      mockApiClient
    );

    expect(result.content[0].text).toContain('Alice');
    expect(mockApiClient.searchUsers).toHaveBeenCalledWith({
      q: 'Alice', limit: 10, offset: 0,
    });
  });

  it('should return error response for API failure', async () => {
    mockApiClient.searchUsers.mockRejectedValue(new Error('Service unavailable'));

    const result = await handleSearchUsers(
      { query: 'Alice', limit: 10, offset: 0 },
      mockApiClient
    );

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('SERVICE_UNAVAILABLE');
  });
});
```

#### Integration Testing with MCP Inspector

Use MCP Inspector to validate tool registration and end-to-end behavior:

```bash
# Build and test with MCP Inspector
npm run build
npx @modelcontextprotocol/inspector dist/index.js
```

Verify in Inspector:
- All tools listed with correct names, descriptions, and schemas
- Tool annotations (readOnlyHint, destructiveHint) are accurate
- Input validation rejects malformed inputs with helpful errors
- Responses include `next_actions` and `suggestion` fields

#### Testing Resilience Patterns

```typescript
describe('circuit breaker', () => {
  it('should open after threshold failures', async () => {
    const breaker = new CircuitBreaker({ failureThreshold: 3, resetTimeout: 1000 });

    // Trigger 3 failures
    for (let i = 0; i < 3; i++) {
      await breaker.execute(() => Promise.reject(new Error('fail'))).catch(() => {});
    }

    expect(breaker.getState()).toBe('open');
  });

  it('should transition to half-open after reset timeout', async () => {
    const breaker = new CircuitBreaker({ failureThreshold: 1, resetTimeout: 100 });
    await breaker.execute(() => Promise.reject(new Error('fail'))).catch(() => {});

    await new Promise(resolve => setTimeout(resolve, 150));
    expect(breaker.getState()).toBe('half-open');
  });
});
```

#### Testing Security Middleware

```typescript
describe('security middleware', () => {
  it('should reject SQL injection attempts', async () => {
    const result = await callTool('search_users', {
      query: "admin' OR '1'='1",
    });

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('attack pattern detected');
  });

  it('should sanitize XSS in string inputs', async () => {
    const result = await callTool('create_note', {
      title: '<script>alert("xss")</script>My Note',
    });

    expect(result.content[0].text).not.toContain('<script>');
  });
});
```

---

## Documentation Requirements

- Provide clear documentation of all tools and capabilities
- Include working examples (at least 3 per major feature)
- Document security considerations
- Specify required permissions and access levels
- Document rate limits and performance characteristics

---

## Audit Logging Requirements

Every MCP server MUST implement audit logging:

- Generate a `correlation_id` for every incoming request
- Write tools: one record per decision (allowed and denied) with the required field set in [security-pii-compliance.md](security-pii-compliance.md) §3, written before the effect
- Log tool invocations with: tool name, input hash (not raw input), output status, duration
- Include tenant context if multi-tenant (tenant_id, organization_id)
- Track the full tool chain for multi-step operations
- Log all security-relevant events (auth failures, attack pattern detections, escalations)
- See [error-taxonomy.md](error-taxonomy.md) for AuditLogger implementation

---

## MCP Protocol Primitives

MCP has THREE core primitives — implement all three:

| Primitive | Purpose | Control | Registration |
|-----------|---------|---------|-------------|
| **Tools** | Actions with side effects | Model-invoked | `server.registerTool()` |
| **Resources** | Read-only data access | App-controlled | `server.registerResource()` |
| **Prompts** | Reusable templates | User-triggered | `server.registerPrompt()` |

### Prompts Registration

Prompts are reusable templates that users can trigger:

```typescript
server.registerPrompt(
  "code_review",
  {
    title: "Code Review",
    description: "Generate a structured code review for the given code",
    argsSchema: {
      code: z.string().describe("Code to review"),
      language: z.string().describe("Programming language"),
      focus: z.enum(["security", "performance", "readability"]).optional(),
    },
  },
  async ({ code, language, focus }) => ({
    messages: [{
      role: "user",
      content: {
        type: "text",
        text: `Review this ${language} code${focus ? ` with focus on ${focus}` : ''}:\n\n\`\`\`${language}\n${code}\n\`\`\`\n\nProvide:\n1. Summary\n2. Issues found (with severity)\n3. Suggested improvements\n4. Security considerations`,
      },
    }],
  })
);
```

Always register Prompts for common workflows that agents or users frequently need.

---
