#!/usr/bin/env bash
# Angular UI mode: resolve, detect and check the project's UI component system (daisyui | spartan | hybrid).
# One detector, three callers: /scaffold-angular-app (resolve), the PostToolUse advisory
# post-edit-angular-ui-mode-advisory.sh (check-file), and /verify + CI (detect).
# Canonical guidance: .claude/skills/angular-spa/reference/ui-mode-selection.md
#
# The mode lives in the Angular workspace's package.json:  "config": { "uiMode": "daisyui" }
# (npm's per-package config field; set with `npm pkg set config.uiMode=<mode>`).
#
# usage:
#   angular-ui-mode.sh resolve [--args "<command arguments>"] [--project <dir>] [--noninteractive]
#       stdout  MODE=<mode> + SOURCE=<flag|project|default-noninteractive>   exit 0
#               ACTION=ask (interactive session, nothing chosen yet)          exit 0
#       exit 2  invalid or contradictory --ui value (message lists the supported modes)
#       exit 3  --ui differs from the mode the existing project already uses (changing it is a migration)
#       Non-interactive when --noninteractive is passed or CI is set to a non-empty value other than 0/false.
#   angular-ui-mode.sh detect <dir>
#       stdout  ROOT= DECLARED= INSTALLED= MODE=  then one line per inconsistency
#       exit 0 consistent (or not an Angular workspace: MODE=none), 1 inconsistent, 2 usage
#   angular-ui-mode.sh check-file <file>
#       stdout  "<line>: [rule] message" per finding for the file's project mode
#       exit 0 clean or out of scope, 1 findings, 2 usage
#   angular-ui-mode.sh --selftest
set -uo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "angular-ui-mode: python3 not found" >&2
  exit 2
fi

UI_MODE_SELF="$0" PYTHONDONTWRITEBYTECODE=1 exec python3 -I - "$@" <<'PY'
import json, os, re, subprocess, sys, tempfile, shutil

MODES = ("daisyui", "spartan", "hybrid")
# "none" = the pre-existing opt-out: Angular without Tailwind or a UI library. Accepted as a flag, never offered in the question.
SELECTABLE = MODES + ("none",)
SUPPORTED = "Supported: --ui=daisyui (recommended default), --ui=spartan, --ui=hybrid (or --ui=none: no Tailwind, no UI library)"

# daisyUI 5 component class roots. Excluded on purpose because Tailwind or plain HTML use the same word:
# table, collapse, hidden, container, footer, hero, list, mask, stack, filter, link, label, status, diff.
DAISY_CLASSES = (
    "alert avatar badge breadcrumbs btn card carousel chat checkbox countdown divider dock drawer dropdown "
    "fab fieldset file-input indicator input join kbd loading menu modal navbar progress radial-progress "
    "radio range rating select skeleton stat stats steps swap tab tabs textarea timeline toast toggle "
    "tooltip validator"
).split()
# Hybrid ownership: Spartan owns these interactions, so the daisyUI versions must not appear.
HYBRID_SPARTAN_OWNED_DAISY = {"modal": "dialog", "dropdown": "dropdown menu / popover", "select": "select / combobox",
                              "tooltip": "tooltip"}
# Hybrid ownership: daisyUI owns these presentation components, so the helm versions must not appear.
# `alert-dialog` is a Spartan-owned overlay, not the daisyUI-owned `alert` (a bare \b would match `<hlm-alert-dialog`).
HYBRID_DAISY_OWNED_HELM = re.compile(
    r"<hlm-(?:card|badge|alert(?!-dialog)|spinner|skeleton|table)(?![\w-])"
    r"|<hlm-(?:card|alert(?!-dialog)|table)-[a-z]"
    r"|\bhlm(?:Card|Badge|Alert(?!Dialog)|Spinner|Skeleton|Table)[A-Za-z]*\b")
HELM_OR_BRAIN = re.compile(r"<(hlm|brn)-[a-z]|\b(hlm|brn)[A-Z][A-Za-z]*\b")
SPARTAN_IMPORT = re.compile(r"""from\s+['"]@spartan-ng/|import\s*\(\s*['"]@spartan-ng/|['"]@spartan-ng/brain/hlm-tailwind-preset\.css['"]""")
DAISY_PLUGIN = re.compile(r"""@plugin\s+['"]daisyui(/theme)?['"]""")
CLASS_ATTR = re.compile(r"""\bclass\s*=\s*(["'])(.*?)\1""", re.S)
DARK_CLASS_TOGGLE = re.compile(r"""classList\.(add|toggle|remove)\(\s*['"]dark['"]""")
OBSOLETE_CSS = [
    (re.compile(r"@tailwind\s+(base|components|utilities)\b"), "obsolete", "Tailwind 3 `@tailwind` directive: use `@import \"tailwindcss\";`"),
    (re.compile(r"""@import\s+['"]daisyui['"]"""), "obsolete", "daisyUI is a Tailwind 4 plugin: `@plugin \"daisyui\";`, never `@import \"daisyui\"`"),
    (re.compile(r"""@config\s+['"]"""), "obsolete", "JS config via `@config`: Tailwind 4 is CSS-first (`@theme`, `@plugin`)"),
]


def die(code, msg):
    print(msg, file=sys.stderr)
    sys.exit(code)


def find_root(start):
    d = os.path.abspath(start if os.path.isdir(start) else os.path.dirname(start))
    for _ in range(10):
        if os.path.isfile(os.path.join(d, "angular.json")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def global_css(root):
    """Text of the workspace's global stylesheets (angular.json build styles, else src/styles.css)."""
    paths = []
    ng = read_json(os.path.join(root, "angular.json")) or {}
    for proj in (ng.get("projects") or {}).values():
        styles = (((proj.get("architect") or {}).get("build") or {}).get("options") or {}).get("styles") or []
        for s in styles:
            p = s.get("input") if isinstance(s, dict) else s
            if isinstance(p, str) and p.endswith(".css"):
                paths.append(os.path.join(root, p))
    if not paths:
        paths = [os.path.join(root, "src", "styles.css")]
    text = ""
    for p in paths:
        try:
            with open(p, encoding="utf-8") as fh:
                text += fh.read() + "\n"
        except OSError:
            pass
    return text


def detect(root):
    pkg = read_json(os.path.join(root, "package.json")) or {}
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    declared = ((pkg.get("config") or {}).get("uiMode") or "")
    has_daisy = "daisyui" in deps
    has_spartan = "@spartan-ng/brain" in deps
    installed = "hybrid" if has_daisy and has_spartan else "daisyui" if has_daisy else "spartan" if has_spartan else "none"
    css = global_css(root)
    problems = []
    if declared and declared not in SELECTABLE:
        problems.append(f"config.uiMode '{declared}' is not a UI mode. {SUPPORTED}")
    if declared in SELECTABLE and declared != installed and (installed != "none" or declared == "none"):
        problems.append(f"config.uiMode is '{declared}' but the installed UI packages make it '{installed}': "
                        "remove the unselected library or change the mode deliberately (a migration)")
    if not declared and installed != "none":
        problems.append(f"no config.uiMode: run `npm pkg set config.uiMode={installed}` to record the mode")
    if has_daisy and not DAISY_PLUGIN.search(css):
        problems.append("daisyui is installed but the global stylesheet has no `@plugin \"daisyui\"`")
    if DAISY_PLUGIN.search(css) and not has_daisy:
        problems.append("`@plugin \"daisyui\"` in the global stylesheet but daisyui is not in package.json")
    if has_spartan and "hlm-tailwind-preset.css" not in css:
        problems.append("@spartan-ng/brain is installed but the global stylesheet does not import "
                        "`@spartan-ng/brain/hlm-tailwind-preset.css`")
    if has_spartan and not os.path.isfile(os.path.join(root, "components.json")):
        problems.append("@spartan-ng/brain is installed but components.json is missing (run `ng g @spartan-ng/cli:init`)")
    if os.path.isfile(os.path.join(root, "components.json")) and not has_spartan:
        problems.append("components.json exists but @spartan-ng/brain is not installed")
    mode = declared if declared in SELECTABLE else installed
    css_code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    if mode == "hybrid" and not re.search(r"@custom-variant\s+dark\s*\([^;]*data-theme", css_code):
        problems.append("hybrid: dark mode must follow daisyUI's data-theme; redeclare "
                        "`@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));` after the Spartan preset")
    # daisyUI 5 reads --border as the border WIDTH; a colour there (Spartan's meaning) removes every daisyUI border.
    if has_daisy and re.search(r"(?<![\w-])--border\s*:\s*[^;]*(?:color|oklch|oklab|rgb|hsl|#)", css_code):
        problems.append("`--border` is set to a colour: daisyUI 5 uses `--border` as the border width (inputs, buttons and "
                        "fieldsets lose their border). Map Spartan's border colour with `@theme inline { --color-border: ... }`")
    return {"root": root, "declared": declared or "none", "declared_raw": declared, "installed": installed, "mode": mode, "problems": problems}


def parse_ui_args(text):
    """Return the list of --ui values found in the command arguments (both --ui=x and --ui x)."""
    tokens = (text or "").split()
    values = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--ui="):
            values.append(t[5:])
        elif t == "--ui":
            values.append(tokens[i + 1] if i + 1 < len(tokens) and not tokens[i + 1].startswith("--") else "")
            i += 1
        i += 1
    return values


def cmd_resolve(argv):
    args_text, project, noninteractive = "", None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--args" and i + 1 < len(argv):
            args_text = argv[i + 1]; i += 2; continue
        if a == "--project" and i + 1 < len(argv):
            project = argv[i + 1]; i += 2; continue
        if a == "--noninteractive":
            noninteractive = True; i += 1; continue
        die(2, f"resolve: unknown argument '{a}'")
    if os.environ.get("CI", "").strip().lower() not in ("", "0", "false"):
        noninteractive = True
    values = [v.strip().lower() for v in parse_ui_args(args_text)]
    for v in values:
        if v not in SELECTABLE:
            die(2, f"Invalid UI mode '{v or '(empty)'}'. {SUPPORTED}")
    if len(set(values)) > 1:
        die(2, f"Conflicting --ui values: {', '.join(sorted(set(values)))}. Pass one. {SUPPORTED}")
    flag = values[0] if values else None
    root = find_root(project) if project and os.path.exists(project) else None
    if root:
        info = detect(root)
        existing = info["mode"]
        if existing in SELECTABLE and (existing != "none" or info["declared_raw"] == "none"):
            if flag and flag != existing:
                die(3, f"The project at {root} already uses UI mode '{existing}'; --ui={flag} would mix systems. "
                       "Keep the existing mode, or plan a migration (remove the old library, update config.uiMode).")
            print(f"MODE={existing}\nSOURCE=project")
            return 0
    if flag:
        print(f"MODE={flag}\nSOURCE=flag")
        return 0
    if noninteractive:
        print("MODE=daisyui\nSOURCE=default-noninteractive")
        return 0
    print("ACTION=ask")
    return 0


def cmd_detect(argv):
    if len(argv) != 1:
        die(2, "usage: angular-ui-mode.sh detect <dir>")
    root = find_root(argv[0])
    if not root:
        print("ROOT=none\nMODE=none")
        return 0
    info = detect(root)
    print(f"ROOT={root}\nDECLARED={info['declared']}\nINSTALLED={info['installed']}\nMODE={info['mode']}")
    for p in info["problems"]:
        print(f"PROBLEM: {p}")
    return 1 if info["problems"] else 0


def strip_comments(text, ext):
    """Blank out comments but keep line numbers."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    if ext == ".html":
        return re.sub(r"<!--.*?-->", blank, text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", blank, text, flags=re.S)
    if ext in (".ts", ".mts"):
        text = re.sub(r"(?m)^\s*//.*$", blank, text)
    return text


def classes_with_lines(text):
    for m in CLASS_ATTR.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        for cls in m.group(2).split():
            yield line, cls


def check_file(path):
    ext = os.path.splitext(path)[1]
    if ext not in (".ts", ".mts", ".html", ".css"):
        return []
    norm = path.replace(os.sep, "/")
    if any(p in norm for p in ("/node_modules/", "/dist/", "/.angular/")) or norm.endswith(".d.ts"):
        return []
    root = find_root(path)
    if not root or not os.path.isfile(path):
        return []
    info = detect(root)
    mode = info["mode"]
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
    except (OSError, UnicodeDecodeError):
        return []
    text = strip_comments(raw, ext)
    lines = text.split("\n")
    out = []

    def add(n, rule, msg):
        if "ui-mode-ok:" in raw.split("\n")[n - 1] or (n > 1 and "ui-mode-ok:" in raw.split("\n")[n - 2]):
            return
        out.append(f"{n}: [{rule}] {msg}")

    if ext == ".css":
        for n, line in enumerate(lines, 1):
            for rx, rule, msg in OBSOLETE_CSS:
                if rx.search(line):
                    add(n, rule, msg)
            if mode == "spartan" and DAISY_PLUGIN.search(line):
                add(n, "unselected-library", "daisyUI plugin in a Spartan-mode project (config.uiMode=spartan)")
            if mode == "daisyui" and "hlm-tailwind-preset.css" in line:
                add(n, "unselected-library", "Spartan preset in a daisyUI-mode project (config.uiMode=daisyui)")
        return out

    in_helm_lib = rel.startswith(("libs/ui/", "libs/helm/"))  # generated Spartan Helm code is Spartan by definition
    for n, line in enumerate(lines, 1):
        if mode == "daisyui":
            if SPARTAN_IMPORT.search(line) or HELM_OR_BRAIN.search(line):
                add(n, "unselected-library", "Spartan (helm/brain) in a daisyUI-mode project (config.uiMode=daisyui)")
        if mode == "hybrid" and not in_helm_lib:
            if HYBRID_DAISY_OWNED_HELM.search(line):
                add(n, "ownership", "hybrid: daisyUI owns cards, badges, alerts, loading and tables: use the daisyUI class, not the helm component")
            if DARK_CLASS_TOGGLE.search(line):
                add(n, "theme", "hybrid: dark mode is `data-theme` on <html> (one toggle for both libraries), not a `.dark` class")
    if mode in ("spartan", "hybrid") and not in_helm_lib:
        for n, cls in classes_with_lines(text):
            base = cls.split(":")[-1]
            if mode == "spartan" and base in DAISY_CLASSES:
                add(n, "unselected-library", f"daisyUI class `{cls}` in a Spartan-mode project (config.uiMode=spartan)")
            if mode == "hybrid" and base in HYBRID_SPARTAN_OWNED_DAISY:
                add(n, "ownership", f"hybrid: Spartan owns the {HYBRID_SPARTAN_OWNED_DAISY[base]}: replace daisyUI `{cls}` with the Spartan component")
    return sorted(set(out), key=lambda s: int(s.split(":")[0]))


def cmd_check_file(argv):
    if len(argv) != 1:
        die(2, "usage: angular-ui-mode.sh check-file <file>")
    findings = check_file(argv[0])
    for f in findings:
        print(f)
    return 1 if findings else 0


def selftest():
    fail = 0
    me = os.environ.get("UI_MODE_SELF") or ""
    tmp = tempfile.mkdtemp()

    def write(path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def project(name, mode, daisy, spartan, css):
        root = os.path.join(tmp, name)
        deps = {"@angular/core": "~22.3.0"}
        if daisy:
            deps["daisyui"] = "5.8.2"
        if spartan:
            deps["@spartan-ng/brain"] = "1.10.1"
            write(os.path.join(root, "components.json"), '{"componentsPath":"libs/ui"}')
        pkg = {"name": name, "dependencies": deps}
        if mode:
            pkg["config"] = {"uiMode": mode}
        write(os.path.join(root, "package.json"), json.dumps(pkg))
        write(os.path.join(root, "angular.json"), json.dumps({"projects": {name: {"architect": {"build": {"options": {"styles": ["src/styles.css"]}}}}}}))
        write(os.path.join(root, "src", "styles.css"), css)
        return root

    D_CSS = '@import "tailwindcss";\n@plugin "daisyui";\n'
    S_CSS = '@import "tailwindcss";\n@import "@spartan-ng/brain/hlm-tailwind-preset.css";\n'
    H_CSS = D_CSS + '@import "@spartan-ng/brain/hlm-tailwind-preset.css";\n@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));\n'
    d = project("d", "daisyui", True, False, D_CSS)
    s = project("s", "spartan", False, True, S_CSS)
    h = project("h", "hybrid", True, True, H_CSS)
    bad = project("bad", "daisyui", True, True, H_CSS)          # declared daisyui, both installed
    und = project("und", None, True, False, D_CSS)               # no config.uiMode
    nn = project("nn", "none", False, False, "")
    nnbad = project("nnbad", "none", True, False, D_CSS)
    fresh = project("fresh", None, False, False, "")
    hdark = project("hdark", "hybrid", True, True, D_CSS + '@import "@spartan-ng/brain/hlm-tailwind-preset.css";\n@custom-variant dark (&:is(.dark *));\n')
    hnovar = project("hnovar", "hybrid", True, True, D_CSS + '@import "@spartan-ng/brain/hlm-tailwind-preset.css";\n/* data-theme */\n')
    hborder = project("hborder", "hybrid", True, True, H_CSS + ':root { --border: var(--color-base-300); }\n/* --border: oklch(1 0 0) in a comment */\n')
    hwidth = project("hwidth", "hybrid", True, True, H_CSS + ':root { --color-border: var(--color-base-300); }\n[data-theme] { --border: 1px; }\n')

    def run(args, env_ci=None):
        env = dict(os.environ)
        env.pop("CI", None)
        if env_ci is not None:
            env["CI"] = env_ci
        p = subprocess.run(["bash", me] + args, capture_output=True, text=True, env=env)
        return p.returncode, p.stdout + p.stderr

    def expect(label, args, code, needle, env_ci=None, absent=None):
        nonlocal fail
        rc, out = run(args, env_ci)
        ok = rc == code and needle in out and (absent is None or absent not in out)
        print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (exit {rc}, got: {out.strip()[:200]})"))
        if not ok:
            fail = 1

    rc = subprocess.run(["bash", "-n", me]).returncode
    print(f"  {'ok  ' if rc == 0 else 'FAIL'} control 0: parses (bash -n)")
    fail |= rc != 0
    # resolve: the six selection behaviours
    expect("resolve: no mode, interactive -> ask", ["resolve", "--args", "my-app"], 0, "ACTION=ask")
    expect("resolve: --ui=spartan -> no question", ["resolve", "--args", "my-app --ui=spartan"], 0, "MODE=spartan\nSOURCE=flag", absent="ACTION=ask")
    expect("resolve: --ui hybrid (space form)", ["resolve", "--args", "--ui hybrid my-app"], 0, "MODE=hybrid")
    expect("resolve: --ui=DaisyUI normalised", ["resolve", "--args", "--ui=DaisyUI"], 0, "MODE=daisyui")
    expect("resolve: noninteractive flag -> daisyui", ["resolve", "--args", "my-app", "--noninteractive"], 0, "MODE=daisyui\nSOURCE=default-noninteractive")
    expect("resolve: CI=true -> daisyui", ["resolve", "--args", "my-app"], 0, "SOURCE=default-noninteractive", env_ci="true")
    expect("resolve: CI=false stays interactive", ["resolve", "--args", "my-app"], 0, "ACTION=ask", env_ci="false")
    expect("resolve: noninteractive keeps an explicit flag", ["resolve", "--args", "--ui=spartan", "--noninteractive"], 0, "MODE=spartan\nSOURCE=flag")
    expect("resolve: invalid mode -> exit 2 + choices", ["resolve", "--args", "--ui=bootstrap"], 2, "Supported: --ui=daisyui")
    expect("resolve: empty --ui= -> exit 2", ["resolve", "--args", "--ui="], 2, "Invalid UI mode '(empty)'")
    expect("resolve: two different --ui -> exit 2", ["resolve", "--args", "--ui=spartan --ui=hybrid"], 2, "Conflicting --ui values")
    expect("resolve: existing project preserved", ["resolve", "--args", "", "--project", os.path.join(s, "src")], 0, "MODE=spartan\nSOURCE=project")
    expect("resolve: existing project wins over noninteractive default", ["resolve", "--project", h, "--noninteractive"], 0, "MODE=hybrid\nSOURCE=project")
    expect("resolve: flag contradicting existing project -> exit 3", ["resolve", "--args", "--ui=daisyui", "--project", s], 3, "already uses UI mode 'spartan'")
    expect("resolve: same flag as existing project -> ok", ["resolve", "--args", "--ui=spartan", "--project", s], 0, "SOURCE=project")
    expect("resolve: undeclared project infers from packages", ["resolve", "--project", und], 0, "MODE=daisyui\nSOURCE=project")
    expect("resolve: --ui=none (legacy opt-out) accepted", ["resolve", "--args", "--ui=none"], 0, "MODE=none\nSOURCE=flag")
    expect("resolve: project declared none is preserved", ["resolve", "--project", nn], 0, "MODE=none\nSOURCE=project")
    expect("resolve: fresh workspace (no mode, no packages) -> ask", ["resolve", "--project", fresh], 0, "ACTION=ask")
    expect("detect: declared none but daisyui installed -> exit 1", ["detect", nnbad], 1, "config.uiMode is 'none'")
    expect("resolve: missing project dir -> falls through to ask", ["resolve", "--project", os.path.join(tmp, "nope")], 0, "ACTION=ask")
    # detect
    expect("detect: consistent daisyui", ["detect", d], 0, "MODE=daisyui")
    expect("detect: consistent hybrid", ["detect", h], 0, "MODE=hybrid")
    expect("detect: declared daisyui but spartan installed -> exit 1", ["detect", bad], 1, "installed UI packages make it 'hybrid'")
    expect("detect: undeclared -> exit 1, says how to record", ["detect", und], 1, "npm pkg set config.uiMode=daisyui")
    expect("detect: hybrid with .dark custom-variant -> exit 1", ["detect", hdark], 1, "dark mode must follow daisyUI's data-theme")
    expect("detect: hybrid with the preset only (no data-theme variant) -> exit 1", ["detect", hnovar], 1, "dark mode must follow daisyUI's data-theme")
    expect("detect: hybrid --border set to a colour -> exit 1", ["detect", hborder], 1, "`--border` is set to a colour")
    expect("detect: --border as a width and --color-border mapping are fine", ["detect", hwidth], 0, "MODE=hybrid", absent="--border")
    expect("detect: not an Angular workspace", ["detect", tmp], 0, "MODE=none")
    # check-file
    write(os.path.join(d, "src/app/x.ts"), "import { HlmButtonImports } from '@spartan-ng/helm/button';\n")
    write(os.path.join(d, "src/app/ok.html"), '<button class="btn btn-primary">Save</button>\n<!-- <hlm-dialog> in a comment -->\n')
    write(os.path.join(s, "src/app/y.html"), '<div class="card md:btn">x</div>\n<button hlmBtn>Ok</button>\n<table class="table">t</table>\n')
    write(os.path.join(s, "libs/ui/button/src/lib/hlm-button.ts"), "const c = 'btn';\n")
    write(os.path.join(h, "src/app/z.html"), '<dialog class="modal">x</dialog>\n<hlm-card>x</hlm-card>\n<button class="btn" hlmDialogTrigger>Open</button>\n<div class="dropdown"></div> <!-- ui-mode-ok: legacy -->\n<p>spacer: a marker also exempts the next line</p>\n<hlm-alert-dialog><hlm-alert-dialog-content>x</hlm-alert-dialog-content></hlm-alert-dialog>\n<button hlmAlertDialogTrigger class="btn">Del</button>\n<h4 hlmAlertTitle>t</h4>\n<hlm-card-header>h</hlm-card-header>\n')
    write(os.path.join(h, "src/app/t.ts"), "document.documentElement.classList.add('dark');\n")
    write(os.path.join(s, "src/styles.extra.css"), '@tailwind base;\n@plugin "daisyui";\n')
    expect("check: Spartan import in daisyui project", ["check-file", os.path.join(d, "src/app/x.ts")], 1, "[unselected-library] Spartan")
    expect("check: daisyui clean + comment ignored", ["check-file", os.path.join(d, "src/app/ok.html")], 0, "")
    expect("check: daisy class in spartan project (variant prefix too)", ["check-file", os.path.join(s, "src/app/y.html")], 1, "daisyUI class `md:btn`")
    expect("check: Tailwind `table` utility is not daisyUI", ["check-file", os.path.join(s, "src/app/y.html")], 1, "1: [unselected-library] daisyUI class `card`", absent="`table`")
    expect("check: generated helm lib is exempt", ["check-file", os.path.join(s, "libs/ui/button/src/lib/hlm-button.ts")], 0, "")
    expect("check: hybrid daisy modal -> ownership", ["check-file", os.path.join(h, "src/app/z.html")], 1, "1: [ownership] hybrid: Spartan owns the dialog")
    expect("check: hybrid helm card -> ownership", ["check-file", os.path.join(h, "src/app/z.html")], 1, "2: [ownership] hybrid: daisyUI owns cards")
    expect("check: hybrid btn on Spartan trigger allowed, ui-mode-ok exempts", ["check-file", os.path.join(h, "src/app/z.html")], 1, "", absent="3:")
    expect("check: ui-mode-ok marker exempts its line", ["check-file", os.path.join(h, "src/app/z.html")], 1, "", absent="4:")
    expect("check: hybrid alert-dialog is Spartan-owned, not the daisyUI alert", ["check-file", os.path.join(h, "src/app/z.html")], 1, "", absent="6:")
    expect("check: hybrid alert-dialog trigger attribute allowed", ["check-file", os.path.join(h, "src/app/z.html")], 1, "", absent="7:")
    expect("check: hybrid helm alert parts -> ownership", ["check-file", os.path.join(h, "src/app/z.html")], 1, "8: [ownership]")
    expect("check: hybrid helm card part element -> ownership", ["check-file", os.path.join(h, "src/app/z.html")], 1, "9: [ownership]")
    expect("check: hybrid .dark class toggle", ["check-file", os.path.join(h, "src/app/t.ts")], 1, "[theme] hybrid")
    expect("check: obsolete @tailwind + daisy plugin in spartan css", ["check-file", os.path.join(s, "src/styles.extra.css")], 1, "1: [obsolete]")
    expect("check: daisy plugin flagged in spartan css", ["check-file", os.path.join(s, "src/styles.extra.css")], 1, "2: [unselected-library] daisyUI plugin")
    expect("check: file outside any Angular workspace", ["check-file", os.path.join(tmp, "loose.ts")], 0, "")
    expect("usage error -> exit 2", ["nonsense"], 2, "usage")
    shutil.rmtree(tmp, ignore_errors=True)
    print("selftest PASS" if not fail else "selftest FAIL")
    return 1 if fail else 0


def main():
    argv = sys.argv[1:]
    if not argv:
        die(2, "usage: angular-ui-mode.sh resolve|detect|check-file|--selftest ...")
    cmd, rest = argv[0], argv[1:]
    if cmd == "--selftest":
        return selftest()
    if cmd == "resolve":
        return cmd_resolve(rest)
    if cmd == "detect":
        return cmd_detect(rest)
    if cmd == "check-file":
        return cmd_check_file(rest)
    die(2, "usage: angular-ui-mode.sh resolve|detect|check-file|--selftest ...")


sys.exit(main())
PY
