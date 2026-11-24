# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = ["jsonschema==4.26.0", "referencing==0.37.0", "pyyaml==6.0.4"]
# [tool.uv]
# exclude-newer = "2026-11-21T00:00:00Z"
# ///
"""Prompt drift detector: Git vs registry vs runtime (PRM section 17: reference/promptops-lifecycle.md section 5).

Inputs are provider-neutral files, so the check runs in CI without registry credentials:
  --prompts-root  the Git prompt tree (hash = validate_prompts.content_hash, the value the sync job records)
  --registry      a registry snapshot exported by your sync job:
                  {"prompts": [{"name": str, "labels": {"production": 4, "staging": 5},
                                "versions": [{"version": 5, "content_hash": "sha256:...", "created_at": "ISO-8601 or null"}]}]}
  --traces        optional JSON list / JSONL of {"prompt_name": str, "prompt_version": int} from production spans

Checks: staging-labelled version != Git hash before release (BLOCK, --mode prerelease) | registry version whose
hash matches no Git hash (current or changelog content_hash): edited outside Git | production behind Git main
for more than --max-behind-days | Git version never synced | registry prompt absent from Git | trace version
not at any label. Severities: BLOCK (exit 1) | REVIEW (exit 1 only with --strict). Exit 2: unreadable input.

Run:  uv run --script prompt_drift.py --prompts-root prompts --registry snapshot.json [--traces spans.jsonl]
                                      [--mode prerelease|scheduled] [--max-behind-days 7] [--today YYYY-MM-DD]
                                      [--strict] [--json drift.json]
      uv run --script prompt_drift.py --selftest
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from validate_prompts import Finding, content_hash, emit, load, prompt_files

TOOL = "prompt_drift"


def git_state(root: Path) -> dict[str, dict]:
    state = {}
    for path in prompt_files(root):
        card = load(path)
        known = {c["content_hash"] for c in card["changelog"] if c.get("content_hash")}
        state[card["name"]] = {"hash": content_hash(card), "known": known | {content_hash(card)},
                               "path": str(path.relative_to(root))}
    return state


def load_traces(path: Path | None) -> list[dict]:
    if path is None:
        return []
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if text.lstrip().startswith("[") else [json.loads(line) for line in text.splitlines() if line.strip()]


def detect(git: dict[str, dict], registry: dict, traces: list[dict], mode: str, max_behind: int,
           today: dt.date) -> list[Finding]:
    out: list[Finding] = []
    reg = {p["name"]: p for p in registry["prompts"]}
    for name, g in sorted(git.items()):
        entry = reg.get(name)
        if entry is None:
            out.append(Finding("DRIFT_NOT_SYNCED", "REVIEW", g["path"], "prompt has no registry entry; run the sync job."))
            continue
        by_version = {v["version"]: v for v in entry["versions"]}
        synced = [v for v in entry["versions"] if v["content_hash"] == g["hash"]]
        if not synced:
            out.append(Finding("DRIFT_NOT_SYNCED", "REVIEW", g["path"], "current Git content has no registry version."))
        labels = entry.get("labels", {})
        staging = by_version.get(labels.get("staging"))
        if mode == "prerelease" and (staging is None or staging["content_hash"] != g["hash"]):
            out.append(Finding("DRIFT_STAGING_MISMATCH", "BLOCK", name,
                               f"staging label (version {labels.get('staging')}) does not serve the Git release content."))
        newest = max(entry["versions"], key=lambda v: v["version"], default=None)
        checked = {v["version"]: v for v in [newest, *(by_version.get(n) for n in labels.values())] if v}
        for version, v in sorted(checked.items()):
            if v["content_hash"] not in g["known"]:
                out.append(Finding("DRIFT_REGISTRY_EDIT", "REVIEW", name,
                                   f"registry version {version} matches no Git content: edited outside Git; revert or back-port."))
        prod = by_version.get(labels.get("production"))
        if prod is not None and prod["content_hash"] != g["hash"] and synced:
            stamps = [dt.datetime.fromisoformat(v["created_at"]).date() for v in synced if v.get("created_at")]
            if not stamps:
                out.append(Finding("DRIFT_AGE_UNKNOWN", "REVIEW", name,
                                   "production differs from Git and the synced version has no created_at; record it at sync."))
            elif (today - min(stamps)).days > max_behind:
                first = min(stamps)
                out.append(Finding("DRIFT_PRODUCTION_BEHIND", "REVIEW", name,
                                   f"production label behind Git for {(today - first).days} days; confirm rollback or promote."))
    for name in sorted(set(reg) - set(git)):
        out.append(Finding("DRIFT_REGISTRY_ORPHAN", "REVIEW", name, "registry prompt has no Git prompt file (UI-only edit)."))
    for span in traces:
        entry = reg.get(span["prompt_name"])
        labelled = set((entry or {}).get("labels", {}).values())
        if span["prompt_version"] not in labelled:
            out.append(Finding("DRIFT_TRACE_UNLABELED", "REVIEW", span["prompt_name"],
                               f"production trace used version {span['prompt_version']}, which is at no label: stale cache or unauthorised caller."))
    unique: dict[tuple, Finding] = {}
    for f in out:
        unique.setdefault((f.rule, f.path, f.message), f)
    return list(unique.values())


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        from selftest_prompts import run_drift_selftest   # sibling fixtures
        return run_drift_selftest()
    parser = argparse.ArgumentParser(prog=TOOL)
    parser.add_argument("--prompts-root", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--traces", type=Path)
    parser.add_argument("--mode", choices=["prerelease", "scheduled"], default="scheduled")
    parser.add_argument("--max-behind-days", type=int, default=7)          # ADAPT: section 17 "<n> days"
    parser.add_argument("--today", type=dt.date.fromisoformat, default=dt.datetime.now(dt.UTC).date())
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    try:
        git = git_state(args.prompts_root)
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        traces = load_traces(args.traces)
    except (OSError, ValueError, KeyError) as exc:
        sys.stderr.write(f"{TOOL}: unreadable input ({type(exc).__name__})\n")
        return 2
    if not git:
        sys.stderr.write(f"{TOOL}: no prompt files under {args.prompts_root}; the check saw no input\n")
        return 2
    findings = detect(git, registry, traces, args.mode, args.max_behind_days, args.today)
    return emit(findings, args.strict, args.json, {"tool_mode": args.mode, "prompts": len(git), "traces": len(traces)},
                tool=TOOL)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
