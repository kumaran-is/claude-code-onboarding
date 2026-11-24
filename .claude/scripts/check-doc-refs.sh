#!/usr/bin/env bash
# check-doc-refs.sh — verify that documentation references in this toolkit resolve.
#
# Scans every tracked or untracked-but-not-ignored Markdown file (git ls-files), skipping fenced code blocks
# (examples of a *user's* project, not references into this one).
#
# Checks
#   L1  A relative Markdown link [text](path) points to a file or directory that exists.
#   L2  A link anchor (path#anchor or #anchor) matches a heading (GitHub slug rules, duplicate suffixes -1, -2)
#       or an explicit <a name|id="..."> in the target Markdown file.
#   T1  A backticked toolkit path `.claude/<skills|agents|commands|rules|hooks|scripts>/...` exists, and a
#       `path:line` or `path:start-end` suffix is within the file. Placeholders (<...>, *, {..}, my-*, xxx, NNN,
#       YYYY) are skipped: they name a file the reader creates.
#   S1  At least one Markdown file was scanned (an empty scan fails instead of reporting clean).
#
# Usage: check-doc-refs.sh [--root <repo>] | --selftest     Exit 0 = clean, 1 = violations, 2 = usage / nothing scanned.
set -uo pipefail
DOC_REFS_SELF="$0" exec python3 - "$@" <<'PY'
import os
import re
import subprocess
import sys
import tempfile

FENCE = re.compile(r"(?ms)^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$")
INLINE_CODE = re.compile(r"`[^`\n]*`")
LINK = re.compile(r"(?<!!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|!\[[^\]\n]*\]\(([^)\s]+)\)")
TOOLKIT_PATH = re.compile(r"`(\.claude/(?:skills|agents|commands|rules|hooks|scripts)/[A-Za-z0-9_./{}<>*-]*[A-Za-z0-9_>}*])(?::(\d+)(?:-(\d+))?)?`")
PLACEHOLDER = re.compile(r"[<>*{}]|(^|/)my-|xxx|NNN|YYYY")
HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
HTML_ANCHOR = re.compile(r"<a\s+[^>]*(?:name|id)=\"([^\"]+)\"", re.I)


def slug(text):
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # [label](url) -> label
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def anchors(path, cache):
    if path in cache:
        return cache[path]
    found, seen = set(), {}
    with open(path, encoding="utf-8", errors="ignore") as fh:
        body = FENCE.sub("", fh.read())
    for line in body.splitlines():
        m = HEADING.match(line)
        if m:
            base = slug(m.group(2))
            n = seen.get(base, 0)
            seen[base] = n + 1
            found.add(base if n == 0 else f"{base}-{n}")
        for a in HTML_ANCHOR.findall(line):
            found.add(a)
    cache[path] = found
    return found


def line_count(path, cache):
    if path not in cache:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            cache[path] = sum(1 for _ in fh)
    return cache[path]


def scan(root):
    out = subprocess.run(["git", "-C", root, "ls-files", "-co", "--exclude-standard", "*.md"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        print(f"check-doc-refs: git ls-files failed in {root}: {out.stderr.strip()}", file=sys.stderr)
        return None, 0, 0
    files = [f for f in out.stdout.splitlines() if "node_modules/" not in f and os.path.isfile(os.path.join(root, f))]
    problems, links, paths = [], 0, 0
    anchor_cache, line_cache = {}, {}
    for rel in files:
        src = os.path.join(root, rel)
        with open(src, encoding="utf-8", errors="ignore") as fh:
            text = FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), fh.read())
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in TOOLKIT_PATH.finditer(line):
                ref, start, end = m.group(1), m.group(2), m.group(3)
                if PLACEHOLDER.search(ref):
                    continue
                paths += 1
                full = os.path.join(root, ref)
                if not os.path.exists(full):
                    problems.append(f"T1 {rel}:{lineno}: `{ref}` does not exist")
                elif start and os.path.isfile(full):
                    last = int(end or start)
                    if int(start) < 1 or last > line_count(full, line_cache):
                        problems.append(f"T1 {rel}:{lineno}: `{ref}:{start}{'-' + end if end else ''}` is outside the file "
                                        f"({line_count(full, line_cache)} lines)")
            for m in LINK.finditer(INLINE_CODE.sub("", line)):
                target = m.group(1) or m.group(2)
                if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("<"):
                    continue
                links += 1
                path_part, _, anchor = target.partition("#")
                dest = os.path.normpath(os.path.join(os.path.dirname(src), path_part)) if path_part else src
                if path_part and not os.path.exists(dest):
                    problems.append(f"L1 {rel}:{lineno}: link target {path_part} does not exist")
                    continue
                if anchor and dest.endswith(".md") and os.path.isfile(dest):
                    if anchor.lower() not in anchors(dest, anchor_cache) and anchor not in anchors(dest, anchor_cache):
                        problems.append(f"L2 {rel}:{lineno}: anchor #{anchor} not found in {os.path.relpath(dest, root)}")
    return problems, len(files), (links, paths)


def run(root):
    problems, scanned, counts = scan(root)
    if problems is None:
        return 2
    if scanned == 0:
        print(f"S1 no Markdown files found under {root}: nothing was checked")
        return 2
    for p in problems:
        print(p)
    print(f"check-doc-refs: scanned {scanned} Markdown files, {counts[0]} relative links, {counts[1]} toolkit paths; "
          f"{len(problems)} violation(s)")
    return 1 if problems else 0


def selftest():
    fail = 0
    self_path = os.environ.get("DOC_REFS_SELF", "")
    rc0 = subprocess.run(["bash", "-n", self_path], capture_output=True).returncode if self_path else 1
    print(f"  {'ok  ' if rc0 == 0 else 'FAIL'} control 0: bash -n on {self_path or '(unknown path)'}")
    fail |= rc0 != 0
    with tempfile.TemporaryDirectory() as tmp:
        def write(rel, body):
            p = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(body)
        subprocess.run(["git", "init", "-q", tmp], check=True)
        write(".claude/skills/demo/SKILL.md", "# Demo\n\n## Setup & Run\n\n## Setup & Run\n\nline 7\n")
        write("README.md", "\n".join([
            "# Top",
            "[ok](.claude/skills/demo/SKILL.md) [ok anchor](.claude/skills/demo/SKILL.md#setup--run-1) [self](#top)",
            "[missing](docs/missing.md)",
            "[bad anchor](.claude/skills/demo/SKILL.md#nope)",
            "`.claude/skills/demo/SKILL.md:7` `.claude/skills/demo/SKILL.md:99` `.claude/agents/ghost.md`",
            "`.claude/skills/my-skill/SKILL.md` `.claude/rules/<name>.md` `[x](inline-code.md)` [web](https://example.com)",
            "```markdown",
            "[fenced](not-checked.md) `.claude/agents/fenced-ghost.md`",
            "```",
        ]) + "\n")
        cases = [
            ("positive L1: missing link target", "L1 README.md:3: link target docs/missing.md"),
            ("positive L2: unknown anchor", "L2 README.md:4: anchor #nope"),
            ("positive T1: line beyond end of file", "`.claude/skills/demo/SKILL.md:99` is outside the file"),
            ("positive T1: missing toolkit path", "`.claude/agents/ghost.md` does not exist"),
        ]
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = run(tmp)
        out = buf.getvalue()
        if rc != 1:
            print(f"  FAIL control: fixture with violations must exit 1 (got {rc})\n{out}")
            fail = 1
        for label, needle in cases:
            ok = needle in out
            print(f"  {'ok  ' if ok else 'FAIL'} {label}")
            fail |= not ok
        for label, needle in [
            ("negative: valid link and duplicate-heading anchor are silent", "setup--run-1"),
            ("negative: in-range line suffix is silent", "SKILL.md:7`"),
            ("negative: placeholders (my-*, <name>) are skipped", "my-skill"),
            ("negative: inline code and fenced examples are not links", "not-checked.md"),
            ("negative: fenced toolkit paths are not checked", "fenced-ghost"),
            ("negative: inline-code link text is not a link", "inline-code.md"),
        ]:
            ok = needle not in out
            print(f"  {'ok  ' if ok else 'FAIL'} {label}")
            fail |= not ok
        if out.count("\n") - 1 != len(cases):
            print(f"  FAIL control: expected exactly {len(cases)} findings\n{out}")
            fail = 1
        write("README.md", "# Top\n[ok](.claude/skills/demo/SKILL.md#demo)\n")
        with contextlib.redirect_stdout(io.StringIO()):
            rc_clean = run(tmp)
        print(f"  {'ok  ' if rc_clean == 0 else 'FAIL'} negative: a clean tree exits 0")
        fail |= rc_clean != 0
    with tempfile.TemporaryDirectory() as empty:
        subprocess.run(["git", "init", "-q", empty], check=True)
        with contextlib.redirect_stdout(io.StringIO()):
            rc_empty = run(empty)
        print(f"  {'ok  ' if rc_empty == 2 else 'FAIL'} positive S1: an empty scan exits 2, never clean")
        fail |= rc_empty != 2
    print("selftest PASS" if not fail else "selftest FAIL")
    return 1 if fail else 0


args = sys.argv[1:]
if args == ["--selftest"]:
    sys.exit(selftest())
root = "."
if args[:1] == ["--root"] and len(args) == 2:
    root = args[1]
elif args:
    print("usage: check-doc-refs.sh [--root <repo>] | --selftest", file=sys.stderr)
    sys.exit(2)
sys.exit(run(os.path.abspath(root)))
PY
