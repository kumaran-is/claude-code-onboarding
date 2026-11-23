# Scenario Schema Reference

Read this when authoring or extending `scenarios.yaml`.

## Top-level structure

```yaml
scenarios:
  - tool: <tool_name_as_registered_in_tools_list>
    cases:
      - name: <unique_identifier>
        input: { ...arguments passed to tools/call... }
        assert: { ...one or more assertions... }
```

## Required case types per tool

The client's coverage check enforces ≥3 cases per tool, including:
- A case with `happy_path` in the name
- A case with `invalid_input` in the name

The third can be any of: `edge_case_*`, `auth_*`, `boundary_*`, `error_*`.

## Assertion DSL — quick reference

| Assertion | Type | Example | Meaning |
|-----------|------|---------|---------|
| `is_error` | bool | `is_error: true` | MCP `isError` flag on response |
| `content_type` | string | `content_type: text` | First content block's `type` field |
| `content_contains` | str or list | `content_contains: ["ord_002", "shipped"]` | All substrings present in text |
| `content_not_contains` | str or list | `content_not_contains: ["null", "undefined"]` | No forbidden tokens |
| `content_matches` | regex string | `content_matches: "\\d{3}-\\d{4}"` | Regex matches text |
| `json_path` | dict | `json_path: { "results.0.id": 42 }` | Dotted-path equality on parsed JSON |
| `min_results` | int | `min_results: 1` | List length ≥ N |
| `max_results` | int | `max_results: 50` | List length ≤ N |
| `error_contains` | string | `error_contains: "permission"` | Substring in error response text |
| `max_duration_ms` | int | `max_duration_ms: 2000` | Tool returned within budget |

## Authoring discipline

1. **One scenario, one assertion theme.** If you need to assert 5 different things, split into 5 scenarios with descriptive names.
2. **Inputs should be minimal.** Only include keys the tool needs for the scenario.
3. **No environment leakage.** Don't put real API keys, real user IDs, or production data in scenarios. Use seeded test fixtures.
4. **Assertions over invariants, not snapshots.** Prefer `min_results: 1` over asserting on exact result IDs that may change.
5. **Name scenarios for behavior, not implementation.** `happy_path_search_by_customer` is good; `test_case_1` is bad.

## Adding a new assertion type

1. Edit `mcp_test_client.py` → `AssertionEngine`
2. Add a method `_assert_<name>(self, expected, result, duration_ms) -> str | None`
3. Return `None` on pass, error string on fail
4. Document it in this file's table and in `assertion_library.md`
