#!/usr/bin/env python3
"""Agent Skills spec + activation eval (extends lint-skills /audit-skills).

One detector, not a second eval framework. Called by lint-skills.sh and
/audit-skills. Authoritative field constraints: https://agentskills.io/specification

Usage:
  check-skill-spec.py --dir DIR [--activation] [--machine]
  check-skill-spec.py --dir DIR --prompt TEXT --expect NAME [--forbid A,B]
  check-skill-spec.py --selftest

Exit: 0 ok, 1 spec or activation finding, 2 usage or broken selftest.
Stdlib only. Never installs plugins or vendors skills-ref.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

SPEC_URL = "https://agentskills.io/specification"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAME_MAX = 64
DESC_MAX = 1024
MIN_ACTIVATE_HITS = 2
STOP = frozenset(
    """
    a an the and or for with when this that use using to of in on is it its be as
    at by from into also should activated covers patterns templates skill provides
    building create creating add adding write writing then than not if else
    """.split()
)
# Shared product nouns that several stacks legitimately share; they must not
# decide activation on their own (React SPA vs Angular SPA).
GENERIC = frozenset(
    """
    spa route routes ui api test tests app apps application web client server
    query form forms auth service services code data user login endpoint rest
    tool tools schema schemas prototype idea design production screen screens
    component components provider providers model models hook hooks
    """.split()
)
# Representative prompts for Flutter, Angular, React, Java, Python, AI/MCP, startup-design.
CASES: tuple[dict[str, object], ...] = (
    {
        "id": "flutter-positive",
        "prompt": "Add a Riverpod provider and a widget test for the Flutter login screen",
        "must": ("flutter-mobile",),
        "must_not": ("angular-spa", "react-spa", "java-spring-api"),
    },
    {
        "id": "angular-positive",
        "prompt": "Create an Angular 22 standalone component with signals and daisyUI",
        "must": ("angular-spa",),
        "must_not": ("react-spa", "flutter-mobile", "java-spring-api"),
    },
    {
        "id": "react-positive",
        "prompt": "Add a React 19 SPA route with shadcn/ui and TanStack Query",
        "must": ("react-spa",),
        "must_not": ("angular-spa", "flutter-mobile", "java-spring-api"),
    },
    {
        "id": "java-positive",
        "prompt": "Write a Spring Boot 4.2 REST controller with virtual threads and JPA",
        "must": ("java-spring-api",),
        "must_not": ("python-dev", "nestjs-api", "flutter-mobile"),
    },
    {
        "id": "python-positive",
        "prompt": "Create a FastAPI endpoint with Pydantic v2 and SQLAlchemy async",
        "must": ("python-dev",),
        "must_not": ("java-spring-api", "flutter-mobile", "angular-spa"),
    },
    {
        "id": "mcp-positive",
        "prompt": "Scaffold a TypeScript MCP server with Fastify and Zod tool schemas",
        "must": ("mcp-builder",),
        "must_not": ("flutter-mobile", "java-spring-api", "startup-design-to-code"),
    },
    {
        "id": "ai-positive",
        "prompt": "Build a LangGraph agent with RAG retrieval and LangChain tools",
        "must": ("agentic-ai-dev",),
        "must_not": ("flutter-mobile", "java-spring-api", "angular-spa", "llamaindex"),
    },
    {
        "id": "llamaindex-positive",
        "prompt": "Build a LlamaIndex IngestionPipeline with VectorStoreIndex and LiteParse",
        "must": ("llamaindex",),
        "must_not": ("flutter-mobile", "java-spring-api", "angular-spa"),
    },
    {
        "id": "startup-positive",
        "prompt": "Turn this startup idea into DESIGN.md and a Google Stitch prototype",
        "must": ("startup-design-to-code",),
        "must_not": ("java-spring-api", "mcp-builder", "python-dev"),
    },
    {
        "id": "startup-aidlc-positive",
        "prompt": "Generate Stitch screens from our approved aidlc inception requirements",
        "must": ("startup-design-to-code",),
        "must_not": ("java-spring-api", "mcp-builder", "aws-aidlc-integration"),
    },
    {
        "id": "monorepo-positive",
        "prompt": "Should this polyglot monorepo use Melos, uv workspaces, npm workspaces, or Nx for affected builds?",
        "must": ("polyglot-monorepo",),
        "must_not": ("java-spring-api", "startup-design-to-code"),
    },
    {
        "id": "generic-negative",
        "prompt": "What is today's date in this repository?",
        "must": (),
        "must_not": (
            "flutter-mobile",
            "angular-spa",
            "react-spa",
            "java-spring-api",
            "python-dev",
            "mcp-builder",
            "agentic-ai-dev",
            "startup-design-to-code",
            "polyglot-monorepo",
        ),
    },
    {
        "id": "wrong-stack-negative",
        "prompt": "Tune a PostgreSQL 18 index and a pgvector query",
        "must": (),
        "must_not": ("flutter-mobile", "angular-spa", "react-spa"),
    },
)


def die(msg: str, code: int) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    rest = text[3:].lstrip("\n")
    end = rest.find("\n---")
    if end < 0:
        return {}
    data: dict[str, str] = {}
    pending: str | None = None
    acc: list[str] = []

    def flush() -> None:
        nonlocal pending, acc
        if pending is not None:
            data[pending] = " ".join(x for x in acc if x)
        pending = None
        acc = []

    for raw in rest[:end].splitlines():
        if pending is not None and (raw.startswith(" ") or raw.startswith("\t")):
            trig = re.match(r"^\s+triggers:\s*(.*)$", raw)
            if trig:
                flush()
                data["triggers"] = trig.group(1).strip().strip("\"'")
                continue
            if re.match(r"^\s+[A-Za-z0-9_-]+:", raw):
                flush()
                continue
            acc.append(raw.strip().strip("\"'"))
            continue
        flush()
        top = re.match(r"^(name|description):\s*(.*)$", raw)
        if top:
            key, val = top.group(1), top.group(2)
            pending = key
            if val in (">", "|", ""):
                acc = []
            else:
                acc = [val.strip().strip("\"'")] if val.strip() else []
            continue
        trig = re.match(r"^\s+triggers:\s*(.*)$", raw)
        if trig:
            data["triggers"] = trig.group(1).strip().strip("\"'")
    flush()
    return data


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP and len(t) > 1}


def load_skills(skills_dir: Path) -> list[dict[str, str]]:
    skills: list[dict[str, str]] = []
    for path in sorted(skills_dir.rglob("SKILL.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            skills.append({"path": str(path), "error": f"unreadable: {exc}"})
            continue
        fm = parse_frontmatter(text)
        skills.append(
            {
                "path": str(path),
                "dir": path.parent.name,
                "name": fm.get("name", ""),
                "description": fm.get("description", ""),
                "triggers": fm.get("triggers", ""),
            }
        )
    return skills


def name_matches_directory(skill: dict[str, str], skills_root: Path | None) -> bool:
    name = skill.get("name") or ""
    directory = skill.get("dir") or ""
    if name == directory:
        return True
    # Nested plugin skills (e.g. daisyui/colors named daisyui-colors) keep a
    # namespaced name; the Agent Skills spec's "match parent directory" rule
    # applies to top-level skill folders.
    if not skills_root or not name.endswith("-" + directory):
        return False
    try:
        rel = Path(skill["path"]).parent.relative_to(skills_root)
    except ValueError:
        return False  # skill path is outside the scanned skills root
    return len(rel.parts) >= 2


def spec_findings(skill: dict[str, str], skills_root: Path | None = None) -> list[str]:
    if skill.get("error"):
        return [skill["error"]]
    out: list[str] = []
    name = skill.get("name") or ""
    desc = skill.get("description") or ""
    if not name:
        out.append("missing required field: name (Agent Skills spec)")
    else:
        if len(name) > NAME_MAX:
            out.append(f"name exceeds {NAME_MAX} characters (Agent Skills spec)")
        if not NAME_RE.fullmatch(name):
            out.append(
                "name must be lowercase alphanumeric with single hyphens, "
                "no leading/trailing/consecutive hyphen (Agent Skills spec)"
            )
        if not name_matches_directory(skill, skills_root):
            out.append(f"name {name!r} must match directory {skill.get('dir')!r} (Agent Skills spec)")
    if not desc.strip():
        out.append("missing required field: description (Agent Skills spec)")
    elif len(desc) > DESC_MAX:
        out.append(f"description exceeds {DESC_MAX} characters (Agent Skills spec)")
    return out


def haystack(skill: dict[str, str]) -> set[str]:
    name = skill.get("name") or ""
    return tokens(" ".join((name.replace("-", " "), skill.get("description") or "", skill.get("triggers") or "")))


def overlap(prompt: str, skill: dict[str, str]) -> set[str]:
    return (tokens(prompt) & haystack(skill)) - GENERIC


def evaluate_case(
    case: dict[str, object],
    by_name: dict[str, dict[str, str]],
) -> dict[str, object]:
    prompt = str(case["prompt"])
    cid = str(case["id"])
    missing = [n for n in list(case["must"]) + list(case["must_not"]) if n not in by_name]
    if missing:
        return {"id": cid, "status": "SKIP", "detail": f"skills not in dir: {', '.join(missing)}"}
    fails: list[str] = []
    for name in case["must"]:
        hits = overlap(prompt, by_name[str(name)])
        if len(hits) < MIN_ACTIVATE_HITS:
            fails.append(f"under-trigger {name} (overlap {sorted(hits) or 'none'})")
    for name in case["must_not"]:
        hits = overlap(prompt, by_name[str(name)])
        if len(hits) >= MIN_ACTIVATE_HITS:
            fails.append(f"over-trigger {name} (overlap {sorted(hits)})")
    if fails:
        return {"id": cid, "status": "FAIL", "detail": "; ".join(fails)}
    return {"id": cid, "status": "PASS", "detail": "activation/non-activation holds"}


def write_skill(root: Path, name: str, description: str, triggers: str = "x, y") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f'description: "{description}"\n'
        "metadata:\n"
        f"  triggers: {triggers}\n"
        "allowed-tools: Read\n"
        "---\n\n## Iron Law\n\nNo-op.\n",
        encoding="utf-8",
    )
    return d / "SKILL.md"


def selftest() -> int:
    fail = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal fail
        if cond:
            print(f"  ok   {label}")
        else:
            fail += 1
            print(f"  FAIL {label} {detail}")

    bad_name = {"path": "x", "dir": "bad-name", "name": "Bad_Name", "description": "Use when handling PDFs.", "triggers": ""}
    check("positive: uppercase/underscore name fails spec", any("lowercase" in e for e in spec_findings(bad_name)))
    hyphen = {"path": "x", "dir": "-pdf", "name": "-pdf", "description": "Use when handling PDFs.", "triggers": ""}
    check("positive: leading hyphen name fails spec", any("hyphen" in e for e in spec_findings(hyphen)))
    dbl = {"path": "x", "dir": "pdf--x", "name": "pdf--x", "description": "Use when handling PDFs.", "triggers": ""}
    check("positive: consecutive hyphens fail spec", any("hyphen" in e for e in spec_findings(dbl)))
    mismatch = {"path": "x", "dir": "other", "name": "pdf-processing", "description": "Use when handling PDFs.", "triggers": ""}
    check("positive: name/directory mismatch fails spec", any("must match directory" in e for e in spec_findings(mismatch)))
    long_desc = {"path": "x", "dir": "pdf-processing", "name": "pdf-processing", "description": "x" * (DESC_MAX + 1), "triggers": ""}
    check("positive: description >1024 fails spec", any("1024" in e for e in spec_findings(long_desc)))
    missing = {"path": "x", "dir": "pdf-processing", "name": "", "description": "", "triggers": ""}
    check("positive: missing name and description fail spec", len(spec_findings(missing)) >= 2)
    good = {
        "path": "x",
        "dir": "pdf-processing",
        "name": "pdf-processing",
        "description": "Extract PDF text. Use when handling PDFs.",
        "triggers": "pdf, forms",
    }
    check("negative: spec-compliant name and description pass", spec_findings(good) == [])

    fm = parse_frontmatter(
        '---\nname: mcp-builder\ndescription: >\n  Use when building MCP servers.\nmetadata:\n  triggers: MCP server, FastMCP\n---\n# Body\n'
    )
    check("negative: folded description and indented triggers parse", fm.get("name") == "mcp-builder" and "MCP" in fm.get("description", "") and "FastMCP" in fm.get("triggers", ""))
    plain = parse_frontmatter(
        "---\nname: mcp-builder\ndescription: Use when building MCP servers to\n"
        "  integrate TypeScript and Fastify.\nmetadata:\n  triggers: MCP server\n---\n# B\n"
    )
    check(
        "negative: plain multiline description keeps continuation lines",
        "TypeScript" in plain.get("description", "") and "Fastify" in plain.get("description", ""),
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_skill(
            root,
            "flutter-mobile",
            "Use when building Flutter screens, Riverpod providers, or widget tests.",
            "Flutter, Dart, Riverpod, widget test",
        )
        write_skill(
            root,
            "java-spring-api",
            "Helps with apps.",
            "generic",
        )
        write_skill(
            root,
            "angular-spa",
            "Use when building Angular 22 standalone components with daisyUI.",
            "Angular, daisyUI, standalone",
        )
        write_skill(
            root,
            "react-spa",
            "Use when building React 19 SPA routes with shadcn/ui and TanStack Query.",
            "React, shadcn, TanStack Query",
        )
        skills = {s["name"]: s for s in load_skills(root) if s.get("name")}
        flutter = evaluate_case(CASES[0], skills)
        check(
            "negative: expected flutter-mobile activates on a Flutter prompt (vague sibling does not)",
            flutter["status"] == "PASS",
            str(flutter),
        )
        vague_java = evaluate_case(
            {"id": "java-positive", "prompt": CASES[3]["prompt"], "must": ("java-spring-api",), "must_not": ()},
            skills,
        )
        check(
            "positive: under-trigger detected when java-spring-api description is too vague",
            vague_java["status"] == "FAIL" and "under-trigger java-spring-api" in str(vague_java["detail"]),
        )
        over = dict(skills["angular-spa"])
        over["description"] = "Flutter Riverpod widget test Angular React Java Spring Boot everything"
        over["triggers"] = "Flutter, Riverpod, widget, test"
        mixed = dict(skills)
        mixed["angular-spa"] = over
        over_case = evaluate_case(CASES[0], mixed)
        check(
            "positive: over-trigger detected when Angular description matches a Flutter prompt",
            over_case["status"] == "FAIL" and "over-trigger angular-spa" in str(over_case["detail"]),
        )
        skipped = evaluate_case(CASES[4], skills)  # python-dev absent
        check("negative: missing case skills are SKIP not FAIL", skipped["status"] == "SKIP")

        rc_spec, spec_lines = run_scan(root, activation=False, machine=True)
        nested = root / "daisyui" / "colors"
        nested.mkdir(parents=True)
        (nested / "SKILL.md").write_text(
            "---\nname: daisyui-colors\ndescription: Use when theming daisyUI color tokens.\n---\n# X\n",
            encoding="utf-8",
        )
        nested_skill = {
            "path": str(nested / "SKILL.md"),
            "dir": "colors",
            "name": "daisyui-colors",
            "description": "Use when theming daisyUI color tokens.",
            "triggers": "",
        }
        check(
            "negative: nested plugin skill may use namespaced {parent}-{leaf} name",
            spec_findings(nested_skill, root) == [],
        )
        check("negative: spec-clean fixture dir has no spec findings", rc_spec == 0)
        # plant an invalid spec name beside valid YAML-ish content
        bad_dir = root / "broken"
        bad_dir.mkdir()
        (bad_dir / "SKILL.md").write_text(
            "---\nname: Bad_Name\ndescription: Use when handling nothing special here.\n---\n# X\n",
            encoding="utf-8",
        )
        rc_bad, bad_lines = run_scan(root, activation=False, machine=True)
        check(
            "positive: machine scan fails on Bad_Name",
            rc_bad == 1 and any("Bad_Name" in x or "lowercase" in x for x in bad_lines),
            "\n".join(bad_lines[:8]),
        )

    # Ad-hoc prompt API
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_skill(root, "flutter-mobile", "Use when building Flutter screens and Riverpod providers.", "Flutter, Riverpod")
        write_skill(root, "angular-spa", "Use when building Angular standalone components.", "Angular")
        skills = {s["name"]: s for s in load_skills(root) if s.get("name")}
        adhoc = evaluate_case(
            {
                "id": "adhoc",
                "prompt": "Add a Riverpod provider to the Flutter app",
                "must": ("flutter-mobile",),
                "must_not": ("angular-spa",),
            },
            skills,
        )
        check("negative: ad-hoc Flutter prompt activates flutter-mobile only", adhoc["status"] == "PASS", str(adhoc))

    print("selftest PASS" if fail == 0 else "selftest FAIL")
    return 1 if fail else 0


def run_scan(skills_dir: Path, activation: bool, machine: bool, extra_case: dict[str, object] | None = None) -> tuple[int, list[str]]:
    skills = load_skills(skills_dir)
    if not skills:
        return 1, [f"ERROR: no SKILL.md under {skills_dir}"]
    lines: list[str] = []
    spec_fail = 0
    for skill in skills:
        findings = spec_findings(skill, skills_dir)
        rel = skill.get("path", "")
        if findings:
            spec_fail += 1
            for item in findings:
                if machine:
                    lines.append(f"SPEC\t{rel}\t{item}")
                else:
                    lines.append(f"FAIL spec {rel}: {item}")
        elif not machine:
            lines.append(f"PASS spec {skill.get('name') or rel}")
    act_fail = 0
    act_pass = 0
    act_skip = 0
    if activation:
        by_name = {s["name"]: s for s in skills if s.get("name")}
        cases = list(CASES)
        if extra_case:
            cases.append(extra_case)
        for case in cases:
            result = evaluate_case(case, by_name)
            status = str(result["status"])
            if status == "FAIL":
                act_fail += 1
            elif status == "PASS":
                act_pass += 1
            else:
                act_skip += 1
            if machine:
                lines.append(f"ACTIVATION\t{status}\t{result['id']}\t{result['detail']}")
            else:
                lines.append(f"{status} activation {result['id']}: {result['detail']}")
        if act_pass + act_fail == 0 and extra_case is None:
            # All representative cases skipped (tiny fixture dir) — not a library eval.
            lines.append("ACTIVATION skipped (representative skills not in dir)")
    rc = 1 if spec_fail or act_fail else 0
    if not machine:
        lines.append(
            f"RESULT: spec_fail={spec_fail} activation_pass={act_pass} "
            f"activation_fail={act_fail} activation_skip={act_skip} spec={SPEC_URL}"
        )
    return rc, lines


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    skills_dir: Path | None = None
    activation = False
    machine = False
    prompt = ""
    expect = ""
    forbid: tuple[str, ...] = ()
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dir" and i + 1 < len(argv):
            skills_dir = Path(argv[i + 1])
            i += 2
            continue
        if a == "--activation":
            activation = True
            i += 1
            continue
        if a == "--machine":
            machine = True
            i += 1
            continue
        if a == "--prompt" and i + 1 < len(argv):
            prompt = argv[i + 1]
            i += 2
            continue
        if a == "--expect" and i + 1 < len(argv):
            expect = argv[i + 1]
            i += 2
            continue
        if a == "--forbid" and i + 1 < len(argv):
            forbid = tuple(x.strip() for x in argv[i + 1].split(",") if x.strip())
            i += 2
            continue
        die(
            "usage: check-skill-spec.py --dir DIR [--activation] [--machine] "
            "[--prompt TEXT --expect NAME [--forbid A,B]] | --selftest",
            2,
        )
    if skills_dir is None or not skills_dir.is_dir():
        die("usage: check-skill-spec.py --dir DIR [--activation] [--machine] | --selftest", 2)
    extra = None
    if prompt:
        if not expect and not forbid:
            die("--prompt requires --expect and/or --forbid", 2)
        extra = {
            "id": "adhoc",
            "prompt": prompt,
            "must": (expect,) if expect else (),
            "must_not": forbid,
        }
        activation = True
    rc, lines = run_scan(skills_dir, activation=activation, machine=machine, extra_case=extra)
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
