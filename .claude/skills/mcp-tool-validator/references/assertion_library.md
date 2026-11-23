# Assertion Library Reference

Full inventory of built-in assertions in `mcp_test_client.py` →
`AssertionEngine`. Read when you need an assertion that's not in the
quick-reference table.

## Protocol-level

### `is_error: bool`
Asserts on the MCP `isError` flag in `tools/call` response.
```yaml
assert:
  is_error: false   # tool succeeded
  is_error: true    # tool returned an error response (still a valid MCP message)
```

### `content_type: str`
Asserts type of FIRST content block.
Allowed: `text`, `image`, `resource`, `audio`.
```yaml
assert:
  content_type: text
```

## Text content

### `content_contains: str | list[str]`
All listed substrings must appear in concatenated text content.
```yaml
content_contains: "ord_002"
content_contains: ["ord_002", "shipped", "1500"]
```

### `content_not_contains: str | list[str]`
None of the listed tokens may appear.
Useful for catching uncaught errors:
```yaml
content_not_contains: ["Traceback", "null", "undefined", "Error:"]
```

### `content_matches: str` (regex)
Python `re.search()` against text content.
```yaml
content_matches: "\\$\\d{3,7}\\.\\d{2}"   # USD price format
```

## Structured (JSON) content

When tools return JSON-serialized text, these assertions parse it.

### `json_path: dict[str, Any]`
Dotted-path equality. Path supports dict keys and integer list indices.
```yaml
json_path:
  status: "ok"
  results.0.id: "ord_001"
  metadata.total: 42
  results: []        # exact equality with empty list
```

### `min_results: int` / `max_results: int`
For tools returning a list, or an object whose first list-valued field is the result set (`{"results": [...]}`, `{"orders": [...]}`). Reads `structuredContent` first, then JSON text content.
```yaml
min_results: 1   # at least one result
max_results: 100 # respects pagination cap
```

## Errors

### `error_contains: str`
Substring match on text content when `is_error: true`. Case-insensitive.
```yaml
assert:
  is_error: true
  error_contains: "permission denied"
```

## Performance

### `max_duration_ms: int`
Tool must respond within budget. The client times every `tools/call`, so this assertion always has a measured duration.
```yaml
max_duration_ms: 2000
```

## Combining assertions

All assertions in one `assert` block are AND-ed. There is no OR. If you need OR semantics, write two scenarios.

```yaml
assert:
  is_error: false
  content_type: text
  content_contains: ["ord_002"]
  min_results: 1
  max_duration_ms: 3000
```

## Adding a custom assertion

Edit `AssertionEngine` in `mcp_test_client.py`:

```python
def _assert_has_field(self, expected: str, result: Any, _: float) -> str | None:
    """Assert response JSON has a top-level field with given name."""
    data = self._json(result)
    if not isinstance(data, dict):
        return f"has_field: response is not a JSON object"
    if expected not in data:
        return f"has_field: missing field {expected!r}"
    return None
```

Then use in scenarios:
```yaml
assert:
  has_field: "request_id"
```

## Anti-patterns to avoid

- **Asserting on exact timestamps or UUIDs** — flaky. Use regex or invariants.
- **Asserting on full response equality** — tightly coupled to implementation. Prefer multiple targeted assertions.
- **Empty `assert` block** — no-op, will always pass. Use `is_error: false` at minimum.
- **Asserting on log lines or stderr** — out of scope; this validates the protocol response only.
