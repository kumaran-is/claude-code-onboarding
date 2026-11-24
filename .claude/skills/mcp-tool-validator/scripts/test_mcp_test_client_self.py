# tests/test_mcp_test_client_self.py
from types import SimpleNamespace

from mcp_test_client import AssertionEngine, surface_diff, surface_hashes


def _result(text: str, is_error: bool = False) -> SimpleNamespace:
    return SimpleNamespace(is_error=is_error, structured_content=None, content=[SimpleNamespace(type="text", text=text)])


def test_content_contains_passes_when_present() -> None:
    assert AssertionEngine().evaluate({"content_contains": "hello"}, _result("hello world"), 1.0) == []


def test_content_contains_fails_when_missing() -> None:
    failures = AssertionEngine().evaluate({"content_contains": "goodbye"}, _result("hello world"), 1.0)
    assert failures and "missing" in failures[0]


def test_unknown_assertion_fails() -> None:
    assert AssertionEngine().evaluate({"no_such_check": 1}, _result("x"), 1.0) == ["unknown assertion 'no_such_check'"]


def _tool(name: str, description: str = "d", schema: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name, description=description, input_schema=schema or {"type": "object"})


def test_surface_lock_unchanged_has_no_drift() -> None:
    locked = surface_hashes([_tool("a"), _tool("b")])
    assert surface_diff(locked, surface_hashes([_tool("b"), _tool("a")])) == {}


def test_surface_lock_reports_added_removed_and_changed_tools() -> None:
    locked = surface_hashes([_tool("a"), _tool("b")])
    current = surface_hashes([_tool("a", description="changed"), _tool("c")])
    assert surface_diff(locked, current) == {"added": ["c"], "removed": ["b"], "changed": ["a"]}


def test_surface_lock_detects_a_schema_only_change() -> None:
    locked = surface_hashes([_tool("a", schema={"type": "object", "properties": {"x": {"type": "string"}}})])
    current = surface_hashes([_tool("a", schema={"type": "object", "properties": {"x": {"type": "integer"}}})])
    assert surface_diff(locked, current) == {"changed": ["a"]}
