#!/usr/bin/env python3
"""Restore other MCP servers after `npx playwright init-agents --loop=claude`.

Observed on @playwright/test@1.65.1: that command *replaces* `.mcp.json` with a
file that contains only `mcpServers.playwright-test`. It does not merge.
Custom files under `.claude/agents/` that are not the three generated names
survive; the three `playwright-test-*.md` files are overwritten.

Usage:
  python3 merge-playwright-test-mcp.py --backup FILE --generated FILE --write FILE
  python3 merge-playwright-test-mcp.py --selftest

Exit: 0 ok, 1 merge finding, 2 usage or broken selftest.
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ALLOWED_PW = {"command": "npx", "args": ["playwright", "run-test-mcp-server"]}


def _is_toolkit_root(directory: Path) -> bool:
    d = directory.resolve()
    return (d / ".claude/scripts/lint-testing-tools.sh").is_file() and (
        d / ".claude/SKILLS_GUIDE.md"
    ).is_file()


def load_mcp(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be an object")
    servers = data.get("mcpServers")
    if servers is None:
        data["mcpServers"] = {}
    elif not isinstance(servers, dict):
        raise ValueError(f"{path}: mcpServers must be an object")
    return data


def merge(backup: dict[str, Any], generated: dict[str, Any]) -> dict[str, Any]:
    pw = (generated.get("mcpServers") or {}).get("playwright-test")
    if not isinstance(pw, dict):
        raise ValueError("generated file has no mcpServers.playwright-test object")
    extra = set(pw) - {"command", "args"}
    if extra:
        raise ValueError(f"playwright-test has unexpected keys: {sorted(extra)}")
    if {"command": pw.get("command"), "args": pw.get("args")} != ALLOWED_PW:
        raise ValueError(
            "playwright-test must be exactly "
            '{"command": "npx", "args": ["playwright", "run-test-mcp-server"]}'
        )
    out = dict(backup)
    servers = dict(backup.get("mcpServers") or {})
    servers["playwright-test"] = {"command": "npx", "args": list(ALLOWED_PW["args"])}
    out["mcpServers"] = servers
    return out


def run_merge(backup_path: Path, generated_path: Path, write_path: Path) -> list[str]:
    if not backup_path.is_file():
        return [f"backup missing: {backup_path}"]
    if not generated_path.is_file():
        return [f"generated missing: {generated_path}"]
    dest = write_path.resolve()
    if _is_toolkit_root(dest.parent):
        return [f"refusing to write {dest}: this is the toolkit checkout"]
    try:
        backup = load_mcp(backup_path)
        generated = load_mcp(generated_path)
        merged = merge(backup, generated)
    except (OSError, ValueError, json.JSONDecodeError) as err:
        return [str(err)]
    payload = json.dumps(merged, indent=2) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(dest)
    restored = sorted(k for k in merged["mcpServers"] if k != "playwright-test")
    print("merged playwright-test; restored", restored)
    return []


def selftest() -> int:
    fail = 0

    def check(name: str, got: object, want: object) -> None:
        nonlocal fail
        ok = got == want
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
        fail += not ok

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        bak = t / "bak.json"
        gen = t / "gen.json"
        out = t / "out.json"
        bak.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "chrome-devtools": {"command": "npx"},
                        "github": {"type": "http", "url": "https://example.invalid"},
                    }
                }
            ),
            encoding="utf-8",
        )
        gen.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "playwright-test": {
                            "command": "npx",
                            "args": ["playwright", "run-test-mcp-server"],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        findings = run_merge(bak, gen, out)
        check("positive-merge-no-findings", findings, [])
        servers = json.loads(out.read_text(encoding="utf-8"))["mcpServers"]
        check(
            "positive-merge-keeps-existing",
            sorted(servers),
            ["chrome-devtools", "github", "playwright-test"],
        )
        check(
            "positive-merge-uses-generated-playwright-test",
            servers["playwright-test"]["args"],
            ["playwright", "run-test-mcp-server"],
        )
        findings = run_merge(t / "missing.json", gen, out)
        check("negative-missing-backup", bool(findings), True)
        gen.write_text(json.dumps({"mcpServers": {"other": {}}}), encoding="utf-8")
        findings = run_merge(bak, gen, out)
        check("negative-generated-without-playwright-test", bool(findings), True)
        gen.write_text(
            json.dumps({"mcpServers": {"playwright-test": {}}}),
            encoding="utf-8",
        )
        findings = run_merge(bak, gen, out)
        check("negative-empty-playwright-test-object", bool(findings), True)
        kit_out = t / "kit" / ".mcp.json"
        kit_out.parent.mkdir()
        (t / "kit" / ".claude/scripts").mkdir(parents=True)
        (t / "kit" / ".claude/scripts/lint-testing-tools.sh").write_text("#\n", encoding="utf-8")
        (t / "kit" / ".claude/SKILLS_GUIDE.md").write_text("#\n", encoding="utf-8")
        gen.write_text(
            json.dumps({"mcpServers": {"playwright-test": ALLOWED_PW}}),
            encoding="utf-8",
        )
        findings = run_merge(bak, gen, kit_out)
        check("negative-refuse-toolkit-checkout", bool(findings), True)
    print("selftest " + ("PASS" if fail == 0 else "FAIL"))
    return 2 if fail else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--generated", type=Path)
    parser.add_argument("--write", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if not (args.backup and args.generated and args.write):
        parser.error("--backup, --generated and --write are required (or --selftest)")
    findings = run_merge(args.backup, args.generated, args.write)
    if findings:
        for line in findings:
            print(line, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
