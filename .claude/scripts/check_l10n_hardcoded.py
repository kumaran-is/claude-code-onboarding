#!/usr/bin/env python3
"""Flutter l10n coverage: user-facing Text/SnackBar literals in lib/.

Parity (keys present in every ARB) is check_l10n_parity.py. This checker flags
Dart UI that never entered the catalogue. Angular/React i18n is out of scope
(use the design-system i18n reference).

Usage:
  check_l10n_hardcoded.py [LIB_DIR] [--selftest]

Exit: 0 clean, 1 findings, 2 NOT APPLICABLE / broken selftest.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

# Text('...'), Text("..."), SnackBar(content: Text('...')) — skip interpolation.
LIT = re.compile(
    r"""(?:Text|SelectableText)\(\s*(?:const\s+)?['\"]([^'\"$\\{][^'\"]{1,})['\"]"""
)
IGNORE = re.compile(r"ignore-l10n:\s*(\S.{7,})")
SKIP_PARTS = {"generated", ".dart_tool", "l10n", "gen_l10n", "test", "testing", "goldens"}
OK_PREFIX = (
    "debug", "todo", "fixme", "http://", "https://", "assets/", "package:",
)


def skip_file(path: Path) -> bool:
    name = path.name
    if name.endswith(("_test.dart", ".g.dart", ".freezed.dart", ".gr.dart")):
        return True
    return any(p in path.parts for p in SKIP_PARTS)


def exempt(text: str, line: str) -> bool:
    low = text.strip().lower()
    if any(low.startswith(p) for p in OK_PREFIX):
        return True
    if len(text) <= 1:
        return True
    if IGNORE.search(line):
        return True
    return False


def check(lib: Path) -> tuple[int, list[str]]:
    if not lib.is_dir():
        return 2, [f"NOT APPLICABLE: {lib} is not a directory"]
    dart = [p for p in lib.rglob("*.dart") if p.is_file() and not skip_file(p)]
    if not dart:
        return 2, [f"NOT APPLICABLE: no Dart UI files under {lib}"]
    hits: list[str] = []
    for p in dart:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines, 1):
            prev = lines[i - 2] if i > 1 else ""
            if IGNORE.search(prev) or IGNORE.search(line):
                continue
            for m in LIT.finditer(line):
                if exempt(m.group(1), line):
                    continue
                hits.append(f"FAIL {p}:{i} hardcoded {m.group(0)[:80]!s} — use l10n / AppLocalizations")
    n_fail = len(hits)
    hits.append(f"scanned: {len(dart)} dart file(s), {n_fail} hit(s)")
    return (1 if n_fail else 0), hits


def selftest() -> int:
    fail = 0

    def ok(cond: bool, name: str, detail: object = "") -> None:
        nonlocal fail
        print(f"  {'ok  ' if cond else 'FAIL'} {name}" + ("" if cond else f" -> {detail}"))
        fail += 0 if cond else 1

    with tempfile.TemporaryDirectory() as d:
        lib = Path(d) / "lib"
        lib.mkdir()
        (lib / "ok.dart").write_text("Text(l10n.hello);\nText(AppLocalizations.of(context).bye);\n")
        rc, out = check(lib)
        ok(rc == 0, "negative: l10n getters pass", out)

        (lib / "bad.dart").write_text("Widget build() => Text('Save changes');\n")
        rc, out = check(lib)
        ok(rc == 1 and any("Save changes" in l for l in out), "positive: Text('Save changes') FAILs", out)

        (lib / "exempt.dart").write_text(
            "Text('https://example.com');\nText('BrandMark'); // ignore-l10n: brand mark\n"
        )
        (lib / "bad.dart").unlink()
        rc, out = check(lib)
        ok(rc == 0, "negative: url + ignore-l10n pass", out)

        rc, out = check(Path(d) / "missing")
        ok(rc == 2, "negative: missing dir is NOT APPLICABLE", out)

        gen = lib / "l10n"
        gen.mkdir()
        (gen / "app_localizations.dart").write_text("Text('Submit');\n")
        rc, out = check(lib)
        ok(rc == 0 and not any("Submit" in l for l in out), "negative: lib/l10n generated files skipped", out)

    print("selftest PASS" if fail == 0 else "selftest FAIL")
    return 0 if fail == 0 else 2


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        return selftest()
    lib = Path(argv[0]) if argv else Path("lib")
    rc, lines = check(lib)
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
