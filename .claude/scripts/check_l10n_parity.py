#!/usr/bin/env python3
"""l10n catalog parity for Flutter ARB files, checked both ways against the template.

FAIL: a locale lacks a template key, has a key the template lacks (stale or typo), or a message's
`{placeholder}` set differs from the template's. Metadata keys (`@key`, `@@locale`) are ignored.
Coverage (hardcoded strings in widgets) is a separate check: parity can be green while coverage is red.

Usage: check_l10n_parity.py [L10N_DIR] [--template app_en.arb]  (defaults: lib/l10n, template from l10n.yaml or app_en.arb)
       --selftest
Exit: 0 clean, 1 findings, 2 cannot run (no template, or fewer than 2 ARB files).
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

if sys.version_info < (3, 10):  # `X | None` annotations below need 3.10; say so instead of a TypeError
    sys.exit(f"{Path(__file__).name} needs Python 3.10+, found {sys.version.split()[0]}")

PH_RE = re.compile(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*[,}]")


def placeholders(msg: str) -> set[str]:
    """Argument names of top-level `{arg}` / `{arg, plural|select, ...}`; nested ICU branch text is not an argument
    (`{n, plural, one{# item} other{...}}`), but a `{arg}` nested inside a branch is."""
    if not isinstance(msg, str):
        return set()
    names, depth, i, arg_depths = set(), 0, 0, []
    while i < len(msg):
        ch = msg[i]
        if ch == "'" and i + 1 < len(msg) and msg[i + 1] in "{}'":  # ICU apostrophe quoting
            i += 2
            continue
        if ch == "{":
            m = PH_RE.match(msg, i)
            # an argument opens at depth 0, or inside a branch body: arg `{` -> branch `{` (arg + 1) -> arg (arg + 2)
            if m and (depth == 0 or (arg_depths and depth == arg_depths[-1] + 2)):
                names.add(m.group(1))
                arg_depths.append(depth)
            depth += 1
        elif ch == "}":
            depth -= 1
            if arg_depths and arg_depths[-1] == depth:
                arg_depths.pop()
        i += 1
    return names


def messages(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("@")}


def template_name(root: Path, l10n_dir: Path, given: str | None) -> str:
    if given:
        return given
    cfg = root / "l10n.yaml"
    if cfg.is_file():
        m = re.search(r"^template-arb-file:\s*['\"]?([^'\"\s]+)", cfg.read_text(), re.M)
        if m:
            return m.group(1)
    return "app_en.arb"


def check(l10n_dir: Path, template: str) -> tuple[int, list[str]]:
    tpl_path = l10n_dir / template
    files = sorted(l10n_dir.glob("*.arb"))
    if not tpl_path.is_file() or len(files) < 2:
        return 2, [f"BLOCKED: need the template {tpl_path} and at least one other ARB file (found {len(files)})"]
    tpl = messages(tpl_path)
    lines = []
    for f in files:
        if f == tpl_path:
            continue
        try:
            loc = messages(f)
        except (ValueError, OSError) as exc:
            lines.append(f"FAIL {f.name}: unreadable ({type(exc).__name__}: {exc})")
            continue
        lines += [f"FAIL {f.name}: missing key {k}" for k in sorted(tpl.keys() - loc.keys())]
        lines += [f"FAIL {f.name}: extra key {k} (not in {template})" for k in sorted(loc.keys() - tpl.keys())]
        for k in sorted(tpl.keys() & loc.keys()):
            a, b = placeholders(tpl[k]), placeholders(loc[k])
            if a != b:
                lines.append(f"FAIL {f.name}: {k} placeholders {sorted(b)} != template {sorted(a)}")
    lines.append(f"scanned: {len(files)} ARB file(s), {len(tpl)} template key(s)")
    return (1 if any(l.startswith("FAIL") for l in lines) else 0), lines


def selftest() -> int:
    fails = 0

    def ok(cond: bool, label: str, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f" -> {detail}"))
        fails += 0 if cond else 1

    with tempfile.TemporaryDirectory() as d:
        l10n = Path(d)
        w = lambda name, obj: (l10n / name).write_text(json.dumps(obj))  # noqa: E731 - selftest fixture writer
        w("app_en.arb", {"@@locale": "en", "hello": "Hello {name}", "@hello": {"placeholders": {"name": {}}}, "bye": "Bye"})
        w("app_es.arb", {"@@locale": "es", "hello": "Hola {name}", "bye": "Adiós"})
        rc, out = check(l10n, "app_en.arb")
        ok(rc == 0, "negative: matching catalogs are clean (metadata ignored)", out)
        w("app_es.arb", {"hello": "Hola {nombre}", "adios": "Adiós"})
        rc, out = check(l10n, "app_en.arb")
        text = "\n".join(out)
        ok(rc == 1 and "missing key bye" in text, "positive: a key missing from a locale FAILs", out)
        ok("extra key adios" in text, "positive: a key only in a locale FAILs (the other direction)", out)
        ok("hello placeholders" in text, "positive: a renamed placeholder FAILs", out)
        w("app_es.arb", {"hello": "Hola {name, plural, one{uno} other{otros}}", "bye": "Adiós"})
        ok(placeholders("{n, plural, one{{who} has one} other{{who} has #}}") == {"n", "who"},
           "an argument nested inside a plural branch is still an argument")
        rc, out = check(l10n, "app_en.arb")
        ok(rc == 0, "negative: ICU plural syntax keeps the same placeholder", out)
        (l10n / "app_es.arb").unlink()
        rc, out = check(l10n, "app_en.arb")
        ok(rc == 2, "a lone template is BLOCKED, never clean", out)
    print("selftest PASS" if fails == 0 else "selftest FAIL")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("l10n_dir", nargs="?", default="lib/l10n")
    ap.add_argument("--template")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    l10n_dir = Path(a.l10n_dir).resolve()
    rc, lines = check(l10n_dir, template_name(Path.cwd(), l10n_dir, a.template))
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main())
