#!/usr/bin/env bash
# lint-testing-tools.sh — detect incorrect test-tool recommendations.
#
# Canonical rule: .claude/rules/testing-tool-selection.md
#   Flutter Android/iOS UI/E2E -> Maestro CLI/MCP only. Browser automation (Playwright, Chrome DevTools,
#   Browser-Use, claude-in-chrome, Puppeteer, Cypress, Selenium) is for web targets.
#
# Checks
#   R1  Flutter/mobile-context files must not mention a browser-automation tool unless the same line carries a
#       guard word (never / not / instead / web / Angular / React / BLOCKED / ...).
#   R2  Files that teach browser testing must link the canonical rule (so they state their scope).
#   R3  The canonical rule exists and is linked from CLAUDE.md, the flutter-mobile skill, flutter-e2e-maestro.md
#       and skill-triggers.md.
#   R4  No line anywhere pairs a mobile target (Android, iOS, iPhone/iPad, emulator, physical device, mobile app...)
#       with a browser tool, a browser or a resized viewport unless it carries a guard word. Browser-testing assets
#       are checked too (their web lines carry the "web" guard).
#   R5  No stale browser-tool syntax in docs: `playwright-cli ... --output` (flag is --filename), `playwright-cli
#       network` (command is `requests`), installing playwright-cli from @playwright/mcp (package is @playwright/cli),
#       or Browser-Use tool names the configured MCP server does not expose (it exposes browser_exec,
#       browser_screenshot, browser_login, browser_feedback). Lines that say the old form does not exist are allowed.
#   R6  Flutter-context files (MOBILE_CONTEXT without the React Native skill/agent) must not recommend another device
#       UI/E2E driver (Detox, Appium, Patrol, Espresso, XCUITest, flutter_driver) unless the line carries a guard word.
#
# Usage: lint-testing-tools.sh [--root <repo>] [--selftest]      Exit 0 = clean, 1 = violations.
set -uo pipefail
exec python3 - "$@" <<'PY'
import glob
import os
import re
import sys
import tempfile

BT = re.compile(r"playwright|chrome[- ]?devtools|browser-use|puppeteer|cypress|selenium|claude-in-chrome|mcp__chrome|mcp__browser", re.I)
# R4 also treats "a browser" and a resized/emulated viewport as browser testing (rule 3 of the canonical rule)
BT_WIDE = re.compile(BT.pattern + r"|\b(a|the|in a|chrome|desktop) browser\b|\bviewport\b|\bresiz\w* (the )?(browser|window|viewport)", re.I)
GUARD = re.compile(r"\b(never|not|n't|do not|instead|rather than|forbidden|prohibit\w*|blocked|not run|substitut\w*|web|angular|react|website|canonical|testing-tool-selection|detox)\b|❌|✗|⛔", re.I)
MOBILE = re.compile(r"android|\bios\b|iphone|ipad|emulator|physical device|mobile app|flutter mobile|flutter (ios|android)|mobile e2e|mobile ui|on[- ]device", re.I)
CANON = ".claude/rules/testing-tool-selection.md"

MOBILE_CONTEXT = [
    ".claude/skills/flutter-mobile/**/*.md", ".claude/skills/flutter-genui/**/*.md", ".claude/skills/flutter-animations/**/*.md",
    ".claude/skills/mobile-design/**/*.md", ".claude/skills/mobile-developer/**/*.md", ".claude/skills/screenshot-to-flutter/**/*.md",
    ".claude/skills/flutter-security-expert/**/*.md", ".claude/skills/riverpod-patterns/**/*.md",
    ".claude/agents/flutter-*.md", ".claude/agents/mobile-developer.md", ".claude/agents/riverpod-reviewer.md",
    ".claude/commands/scaffold-flutter-*.md", ".claude/rules/flutter-*.md", "docs/workflows/feature-flutter-mobile.md",
]
BROWSER_ASSETS = [
    ".claude/agents/browser-testing.md", ".claude/skills/browser-testing/SKILL.md",
    ".claude/agents/reality-checker.md", "docs/workflows/browser-e2e-testing.md",
]
MUST_LINK_CANON = ["CLAUDE.md", ".claude/skills/flutter-mobile/SKILL.md",
                   ".claude/skills/flutter-mobile/reference/flutter-e2e-maestro.md", ".claude/rules/skill-triggers.md"]
FLUTTER_CONTEXT = [p for p in MOBILE_CONTEXT if "mobile-developer" not in p]
OTHER_E2E = re.compile(r"\b(detox|appium|patrol|espresso|xcuitest|flutter_driver)\b", re.I)
GUARD_R6 = re.compile(GUARD.pattern.replace("|detox", ""), re.I)
R4_SKIP = {CANON, ".claude/scripts/lint-testing-tools.sh", ".claude/hooks/pre-browser-tool-advisory.sh"}
R4_SKIP_DIRS = (".claude/skills/ui-ux-pro-max/", ".git/", "node_modules/")
STALE = [
    (re.compile(r"playwright-cli\b[^\n|]*\s--output\b"), "playwright-cli has no --output flag; use --filename"),
    (re.compile(r"playwright-cli(\s+-s=\S+)?\s+network(?![-\w])"), "playwright-cli `network` was replaced by `requests` / `request <n>`"),
    (re.compile(r"(npm\s+(i|install)\s+(-g\s+)?|npx\s+(-y\s+)?)@playwright/mcp\b"), "playwright-cli comes from @playwright/cli (pinned), not @playwright/mcp"),
    (re.compile(r"\bbrowser_(navigate|get_state|input|click|extract_content|scroll_down|scroll_up|go_back|list_tabs|switch_tab|close_tab|get_html|type)\b|mcp__browser-use__(?!browser_(exec|screenshot|login|feedback)\b)\w+"), "Browser-Use MCP exposes only browser_exec, browser_screenshot, browser_login, browser_feedback"),
]
STALE_OK = re.compile(r"do(es)? not exist|not a command|no longer|older docs|was `|renamed|stale|lint-testing-tools", re.I)
R5_SKIP = {".claude/scripts/lint-testing-tools.sh"}


def files(root, patterns):
    out = set()
    for p in patterns:
        out.update(glob.glob(os.path.join(root, p), recursive=True))
    return sorted(f for f in out if os.path.isfile(f))


def all_files(root):
    # os.walk, not glob("**"): glob skips dot-directories, so .claude/ (every skill, agent and rule) was never scanned
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if x not in (".git", "node_modules")]
        for name in fs:
            yield os.path.join(d, name)


def rel(root, f):
    return os.path.relpath(f, root)


def lint(root):
    bad = []
    # R1
    for f in files(root, MOBILE_CONTEXT):
        for n, line in enumerate(open(f, errors="ignore"), 1):
            if BT.search(line) and not GUARD.search(line):
                bad.append(f"R1 {rel(root, f)}:{n}: mobile-context file recommends a browser tool: {line.strip()[:110]}")
    # R2
    for p in BROWSER_ASSETS:
        f = os.path.join(root, p)
        if os.path.exists(f) and "testing-tool-selection" not in open(f, errors="ignore").read():
            bad.append(f"R2 {p}: teaches browser testing but does not link {CANON} (scope is unstated)")
    # R3
    if not os.path.exists(os.path.join(root, CANON)):
        bad.append(f"R3 {CANON}: canonical rule is missing")
    else:
        for p in MUST_LINK_CANON:
            f = os.path.join(root, p)
            if not os.path.exists(f):
                bad.append(f"R3 {p}: expected file is missing")
            elif "testing-tool-selection" not in open(f, errors="ignore").read():
                bad.append(f"R3 {p}: does not link the canonical rule {CANON}")
    # R4
    for f in all_files(root):
        r = rel(root, f)
        if not os.path.isfile(f) or not r.endswith((".md", ".yaml", ".yml", ".sh", ".json")) or r in R4_SKIP or r.startswith(R4_SKIP_DIRS):
            continue
        for n, line in enumerate(open(f, errors="ignore"), 1):
            if BT_WIDE.search(line) and MOBILE.search(line) and not GUARD.search(line):
                bad.append(f"R4 {r}:{n}: pairs a mobile target with a browser tool: {line.strip()[:110]}")
    # R5
    for f in all_files(root):
        r = rel(root, f)
        if not os.path.isfile(f) or not r.endswith((".md", ".yaml", ".yml", ".sh", ".json")) or r in R5_SKIP or r.startswith(R4_SKIP_DIRS) or r.startswith(".claude/state/") or "agent-memory" in r:
            continue
        for n, line in enumerate(open(f, errors="ignore"), 1):
            if STALE_OK.search(line):
                continue
            for rx, why in STALE:
                if rx.search(line):
                    bad.append(f"R5 {r}:{n}: {why}: {line.strip()[:110]}")
                    break
    # R6
    for f in files(root, FLUTTER_CONTEXT):
        for n, line in enumerate(open(f, errors="ignore"), 1):
            if OTHER_E2E.search(line) and not GUARD_R6.search(line):
                bad.append(f"R6 {rel(root, f)}:{n}: Flutter file recommends a non-Maestro device E2E tool: {line.strip()[:110]}")
    return bad


def selftest():
    fail = 0
    with tempfile.TemporaryDirectory() as t:
        def w(p, s):
            os.makedirs(os.path.dirname(os.path.join(t, p)), exist_ok=True)
            open(os.path.join(t, p), "w").write(s)
        link = f"See {CANON}.\n"
        w(CANON, "# rule\n")
        for p in MUST_LINK_CANON + BROWSER_ASSETS:
            w(p, link)
        clean = lint(t)
        print("  ok   clean tree has no violations" if not clean else f"  FAIL clean tree flagged: {clean}")
        fail += bool(clean)
        cases = [
            ("R1", ".claude/skills/flutter-mobile/reference/x.md", "Run the Android E2E with playwright-cli goto the emulator\n"),
            ("R1", ".claude/agents/flutter-mobile.md", "Use mcp__chrome-devtools__navigate_page for the screen flow\n"),
            ("R4", "docs/guide.md", "Test the app on the iOS simulator using Chrome DevTools MCP\n"),
            ("R4", "docs/guide2.md", "For the Android emulator, drive the UI with Playwright\n"),
            ("R4", "docs/guide3.md", "Use Playwright to test the Flutter iOS app.\n"),
            ("R4", "docs/guide4.md", "Check the iPhone layout with Chrome DevTools MCP\n"),
            ("R4", "docs/guide5.md", "Resize the viewport to 390 px to check the Flutter mobile app\n"),
            ("R4", ".claude/skills/browser-testing/SKILL.md", "Use playwright-cli for the Flutter iOS app too\n"),
            ("R2", ".claude/agents/reality-checker.md", "uses playwright-cli only\n"),
            ("R3", "CLAUDE.md", "no link here\n"),
            ("R5", "docs/r5a.md", "playwright-cli -s=qa screenshot --output shot.png\n"),
            ("R5", "docs/r5b.md", "playwright-cli -s=qa network\n"),
            ("R5", "docs/r5c.md", "npm install -g @playwright/mcp@latest\n"),
            ("R5", "docs/r5d.md", "browser_navigate({ url: 'http://x' })\n"),
            ("R5", "docs/r5e.md", "call mcp__browser-use__fill with the email\n"),
            ("R5", ".claude/skills/x/SKILL.md", "playwright-cli -s=qa network\n"),
            ("R4", ".claude/agents/x.md", "Drive the iOS simulator with Chrome DevTools\n"),
            ("R6", ".claude/skills/mobile-design/reference/z.md", "| Browser-based E2E | Cannot test native features | Maestro MCP or Detox |\n"),
            ("R6", ".claude/agents/flutter-mobile.md", "Write the checkout journey with Patrol\n"),
        ]
        for code, path, text in cases:
            before = {path: open(os.path.join(t, path)).read() if os.path.exists(os.path.join(t, path)) else None}
            w(path, text)
            hits = [h for h in lint(t) if h.startswith(code) and path in h]
            ok = bool(hits)
            print(f"  {'ok  ' if ok else 'FAIL'} detects {code} violation in {path}")
            fail += (not ok)
            if before[path] is None:
                os.remove(os.path.join(t, path))
            else:
                w(path, before[path])
        guarded = [
            ".claude/skills/flutter-mobile/reference/y.md|Never test the Android emulator app with Playwright; use Maestro.\n",
            "docs/g3.md|Angular web app on an emulator-sized viewport uses Playwright.\n",
            "docs/g4.md|If the iOS simulator is unavailable report BLOCKED, do not substitute Chrome DevTools.\n",
            "docs/g5.md|playwright-cli -s=qa screenshot --filename shot.png; playwright-cli -s=qa requests; playwright-cli -s=qa network-state-set offline\n",
            "docs/g6.md|Use mcp__browser-use__browser_exec then mcp__browser-use__browser_screenshot. Old browser_navigate does not exist.\n",
            ".claude/skills/flutter-mobile/reference/w.md|Never use Patrol, Appium or Detox for Flutter device flows; Maestro only.\n",
            ".claude/skills/mobile-developer/SKILL.md|Detox drives the React Native E2E suite.\n",
        ]
        for g in guarded:
            p, text = g.split("|", 1)
            w(p, text)
        leftover = [h for h in lint(t) if h.startswith(("R1", "R4", "R5", "R6"))]
        print("  ok   guarded sentences and current syntax (never / web / BLOCKED / --filename / requests / browser_exec) are allowed" if not leftover else f"  FAIL false positives: {leftover}")
        fail += bool(leftover)
    print("selftest PASS" if not fail else "selftest FAIL")
    return 1 if fail else 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
    root = os.path.realpath(root)
    bad = lint(root)
    for b in bad:
        print("  " + b)
    print(f"lint-testing-tools: {len(bad)} violation(s)")
    return 1 if bad else 0


sys.exit(main(sys.argv[1:]))
PY
