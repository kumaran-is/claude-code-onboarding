#!/usr/bin/env python3
"""Enforcement kit hook: findings ledger, fresh-evidence PR gate and UI-evidence reminder.

One script, registered for five events; it dispatches on hook_event_name. Opt-in parts act only when
the kit is ON for the branch (`python3 .claude/scripts/review_state.py init`, or CLAUDE_ENFORCEMENT_KIT=1):

  SubagentStart  reviewer agent -> inject the FINDING-line contract (additionalContext)
  SubagentStop   reviewer agent -> record its FINDING lines in the ledger; no contract line -> block once
                 (bounded by stop_hook_active), then record a MEDIUM "report unparsed" finding instead
  PreToolUse     Agent: block re-dispatching a reviewer that still owns open findings
                 Bash:  `gh pr create|merge` / `gh api .../pulls` need a VALID `verify` stamp
                        (kit OFF: advisory only; kit ON: deny, unless REVIEW_GATE_OVERRIDE="<reason>")
  Stop           kit ON: block while findings block (bounded by stop_hook_active)
                 always: UI files changed without a VALID ui-web / ui-mobile stamp -> one reminder per
                         tree state (systemMessage; kit ON: one bounded block)

Reviewer = a project agent whose frontmatter disallows Write and Edit (read-only analysis agents), so the
set follows .claude/agents/ instead of a hard-coded list. Delivery follows the hooks reference: PreToolUse
permissionDecision, Stop/SubagentStop decision+reason, additionalContext, systemMessage.

Test: python3 .claude/hooks/enforcement-kit.py --selftest
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_state():
    spec = importlib.util.spec_from_file_location("review_state", HERE.parent / "scripts" / "review_state.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rs = load_state()
WEB_RE = re.compile(r"(\.(tsx|jsx)$|\.component\.(ts|html|scss|css)$|(^|/)src/app/.+\.(ts|html|scss|css)$)")
SKIP_RE = re.compile(r"(^|/)(\.claude|docs|e2e|test|tests|__tests__|node_modules)/|\.(spec|test)\.[jt]sx?$|_test\.dart$")


def emit(obj: dict) -> int:
    print(json.dumps(obj))
    return 0


def is_reviewer(root: Path, agent_type: str) -> bool:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", agent_type or ""):
        return False
    path = root / ".claude" / "agents" / f"{agent_type}.md"
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").split("\n")
    if not lines or lines[0].strip() != "---":
        return False
    block, inside = [], False  # `disallowedTools: Write, Edit` or the YAML list form
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("disallowedTools:"):
            inside = True
            block.append(line)
        elif inside and re.match(r"\s*-\s", line):
            block.append(line)
        else:
            inside = False
    text = " ".join(block)
    return bool(re.search(r"\bWrite\b", text) and re.search(r"\bEdit\b", text))


# ── PR gate ───────────────────────────────────────────────────────────────────────────────────────
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def split_commands(cmd: str) -> list[str]:
    """Split a shell command into simple commands: heredoc bodies dropped, quotes respected."""
    out, delim = [], None
    for line in cmd.split("\n"):
        if delim is not None:
            if line.strip() == delim:
                delim = None
            continue
        out.append(line)
        m = HEREDOC_RE.search(line.replace("<<<", "   "))
        delim = m.group(2) if m else None
    text, segs, cur, quote, i = "\n".join(out), [], [], "", 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = ""
            elif ch == "\\" and quote == '"' and i + 1 < len(text):
                cur.append(ch)
                i += 1
                ch = text[i]
            cur.append(ch)
        elif ch in "'\"":
            quote = ch
            cur.append(ch)
        elif ch == "\\" and i + 1 < len(text):
            cur.append(" " if text[i + 1] == "\n" else text[i:i + 2])
            i += 1
        elif ch in ";&|\n()`":
            segs.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    segs.append("".join(cur))
    return [s for s in segs if s.strip()]


WRAPPERS = {"command", "env", "time", "sudo", "nohup", "exec", "builtin", "{", "!",
            "if", "then", "else", "elif", "while", "until", "do"}
GH_GLOBAL_FLAGS = {"-R", "--repo", "--hostname"}
PULLS_WRITE_RE = re.compile(r"(^|/)pulls/?$|/pulls/\d+/merge/?$")
GRAPHQL_RE = re.compile(r"\b(createPullRequest|mergePullRequest|enablePullRequestAutoMerge)\b")


def gh_args(toks: list[str]) -> tuple[list[str] | None, str]:
    """(arguments after `gh`, REVIEW_GATE_OVERRIDE assigned in front of it) when the simple command runs gh.
    Wrappers, shell keywords, env assignments and gh global flags are skipped; the override counts only as an
    assignment prefix of this very command, never as text elsewhere (a PR body may mention it)."""
    override = ""
    while toks and (toks[0] in WRAPPERS or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", toks[0]) or toks[0].startswith("-") and toks[0] != "--"):
        if toks[0].startswith("REVIEW_GATE_OVERRIDE="):
            override = toks[0].split("=", 1)[1]
        toks = toks[1:]  # `env -i`, `time -p`, `sudo -u x` flags are skipped crudely; good enough for a reminder gate
    if not toks or os.path.basename(toks[0]) != "gh":
        return None, ""
    args = toks[1:]
    while args and (args[0] in GH_GLOBAL_FLAGS or args[0].split("=")[0] in GH_GLOBAL_FLAGS):
        args = args[2:] if "=" not in args[0] else args[1:]
    return args, override


def pr_segments(cmd: str) -> tuple[list[str], str]:
    """Return (gated gh invocations, override reason) for a Bash command, anchored at command position.

    Covers `gh pr create|merge`, `gh api` writes to .../pulls or .../pulls/N/merge, and GraphQL create/merge
    mutations, behind `command`/`env`/`time`/`sudo`, env assignments, `-R owner/repo` and an absolute gh path.
    Out of scope (a cooperative-agent reminder, not a sandbox): `bash -c "..."`, `xargs gh`, aliases."""
    hits, overrides = [], []
    for seg in split_commands(cmd):
        try:
            toks = shlex.split(seg)
        except ValueError:
            toks = seg.split()  # unbalanced quoting: fall back to whitespace so a gh command is still seen
        args, seg_override = gh_args(toks)
        if not args:
            continue
        before = len(hits)
        if args[0] == "pr" and len(args) > 1 and args[1] in ("create", "merge"):
            hits.append(f"gh pr {args[1]}")
        elif args[0] == "api":
            method = next((args[k + 1].upper() for k, a in enumerate(args[:-1]) if a in ("-X", "--method")), "")
            method = method or next((a.split("=", 1)[1].upper() for a in args if a.startswith("--method=")), "")
            method = method or next((a[2:].upper() for a in args if re.fullmatch(r"-X[A-Za-z]+", a)), "")
            fields = any(a in ("-f", "-F", "--field", "--raw-field", "--input") or a.startswith(("--field=", "--raw-field=")) for a in args)
            writes = method in ("POST", "PUT", "PATCH") or (not method and fields)
            path = next((a for a in args[1:] if "/pulls" in a and not a.startswith("-")), "")
            if path and writes and PULLS_WRITE_RE.search(path.split("?")[0]):
                hits.append("gh api .../pulls (create or merge)")
            elif "graphql" in args and GRAPHQL_RE.search(seg):
                hits.append("gh api graphql (create or merge a PR)")
        if len(hits) > before:
            overrides.append(seg_override)
    # every gated invocation needs its own override; one unprefixed gh means no override at all
    return hits, (overrides[0] if overrides and all(o == overrides[0] for o in overrides) and overrides[0] else "")


def on_bash(root: Path, payload: dict) -> int:
    hits, override = pr_segments((payload.get("tool_input") or {}).get("command", ""))
    if not hits:
        return 0
    status, why = rs.stamp_check(root, "verify")
    if status == "VALID":
        return 0
    enabled = rs.is_enabled(root)
    fix = ("Run /verify on the current tree (it writes the stamp with "
           "`python3 .claude/scripts/review_state.py stamp write verify --note \"<checks and counts>\"` after every check PASSES).")
    if enabled and len(override.strip()) < 10:
        return emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                     "permissionDecisionReason": f"Enforcement kit: {hits[0]} needs fresh verification evidence; stamp is {status} ({why}). {fix} "
                                                 "A deliberate exception: prefix REVIEW_GATE_OVERRIDE=\"<reason, 10+ chars>\" and state the reason in the PR."}})
    note = f"override: {override.strip()}" if enabled else "advisory (kit off)"
    return emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
                 f"Verification evidence for {hits[0]} is {status} ({why}); {note}. Stale or missing evidence is not evidence: say so in the PR, or {fix}"}})


# ── reviewer contract, recording and dispatch gate ────────────────────────────────────────────────
def on_subagent_start(root: Path, payload: dict) -> int:
    if rs.is_enabled(root) and is_reviewer(root, payload.get("agent_type", "")):
        return emit({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": rs.CONTRACT}})
    return 0


def on_subagent_stop(root: Path, payload: dict) -> int:
    agent, agent_id = payload.get("agent_type", ""), payload.get("agent_id", "")
    if not (rs.is_enabled(root) and is_reviewer(root, agent)):
        return 0
    text = payload.get("last_assistant_message") or ""
    with rs.ledger(root, write=True) as data:
        status, n = rs.record_report(data, agent, agent_id, text)
        if status == "missing" and payload.get("stop_hook_active"):
            rs.add_finding(data, agent, "MEDIUM", "reviewer report had no FINDING contract lines; triage it by hand", "-", agent_id)
            data["reports"][agent_id or f"anon-{len(data['reports']) + 1}"] = {"reviewer": agent, "at": rs.time.time(), "count": 0}
    if status == "missing" and not payload.get("stop_hook_active"):
        return emit({"decision": "block", "reason": rs.CONTRACT + " Add those lines now; nothing else needs to change."})
    return 0


def on_agent(root: Path, payload: dict) -> int:
    target = (payload.get("tool_input") or {}).get("subagent_type", "")
    if not (rs.is_enabled(root) and is_reviewer(root, target)):
        return 0
    with rs.ledger(root) as data:  # same rule as Stop: from round 3 MEDIUM/LOW no longer hold up a re-review
        owned = [f for f in rs.blocking(data) if f["reviewer"] == target]
    if not owned:
        return 0
    ids = ", ".join(f"{f['id']} ({f['severity']}, {f['state']})" for f in owned[:8])
    return emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                 "permissionDecisionReason": f"Enforcement kit: {target} still owns open findings {ids}. Fix each and close it with evidence "
                                             "(`review_state.py findings close ID --class CONTROL|MECHANISM|STATIC|NOCONTROL --evidence ...`), "
                                             "record a failed fix (`findings fail ID --note ...`) or dismiss it with a reason; then re-dispatch for verification."}})


# ── Stop: open findings + UI evidence ─────────────────────────────────────────────────────────────
def changed_files(root: Path) -> list[str]:
    files: set[str] = set()
    for base in ("origin/HEAD", "origin/develop", "origin/main", "develop", "main"):
        try:
            mb = rs.git("merge-base", "HEAD", base, cwd=root)
            files |= set(rs.git("diff", "--name-only", "--relative", f"{mb}...HEAD", cwd=root).splitlines())
            break
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            continue
    for args in (("diff", "--name-only", "--relative", "HEAD"), ("ls-files", "--others", "--exclude-standard")):
        try:
            files |= set(rs.git(*args, cwd=root).splitlines())
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            pass
    return sorted(f for f in files if f)


def ui_targets(root: Path, files: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"ui-web": [], "ui-mobile": []}
    for f in files:
        if SKIP_RE.search(f):
            continue
        if WEB_RE.search(f):
            out["ui-web"].append(f)
        elif f.endswith(".dart") and "/lib/" in f"/{f}":
            pkg = f"/{f}".split("/lib/")[0].lstrip("/")
            if (root / pkg / "pubspec.yaml").is_file():
                out["ui-mobile"].append(f)
    return {k: v for k, v in out.items() if v}


def ui_reminder(root: Path) -> tuple[str, str]:
    """Return (message, marker path) when UI changed without a VALID stamp and this tree was not reminded yet."""
    targets = ui_targets(root, changed_files(root))
    stale = {k: v for k, v in targets.items() if rs.stamp_check(root, k)[0] != "VALID"}
    if not stale:
        return "", ""
    marker = rs.state_dir(root) / f"ui-reminded-{rs.fingerprint(root)[:16]}"
    if marker.is_file():
        return "", ""
    for old in marker.parent.glob("ui-reminded-*"):  # only the current tree state needs a marker
        old.unlink(missing_ok=True)
    tool = {"ui-web": "web: Playwright CLI or @playwright/test", "ui-mobile": "Flutter Android/iOS: Maestro"}
    parts = [f"{k} ({len(v)} file(s), e.g. {v[0]}; {tool[k]})" for k, v in stale.items()]
    msg = ("UI code changed with no executed test evidence for the current tree: " + "; ".join(parts) +
           ". Run it and record `python3 .claude/scripts/review_state.py stamp write <ui-web|ui-mobile> --note \"<command, counts>\"`, "
           "or report the check as NOT RUN or BLOCKED with the reason (.claude/rules/testing-tool-selection.md). Never a browser for the mobile app.")
    return msg, str(marker)


def on_stop(root: Path, payload: dict) -> int:
    active = bool(payload.get("stop_hook_active"))
    enabled = rs.is_enabled(root)
    reasons: list[str] = []
    notices: list[str] = []
    if enabled and (rs.state_dir(root) / "ledger.json").is_file():
        with rs.ledger(root) as data:
            rows = rs.blocking(data)
            rnd = rs.review_round(data)
        seen = rs.state_dir(root) / "stop-blocked.txt"  # block once per set of blocking findings, not every turn
        ids = ",".join(sorted(f["id"] + f["state"] for f in rows))
        already = seen.is_file() and seen.read_text() == ids
        if rows and not already:
            seen.write_text(ids)
        if rows and already:
            notices = [f"{len(rows)} finding(s) still block (unchanged since the last stop): `review_state.py findings list`."]
        else:
            notices = []
        if rows and not already:
            listing = "; ".join(f"{f['id']} {f['severity']} {f['reviewer']}: {f['summary'][:80]}" for f in rows[:6])
            reasons.append(f"{len(rows)} finding(s) still block (review round {rnd}): {listing}. Close each with evidence, "
                           "record a failed fix, or dismiss with a reason (`python3 .claude/scripts/review_state.py findings list`).")
    try:
        ui_msg, marker = ui_reminder(root)
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        ui_msg, marker = "", ""
    if marker:
        Path(marker).parent.mkdir(parents=True, exist_ok=True)
        Path(marker).write_text("reminded\n")
    if ui_msg and enabled:
        reasons.append(ui_msg)
    if reasons and not active:
        return emit({"decision": "block", "reason": "Enforcement kit: " + " ".join(reasons)})
    if reasons:  # second stop in a row: never loop, surface it to the user instead
        return emit({"systemMessage": "Enforcement kit (not blocking again): " + " ".join(reasons)})
    if ui_msg or notices:
        return emit({"systemMessage": " ".join(notices + ([ui_msg] if ui_msg else []))})
    return 0


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw or "{}")
    except ValueError:
        return 0
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
    if payload.get("tool_name") == "Bash" and not pr_segments((payload.get("tool_input") or {}).get("command", ""))[0]:
        return 0  # the common case costs no git call
    try:
        rs.git("rev-parse", "--git-dir", cwd=root)
    except (RuntimeError, OSError):
        return 0  # not a git work tree: nothing to fingerprint or diff
    except subprocess.TimeoutExpired:  # loud, never a silent skip
        return emit({"systemMessage": "enforcement-kit: git did not answer in time; review/PR gates were NOT checked for this call."})
    event = payload.get("hook_event_name", "")
    try:
        if event == "PreToolUse":
            tool = payload.get("tool_name", "")
            return on_bash(root, payload) if tool == "Bash" else on_agent(root, payload) if tool in ("Agent", "Task") else 0
        handler = {"SubagentStart": on_subagent_start, "SubagentStop": on_subagent_stop, "Stop": on_stop}.get(event)
        return handler(root, payload) if handler else 0
    except Exception as exc:  # noqa: BLE001 - a hook must not crash the session; report it instead of failing silently
        return emit({"systemMessage": f"enforcement-kit hook error on {event}: {type(exc).__name__}: {exc}"})


# ── selftest ──────────────────────────────────────────────────────────────────────────────────────
def selftest() -> int:
    import tempfile
    fails = 0

    def run(root: Path, payload: dict, env: dict | None = None) -> tuple[int, dict]:
        e = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), **(env or {})}
        e.pop("CLAUDE_ENFORCEMENT_KIT", None) if not (env and "CLAUDE_ENFORCEMENT_KIT" in env) else None
        p = subprocess.run([sys.executable, __file__], input=json.dumps(payload), capture_output=True, text=True, env=e, timeout=60)
        try:
            return p.returncode, json.loads(p.stdout) if p.stdout.strip() else {}
        except ValueError:
            return p.returncode, {"raw": p.stdout + p.stderr}

    def ok(cond: bool, label: str, got=None) -> None:
        nonlocal fails
        print(f"  {'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f" -> {got}"))
        fails += 0 if cond else 1

    def deny(out: dict) -> bool:
        return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        g = lambda *a: rs.git(*a, cwd=root)  # noqa: E731
        g("init", "-q"); g("config", "user.email", "t@example.invalid"); g("config", "user.name", "t")
        (root / ".gitignore").write_text(".claude/state/\n")
        agents = root / ".claude" / "agents"; agents.mkdir(parents=True)
        (agents / "x-reviewer.md").write_text("---\nname: x-reviewer\ndisallowedTools: Write, Edit\n---\nbody\n")
        (agents / "builder.md").write_text("---\nname: builder\ntools: Read, Write, Edit\n---\nbody\n")
        (root / "README.md").write_text("x\n"); g("add", "-A"); g("commit", "-qm", "init")
        bash = lambda c: {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": c}}  # noqa: E731

        # kit OFF
        rc, out = run(root, {"hook_event_name": "SubagentStart", "agent_type": "x-reviewer", "agent_id": "s0"})
        ok(out == {}, "negative: kit off -> no contract injected", out)
        rc, out = run(root, bash("gh pr create --fill"))
        ok(not deny(out) and "MISSING" in json.dumps(out), "kit off: gh pr create with no stamp -> advisory, not a deny", out)
        rc, out = run(root, bash('echo "gh pr create" && git status'))
        ok(out == {}, "negative: 'gh pr create' inside an argument is not at command position", out)
        heredoc = "python3 - <<'PY'\nprint(1)\ngh pr create \\\n  --fill\nPY\ngit status"
        rc, out = run(root, bash(heredoc))
        ok(out == {}, "negative: 'gh pr create' inside a heredoc body is not a command", out)
        rc, out = run(root, bash('git commit -m "notes\ngh pr merge 7"'))
        ok(out == {}, "negative: 'gh pr merge' inside a multi-line quoted argument is not a command", out)
        rc, out = run(root, bash("cd sub\ngh pr create --fill"))
        ok("MISSING" in json.dumps(out), "positive: a command on its own line after a newline is still seen", out)
        for shape in ['gh pr create --title t --body "line1\nline2; a | b && c"',
                      "cd x && gh pr create --title 'a; b'",
                      'gh pr create --body "$(cat <<\'EOF\'\nbody; with | ops\nEOF\n)"',
                      "gh -R o/r pr create --fill", "command gh pr merge 7", "/usr/local/bin/gh pr merge 7",
                      "FOO=1 env gh pr create", "gh api graphql -f query='mutation{mergePullRequest(input:{}){clientMutationId}}'",
                      "gh api --method=POST repos/o/r/pulls -f title=t"]:
            rc, out = run(root, bash(shape))
            ok("MISSING" in json.dumps(out), f"positive: gated shape seen: {shape[:48]!r}", out)
        for shape in ["gh api -X POST repos/o/r/pulls/7/comments -f body=hi", "gh pr view 7", "git log --grep 'gh pr create'"]:
            rc, out = run(root, bash(shape))
            ok(out == {}, f"negative: not a create/merge: {shape[:48]!r}", out)

        # kit ON
        on = {"CLAUDE_ENFORCEMENT_KIT": "1"}
        rc, out = run(root, {"hook_event_name": "SubagentStart", "agent_type": "x-reviewer", "agent_id": "s1"}, on)
        ok("FINDING:" in json.dumps(out), "positive: reviewer gets the FINDING contract", out)
        rc, out = run(root, {"hook_event_name": "SubagentStart", "agent_type": "builder", "agent_id": "s2"}, on)
        ok(out == {}, "negative: a Write-capable agent is not a reviewer", out)
        stop = {"hook_event_name": "SubagentStop", "agent_type": "x-reviewer", "agent_id": "r1", "stop_hook_active": False,
                "last_assistant_message": "All good, HIGH quality."}
        rc, out = run(root, stop, on)
        ok(out.get("decision") == "block", "positive: reviewer report without contract lines is sent back once", out)
        stop.update(last_assistant_message="Done.\nFINDING: HIGH | src/a.ts:3 | missing auth check")
        rc, out = run(root, stop, on)
        ok(out == {}, "a contract report is recorded silently", out)
        rc, out = run(root, stop, on)
        with rs.ledger(root) as data:
            ok(len(data["findings"]) == 1 and len(data["reports"]) == 1 and rs.review_round(data) == 1,
               "negative: a second SubagentStop for the same agent_id records nothing (round stays 1)", data)
        rc, out = run(root, {"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": {"subagent_type": "x-reviewer"}}, on)
        ok(deny(out) and "F1" in json.dumps(out), "positive: re-dispatching a reviewer that owns an open finding is denied", out)
        rc, out = run(root, {"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": {"subagent_type": "builder"}}, on)
        ok(out == {}, "negative: other agents dispatch freely", out)
        rc, out = run(root, {"hook_event_name": "Stop", "stop_hook_active": False}, on)
        ok(out.get("decision") == "block" and "F1" in out.get("reason", ""), "positive: Stop blocks on an open HIGH finding", out)
        rc, out = run(root, {"hook_event_name": "Stop", "stop_hook_active": True}, on)
        ok("decision" not in out and out.get("systemMessage"), "bounded: stop_hook_active never blocks twice (it notifies)", out)
        rc, out = run(root, {"hook_event_name": "Stop", "stop_hook_active": False}, on)
        ok("decision" not in out and "unchanged" in out.get("systemMessage", ""), "the same open findings block only once, then notify", out)
        (agents / "y-reviewer.md").write_text("---\nname: y-reviewer\ndisallowedTools:\n- Write\n- Edit\n---\nbody\n")
        rc, out = run(root, {"hook_event_name": "SubagentStart", "agent_type": "y-reviewer", "agent_id": "s3"}, on)
        ok("FINDING:" in json.dumps(out), "positive: YAML list form of disallowedTools is a reviewer", out)
        with rs.ledger(root, write=True) as data:
            rs.add_finding(data, "x-reviewer", "CRITICAL", "fresh blocker never seen by Stop", "src/z.ts:1")
        rc, out = run(root, {"hook_event_name": "Stop", "stop_hook_active": True}, on)
        ok("decision" not in out and "fresh blocker" in out.get("systemMessage", ""), "bounded: a NEW blocking set under stop_hook_active notifies, never blocks", out)
        with rs.ledger(root, write=True) as data:
            rs.dismiss(data, f"F{data['next_id'] - 1}", "selftest fixture finding, not a real defect")
        with rs.ledger(root, write=True) as data:
            rs.close(data, "F1", "CONTROL", "tests/auth.spec.ts failed before the guard, passes now")
        rc, out = run(root, {"hook_event_name": "Stop", "stop_hook_active": False}, on)
        ok(out == {}, "negative: no blocking findings -> Stop is silent", out)

        rc, out = run(root, bash("gh pr create --fill"), on)
        ok(deny(out) and "MISSING" in json.dumps(out), "positive: kit on, no stamp -> gh pr create denied", out)
        rc, out = run(root, bash("gh api -X PUT repos/o/r/pulls/7/merge"), on)
        ok(deny(out), "positive: gh api merge write is gated too", out)
        rc, out = run(root, bash("gh api repos/o/r/pulls/7"), on)
        ok(out == {}, "negative: a read-only gh api call is not gated", out)
        rs_env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
        subprocess.run([sys.executable, str(HERE.parent / "scripts" / "review_state.py"), "stamp", "write", "verify", "--note", "selftest"],
                       cwd=root, env=rs_env, check=True, capture_output=True)
        rc, out = run(root, bash("cd sub && gh pr create --fill"), on)
        ok(out == {}, "negative: VALID stamp -> gh pr create passes", out)
        (root / "src").mkdir(); (root / "src" / "app.component.ts").write_text("export class A {}\n")
        rc, out = run(root, bash("gh pr merge 7 --squash"), on)
        ok(deny(out) and "CHANGED" in json.dumps(out), "positive: an edit after the stamp -> CHANGED -> merge denied", out)
        rc, out = run(root, bash('REVIEW_GATE_OVERRIDE="hotfix approved by owner" gh pr merge 7 --squash'), on)
        ok(not deny(out) and "override" in json.dumps(out), "override with a reason is allowed and noted", out)
        for shape in ['gh pr create --body "set REVIEW_GATE_OVERRIDE=bypassbypassbypass to skip"',
                      "cat <<'EOF'\nREVIEW_GATE_OVERRIDE=bypassbypassbypass\nEOF\ngh pr merge 7",
                      'REVIEW_GATE_OVERRIDE="hotfix approved by owner" gh pr view 1 && gh pr merge 7']:
            rc, out = run(root, bash(shape), on)
            ok(deny(out), f"negative: override text not prefixing the gated gh is ignored: {shape[:40]!r}", out)
        rc, out = run(root, bash('cd sub && REVIEW_GATE_OVERRIDE="hotfix approved by owner" gh pr merge 7'), on)
        ok(not deny(out), "override prefixing the gated gh after cd && is honoured", out)
        for shape in ["if gh pr create --fill; then echo ok; fi", "x=`gh pr merge 7`", "while true; do gh pr merge 7; done"]:
            rc, out = run(root, bash(shape), on)
            ok(deny(out), f"positive: gated gh after a shell keyword or backtick: {shape[:40]!r}", out)

        # UI evidence reminder (web file added above, kit on)
        rc, out = run(root, {"hook_event_name": "Stop", "stop_hook_active": False}, on)
        ok(out.get("decision") == "block" and "ui-web" in out.get("reason", ""), "positive: UI change without ui-web evidence -> one bounded block", out)
        rc, out = run(root, {"hook_event_name": "Stop", "stop_hook_active": False}, on)
        ok(out == {}, "negative: the same tree is reminded only once", out)
        (root / "src" / "app.component.html").write_text("<p>x</p>\n")
        rc, out = run(root, {"hook_event_name": "Stop", "stop_hook_active": False})
        ok("decision" not in out and "ui-web" in out.get("systemMessage", ""), "kit off: UI reminder is a systemMessage, never a block", out)
        subprocess.run([sys.executable, str(HERE.parent / "scripts" / "review_state.py"), "stamp", "write", "ui-web", "--note", "selftest"],
                       cwd=root, env=rs_env, check=True, capture_output=True)
        (root / "src" / "x.ts").write_text("1\n")
        rc, out = run(root, {"hook_event_name": "Stop", "stop_hook_active": False})
        ok("ui-web" not in json.dumps(out), "negative: a non-UI edit after a ui-web stamp does not re-trigger", out)
    rc = subprocess.run([sys.executable, __file__], input="not json", capture_output=True, text=True).returncode
    ok(rc == 0, "malformed stdin exits 0 (never wedges the session)", rc)
    print("selftest PASS" if fails == 0 else "selftest FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(selftest() if sys.argv[1:] == ["--selftest"] else main())
