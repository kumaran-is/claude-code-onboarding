#!/usr/bin/env python3
"""Enforcement kit hook: findings ledger, fresh-evidence PR gate and UI-evidence reminder.

One script, registered for five events; it dispatches on hook_event_name. Opt-in parts act only when
the kit is ON for the branch (`python3 .claude/scripts/review_state.py init`, or CLAUDE_ENFORCEMENT_KIT=1):

  SubagentStart  reviewer agent -> inject the FINDING-line contract (additionalContext)
  SubagentStop   reviewer agent -> record its FINDING lines in the ledger; no contract line -> block once
                 (bounded by stop_hook_active), then record a MEDIUM "report unparsed" finding instead
  PreToolUse     Agent: block re-dispatching a reviewer that still owns open findings; before the first review
                        round with no recorded `verify` run on this tree -> one notice (additionalContext)
                 Bash:  `gh pr create|merge` / `gh api .../pulls` need a VALID `verify` stamp from a
                        `full` or `pre-pr` run (a quick run executes no tests); a merge also needs a VALID
                        `lessons` stamp (the end-of-PR lessons review ran on this tree, "no lesson" allowed)
                        (kit OFF: advisory only; kit ON: deny, unless REVIEW_GATE_OVERRIDE="<reason>")
  Stop           kit ON: block while findings block (bounded by stop_hook_active)
                 always: UI files changed without a VALID ui-web / ui-mobile stamp -> one reminder per
                         tree state (systemMessage; kit ON: one bounded block)
                 always: branch changes more than 15 / 25 files -> one scope notice per threshold (systemMessage)

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


def drop_heredocs(cmd: str) -> str:
    out, delim = [], None
    for line in cmd.split("\n"):
        if delim is not None:
            if line.strip() == delim:
                delim = None
            continue
        out.append(line)
        m = HEREDOC_RE.search(line.replace("<<<", "   "))
        delim = m.group(2) if m else None
    return "\n".join(out)


def split_commands(cmd: str) -> list[str]:
    """Split a shell command into simple commands: heredoc bodies dropped, quotes respected."""
    text, segs, cur, quote, i = drop_heredocs(cmd), [], [], "", 0
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


SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish"}
RUNNERS = {"xargs", "timeout", "gtimeout", "nice", "ionice", "stdbuf", "doas", "watch", "parallel", "caffeinate",
           "flock", "find", "setsid", "chronic", "unbuffer", "script"}
ASSIGN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
DYNAMIC_GH_RE = re.compile(  # `$(which gh) pr merge`, `$GH pr create`: a gh whose name is computed
    r"(?:^|[;&|\n(])\s*(?:[A-Za-z_]\w*=\S*\s+)*(?:\$\(\s*(?:command\s+-v|which|type\s+-p)\s+gh\s*\)|`\s*(?:command\s+-v|which)\s+gh\s*`"
    r"|\"?\$\{?[A-Za-z_]\w*\}?\"?)\s+(?:-R\s+\S+\s+)?pr\s+(create|merge)\b")


def substitutions(seg: str) -> list[str]:
    """Bodies of `$(...)` and backticks that the shell runs (anything outside single quotes). Unquoted ones were
    already split out by split_commands; this finds the ones inside double quotes."""
    out, i, single = [], 0, False
    while i < len(seg):
        ch = seg[i]
        if ch == "'" and not single and seg.count("'", i + 1):
            single = True
        elif ch == "'" and single:
            single = False
        elif not single and seg.startswith("$(", i):
            depth, j = 1, i + 2
            while j < len(seg) and depth:
                depth += {"(": 1, ")": -1}.get(seg[j], 0)
                j += 1
            out.append(seg[i + 2:j - 1])
            i = j
            continue
        elif not single and ch == "`":
            j = seg.find("`", i + 1)
            if j > i:
                out.append(seg[i + 1:j])
                i = j
        i += 1
    return out


def inner_commands(seg: str, toks: list[str]) -> list[str]:
    """Command strings a simple command runs on our behalf: `bash -c S`, `eval ...`, `env -S S`, a runner
    (`xargs`, `timeout`, `nice`, `sudo -u x`...) in front of gh / a shell / eval, and quoted substitutions."""
    out = substitutions(seg)
    if not toks:
        return out
    word = os.path.basename(toks[0])
    if word in SHELLS:
        for j in range(1, len(toks)):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", toks[j]):
                out += toks[j + 1:j + 2]
                break
            if not toks[j].startswith("-"):
                break  # `bash script.sh`: the script body is not visible here
    elif word == "eval":
        out.append(" ".join(toks[1:]))
    elif word in RUNNERS or word in WRAPPERS or ASSIGN_RE.fullmatch(toks[0]):
        for j in range(1, len(toks)):  # walk the runner prefix up to the command it runs
            tok, prev = toks[j], toks[j - 1]
            if prev in ("-S", "--split-string") or tok.startswith("--split-string="):
                out.append(tok.split("=", 1)[1] if tok.startswith("--split-string=") else tok)
                break
            if os.path.basename(tok) in SHELLS | {"gh", "eval"}:
                out.append(shlex.join(toks[j:]))
                break
            prefix_part = (tok.startswith("-") or tok in RUNNERS or tok in WRAPPERS or ASSIGN_RE.fullmatch(tok)
                           or re.fullmatch(r"[\d.]+[smhd]?|\{\}", tok) or re.fullmatch(r"-[A-Za-z]", prev))
            if not prefix_part:
                break  # `xargs echo gh ...`: echo is the command; gh is only its argument
    return out


def pr_segments(cmd: str) -> tuple[list[str], str]:
    """Return (gated gh invocations, override reason) for a Bash command, anchored at command position.

    Covers `gh pr create|merge`, `gh api` writes to .../pulls or .../pulls/N/merge, and GraphQL create/merge
    mutations, behind `command`/`env`/`time`/`sudo`, env assignments, `-R owner/repo` and an absolute gh path, and
    inside `bash -c` / `sh -c` strings, `eval`, `env -S`, runners (`xargs gh`, `timeout 30 gh`, `nice gh`), quoted
    `$(...)` / backticks and a computed gh name (`$(which gh) pr merge`). Out of scope (defense in depth; CI and
    branch protection are the real gate): script files, interpreter one-liners (`python -c`), aliases."""
    found = scan_pr(cmd, "", 0)
    hits = [h for h, _ in found]
    overrides = [o for _, o in found]
    # every gated invocation needs its own override; one unprefixed gh means no override at all
    return hits, (overrides[0] if overrides and all(o == overrides[0] for o in overrides) and overrides[0] else "")


def scan_pr(cmd: str, inherited: str, depth: int) -> list[tuple[str, str]]:
    if depth > 6:
        return [("gh (command nesting too deep to analyse)", "")]
    found = [(f"gh pr {m.group(1)} (computed command name)", inherited) for m in DYNAMIC_GH_RE.finditer(drop_heredocs(cmd))]
    for seg in split_commands(cmd):
        try:
            toks = shlex.split(seg)
        except ValueError:
            toks = seg.split()  # unbalanced quoting: fall back to whitespace so a gh command is still seen
        args, seg_override = gh_args(toks)
        if not args:
            prefix = next((t.split("=", 1)[1] for t in toks if t.startswith("REVIEW_GATE_OVERRIDE=")), "") if toks and ASSIGN_RE.fullmatch(toks[0]) else ""
            for inner in inner_commands(seg, toks):
                found += scan_pr(inner, prefix or inherited, depth + 1)
            continue
        hits = []
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
                hits.append("gh api .../pulls/N/merge" if "/merge" in path else "gh api .../pulls (create)")
            elif "graphql" in args and GRAPHQL_RE.search(seg):
                merges = re.search(r"\b(mergePullRequest|enablePullRequestAutoMerge)\b", seg)
                hits.append("gh api graphql (merge a PR)" if merges else "gh api graphql (create a PR)")
        found += [(h, seg_override or inherited) for h in hits]
        for inner in substitutions(seg):  # `gh pr create --body "$(gh pr merge 7)"` runs both
            found += scan_pr(inner, inherited, depth + 1)
    return found


VERIFY_MODES = ("full", "pre-pr")  # /verify quick and pre-commit run no tests: never PR evidence
FIXES = {
    "verify": "run `/verify full` or `/verify pre-pr` on the current tree (it writes the stamp with "
              "`python3 .claude/scripts/review_state.py stamp write verify --mode <full|pre-pr> --note \"<checks and counts>\"` after every check PASSES)",
    "review": rs.REVIEW_FIX,
    "lessons": "run the end-of-PR lessons review (/create-pr Step 2.3 or /ship) and record it with "
               "`python3 .claude/scripts/review_state.py stamp write lessons --note \"<N routed | no new lesson>\"`",
}


# A text heuristic, not a sandbox: CI and branch protection remain the real merge gate.
STATE_WRITE_RE = re.compile(r">|\btee\b|\b(cp|mv|rm|ln|install|truncate|dd|sed|perl|python3?|node|ruby|jq|touch|chmod|unlink|rsync)\b"
                            r"|\bfind\b.*\s-(delete|exec)\b|\bgit\s+(checkout|restore|stash|clean)\b")


# The one legitimate writer: a single plain call of the CLI, no chaining, redirection or substitution.
REVIEW_CLI_RE = re.compile(r"^\s*(?:uv\s+run\s+)?python3?\s+(?:\S*/)?\.claude/scripts/review_state\.py(?:\s+[^;&|<>`$()]*)?\s*$")


def _normalise(cmd: str) -> str:
    """Case-fold (APFS is case-insensitive) and collapse `//`, `/./` so path spellings cannot dodge the match."""
    s = cmd.lower()
    s = re.sub(r"/+", "/", s)
    return re.sub(r"/(?:\./)+", "/", s)


def state_tamper(root: Path, cmd: str) -> bool:
    """A Bash command that would write the kit's own evidence (ledger, stamps) in THIS project by hand."""
    if REVIEW_CLI_RE.match(cmd) or not STATE_WRITE_RE.search(cmd):
        return False
    s = _normalise(cmd)
    root_s = _normalise(str(root)).rstrip("/") + "/"
    # `cd .claude && ... > state/review/...` names the evidence directory without the `.claude/state` spelling
    if ".claude" in s and re.search(r"(?:^|[\s'\"=(<>,/])state/(?:review|stamps)\b", s):
        return True
    for m in re.finditer(r"(\S*?)\.claude/state\b", s):
        prefix = re.split(r"[\s'\"=(<>,]", m.group(1))[-1]  # the path part only: `open(".claude/...` -> ''
        # An absolute path into ANOTHER project is not ours; everything else (relative, ~, $PWD, $VAR, this root) is.
        if prefix.startswith("/") and prefix != root_s:
            continue
        return True
    return False


def on_bash(root: Path, payload: dict) -> int:
    cmd = (payload.get("tool_input") or {}).get("command", "")
    enabled = rs.is_enabled(root)
    if enabled and state_tamper(root, cmd):
        return emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                     "permissionDecisionReason": "Enforcement kit: .claude/state holds the review evidence; only review_state.py and the "
                                                 "kit's hooks write it. Use `review_state.py` (findings close/dismiss, stamp write, disable)."}})
    hits, override = pr_segments(cmd)
    if not hits:
        return 0
    needs = [("verify", VERIFY_MODES)]
    if enabled:  # reviews are recorded only while the kit is on, so off it would always read MISSING
        needs.append(("review", ()))
    if any("merge" in h for h in hits):  # the lessons review is the backstop before the branch context is gone
        needs.append(("lessons", ()))
    missing = []
    for name, modes in needs:
        status, why = rs.review_check(root) if name == "review" else rs.stamp_check(root, name, modes)
        if status != "VALID":
            missing.append((name, status, why))
    if not missing:
        return 0
    what = "; ".join(f"`{n}` {'evidence' if n == 'review' else 'stamp'} is {s} ({w})" for n, s, w in missing)
    fix = "; ".join(FIXES[n] for n, _, _ in missing)
    if enabled and len(override.strip()) < 10:
        return emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                     "permissionDecisionReason": f"Enforcement kit: {hits[0]} needs fresh evidence: {what}. To fix: {fix}. "
                                                 "A deliberate exception: prefix REVIEW_GATE_OVERRIDE=\"<reason, 10+ chars>\" and state the reason in the PR."}})
    note = f"override: {override.strip()}" if enabled else "advisory (kit off)"
    return emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
                 f"Evidence for {hits[0]}: {what}; {note}. Stale or missing evidence is not evidence: say so in the PR, or {fix}."}})


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
    try:
        tree = rs.fingerprint(root)  # the tree this reviewer saw: the only thing review_check() accepts as current
    except (RuntimeError, OSError, rs.subprocess.TimeoutExpired):
        tree = ""
    with rs.ledger(root, write=True) as data:
        status, n = rs.record_report(data, agent, agent_id, text, tree)
        if status == "missing" and payload.get("stop_hook_active"):
            rs.add_finding(data, agent, "MEDIUM", "reviewer report had no FINDING contract lines; triage it by hand", "-", agent_id)
            data["reports"][agent_id or f"anon-{len(data['reports']) + 1}"] = {"reviewer": agent, "at": rs.time.time(), "count": 0, "tree": tree}
    if status == "missing" and not payload.get("stop_hook_active"):
        return emit({"decision": "block", "reason": rs.CONTRACT + " Add those lines now; nothing else needs to change."})
    return 0


def on_agent(root: Path, payload: dict) -> int:
    target = (payload.get("tool_input") or {}).get("subagent_type", "")
    if not (rs.is_enabled(root) and is_reviewer(root, target)):
        return 0
    with rs.ledger(root) as data:  # same rule as Stop: from round 3 MEDIUM/LOW no longer hold up a re-review
        owned = [f for f in rs.blocking(data) if f["reviewer"] == target]
        first_round = not data["reports"]
    if not owned:
        return first_review_notice(root, target) if first_round else 0
    ids = ", ".join(f"{f['id']} ({f['severity']}, {f['state']})" for f in owned[:8])
    return emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                 "permissionDecisionReason": f"Enforcement kit: {target} still owns open findings {ids}. Fix each and close it with evidence "
                                             "(`review_state.py findings close ID --class CONTROL|MECHANISM|STATIC|NOCONTROL --evidence ...`), "
                                             "record a failed fix (`findings fail ID --note ...`) or dismiss it with a reason; then re-dispatch for verification."}})


def first_review_notice(root: Path, target: str) -> int:
    """First review round on a tree no verify run backs: say so once per tree state (never blocks)."""
    if rs.stamp_check(root, "verify")[0] == "VALID":  # any mode: quick is enough before a review round
        return 0
    marker = rs.state_dir(root) / f"review-noticed-{rs.fingerprint(root)[:16]}"
    if marker.is_file():
        return 0
    marker.parent.mkdir(parents=True, exist_ok=True)
    for old in marker.parent.glob("review-noticed-*"):
        old.unlink(missing_ok=True)
    marker.write_text("noticed\n")
    return emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
                 f"Enforcement kit: first review round ({target}) on a tree with no recorded verify run. Run /verify (quick at least) "
                 "and record its stamp first, so the review round is spent on design and logic, not compile or lint errors. Not blocking."}})


SCOPE_THRESHOLDS = (15, 25)  # first-principles.md commit discipline: more than 15 files = split first


def scope_notice(root: Path, files: list[str]) -> str:
    """One notice each time the branch's changed-file count first exceeds a threshold."""
    crossed = [n for n in SCOPE_THRESHOLDS if len(files) > n]
    marker = rs.state_dir(root) / "scope-noticed.txt"
    if not crossed:
        marker.unlink(missing_ok=True)  # back under the limit: a later crossing is reported again
        return ""
    try:
        last = int(marker.read_text().strip()) if marker.is_file() else 0
    except ValueError:
        last = 0
    if crossed[-1] <= last:
        return ""
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{crossed[-1]}\n")
    return (f"Scope check: {len(files)} files changed on this branch (more than {crossed[-1]}). first-principles.md caps a commit at 15 "
            "files with no unrelated files: confirm every file traces to the request, then plan commits of at most 15.")


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


def ui_reminder(root: Path, files: list[str]) -> tuple[str, str]:
    """Return (message, marker path) when UI changed without a VALID stamp and this tree was not reminded yet."""
    targets = ui_targets(root, files)
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
        files = changed_files(root)
        ui_msg, marker = ui_reminder(root, files)
        scope_msg = scope_notice(root, files)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        ui_msg, marker, scope_msg = "", "", f"enforcement-kit: changed files not checked ({type(exc).__name__}); UI-evidence and scope notices skipped."
    if scope_msg:
        notices.append(scope_msg)
    if marker:
        Path(marker).parent.mkdir(parents=True, exist_ok=True)
        Path(marker).write_text("reminded\n")
    if ui_msg and enabled:
        reasons.append(ui_msg)
    if reasons and not active:  # carry the notices too: their markers are already written
        return emit({"decision": "block", "reason": "Enforcement kit: " + " ".join(reasons + notices)})
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
    bash_cmd = (payload.get("tool_input") or {}).get("command", "") if payload.get("tool_name") == "Bash" else None
    if bash_cmd is not None and not pr_segments(bash_cmd)[0] and ".claude" not in bash_cmd.lower():
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
        gated = bash_cmd is not None and (pr_segments(bash_cmd)[0] or ".claude/state" in _normalise(bash_cmd))
        try:
            enabled = rs.is_enabled(root)
        except Exception:  # noqa: BLE001 - cannot tell: treat as enabled (fail closed)
            enabled = True
        if event == "PreToolUse" and gated and enabled:  # fail CLOSED: an error must never wave a PR/merge through
            return emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                         "permissionDecisionReason": f"Enforcement kit could not check the PR/review evidence "
                                                     f"({type(exc).__name__}: {exc}); fix the cause, then retry."}})
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
                      "gh api --method=POST repos/o/r/pulls -f title=t",
                      # wrappers that run a command for us (G9)
                      "bash -c 'gh pr merge 3'", 'sh -c "gh pr create --fill"', "bash -lc 'gh pr merge 3'", "zsh -ec 'gh pr merge 3'",
                      "eval gh pr merge 3", "eval 'gh pr create --fill'", "echo 3 | xargs gh pr merge", "xargs -I {} gh pr merge {} < ids",
                      "timeout 30 gh pr merge 3", "nice -n 5 gh pr create --fill", "sudo -u ci gh pr merge 3", "env -S 'gh pr merge 3'",
                      'echo "$(gh pr merge 3)"', "x=`gh pr merge 3`", "$(which gh) pr merge 3", "$GH pr create --fill",
                      "bash -c \"eval 'gh pr merge 3'\"", "f(){ gh pr merge 3; }; f", "ls && bash -c 'cd x && gh pr merge 3'"]:
            rc, out = run(root, bash(shape))
            ok("MISSING" in json.dumps(out), f"positive: gated shape seen: {shape[:48]!r}", out)
        for shape in ["gh api -X POST repos/o/r/pulls/7/comments -f body=hi", "gh pr view 7", "git log --grep 'gh pr create'",
                      "bash -c 'gh pr view 3'", "echo 'bash -c \"gh pr merge 3\"'", "xargs echo gh pr merge", "bash deploy.sh gh pr merge",
                      'git commit -m "$(cat msg.txt)"', "echo '$(gh pr merge 3)'", 'git commit -m "run $GH pr merge later"',
                      "cat <<'EOF'\n$GH pr merge 3\nEOF", "eval echo done"]:
            rc, out = run(root, bash(shape))
            ok(out == {}, f"negative: not a create/merge: {shape[:48]!r}", out)

        # kit ON
        on = {"CLAUDE_ENFORCEMENT_KIT": "1"}
        agent = {"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": {"subagent_type": "x-reviewer"}}
        rc, out = run(root, agent, on)
        ok(not deny(out) and "first review round" in json.dumps(out), "positive: first reviewer dispatch with no verify run -> one notice", out)
        rc, out = run(root, agent, on)
        ok(out == {}, "negative: the same tree gets the first-review notice only once", out)
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
        def stamp(*args: str) -> None:
            subprocess.run([sys.executable, str(HERE.parent / "scripts" / "review_state.py"), "stamp", "write", *args],
                           cwd=root, env=rs_env, check=True, capture_output=True)
        stamp("verify", "--mode", "quick", "--note", "lint only")
        rc, out = run(root, bash("gh pr create --fill"), on)
        ok(deny(out) and "INSUFFICIENT" in json.dumps(out), "positive: a /verify quick stamp never authorizes gh pr create", out)
        stamp("verify", "--note", "no mode")
        rc, out = run(root, bash("gh pr create --fill"), on)
        ok(deny(out) and "INSUFFICIENT" in json.dumps(out), "positive: a mode-less verify stamp fails closed", out)
        stamp("verify", "--mode", "full", "--note", "selftest")
        rc, out = run(root, bash("cd sub && gh pr create --fill"), on)
        ok(deny(out) and "`review` evidence is CHANGED" in json.dumps(out), "positive (G2): verify VALID but no review of the current tree -> denied", out)
        rs_cli = [sys.executable, str(HERE.parent / "scripts" / "review_state.py")]
        forged = subprocess.run(rs_cli + ["stamp", "write", "review", "--note", "trust me"], cwd=root, env=rs_env, capture_output=True, text=True)
        ok(forged.returncode == 2 and "cannot be written by hand" in forged.stderr, "positive (G2): `stamp write review` is refused", forged.stderr)
        rel = rs.state_dir(root).relative_to(root)
        for shape in [f"echo '{{}}' > {rel}/stamps/review.json", f"python3 -c 'open(\"{rel}/ledger.json\",\"w\")'",
                      f"cp /tmp/x.json ./{rel}/ledger.json", f"rm -rf .claude/state",
                      # security review bypasses: CLI-name exemption, relative after cd, path spellings, variables
                      f"echo '{{}}' > {rel}/ledger.json; python3 .claude/scripts/review_state.py findings list",
                      f"echo '{{}}' > {rel}/ledger.json # review_state.py",
                      "python3 .claude/scripts/review_state.py findings list > .claude/state/x",
                      "cd .claude && echo x > state/review/main/ledger.json", "echo x > .claude//state/review/l.json",
                      "echo x > .claude/./state/review/l.json", "echo x > .CLAUDE/state/review/l.json",
                      'echo x > "$PWD/.claude/state/review/l.json"', 'rm -rf "$T/.claude/state"',
                      "unlink .claude/state/enabled", "find .claude/state -name enabled -delete", "git checkout -- .claude/state",
                      "rsync -a /tmp/x/ .claude/state/"]:
            rc, out = run(root, bash(shape), on)
            ok(deny(out) and ".claude/state" in json.dumps(out), f"positive (G2): hand-writing the evidence is denied: {shape[:44]!r}", out)
        for shape in ["python3 .claude/scripts/review_state.py findings list", "rm -rf /tmp/other-project/.claude/state", "cat .claude/state/x/ledger.json"]:
            rc, out = run(root, bash(shape), on)
            ok(not deny(out), f"negative (G2): not a hand write of this project's evidence: {shape[:44]!r}", out)
        rc, out = run(root, {"hook_event_name": "SubagentStop", "agent_type": "x-reviewer", "agent_id": "ok1", "stop_hook_active": False,
                             "last_assistant_message": "Re-review done.\nFINDINGS: none"}, on)
        rc, out = run(root, bash("cd sub && gh pr create --fill"), on)
        ok(out == {}, "negative: VALID full-mode stamp -> gh pr create passes (no lessons stamp needed to open a PR)", out)
        rc, out = run(root, bash("gh pr merge 7 --squash"), on)
        ok(deny(out) and "lessons" in json.dumps(out) and "verify" not in json.dumps(out).split("To fix")[0].replace("`lessons`", ""),
           "positive: merge with verify VALID but no lessons review -> denied, naming only the lessons stamp", out)
        rc, out = run(root, bash("gh api -X PUT repos/o/r/pulls/7/merge"))
        ok(not deny(out) and "lessons" in json.dumps(out), "kit off: a merge without the lessons review is advisory", out)
        rc, out = run(root, bash("gh api graphql -f query='mutation{createPullRequest(input:{}){clientMutationId}}'"), on)
        ok(out == {}, "negative: a GraphQL PR create needs no lessons stamp", out)
        rc, out = run(root, bash("gh api graphql -f query='mutation{mergePullRequest(input:{}){clientMutationId}}'"), on)
        ok(deny(out) and "lessons" in json.dumps(out), "positive: a GraphQL merge needs the lessons stamp", out)
        stamp("lessons", "--note", "no new lesson")
        rc, out = run(root, bash("gh pr merge 7 --squash"), on)
        ok(out == {}, "negative: verify (full) + lessons VALID -> merge passes", out)
        ledger_path = rs.state_dir(root) / "ledger.json"
        good_ledger = ledger_path.read_text()
        ledger_path.write_text("{not json")
        rc, out = run(root, bash("gh pr merge 7 --squash"), on)
        ok(deny(out), "positive (fail closed): a corrupt ledger never lets a merge through", out)
        ledger_path.write_text(good_ledger)
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
        ok("Scope check" not in json.dumps(out), "negative: a few changed files -> no scope notice", out)
        many = root / "src" / "many"; many.mkdir()
        for i in range(16):
            (many / f"m{i}.py").write_text(f"x = {i}\n")
        rc, out = run(root, {"hook_event_name": "Stop", "stop_hook_active": False})
        ok("Scope check" in out.get("systemMessage", "") and "more than 15" in out.get("systemMessage", ""),
           "positive: more than 15 changed files -> scope notice", out)
        rc, out = run(root, {"hook_event_name": "Stop", "stop_hook_active": False})
        ok("Scope check" not in json.dumps(out), "negative: the scope notice is not repeated below the next threshold", out)
        for i in range(16):
            (many / f"m{i}.py").unlink()
        run(root, {"hook_event_name": "Stop", "stop_hook_active": False})
        for i in range(16):
            (many / f"m{i}.py").write_text(f"y = {i}\n")
        with rs.ledger(root, write=True) as data:
            rs.add_finding(data, "x-reviewer", "CRITICAL", "blocker that makes this Stop a block", "src/q.ts:1")
        rc, out = run(root, {"hook_event_name": "Stop", "stop_hook_active": False}, on)
        ok(out.get("decision") == "block" and "Scope check" in out.get("reason", ""),
           "positive: crossing again after dropping under re-notifies, carried inside a Stop block", out)
    rc = subprocess.run([sys.executable, __file__], input="not json", capture_output=True, text=True).returncode
    ok(rc == 0, "malformed stdin exits 0 (never wedges the session)", rc)
    print("selftest PASS" if fails == 0 else "selftest FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(selftest() if sys.argv[1:] == ["--selftest"] else main())
