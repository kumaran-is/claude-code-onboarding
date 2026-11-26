#!/usr/bin/env python3
"""Preflight, compatibility, and dry-run planner for `/setup-aidlc`.

Does not install AI-DLC, does not call `aidlc config` for real, and does not
copy upstream skills/agents/hooks. Tests use fixtures and mocked GitHub JSON.

Usage:
  check-aidlc-setup.py --selftest
  check-aidlc-setup.py --scan-skill
  check-aidlc-setup.py --discover --root DIR
  check-aidlc-setup.py --preflight --root DIR
  check-aidlc-setup.py --compat --root DIR [--plan PLAN.json]
  check-aidlc-setup.py --install-plan [--pin X.Y.Z] [--os darwin|linux|windows]
  check-aidlc-setup.py --latest-stable [--releases RELEASES.json]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
UPSTREAM_REPO = "awslabs/aidlc-workflows"
GITHUB_API_LATEST = f"https://api.github.com/repos/{UPSTREAM_REPO}/releases/latest"
GITHUB_API_RELEASES = f"https://api.github.com/repos/{UPSTREAM_REPO}/releases"
INSTALL_SH = f"https://github.com/{UPSTREAM_REPO}/releases/latest/download/install.sh"
INSTALL_PS1 = f"https://github.com/{UPSTREAM_REPO}/releases/latest/download/install.ps1"
DOCS_GETTING_STARTED = "https://awslabs.github.io/aidlc-workflows/guide/01-getting-started/"
DOCS_LIFECYCLE = "https://awslabs.github.io/aidlc-workflows/guide/18-install-and-lifecycle/"

TOOLKIT_COMMANDS = (
    "next.md",
    "verify.md",
    "ship.md",
    "ralph-loop.md",
    "review-code.md",
    "create-pr.md",
    "setup-aidlc.md",
)
TOOLKIT_SKILLS = (
    "next-issue",
    "verification-before-completion",
    "subagent-driven-development",
    "aws-aidlc-integration",
)
PROTECTED_SETTINGS = ("model",)
PROTECTED_PERMISSION_KEYS = ("defaultMode",)
PIPE_INSTALL_RE = re.compile(
    r"curl\s+[^\n]*install\.sh[^\n]*\|\s*(?:ba)?sh|"
    r"irm\s+[^\n]*install\.ps1[^\n]*\|\s*iex",
    re.I,
)
VERSION_RE = re.compile(r"^v?(\d+\.\d+\.\d+(?:-preview\.\d+\.\d+)?)$", re.I)

REQUIRED_SKILL_MARKERS = (
    "NEVER pipe",
    "aidlc config --harness claude",
    "aidlc doctor",
    "/aidlc",
    "human approval",
    "Do not copy",
    "independently",
    "model",
    "permissions",
)
FORBIDDEN_SKILL_MARKERS = (
    "property-harbor",
    "propertyharbor",
    "curl -fsSL https://github.com/awslabs/aidlc-workflows/releases/latest/download/install.sh | sh",
)


def normalize_tag(tag: str) -> str:
    text = (tag or "").strip()
    if text.lower().startswith("v") and text[1:2].isdigit():
        return text[1:]
    return text.lstrip("v") if text.startswith("v") else text


def is_preview(version: str) -> bool:
    return "preview" in normalize_tag(version).lower()


def parse_semver(version: str) -> tuple[int, int, int] | None:
    core = normalize_tag(version).split("-", 1)[0]
    parts = core.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


def version_cmp(a: str, b: str) -> int:
    pa, pb = parse_semver(a), parse_semver(b)
    if pa is None or pb is None:
        return 0 if normalize_tag(a) == normalize_tag(b) else -1
    return (pa > pb) - (pa < pb)


def latest_stable(releases: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick GitHub-style release objects. Skip drafts and previews."""
    stable: list[dict[str, Any]] = []
    for rel in releases:
        tag = str(rel.get("tag_name") or rel.get("tag") or "")
        if rel.get("draft") is True:
            continue
        if rel.get("prerelease") is True or is_preview(tag):
            continue
        if not parse_semver(tag):
            continue
        stable.append(rel)
    if not stable:
        raise ValueError("no stable AI-DLC release found")
    stable.sort(key=lambda r: parse_semver(str(r.get("tag_name") or r.get("tag"))) or (0, 0, 0), reverse=True)
    winner = stable[0]
    tag = str(winner.get("tag_name") or winner.get("tag"))
    return {"tag": tag, "version": normalize_tag(tag), "name": winner.get("name") or tag, "prerelease": False}


def fetch_latest_stable(url: str = GITHUB_API_LATEST, timeout: int = 15) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "claude-code-onboarding-aidlc-setup", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — GitHub API, TLS
        data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, list):
        return latest_stable(data)
    tag = str(data.get("tag_name") or "")
    if data.get("prerelease") or is_preview(tag):
        raise ValueError("latest endpoint returned a preview; pass --releases")
    return {"tag": tag, "version": normalize_tag(tag), "name": data.get("name") or tag, "prerelease": False}


def detect_os(name: str | None = None) -> str:
    raw = (name or platform.system()).lower()
    if raw.startswith("darwin") or raw == "mac" or raw == "macos":
        return "darwin"
    if raw.startswith("win"):
        return "windows"
    return "linux"


def which_aidlc(path_env: str | None = None) -> str | None:
    path = path_env if path_env is not None else os.environ.get("PATH", "")
    names = ("aidlc.exe", "aidlc") if os.name == "nt" else ("aidlc",)
    for directory in path.split(os.pathsep):
        if not directory:
            continue
        for name in names:
            candidate = Path(directory) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


def toolkit_present(root: Path) -> bool:
    return (root / ".claude" / "commands" / "next.md").is_file() and (root / ".claude" / "skills" / "next-issue" / "SKILL.md").is_file()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"_error": "unreadable"}
    return data if isinstance(data, dict) else {"_error": "not-object"}


def discover(root: Path, *, os_name: str | None = None, path_env: str | None = None, aidlc_version: str | None = None, available: str | None = None, claude_version: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    aidlc = which_aidlc(path_env)
    installed = aidlc_version
    if aidlc and installed is None:
        installed = "unknown"
    return {
        "project_root": str(root),
        "os": detect_os(os_name),
        "claude_version": claude_version or os.environ.get("CLAUDE_CODE_VERSION") or "unknown",
        "toolkit_present": toolkit_present(root),
        "aidlc_command": aidlc,
        "aidlc_installed_version": installed,
        "aidlc_available_version": available,
        "aidlc_dir": (root / "aidlc").is_dir(),
        "aidlc_pin": (root / ".aidlc-version").is_file(),
        "mismatch": bool(installed and available and installed not in {"unknown", ""} and version_cmp(installed, available) < 0),
        "partial": bool((root / "aidlc").is_dir() and not aidlc),
    }


def preflight(root: Path) -> dict[str, Any]:
    claude = root / ".claude"
    settings = read_json(claude / "settings.json") or {}
    mcp = read_json(root / ".mcp.json") or read_json(claude / "mcp.json")
    commands = sorted(p.name for p in (claude / "commands").glob("*.md")) if (claude / "commands").is_dir() else []
    skills = sorted(p.name for p in (claude / "skills").iterdir() if p.is_dir()) if (claude / "skills").is_dir() else []
    hooks_dir = claude / "hooks"
    hooks = sorted(p.name for p in hooks_dir.iterdir() if p.suffix in {".sh", ".py"}) if hooks_dir.is_dir() else []
    hook_events = list((settings.get("hooks") or {}).keys()) if isinstance(settings.get("hooks"), dict) else []
    permissions = settings.get("permissions") if isinstance(settings.get("permissions"), dict) else {}
    return {
        "claude_dir": claude.is_dir(),
        "settings": {
            "present": (claude / "settings.json").is_file(),
            "model": settings.get("model"),
            "permissions": permissions,
            "permission_keys": sorted(permissions.keys()) if permissions else [],
            "hook_events": hook_events,
            "unreadable": "_error" in settings,
        },
        "commands": commands,
        "skills": skills,
        "hooks_files": hooks,
        "mcp_present": bool(mcp),
        "mcp_servers": sorted((mcp or {}).get("mcpServers") or (mcp or {}).get("servers") or []) if isinstance(mcp, dict) and "_error" not in mcp else [],
        "aidlc_workspace": (root / "aidlc").is_dir(),
        "aidlc_command_file": (claude / "commands" / "aidlc.md").is_file() or any(n.startswith("aidlc") for n in commands),
    }


def pipe_install_forbidden(command: str) -> bool:
    return bool(PIPE_INSTALL_RE.search(command or ""))


def install_plan(*, os_name: str, pin: str | None = None, tag: str | None = None) -> dict[str, Any]:
    """Official installer: download, inspect, attest, then run. Never pipe."""
    os_key = detect_os(os_name)
    version = normalize_tag(pin or tag or "")
    tag_name = f"v{version}" if version else None
    if os_key == "windows":
        download = [
            f'New-Item -ItemType Directory -Force $env:TEMP\\aidlc-install | Out-Null',
            f'Invoke-WebRequest -Uri {INSTALL_PS1} -OutFile $env:TEMP\\aidlc-install\\install.ps1' if not tag_name else f'gh release download {tag_name} --repo github.com/{UPSTREAM_REPO} --dir $env:TEMP\\aidlc-install --pattern install.ps1 --pattern aidlc-release.intoto.jsonl',
            "Get-Content $env:TEMP\\aidlc-install\\install.ps1 | Select-Object -First 80",
            f'gh attestation verify $env:TEMP\\aidlc-install\\install.ps1 --bundle $env:TEMP\\aidlc-install\\aidlc-release.intoto.jsonl --repo {UPSTREAM_REPO} --signer-workflow {UPSTREAM_REPO}/.github/workflows/release.yml --hostname github.com' + (f' --source-ref refs/tags/{tag_name}' if tag_name else ""),
            "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force",
            "& $env:TEMP\\aidlc-install\\install.ps1" + (f" -Version {version}" if version else ""),
        ]
        forbidden = "irm https://github.com/awslabs/aidlc-workflows/releases/latest/download/install.ps1 | iex"
    else:
        download = [
            'tmp="$(mktemp -d)"',
            f'gh release download {tag_name or "$(gh release view --repo github.com/" + UPSTREAM_REPO + " --json tagName --jq .tagName)"} --repo github.com/{UPSTREAM_REPO} --dir "$tmp" --pattern install.sh --pattern aidlc-release.intoto.jsonl',
            'sed -n "1,80p" "$tmp/install.sh"',
            f'gh attestation verify "$tmp/install.sh" --bundle "$tmp/aidlc-release.intoto.jsonl" --repo {UPSTREAM_REPO} --signer-workflow {UPSTREAM_REPO}/.github/workflows/release.yml --hostname github.com --source-ref "refs/tags/{tag_name or "${tag}"}"',
            'sh "$tmp/install.sh"' + (f" --version {version}" if version else ""),
            'rm -rf "$tmp"',
        ]
        forbidden = f"curl -fsSL {INSTALL_SH} | sh"
    return {
        "os": os_key,
        "pin": version or None,
        "docs": DOCS_LIFECYCLE,
        "steps": download,
        "never": forbidden,
        "notes": [
            "Download the official installer to a file, inspect it, verify attestation/checksums, then run it.",
            "Do not pipe a remote script into a shell.",
            "The installer itself still verifies SHA-256; GitHub CLI attestation is additional.",
            "Human approval is required before running the installer.",
        ],
    }


def config_plan(*, pin: str | None = None, mcp: str = "none") -> dict[str, Any]:
    cmds = [
        "aidlc config --harness claude --dry-run",
        "aidlc config --harness claude --mcp none --yes" if mcp == "none" else f"aidlc config --harness claude --mcp {mcp} --yes",
        "aidlc doctor",
    ]
    if pin:
        cmds.insert(1, f"aidlc config --pin {normalize_tag(pin)}")
    return {
        "commands": cmds,
        "docs": DOCS_GETTING_STARTED,
        "preserve": ["model", "permissions.defaultMode", "existing hooks", "MCP servers already in .mcp.json"],
        "never": ["aidlc config --force", "overwrite .claude/commands/next.md", "change model or defaultMode"],
    }


def compatibility(root: Path, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fail-closed when official config would clobber toolkit ownership."""
    pf = preflight(root)
    blockers: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    settings = pf["settings"]
    plan = plan or {}

    overwrite = [str(x) for x in plan.get("overwrite") or plan.get("replace") or []]
    create = [str(x) for x in plan.get("create") or []]
    update = [str(x) for x in plan.get("update") or []]
    settings_changes = plan.get("settings_changes") or {}
    proposed_cmd = str(plan.get("install_command") or "")

    if pipe_install_forbidden(proposed_cmd):
        blockers.append("proposed install pipes a remote script into a shell; download, inspect, then run")
    if plan.get("force") is True or "--force" in str(plan.get("config_args") or ""):
        blockers.append("aidlc config --force is forbidden on a toolkit project (would replace managed files)")

    for path in overwrite:
        name = Path(path).name
        if name in TOOLKIT_COMMANDS or name in {"CLAUDE.md"}:
            blockers.append(f"plan would overwrite toolkit file {path}")
        if "/skills/" in path.replace("\\", "/") and any(s in path for s in TOOLKIT_SKILLS):
            blockers.append(f"plan would overwrite toolkit skill {path}")

    if settings_changes.get("model") not in (None, "", settings.get("model")):
        if settings.get("model"):
            blockers.append(f"plan would change settings.json model {settings.get('model')!r} → {settings_changes.get('model')!r}")
    perm_change = settings_changes.get("permissions") or {}
    if isinstance(perm_change, dict) and "defaultMode" in perm_change:
        current = (settings.get("permissions") or {}).get("defaultMode")
        if perm_change.get("defaultMode") != current:
            blockers.append("plan would change permissions.defaultMode")

    if any("commands/next.md" in x.replace("\\", "/") for x in update + overwrite):
        blockers.append("plan would modify /next")

    if "hooks" in settings_changes and settings_changes.get("hooks_mode") == "replace":
        blockers.append("plan would replace the entire hooks block (toolkit Stop/PreToolUse hooks would be lost)")

    if pf["aidlc_command_file"] and pf["claude_dir"]:
        notes.append("AI-DLC /aidlc already present; refresh uses official aidlc config, not a second orchestrator")

    if toolkit_present(root) and pf["aidlc_workspace"]:
        notes.append("toolkit /next and AI-DLC /aidlc can coexist; neither should invoke the other")

    if toolkit_present(root):
        warnings.append("aidlc config merges AI-DLC hook registrations and permissions.allow into .claude/settings.json; defaultMode and model must stay unchanged")
        warnings.append("run aidlc config --harness claude --dry-run and review create/update/merge counts before --yes")
        if settings.get("permission_keys") and settings.get("permission_keys") != ["defaultMode"]:
            warnings.append("permissions already have extra keys; confirm the dry-run keeps deny/ask and defaultMode")

    if plan.get("mcp") in {"defaults", "on", True}:
        warnings.append("enabling AI-DLC default MCP servers requires explicit approval; prefer --mcp none")

    collision = [c for c in pf["commands"] if c.startswith("aidlc") and c not in {"aidlc.md"}]
    if "next.md" in create:
        blockers.append("plan would create a second next.md")

    if pf["settings"].get("unreadable"):
        blockers.append(".claude/settings.json is unreadable; refuse to let official config rewrite it")

    # Conflicting skill/command names from the plan
    for path in create + overwrite:
        base = Path(path).name
        if base in TOOLKIT_COMMANDS and path not in (root / ".claude" / "commands" / base).as_posix():
            blockers.append(f"command name collision: {base}")

    if collision:
        warnings.append(f"extra aidlc command files: {collision}")

    missing_cli = plan.get("aidlc_missing") is True
    if missing_cli and plan.get("phase") == "config":
        blockers.append("aidlc CLI is missing; install the official CLI before config")

    verdict = "BLOCKED" if blockers else ("WARN" if warnings else "OK")
    return {
        "verdict": verdict,
        "blockers": blockers,
        "warnings": warnings,
        "notes": notes,
        "toolkit_present": toolkit_present(root),
        "independence": {
            "toolkit_owns": ["/next", "/verify", "/ship", "Ralph", "SDD", "stack skills"],
            "aidlc_owns": ["/aidlc", "AI-DLC phases", "aidlc/ workspace", "upstream updates"],
            "do_not_merge_orchestrators": True,
        },
    }


def recovery(root: Path, discover_info: dict[str, Any] | None = None) -> dict[str, Any]:
    info = discover_info or discover(root)
    steps: list[str] = []
    state = "clean"
    if info.get("aidlc_dir") and not info.get("aidlc_command"):
        state = "partial-project-without-cli"
        steps = [
            "Install the official CLI (download install.sh, inspect, attest, run).",
            "Then: aidlc config --harness claude --dry-run",
            "Do not delete aidlc/ until doctor says the workspace is foreign.",
        ]
    elif info.get("aidlc_command") and not info.get("aidlc_dir") and not info.get("aidlc_pin"):
        state = "cli-without-project"
        steps = [
            "From the project root: aidlc config --harness claude --dry-run",
            "Approve, then aidlc config --harness claude --mcp none --yes",
            "aidlc doctor",
        ]
    elif info.get("mismatch"):
        state = "version-mismatch"
        steps = [
            "aidlc version  # installed",
            "Compare to GitHub latest stable (releases/latest, not previews)",
            "aidlc update && aidlc config --harness claude --dry-run && aidlc doctor",
            "Or pin: aidlc config --pin <version> then refresh",
        ]
    elif info.get("aidlc_command") and info.get("aidlc_dir"):
        state = "configured"
        steps = ["aidlc doctor", "aidlc version"]
    else:
        state = "not-installed"
        steps = ["Follow install-plan after human approval."]
    return {"state": state, "steps": steps, "uninstall_docs": DOCS_LIFECYCLE, "uninstall": ["aidlc uninstall  # does not delete unrelated project files", "Review leftover paths; --purge does not delete unrelated content"]}


def scan_skill(skill_dir: Path = SKILL_DIR) -> list[str]:
    findings: list[str] = []
    skill = skill_dir / "SKILL.md"
    if not skill.is_file():
        return [f"missing {skill}"]
    text = skill.read_text(encoding="utf-8")
    for needle in REQUIRED_SKILL_MARKERS:
        if needle not in text:
            findings.append(f"SKILL.md missing {needle}")
    for bad in FORBIDDEN_SKILL_MARKERS:
        if bad.lower() in text.lower() and bad.startswith("curl"):
            findings.append("SKILL.md documents a piped installer; use download-then-run")
        elif bad.lower() in text.lower() and not bad.startswith("curl"):
            findings.append(f"SKILL.md contains forbidden marker: {bad}")
    if PIPE_INSTALL_RE.search(text):
        findings.append("SKILL.md contains a piped install command")
    cmd = skill_dir.parent.parent / "commands" / "setup-aidlc.md"
    if not cmd.is_file():
        findings.append("missing commands/setup-aidlc.md")
    else:
        body = cmd.read_text(encoding="utf-8")
        if "aws-aidlc-integration" not in body:
            findings.append("setup-aidlc.md must load the skill")
        if PIPE_INSTALL_RE.search(body):
            findings.append("setup-aidlc.md contains a piped install command")
    refs = skill_dir / "references"
    for name in ("official-commands.md", "compatibility.md"):
        if not (refs / name).is_file():
            findings.append(f"missing references/{name}")
    official = (refs / "official-commands.md").read_text(encoding="utf-8") if (refs / "official-commands.md").is_file() else ""
    if official and PIPE_INSTALL_RE.search(official):
        findings.append("official-commands.md contains a piped install command")
    if "2.11.5" in text and "do not hardcode" not in text.lower():
        findings.append("SKILL.md must not hardcode 2.11.5 as the install version")
    return findings


def selftest() -> int:
    fail = 0

    def check(name: str, got: Any, expect: Any) -> None:
        nonlocal fail
        if got != expect:
            print(f"  FAIL {name}: got {got!r} expected {expect!r}")
            fail += 1
        else:
            print(f"  ok   {name}")

    def check_true(name: str, pred: bool) -> None:
        check(name, bool(pred), True)

    check("positive-latest-skips-preview", latest_stable([
        {"tag_name": "v9.9.9-preview.20260101.1", "prerelease": True},
        {"tag_name": "v3.2.1"},
        {"tag_name": "v3.1.0"},
    ])["version"], "3.2.1")
    try:
        latest_stable([{"tag_name": "v9.9.9-preview.1", "prerelease": True}])
        check("negative-preview-only", True, False)
    except ValueError:
        check("negative-preview-only", True, True)
    check_true("negative-pipe-curl", pipe_install_forbidden("curl -fsSL https://github.com/awslabs/aidlc-workflows/releases/latest/download/install.sh | sh"))
    check_true("negative-pipe-iex", pipe_install_forbidden("irm https://github.com/awslabs/aidlc-workflows/releases/latest/download/install.ps1 | iex"))
    check("positive-download-not-pipe", pipe_install_forbidden('curl -fsSL .../install.sh -o "$tmp/install.sh"'), False)
    plan = install_plan(os_name="darwin", pin="3.2.1")
    check_true("positive-pin-in-plan", any("--version 3.2.1" in s for s in plan["steps"]))
    check_true("positive-never-pipe-documented", pipe_install_forbidden(plan["never"]))
    check("no-hardcoded-2115-in-plan", "2.11.5" in json.dumps(plan), False)

    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "empty"
        empty.mkdir()
        d = discover(empty, os_name="darwin", path_env="/nonexistent", available="3.2.1")
        check("empty-no-toolkit", d["toolkit_present"], False)
        check("empty-no-cli", d["aidlc_command"], None)
        pf = preflight(empty)
        check("empty-no-claude", pf["claude_dir"], False)
        compat = compatibility(empty, {"phase": "config", "aidlc_missing": True})
        check("empty-config-without-cli-blocked", compat["verdict"], "BLOCKED")

        toolkit = Path(td) / "toolkit"
        (toolkit / ".claude" / "commands").mkdir(parents=True)
        (toolkit / ".claude" / "skills" / "next-issue").mkdir(parents=True)
        (toolkit / ".claude" / "hooks").mkdir(parents=True)
        (toolkit / ".claude" / "commands" / "next.md").write_text("# /next\nNever chain the next issue.\n", encoding="utf-8")
        (toolkit / ".claude" / "skills" / "next-issue" / "SKILL.md").write_text("# next\n", encoding="utf-8")
        (toolkit / ".claude" / "settings.json").write_text(
            json.dumps({"model": "sonnet", "permissions": {"defaultMode": "auto"}, "hooks": {"Stop": []}}),
            encoding="utf-8",
        )
        (toolkit / ".claude" / "hooks" / "stop-ralph-loop.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        d = discover(toolkit, os_name="linux", path_env="/nonexistent", available="3.2.1")
        check("toolkit-detected", d["toolkit_present"], True)
        c = compatibility(toolkit, {})
        check("toolkit-compat-warn-not-block", c["verdict"], "WARN")
        check_true("toolkit-independence-note", c["independence"]["do_not_merge_orchestrators"])

        blocked = compatibility(toolkit, {"overwrite": [".claude/commands/next.md"]})
        check("conflict-overwrite-next", blocked["verdict"], "BLOCKED")
        blocked = compatibility(toolkit, {"settings_changes": {"model": "opus"}})
        check("conflict-model-change", blocked["verdict"], "BLOCKED")
        blocked = compatibility(toolkit, {"settings_changes": {"permissions": {"defaultMode": "bypassPermissions"}}})
        check("conflict-permissions-mode", blocked["verdict"], "BLOCKED")
        blocked = compatibility(toolkit, {"force": True})
        check("conflict-force", blocked["verdict"], "BLOCKED")
        blocked = compatibility(toolkit, {"install_command": "curl -fsSL https://github.com/awslabs/aidlc-workflows/releases/latest/download/install.sh | sh"})
        check("conflict-pipe-install", blocked["verdict"], "BLOCKED")
        blocked = compatibility(toolkit, {"hooks_mode": "replace", "settings_changes": {"hooks_mode": "replace", "hooks": {}}})
        check("conflict-replace-hooks", blocked["verdict"], "BLOCKED")
        mcp_warn = compatibility(toolkit, {"mcp": "defaults"})
        check_true("warn-mcp-defaults", mcp_warn["verdict"] in {"WARN", "BLOCKED"} and any("MCP" in w for w in mcp_warn["warnings"]))

        both = toolkit
        (both / "aidlc").mkdir()
        (both / ".claude" / "commands" / "aidlc.md").write_text("# /aidlc\n", encoding="utf-8")
        d = discover(both, os_name="darwin", path_env=str(both), available="3.2.1", aidlc_version="3.2.1")
        c = compatibility(both, {})
        check_true("coexist-ok", c["verdict"] != "BLOCKED")
        check_true("coexist-note", any("coexist" in n for n in c["notes"]))

        already = Path(td) / "aidlc-only"
        already.mkdir()
        (already / "aidlc").mkdir()
        (already / ".claude" / "commands").mkdir(parents=True)
        (already / ".claude" / "commands" / "aidlc.md").write_text("# /aidlc\n", encoding="utf-8")
        rec = recovery(already, discover(already, path_env="/nonexistent"))
        check("already-partial-without-cli", rec["state"], "partial-project-without-cli")

        bin_dir = Path(td) / "bin"
        bin_dir.mkdir()
        aidlc_bin = bin_dir / "aidlc"
        aidlc_bin.write_text("#!/bin/sh\necho mock\n", encoding="utf-8")
        aidlc_bin.chmod(0o755)
        cli_only = Path(td) / "cli-only"
        cli_only.mkdir()
        rec = recovery(cli_only, discover(cli_only, path_env=str(bin_dir), aidlc_version="3.1.0", available="3.2.1"))
        check("cli-without-project", rec["state"], "cli-without-project")
        rec = recovery(both, discover(both, path_env=str(bin_dir), aidlc_version="3.1.0", available="3.2.1"))
        check("upgrade-mismatch", rec["state"], "version-mismatch")

        preserve = compatibility(toolkit, {"settings_changes": {"model": "sonnet"}, "update": [".claude/settings.json"]})
        check("preserve-same-model", preserve["verdict"] != "BLOCKED", True)

        interrupted = Path(td) / "interrupted"
        interrupted.mkdir()
        (interrupted / "aidlc").mkdir()
        rec = recovery(interrupted, {"aidlc_dir": True, "aidlc_command": None, "mismatch": False, "aidlc_pin": False})
        check("interrupted-partial", rec["state"], "partial-project-without-cli")

    iso = scan_skill()
    if iso:
        print("  FAIL skill scan:")
        for f in iso:
            print(f"    - {f}")
        fail += 1
    else:
        print("  ok   skill scan")

    print("selftest PASS" if fail == 0 else "selftest FAIL")
    return 0 if fail == 0 else 2


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--scan-skill", action="store_true")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--compat", action="store_true")
    parser.add_argument("--install-plan", action="store_true")
    parser.add_argument("--config-plan", action="store_true")
    parser.add_argument("--recovery", action="store_true")
    parser.add_argument("--latest-stable", action="store_true")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--plan", type=Path, default=None)
    parser.add_argument("--releases", type=Path, default=None)
    parser.add_argument("--pin", default=None)
    parser.add_argument("--os", dest="os_name", default=None)
    parser.add_argument("--mcp", default="none")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.scan_skill:
        findings = scan_skill()
        if findings:
            for f in findings:
                print(f)
            return 1
        print("SCAN PASS")
        return 0
    root = (args.root or Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())).resolve()
    if args.latest_stable:
        try:
            if args.releases:
                data = json.loads(args.releases.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data = data.get("releases") or [data]
                result = latest_stable(data)
            else:
                result = fetch_latest_stable()
        except (ValueError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            print(json.dumps({"verdict": "BLOCKED", "reason": str(exc)}))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.install_plan:
        print(json.dumps(install_plan(os_name=args.os_name or platform.system(), pin=args.pin), indent=2, sort_keys=True))
        return 0
    if args.config_plan:
        print(json.dumps(config_plan(pin=args.pin, mcp=args.mcp), indent=2, sort_keys=True))
        return 0
    if args.discover:
        print(json.dumps(discover(root, os_name=args.os_name), indent=2, sort_keys=True))
        return 0
    if args.preflight:
        print(json.dumps(preflight(root), indent=2, sort_keys=True))
        return 0
    if args.compat:
        plan = json.loads(args.plan.read_text(encoding="utf-8")) if args.plan else {}
        result = compatibility(root, plan)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["verdict"] != "BLOCKED" else 1
    if args.recovery:
        print(json.dumps(recovery(root), indent=2, sort_keys=True))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
