"""MCP tool validator client (MCP Python SDK v2).

Lists every tool, checks the tool-surface lock and scenario coverage, calls each scenario and
evaluates its assertions.
Exit codes: 0 GREEN, 1 RED (scenario failures), 2 COVERAGE_GAP, 3 CONNECTION (transport/protocol),
4 SURFACE_DRIFT (a tool's name, description or input schema differs from the committed lock).
"""

import argparse
import hashlib
import json
import logging
import os
import re
import shlex
import sys
import time
from pathlib import Path
from typing import Any

import anyio
import httpx2
import yaml
from mcp import Client, MCPError, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger("mcp_test_client")
Assertion = str | None  # None = pass, str = failure message


class AssertionEngine:
    """One `_assert_<name>(expected, result, duration_ms)` per DSL key; all keys in a block are AND-ed."""

    def evaluate(self, spec: dict[str, Any], result: Any, duration_ms: float) -> list[str]:
        failures = []
        for name, expected in spec.items():
            check = getattr(self, f"_assert_{name}", None)
            if check is None:
                failures.append(f"unknown assertion {name!r}")
                continue
            message = check(expected, result, duration_ms)
            if message is not None:
                failures.append(message)
        return failures

    @staticmethod
    def _text(result: Any) -> str:
        return "\n".join(block.text for block in result.content if block.type == "text")

    def _json(self, result: Any) -> Any:
        if result.structured_content is not None:
            return result.structured_content
        try:
            return json.loads(self._text(result))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _as_list(value: str | list[str]) -> list[str]:
        return [value] if isinstance(value, str) else value

    def _assert_is_error(self, expected: bool, result: Any, _: float) -> Assertion:
        actual = bool(result.is_error)
        return None if actual == expected else f"is_error: expected {expected}, got {actual}"

    def _assert_content_type(self, expected: str, result: Any, _: float) -> Assertion:
        actual = result.content[0].type if result.content else None
        return None if actual == expected else f"content_type: expected {expected!r}, got {actual!r}"

    def _assert_content_contains(self, expected: str | list[str], result: Any, _: float) -> Assertion:
        text = self._text(result)
        missing = [s for s in self._as_list(expected) if s not in text]
        return f"content_contains: missing {missing}" if missing else None

    def _assert_content_not_contains(self, expected: str | list[str], result: Any, _: float) -> Assertion:
        text = self._text(result)
        found = [s for s in self._as_list(expected) if s in text]
        return f"content_not_contains: found {found}" if found else None

    def _assert_content_matches(self, expected: str, result: Any, _: float) -> Assertion:
        return None if re.search(expected, self._text(result)) else f"content_matches: no match for {expected!r}"

    def _assert_json_path(self, expected: dict[str, Any], result: Any, _: float) -> Assertion:
        data = self._json(result)
        for path, want in expected.items():
            node = data
            for key in path.split("."):
                if isinstance(node, list) and key.isdigit() and int(key) < len(node):
                    node = node[int(key)]
                elif isinstance(node, dict) and key in node:
                    node = node[key]
                else:
                    return f"json_path: {path} not found"
            if node != want:
                return f"json_path: {path} expected {want!r}, got {node!r}"
        return None

    def _results(self, result: Any) -> list[Any] | None:
        data = self._json(result)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for value in data.values():  # the first list field: {"results": [...]}, {"orders": [...]}
                if isinstance(value, list):
                    return value
        return None

    def _assert_min_results(self, expected: int, result: Any, _: float) -> Assertion:
        items = self._results(result)
        if items is None:
            return "min_results: response has no list"
        return None if len(items) >= expected else f"min_results: expected >= {expected}, got {len(items)}"

    def _assert_max_results(self, expected: int, result: Any, _: float) -> Assertion:
        items = self._results(result)
        if items is None:
            return "max_results: response has no list"
        return None if len(items) <= expected else f"max_results: expected <= {expected}, got {len(items)}"

    def _assert_error_contains(self, expected: str, result: Any, _: float) -> Assertion:
        if not result.is_error:
            return "error_contains: result is not an error"
        return None if expected.lower() in self._text(result).lower() else f"error_contains: {expected!r} not in error text"

    def _assert_max_duration_ms(self, expected: int, _: Any, duration_ms: float) -> Assertion:
        return None if duration_ms <= expected else f"max_duration_ms: took {duration_ms:.0f} ms > {expected}"


def coverage_gaps(tool_names: list[str], scenarios: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    gaps = {}
    for name in tool_names:
        cases = [case["name"] for case in scenarios.get(name, [])]
        if not any("happy_path" in c for c in cases):
            gaps[name] = "no happy_path case"
        elif not any("invalid_input" in c for c in cases):
            gaps[name] = "no invalid_input case"
        elif len(cases) < 3:
            gaps[name] = "fewer than 3 cases"
    for name in scenarios.keys() - set(tool_names):
        gaps[name] = "scenario for a tool the server does not list"
    return gaps


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def surface_hashes(tools: list[Any]) -> dict[str, str]:
    """sha256 over name + description + input schema per tool (tool-surface lock)."""
    hashes = {}
    for tool in tools:
        surface = {"name": tool.name, "description": tool.description, "inputSchema": tool.input_schema}
        hashes[tool.name] = "sha256:" + hashlib.sha256(_canonical(surface).encode()).hexdigest()
    return hashes


def surface_hash(hashes: dict[str, str]) -> str:
    """One hash for the whole surface, recorded with every eval result as tool_surface_hash."""
    return "sha256:" + hashlib.sha256(_canonical(hashes).encode()).hexdigest()


def surface_diff(locked: dict[str, str], current: dict[str, str]) -> dict[str, list[str]]:
    diff = {
        "added": sorted(current.keys() - locked.keys()),
        "removed": sorted(locked.keys() - current.keys()),
        "changed": sorted(name for name in locked.keys() & current.keys() if locked[name] != current[name]),
    }
    return {kind: names for kind, names in diff.items() if names}


def server_target(url: str) -> StdioServerParameters | str:
    if url.startswith("stdio://"):
        command, *args = shlex.split(url.removeprefix("stdio://"))
        return StdioServerParameters(command=command, args=args, env=dict(os.environ))
    return url


async def run(url: str, scenarios_path: Path, report_path: Path, lock_path: Path | None, update_lock: bool) -> int:
    scenarios = {s["tool"]: s["cases"] for s in yaml.safe_load(scenarios_path.read_text())["scenarios"]}
    engine = AssertionEngine()
    target = server_target(url)
    token = os.environ.get("MCP_TOKEN")
    results: list[dict[str, Any]] = []
    connection_error: BaseException | None = None
    try:
        async with httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"} if token else {}, timeout=httpx2.Timeout(30, read=300)
        ) as http:
            server = target if isinstance(target, StdioServerParameters) else streamable_http_client(target, http_client=http)
            async with Client(server) as client:
                listed = (await client.list_tools()).tools
                tools = [tool.name for tool in listed]
                hashes = surface_hashes(listed)
                if lock_path is not None and update_lock:
                    lock_path.write_text(json.dumps({"tools": hashes}, indent=2, sort_keys=True) + "\n")
                    logger.info("wrote tool-surface lock %s (%d tools); review the diff and justify it in the PR", lock_path, len(hashes))
                    return 0
                if lock_path is not None:
                    drift = surface_diff(json.loads(lock_path.read_text())["tools"], hashes)
                    if drift:
                        report_path.write_text(json.dumps({"verdict": "SURFACE_DRIFT", "drift": drift}, indent=2))
                        logger.error("tool surface differs from %s: %s", lock_path, drift)
                        return 4
                gaps = coverage_gaps(tools, scenarios)
                if gaps:
                    report_path.write_text(json.dumps({"verdict": "COVERAGE_GAP", "gaps": gaps}, indent=2))
                    logger.error("coverage gap: %s", gaps)
                    return 2
                for tool in tools:
                    for case in scenarios[tool]:
                        start = time.perf_counter()
                        result = await client.call_tool(tool, case.get("input", {}))
                        duration_ms = (time.perf_counter() - start) * 1000
                        failures = engine.evaluate(case.get("assert", {}), result, duration_ms)
                        results.append({"tool": tool, "scenario": case["name"], "passed": not failures,
                                        "failures": failures, "duration_ms": round(duration_ms, 1)})
                protocol_version = client.protocol_version
    except* (MCPError, OSError, httpx2.HTTPError) as group:
        # The SDK runs transports in a task group, so transport errors arrive wrapped in an ExceptionGroup.
        connection_error = group.exceptions[0]
    if connection_error is not None:
        logger.error("connection or protocol failure: %r", connection_error)
        report_path.write_text(json.dumps({"verdict": "CONNECTION", "error": repr(connection_error)}, indent=2))
        return 3
    failed = [r for r in results if not r["passed"]]
    verdict = "RED" if failed else "GREEN"
    report_path.write_text(json.dumps({"verdict": verdict, "protocol_version": protocol_version,
                                       "tool_surface_hash": surface_hash(hashes), "tools": len(tools),
                                       "passed": len(results) - len(failed), "failed": len(failed),
                                       "results": results}, indent=2))
    logger.info("%s: %d tools, %d scenarios, %d failed", verdict, len(tools), len(results), len(failed))
    return 1 if failed else 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Validate every MCP tool against scenarios.yaml")
    parser.add_argument("--server-url", default=os.environ.get("SERVER_URL", "http://localhost:8080/mcp"),
                        help="Streamable HTTP URL, or stdio://<command> <args>")
    parser.add_argument("--scenarios", type=Path, default=Path(os.environ.get("SCENARIOS_FILE", "tests/scenarios.yaml")))
    parser.add_argument("--report", type=Path, default=Path("tests/validation_report.json"))
    parser.add_argument("--surface-lock", type=Path, default=None,
                        help="committed tool-surface lock (JSON); a difference exits 4 before any tool is called")
    parser.add_argument("--update-surface-lock", action="store_true",
                        help="write the current surface to --surface-lock and exit 0 (an intentional, reviewed change)")
    args = parser.parse_args()
    if args.update_surface_lock and args.surface_lock is None:
        parser.error("--update-surface-lock needs --surface-lock")
    sys.exit(anyio.run(run, args.server_url, args.scenarios, args.report, args.surface_lock, args.update_surface_lock))


if __name__ == "__main__":
    main()
