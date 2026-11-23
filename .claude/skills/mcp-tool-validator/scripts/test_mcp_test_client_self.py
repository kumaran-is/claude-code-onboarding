# tests/test_mcp_test_client_self.py
from types import SimpleNamespace

from mcp_test_client import AssertionEngine


def _result(text: str, is_error: bool = False) -> SimpleNamespace:
    return SimpleNamespace(is_error=is_error, structured_content=None, content=[SimpleNamespace(type="text", text=text)])


def test_content_contains_passes_when_present() -> None:
    assert AssertionEngine().evaluate({"content_contains": "hello"}, _result("hello world"), 1.0) == []


def test_content_contains_fails_when_missing() -> None:
    failures = AssertionEngine().evaluate({"content_contains": "goodbye"}, _result("hello world"), 1.0)
    assert failures and "missing" in failures[0]


def test_unknown_assertion_fails() -> None:
    assert AssertionEngine().evaluate({"no_such_check": 1}, _result("x"), 1.0) == ["unknown assertion 'no_such_check'"]
