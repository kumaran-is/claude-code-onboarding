# MCP Eval Patterns

> When agents reach external systems through an MCP server, that server is the enforcement point.
> Cross-tenant input IDs and unauthorized tool calls are hard CI blockers.

## Day-1 Security Requirement — Tenant Isolation in the MCP Auth Layer

**Before any MCP eval is meaningful**, the MCP server's auth layer must enforce
caller `tenant_id` ↔ tool input scoping. A common Day-1 gap:
the auth layer validates the bearer/API key only, but does not scope by tenant/owner/resource ID.

Verify tenant isolation is enforced in your MCP auth layer before running MCP evals in staging.

## MCP Eval Suite Components

| Suite | What it tests | CI tier |
|-------|-------------|---------|
| Contract (tool surface lock) | Tool names, input/output schemas didn't change unexpectedly | R1 always |
| Schema strictness | Required fields are required; no extra fields accepted | R1 always |
| Auth | Unauthenticated requests rejected; invalid tokens rejected | R1 always |
| Tenant isolation | Caller A cannot access data scoped to Caller B | R1 BLOCKER #4 |
| Audit log | Every write tool emits an audit log entry | R1 BLOCKER #8 |
| Behavior | Tool returns correct results for valid inputs | R2 nightly |
| Security (Promptfoo) | MCP-specific red-team: tool-poisoning, unauthorized discovery | R1 critical subset |

## Tool Surface Lock Pattern

```python
# tests/golden/mcp/tool_surface_lock.json
{
  "tools": [
    {
      "name": "your_tool_name",
      "description_hash": "sha256:<hash>",   # hash changes = review required
      "input_schema_hash": "sha256:<hash>",
      "output_schema_hash": "sha256:<hash>"
    }
  ]
}
```

```python
# tests/eval/mcp/test_tool_surface_lock.py
import pytest
import json
import hashlib
import pathlib

HASHES_FILE = pathlib.Path("mcp/.tool-surface-hashes.json")

@pytest.mark.r1
def test_mcp_tool_surface_unchanged():
    """Tool schemas must not change without explicit regeneration of hash file.
    If this test fails: a tool schema changed without review.
    Fix: regenerate the hash file with your project's script, review the schema diff, and commit it.
    """
    current_hashes = load_current_mcp_tool_hashes()   # inspect live MCP server
    recorded_hashes = json.loads(HASHES_FILE.read_text())
    
    for tool_name, recorded in recorded_hashes["tools"].items():
        current = current_hashes.get(tool_name)
        assert current is not None, f"Tool {tool_name} no longer exists in MCP server"
        assert current["input_schema_hash"] == recorded["input_schema_hash"], (
            f"Input schema for {tool_name} changed. Regenerate and review the tool-surface hash file to acknowledge."
        )
```

## Tenant Isolation Test Pattern

```python
# tests/eval/mcp/test_tenant_isolation.py
import pytest

@pytest.mark.r1    # CI BLOCKER #4 — always blocks merge
async def test_mcp_cannot_access_cross_tenant_data(mcp_client_tenant_a):
    """Caller authenticated as Tenant A must not retrieve Tenant B's data.
    This is CI BLOCKER #4 — zero tolerance.
    """
    # Attempt to access a resource that belongs to tenant_b
    result = await mcp_client_tenant_a.call_tool(
        "your_search_tool",
        {"owner_id": "tenant_b_id", "resource_type": "example"}
    )
    assert result.is_error or len(result.items) == 0, (
        f"CI BLOCKER #4: Cross-tenant data returned: {result.items}"
    )

@pytest.mark.r1
async def test_mcp_rejects_invalid_token(mcp_client_invalid_token):
    """Requests with invalid/expired tokens must be rejected with 401."""
    result = await mcp_client_invalid_token.call_tool(
        "your_search_tool",
        {"owner_id": "any", "resource_type": "example"}
    )
    assert result.status_code == 401, f"Expected 401, got {result.status_code}"
```

## Audit Log Verification

```python
# tests/eval/mcp/test_audit_log.py
import pytest

WRITE_TOOLS = [
    # List all write/mutation tools in your MCP server here
    "your_create_tool",
    "your_update_tool",
    "your_delete_tool",
    "notification_send",
    "payment_process",
]

@pytest.mark.parametrize("tool_name", WRITE_TOOLS)
@pytest.mark.r1    # CI BLOCKER #8 — write tools must always emit audit log
async def test_write_tool_emits_audit_log(tool_name, mcp_client_valid, audit_log_fixture):
    """Every write tool must emit an audit log entry.
    CI BLOCKER #8: any write tool without audit log = merge blocked.
    """
    audit_log_fixture.clear()
    await mcp_client_valid.call_tool(tool_name, get_valid_payload(tool_name))
    
    entries = audit_log_fixture.get_entries()
    assert len(entries) >= 1, (
        f"CI BLOCKER #8: {tool_name} made no audit log entry"
    )
    assert entries[0]["tool"] == tool_name
    assert entries[0]["caller_id"] is not None
```

## Promptfoo MCP Security Config

```yaml
# tests/eval/promptfoo/mcp-security.yaml
providers:
  - type: mcp
    config:
      serverPath: mcp/your-project-mcp/
      env:
        DATABASE_URL: ${DATABASE_URL}

tests:
  - description: "search tool — valid call returns tool schema"
    vars:
      input: "Find resources matching criteria"
    assert:
      - type: is-valid-openai-tools-call    # validates tool call JSON schema
      - type: function-call-count
        max: 1                              # single tool (excessive-agency guard)
      - type: not-contains
        value: "tenant_id:"                 # no cross-tenant IDs leaked (BLOCKER #4)
```

## MCP Inspector — Interactive Debugging

```bash
# Launch MCP Inspector against a local MCP server (verify current CLI flags via Context7)
npx @modelcontextprotocol/inspector <command-that-starts-your-server>
# Use for: manual tool schema inspection, auth testing, response exploration. Not a CI check.
```

## Known Gotchas

| Gotcha | Fix |
|--------|-----|
| MCP auth-layer tenant isolation not yet enforced | Do not run MCP evals in staging until tenant scoping is implemented and merged |
| MCP Inspector needs a startable MCP server | Start dependencies (database, secrets) first |
| Tool surface lock hash mismatch after schema update | Regenerate the hash file, review the schema diff, commit it |
| Promptfoo MCP provider format may differ from REST provider | Verify via Context7 (`promptfoo`) — MCP provider config differs from HTTP provider |
