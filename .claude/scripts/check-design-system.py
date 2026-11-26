#!/usr/bin/env python3
"""Design-system gate for Flutter, Angular and React projects (one detector, three callers).

Callers: /lint-design-system (local), /verify (UI stacks), CI. Write-time advisories are the hookify
rules in .claude/hookify.design-*.local.md; this script is the blocking check.

Checks (rule IDs in the output; the canonical rules live in
.claude/skills/design-system/reference/token-governance.md and atomic-decision-tree.md):
  DS-COLOR          raw colour literal or framework named palette outside token-definition files
  DS-SHAPE          literal corner radius in Dart (BorderRadius.circular(12))
  DS-SPACING        literal spacing value (Dart EdgeInsets/SizedBox numbers, Tailwind p-[13px], CSS 12px)
  DS-TYPE           literal font size or family outside the theme
  DS-INLINE-STYLE   style="...", [style.x]= or [ngStyle] in an Angular template
  DS-DAISYUI4       daisyUI 4 class names (emit no CSS in daisyUI 5)
  DS-SPACING-SHADOW --spacing-xs..2xl tokens in CSS (they shadow max-w-* in Tailwind 4)
  DS-TIER           shared-library component without a line-1 `// Tier: Atom|Molecule|Organism`
  DS-PRESENTATIONAL shared-library component that reaches state, data access or feature code
  DS-ICON-ISOLATION icon package imported outside the icon wrapper / shared UI library
  DS-ICON-FAMILY    more than one icon family in one app
  DS-ANIM           Lottie/Rive runtime imported outside a shared animation wrapper
  DS-ANIM-DECISION  Lottie/Rive listed as a dependency but DESIGN.md Motion does not name that engine
  DS-REFRESH        RefreshIndicator / pull-to-refresh used without a `refresh-strategy:` record
  DS-AUTHORITY      Dart colour literals defined in more than one token root (workspace-wide)
  DS-REDUCED-MOTION daisyUI loading-* indicator in an app whose global stylesheet lacks the reduced-motion override
  DS-SCALE          more than one scale class for the same token family (spacing, radius, motion)
  DS-MUTED-TEXT     text-base-content/10..50 (warning: below the contrast floor on text)

Scope: UI source of each app root (nearest pubspec.yaml or package.json with Angular/React), minus
token-definition files, CSS custom-property definition lines, generated files, tests and CLI-owned UI-kit
folders (src/components/ui, libs/ui, helm). Escape hatch: `ignore-design: <reason of 12+ chars>` on the
hit line or the line directly above; a shorter or missing reason does not exempt.

Every run first proves each detector on planted fixtures (positive and negative controls); a detector
that stops matching exits 2 before any project file is judged.

Usage: check-design-system.py [--root DIR] [--files F ...] [--require-design-md] [--selftest]
Exit: 0 no errors (warnings may print), 1 errors found, 2 detector broken or bad usage.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {
    "node_modules", ".git", ".dart_tool", "build", "dist", ".angular", "coverage", ".next", "out",
    ".worktrees", "worktrees", ".claude", ".idea", ".vscode", "Pods", ".gradle", "playwright-report",
    "test-results",
}
DESIGN_MD_CANDIDATES = ("DESIGN.md", "docs/DESIGN.md", "design/DESIGN.md")
TIERS = ("Atom", "Molecule", "Organism")
TIER_LINE = re.compile(r"^// Tier: (?:Atom|Molecule|Organism)[ \t]*$")
REASON = re.compile(r"ignore-design:\s*(\S.{11,})")  # 12+ characters of reason
COMMENT_LINE = re.compile(r"^\s*(?://|/\*|\*|<!--|#)")
CSS_CUSTOM_PROP_DECL = re.compile(r"--[\w-]+\s*:[^;}]*")
# The app's global stylesheet owns the theme variables; a component or feature stylesheet that re-declares them with
# literal values is a parallel token authority and is scanned like any other line.
GLOBAL_STYLESHEET = re.compile(r"^src/(styles|index|globals?|app)\.s?css$")

# Paths
UI_KIT = re.compile(r"(^|/)(src/components/ui|libs/ui|[^/]*helm|[^/]*brain)/")
TEST_OR_GEN = re.compile(
    r"(_test\.dart|\.g\.dart|\.freezed\.dart|\.gr\.dart|\.mocks\.dart|\.d\.ts|\.(spec|test|stories)\.[jt]sx?)$"
    r"|(^|/)(test|tests|__tests__|e2e|integration_test|test_driver|testing)/"
)
DART_TOKEN_DIR = re.compile(r"^(?!(.*/)?features/)(.*/)?(tokens|theme|themes|typography|foundations)/")  # never feature-local
DART_TOKEN_FILE = re.compile(
    r"^(?!(.*/)?features/)(.*/)?(app_(colors?|color_scheme|theme\w*|spacing|radius|radii|motion|typography|text_styles?|text_theme"
    r"|elevation|shadows?|icons|tokens|sizes|breakpoints)|\w+_tokens|\w+_theme(_extension)?)\.dart$"
)
WEB_TOKEN_FILE = re.compile(r"(^|/)((tokens?|theme)[^/]*\.s?css|(tokens|theme|themes)/[^/]+\.s?css)$")
# Governed shared libraries (tier + presentational rules); path is relative to the scan root.
DART_LIB = re.compile(
    r"(^|/)(packages/(shared_ui|ui|[a-z0-9_]+_ui)/lib/.+/[^/]+\.dart|lib/design_system/components/.+\.dart)$"
)
DART_LIB_EXCLUDE = re.compile(
    r"(^|/)(tokens|theme|themes|typography|foundations|utils|extensions|l10n|generated)/|(^|/)index\.dart$"
    r"|/(?P<dir>[^/]+)/(?P=dir)\.dart$"  # barrel named after its folder (components/components.dart)
)
NG_LIB = re.compile(r"(^|/)src/app/(.*/)?shared/components/.+\.ts$")
NG_LIB_EXCLUDE = re.compile(r"(^|/)index\.ts$|\.(model|models|types|tokens|constants|util|utils)\.ts$")
RX_LIB = re.compile(r"(^|/)src/shared/ui/.+\.tsx$")
RX_LIB_EXCLUDE = re.compile(r"(^|/)index\.tsx$|(^|/)[^/]*(provider|context)[^/]*\.tsx$")
WRAPPER_NAME = re.compile(r"(^|/)([^/]*[_.-])?(icons?|Icons?)([_.-][^/]*)?\.[a-z]+$")  # whole word: not lexicon_screen

# Detectors: (rule, severity, stacks, regex). Stacks: d=dart, w=web markup/style/script.
NAMED_PALETTE = (
    r"slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet"
    r"|purple|fuchsia|pink|rose"
)
LINE_RULES: list[tuple[str, str, str, re.Pattern[str], str]] = [
    ("DS-COLOR", "error", "d", re.compile(
        r"Color\(\s*0x[0-9A-Fa-f]+\s*\)|Color\.from(ARGB|RGBO)?\(|(?<![\w.])(Cupertino)?Colors\.(?!transparent\b)[a-z]\w*"),
     "raw colour: use a ColorScheme role or a ThemeExtension token"),
    ("DS-SPACING", "error", "d", re.compile(
        r"EdgeInsets(Directional)?\.(all|symmetric|only|fromLTRB|fromSTEB)\([^)]*?(?<![\w.])(?!0(\.0)?\b)\d+(\.\d+)?\b"
        r"|SizedBox(\.square)?\(\s*(width|height|dimension)\s*:\s*(?!0(\.0)?\b)\d|\bGap\(\s*(?!0\b)\d"),
     "literal spacing: use the project spacing scale (for example AppSpacing.md)"),
    ("DS-SHAPE", "error", "d", re.compile(r"\b(BorderRadius|Radius)\.circular\(\s*(?!0(\.0)?\b)\d"),
     "literal radius: use the project radius scale (for example AppRadius.md)"),
    ("DS-TYPE", "error", "d", re.compile(r"\bfontSize\s*:\s*\d|\bfontFamily\s*:\s*['\"]"),
     "literal font size/family: use a TextTheme role"),
    ("DS-COLOR", "error", "w", re.compile(
        r"\b(bg|text|border|ring|fill|stroke|from|via|to|outline|decoration|accent|caret|shadow|divide)-\[(#|(rgba?|hsla?|oklch|oklab|hwb|lab|lch)\()"
        r"|(background(-color)?|backgroundColor|(?<![\w-])color|border(-[a-z]+)?-color|border[A-Z][a-z]*Color|outline(-color)?|(?<![\w-])fill|(?<![\w-])stroke|box-shadow|boxShadow)"
        r"\s*:\s*['\"]?[^;'\"}\n]*?(#[0-9a-fA-F]{3,8}\b|\b(rgba?|hsla?|oklch|oklab|hwb|lab|lch)\()"
        rf"|\b(bg|text|border|ring|fill|stroke|from|via|to|outline|decoration|accent|caret|divide|placeholder)-({NAMED_PALETTE})-(50|[1-9]00|950)\b"
        # a theme variable re-declared with a literal outside the global stylesheet (stripped there)
        r"|(?<![\w-])--[\w-]+\s*:\s*[^;}\n]*?(#[0-9a-fA-F]{3,8}\b|\b(rgba?|hsla?|oklch|oklab|hwb|lab|lch)\()"
        # a literal passed to a colour-named input/prop: color="#E53935", [color]="'#…'", color={"#…"}
        r"""|\[?\b(colou?r|tone|tint|bg|background|fill|stroke|accent)\w*\]?\s*=\s*[\"'{]\s*[\"'`]?\s*#[0-9a-fA-F]{3,8}\b"""),
     "raw colour or named palette: use a semantic token (bg-primary, text-base-content, var(--color-...))"),
    # Any quoted string that is exactly a hex colour (status maps, constants, ternaries, camelCase props).
    # Anchor attribute values (href="#add") are filtered in scan_file; a neighbouring `id` key is not a skip.
    ("DS-COLOR", "error", "w", re.compile(
        r"""(?<![\w#])[\"'`]#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})[\"'`]"""),
     "raw hex colour literal: pass a semantic tone/variant and map it to a token in the shared component"),
    ("DS-SPACING", "error", "w", re.compile(
        r"(^|[\s\"'`:])-?([mp][xytrblse]?|gap(-[xy])?|space-[xy]|inset(-[xy])?)-\[[^\]v][^\]]*\]"
        r"|(?<![\w-])(margin|padding|gap)(-[a-z]+)?\s*:\s*-?([1-9][0-9.]*|0?\.[0-9]+)(px|rem|em)\b"
        r"|\b(margin|padding|gap)[A-Z]?[a-z]*\s*:\s*['\"]?-?[1-9]"),
     "literal spacing: use the numeric Tailwind scale (p-4, gap-2) or a spacing token"),
    ("DS-TYPE", "error", "w", re.compile(
        r"\btext-\[[0-9.]+(px|rem|em)\]|\bfont-\[[^\]v][^\]]*\]|(?<![\w-])font-size\s*:\s*[0-9]|\bfontSize\s*:\s*['\"]?[0-9]"
        r"|(?<![\w-])font-family\s*:(?!\s*var\()"),
     "literal type value: use the type scale (text-sm, text-lg) or the theme font"),
    ("DS-INLINE-STYLE", "error", "h", re.compile(r"\sstyle=\"|\[style(\.[\w-]+)*\]=|\[ngStyle\]="),
     "inline style in a template: use utilities or component styles with tokens"),
    ("DS-SHAPE", "error", "w", re.compile(
        r"(?<![\w-])border(-[a-z]+)*-radius\s*:\s*[^;}\n]*?(?<![\w.(-])[1-9][0-9.]*(px|rem|em)\b|\brounded(-[a-z]+)?-\[[^\]v][^\]]*\]"
        r"|(?<![\w-])--(radius|rounded)[\w-]*\s*:\s*[0-9.]+(px|rem|em)\b|\bborderRadius\s*:\s*['\"]?[1-9]"),
     "literal radius: use the radius tokens (rounded-box, rounded-field, rounded-md, var(--radius-…))"),
    ("DS-DAISYUI4", "error", "w", re.compile(
        r"\b(input|select|textarea|file-input)-bordered\b|\bform-control\b|\blabel-text(-alt)?\b|\bcard-bordered\b|\bbtn-group\b"),
     "daisyUI 4 class (no CSS in daisyUI 5): input, fieldset/fieldset-legend, label, card-border, join"),
    ("DS-SPACING-SHADOW", "error", "c", re.compile(r"--spacing-(xs|sm|md|lg|xl|2xl)\s*:"),
     "--spacing-<size> shadows max-w-<size> in Tailwind 4: keep the default --spacing multiplier"),
    ("DS-MUTED-TEXT", "warning", "w", re.compile(r"\btext-base-content/(10|20|30|40|50)\b"),
     "muted text below the contrast floor: /60 minimum on base-100, /70 on base-200/300"),
]

# Injectables a presentational Angular component may use: DOM, rendering, forms (CVA), CDK a11y/overlay plumbing.
UI_INJECTABLES = (
    "ElementRef", "DestroyRef", "Renderer2", "ChangeDetectorRef", "Injector", "NgZone", "ViewContainerRef",
    "TemplateRef", "DOCUMENT", "PLATFORM_ID", "LOCALE_ID", "DomSanitizer", "NgControl", "ControlContainer",
    "FocusMonitor", "LiveAnnouncer", "Directionality", "Overlay", "DialogRef", "BrnDialogRef",
)

PRESENTATIONAL = {
    "dart": re.compile(
        r"^\s*import\s+['\"]package:(flutter_riverpod|hooks_riverpod|riverpod|riverpod_annotation|dio|http|cloud_firestore"
        r"|firebase_[a-z_]+|go_router|drift|shared_preferences|flutter_secure_storage|flutter_bloc|bloc|provider|get_it)/"
        r"|^\s*import\s+['\"][^'\"]*/(features|data|repositories|providers|services)/"
        r"|extends\s+(Hook)?Consumer(Stateful)?Widget\b|\bConsumerState<|\bref\.(watch|read|listen)\("),
    "angular": re.compile(
        r"from\s+['\"]@angular/common/http['\"]|\bhttpResource\b|from\s+['\"]@ngrx/|from\s+['\"][^'\"]*/(features|data-access)/"
        r"|from\s+['\"][^'\"]*\.(service|store|facade|repository)['\"]"
        # any inject() that is not a DOM/UI-level token: Angular 22 services carry no suffix (AuthSession, DashboardApi)
        r"|\binject(<[^>]*>)?\(\s*(?!(" + "|".join(UI_INJECTABLES) + r")\b)[A-Za-z_]"
        # constructor injection: a parameter property typed with anything but a DOM/UI token
        r"|(constructor\s*\(|^\s*|,\s*)(@\w+\([^)]*\)\s*)*(private|public|protected)\s+(readonly\s+)?\w+\s*:\s*(?!("
        + "|".join(UI_INJECTABLES) + r")\b)[A-Z]\w*\s*[,)]"),
    "react": re.compile(
        r"from\s+['\"](@tanstack/react-query|zustand|@reduxjs/toolkit|react-redux|jotai|swr|axios)['\"/]"
        r"|from\s+['\"][^'\"]*/(features|store|stores|api)(/|['\"])|\bfetch\("
        r"|\buse(Query|Mutation|SuspenseQuery|InfiniteQuery|Store|Selector|Dispatch|Navigate|Params)\("
        r"|useContext\(\s*\w*(Store|Auth|Session|Cart|User)Context"),
}

ICON_PKG = {
    "dart": re.compile(
        r"^\s*import\s+['\"]package:(phosphor_flutter|lucide_icons(_flutter)?|font_awesome_flutter|material_symbols_icons"
        r"|hugeicons|iconsax[a-z_]*|remixicon[a-z_]*|heroicons[a-z_]*|fluentui_system_icons)/"),
    "web": re.compile(
        r"from\s+['\"](lucide-react|lucide-angular|@lucide/angular|@ng-icons/(?!core)[a-z-]+|@heroicons/[a-z-]+|react-icons"
        r"|@fortawesome/[a-z-]+|@phosphor-icons/[a-z-]+|@tabler/icons[a-z-]*|@mui/icons-material|@radix-ui/react-icons"
        r"|@iconify/[a-z-]+)"),
}
ANIM_PKG = {
    "dart": re.compile(r"^\s*import\s+['\"]package:(lottie|rive)/"),
    "web": re.compile(r"from\s+['\"](lottie-web|lottie-react|@lottiefiles/[a-z-]+|ngx-lottie|@rive-app/[a-z-]+|rive-react)"),
}
DART_COLOR_LITERAL = re.compile(r"Color\(\s*0x[0-9A-Fa-f]+\s*\)|Color\.from(ARGB|RGBO)?\(")
DART_AUTHORITY_DIR = re.compile(r"^(?P<root>.*?)/?(tokens|theme|themes|typography|foundations)/")
LOADING_INDICATOR = re.compile(r"\bloading-(spinner|dots|ring|ball|bars|infinity)\b")
RM_LOADING_OVERRIDE = re.compile(r"prefers-reduced-motion\s*:\s*reduce[^{]*\{[^@]*?\.loading\b[^{]*\{[^}]*mask-image\s*:\s*none")
SCALE_CLASS = re.compile(
    r"^\s*(?:abstract\s+|final\s+|sealed\s+|base\s+)*class\s+(\w*(Spacing|Spacings|Gaps?|Radius|Radii|Motion|Durations)(Tokens)?)\b"
    r"(?!\s+extends\s+ThemeExtension)")
DART_ICON_LITERAL = re.compile(r"(?<![\w.])(?:Cupertino)?Icons\.\w")
PTR_USAGE = re.compile(
    r"\bRefreshIndicator\b|\bCupertinoSliverRefreshControl\b"
    r"|package:(pull_to_refresh|liquid_pull_to_refresh)/"
    r"|from\s+['\"](?:react-simple-pull-to-refresh|ngx-pull-to-refresh)['\"]"
)
REFRESH_RECORD = re.compile(
    r"refresh-strategy:\s*(background|automatic|realtime|pull-to-refresh|explicit|none)\b", re.I)
QUOTED_HEX = re.compile(
    r"""(?<![\w#])[\"'`]#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})[\"'`]""")
ANCHOR_ATTR_HEX = re.compile(
    r"""\b(?:href|fragment|routerLink|xlink:href|id|anchor)\s*=\s*[\"'`]#[0-9a-fA-F]{3,8}[\"'`]""")
PUBSPEC_ANIM_DEP = re.compile(r"^\s+(lottie|rive)\s*:", re.M)
NPM_LOTTIE = re.compile(r"^(lottie-web|lottie-react|ngx-lottie|@lottiefiles/.+)$")
NPM_RIVE = re.compile(r"^(rive-react|@rive-app/.+)$")


def quoted_hex_is_only_anchor(line: str) -> bool:
    """True when every quoted hex on the line is an href/fragment/id/anchor attribute value."""
    if not QUOTED_HEX.search(line):
        return False
    return not QUOTED_HEX.search(ANCHOR_ATTR_HEX.sub("", line))


def anim_deps_from_pubspec(text: str) -> set[str]:
    return {m.group(1).lower() for m in PUBSPEC_ANIM_DEP.finditer(text)}


def anim_deps_from_package_json(text: str) -> set[str]:
    try:
        pkg = json.loads(text)
    except ValueError:
        return set()
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    found: set[str] = set()
    for name in deps:
        if NPM_LOTTIE.match(name):
            found.add("lottie")
        if NPM_RIVE.match(name):
            found.add("rive")
    return found


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    severity: str
    message: str
    snippet: str = ""

    def render(self) -> str:
        loc = f"{self.path}:{self.line}" if self.line else self.path
        tail = f" :: {self.snippet.strip()[:120]}" if self.snippet else ""
        return f"{loc}: {self.severity.upper()} {self.rule} {self.message}{tail}"


def icon_family(spec: str) -> str:
    spec = spec.lower()
    if "lucide" in spec:
        return "lucide"
    for name in ("heroicons", "phosphor", "tabler", "fontawesome", "font_awesome", "material_symbols", "hugeicons",
                 "iconsax", "remixicon", "fluentui", "radix", "iconify", "react-icons", "mui"):
        if name.replace("_", "") in spec.replace("_", "").replace("-", ""):
            return name
    return spec


def find_app_roots(root: Path) -> dict[Path, str]:
    """Nearest pubspec.yaml (flutter) or package.json with @angular/core or react (angular/react)."""
    roots: dict[Path, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        here = Path(dirpath)
        if "pubspec.yaml" in filenames:
            roots[here] = "flutter"
        elif "package.json" in filenames:
            try:
                pkg = json.loads((here / "package.json").read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                print(f"check-design-system: cannot parse {here / 'package.json'}: {exc}", file=sys.stderr)
                continue
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "@angular/core" in deps:
                roots[here] = "angular"
            elif "react" in deps:
                roots[here] = "react"
    return roots


def owning_root(path: Path, roots: dict[Path, str]) -> tuple[Path, str] | None:
    for parent in [path.parent, *path.parents]:
        if parent in roots:
            return parent, roots[parent]
    return None


def in_scope(rel_in_app: str, kind: str) -> bool:
    if TEST_OR_GEN.search(rel_in_app) or UI_KIT.search(rel_in_app):
        return False
    if kind == "flutter":
        return rel_in_app.startswith("lib/") and rel_in_app.endswith(".dart")
    if not rel_in_app.startswith("src/"):
        return False
    exts = (".html", ".ts", ".css", ".scss") if kind == "angular" else (".tsx", ".jsx", ".ts", ".css")
    return rel_in_app.endswith(exts)


def exempt(lines: list[str], idx: int) -> bool:
    if REASON.search(lines[idx]):
        return True
    return idx > 0 and bool(REASON.search(lines[idx - 1])) and COMMENT_LINE.match(lines[idx - 1]) is not None


def governed_kind(rel: str, kind: str) -> bool:
    if kind == "flutter":
        return bool(DART_LIB.search(rel)) and not DART_LIB_EXCLUDE.search(rel)
    if kind == "angular":
        return bool(NG_LIB.search(rel)) and not NG_LIB_EXCLUDE.search(rel) and not TEST_OR_GEN.search(rel)
    return bool(RX_LIB.search(rel)) and not RX_LIB_EXCLUDE.search(rel) and not TEST_OR_GEN.search(rel)


def scan_file(path: Path, rel: str, rel_in_app: str, kind: str) -> tuple[list[Finding], set[str], set[str]]:
    """Return (findings, icon families used, scale classes defined, signals for project-level checks)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [Finding(rel, 0, "DS-READ", "error", f"cannot read file: {exc}")], set(), set()
    lines = text.splitlines() or [""]
    findings: list[Finding] = []
    families: set[str] = set()
    scales: set[str] = set()
    signals: dict[str, bool] = {}
    is_dart = kind == "flutter"
    stack = "dart" if is_dart else "web"
    token_file = bool(DART_TOKEN_DIR.search(rel_in_app) or DART_TOKEN_FILE.search(rel_in_app)) if is_dart \
        else bool(WEB_TOKEN_FILE.search(rel_in_app))
    is_css = rel.endswith((".css", ".scss"))
    is_html = rel.endswith(".html")
    governed = governed_kind(rel, kind)
    lib_or_wrapper = governed or bool(DART_LIB.search(rel) or NG_LIB.search(rel) or RX_LIB.search(rel))

    # Tier marker (shared-library components only; not exemptable).
    if governed and not TIER_LINE.match(lines[0]):
        findings.append(Finding(rel, 1, "DS-TIER", "error",
                                "line 1 must be `// Tier: Atom|Molecule|Organism` (templates/pages belong in features)",
                                lines[0]))

    for idx, line in enumerate(lines):
        if is_dart and token_file and DART_COLOR_LITERAL.search(line):
            signals["colour_authority"] = True
        if not is_dart and LOADING_INDICATOR.search(line) and "motion-reduce:hidden" not in line \
                and not exempt(lines, idx):
            signals.setdefault("loading_line", f"{rel}:{idx + 1}")
        if not is_dart and is_css and GLOBAL_STYLESHEET.search(rel_in_app) and RM_LOADING_OVERRIDE.search(text):
            signals["rm_override"] = True
        if is_dart and SCALE_CLASS.search(line):
            scales.add(SCALE_CLASS.search(line).group(1))
        if COMMENT_LINE.match(line) and not is_css:
            continue
        lineno = idx + 1
        for rule, severity, stacks, rx, message in LINE_RULES:
            applies = ("d" in stacks and is_dart) or ("w" in stacks and not is_dart) or ("h" in stacks and is_html) \
                or ("c" in stacks and is_css)
            if not applies:
                continue
            subject = line
            if rule in ("DS-COLOR", "DS-SPACING", "DS-TYPE", "DS-SHAPE"):
                if token_file:
                    continue
                if is_css and GLOBAL_STYLESHEET.search(rel_in_app):  # theme variables are token definitions
                    subject = CSS_CUSTOM_PROP_DECL.sub("", line)
            if rx.search(subject) and not exempt(lines, idx):
                if rule == "DS-COLOR" and not is_dart and "raw hex colour literal" in message \
                        and quoted_hex_is_only_anchor(line):
                    continue
                findings.append(Finding(rel, lineno, rule, severity, message, line))
        if governed and PRESENTATIONAL[("dart" if is_dart else kind)].search(line) and not exempt(lines, idx):
            findings.append(Finding(rel, lineno, "DS-PRESENTATIONAL", "error",
                                    "shared library components are presentational: data in, events out; move state, data "
                                    "access and feature imports to the smart container", line))
        icon = ICON_PKG[stack].search(line)
        if icon:
            families.add(icon_family(icon.group(1)))
            if not (lib_or_wrapper or WRAPPER_NAME.search(rel)) and not exempt(lines, idx):
                findings.append(Finding(rel, lineno, "DS-ICON-ISOLATION", "error",
                                        "icon package imported in feature code: use the project icon wrapper/registry",
                                        line))
        icon_lit = DART_ICON_LITERAL.search(line) if is_dart else None
        if icon_lit:
            families.add("cupertino" if "CupertinoIcons" in icon_lit.group(0) else "material")
            if not (lib_or_wrapper or WRAPPER_NAME.search(rel) or token_file) and not exempt(lines, idx):
                findings.append(Finding(rel, lineno, "DS-ICON-ISOLATION", "error",
                                        "direct Icons.*/CupertinoIcons.* in feature UI: use the project icon wrapper "
                                        "(ignore-design: for documented framework/system chrome)", line))
        anim = ANIM_PKG[stack].search(line)
        if anim and not lib_or_wrapper and not exempt(lines, idx):
            findings.append(Finding(rel, lineno, "DS-ANIM", "error",
                                    "animation runtime used directly: go through the shared animation wrapper "
                                    "(reduced-motion fallback, lifecycle)", line))
    if PTR_USAGE.search(text) and not REFRESH_RECORD.search(text):
        lineno = next((i + 1 for i, l in enumerate(lines) if PTR_USAGE.search(l)), 1)
        if not exempt(lines, lineno - 1):
            findings.append(Finding(rel, lineno, "DS-REFRESH", "error",
                                    "pull-to-refresh used without a refresh-strategy record "
                                    "(refresh-strategy: background|automatic|realtime|pull-to-refresh|explicit|none)",
                                    lines[lineno - 1] if lines else ""))
    return findings, families, scales, signals


def discover_design_md(root: Path) -> tuple[Path | None, list[Path]]:
    """Canonical DESIGN.md at the scan root (worktree copies are ignored), plus other copies found."""
    canonical = next((root / c for c in DESIGN_MD_CANDIDATES if (root / c).is_file()), None)
    others: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if "DESIGN.md" in filenames:
            p = Path(dirpath) / "DESIGN.md"
            if p != canonical:
                others.append(p)
    return canonical, others


def scan(root: Path, only: list[Path] | None = None) -> tuple[list[Finding], int, dict[str, int]]:
    root = root.resolve()
    roots = find_app_roots(root)
    findings: list[Finding] = []
    counts = {"flutter": 0, "angular": 0, "react": 0}
    per_root_families: dict[Path, dict[str, str]] = {}
    per_root_scales: dict[Path, dict[str, set[str]]] = {}
    authorities: dict[str, str] = {}  # Dart colour-token roots across the whole scan root -> first file
    loading_lines: dict[Path, str] = {}
    rm_override: set[Path] = set()
    candidates: list[Path] = []
    if only is not None:
        candidates = [p.resolve() for p in only if p.is_file()]
    else:
        for app_root in roots:
            for dirpath, dirnames, filenames in os.walk(app_root):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
                here = Path(dirpath)
                if here != app_root and ("pubspec.yaml" in filenames or "package.json" in filenames) and here in roots:
                    dirnames[:] = []  # nested app root: scanned on its own
                    continue
                candidates.extend(here / f for f in filenames)
    for path in sorted(set(candidates)):
        owner = owning_root(path, roots)
        if owner is None:
            continue
        app_root, kind = owner
        rel_in_app = path.relative_to(app_root).as_posix()
        if not in_scope(rel_in_app, kind):
            continue
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
        counts[kind] += 1
        file_findings, families, scales, signals = scan_file(path, rel, rel_in_app, kind)
        findings.extend(file_findings)
        if signals.get("colour_authority"):
            m = DART_AUTHORITY_DIR.match(rel_in_app)
            authority = (app_root / (m.group("root") if m else str(Path(rel_in_app).parent))).resolve()
            authorities.setdefault(authority.relative_to(root).as_posix() if authority.is_relative_to(root)
                                   else authority.as_posix(), rel)
        if "loading_line" in signals:
            loading_lines.setdefault(app_root, signals["loading_line"])
        if signals.get("rm_override"):
            rm_override.add(app_root)
        for fam in families:
            per_root_families.setdefault(app_root, {}).setdefault(fam, rel)
        for name in scales:
            family = next(f for f in ("Spacing", "Gap", "Radi", "Motion", "Duration") if f in name)
            family = {"Gap": "Spacing", "Duration": "Motion"}.get(family, family)
            per_root_scales.setdefault(root, {}).setdefault(family, set()).add(f"{name} ({rel})")  # workspace-wide
    if only is None:
        for app_root, fams in per_root_families.items():
            if len(fams) > 1:
                rel_root = app_root.relative_to(root).as_posix() if app_root != root else "."
                detail = ", ".join(f"{k} (first in {v})" for k, v in sorted(fams.items()))
                findings.append(Finding(rel_root, 0, "DS-ICON-FAMILY", "error",
                                        f"one icon family per app; found {len(fams)}: {detail}"))
        for app_root, fams in per_root_scales.items():
            for family, classes in sorted(fams.items()):
                if len(classes) > 1:
                    rel_root = app_root.relative_to(root).as_posix() if app_root != root else "."
                    findings.append(Finding(rel_root, 0, "DS-SCALE", "error",
                                            f"parallel {family.lower()} scales: {', '.join(sorted(classes))}; keep one"))
        if len(authorities) > 1:
            detail = ", ".join(f"{k or '.'} ({v})" for k, v in sorted(authorities.items()))
            findings.append(Finding(".", 0, "DS-AUTHORITY", "error",
                                    f"colour literals defined in {len(authorities)} token roots: {detail}; keep one"))
        for app_root, where in sorted(loading_lines.items()):
            if app_root not in rm_override:
                rel_root = app_root.relative_to(root).as_posix() if app_root != root else "."
                findings.append(Finding(rel_root, 0, "DS-REDUCED-MOTION", "error",
                                        f"daisyUI loading indicator ({where}) keeps animating under reduced motion (SMIL "
                                        "in mask-image): add the `.loading` reduced-motion override to the global "
                                        "stylesheet or `motion-reduce:hidden` on the element"))
        canonical, _ = discover_design_md(root)
        design_text = ""
        if canonical is not None:
            try:
                design_text = canonical.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                design_text = ""
        for app_root, kind in roots.items():
            deps: set[str] = set()
            try:
                if kind == "flutter":
                    pub = app_root / "pubspec.yaml"
                    if pub.is_file():
                        deps |= anim_deps_from_pubspec(pub.read_text(encoding="utf-8"))
                else:
                    pkg = app_root / "package.json"
                    if pkg.is_file():
                        deps |= anim_deps_from_package_json(pkg.read_text(encoding="utf-8"))
            except OSError:
                continue
            for engine in sorted(deps):
                if not re.search(rf"\b{engine}\b", design_text, re.I):
                    rel_root = app_root.relative_to(root).as_posix() if app_root != root else "."
                    findings.append(Finding(rel_root, 0, "DS-ANIM-DECISION", "error",
                                            f"{engine} is a dependency; record it in DESIGN.md Motion "
                                            "(native/CSS is the default; do not add a runtime as a side effect)"))
    return findings, sum(counts.values()), counts


# --------------------------------------------------------------------------------------------- selftest
FIXTURES: dict[str, tuple[str, set[str]]] = {
    "app/pubspec.yaml": ("name: app\n", set()),
    # PASS: dumb button with isBusy/tone/onPressed and token spacing.
    "app/lib/design_system/components/buttons/primary_button.dart": (
        "// Tier: Atom\nimport 'package:flutter/material.dart';\n\nclass PrimaryButton extends StatelessWidget {\n"
        "  const PrimaryButton({super.key, required this.label, this.isBusy = false, this.tone = ButtonTone.primary,"
        " this.onPressed});\n  final bool isBusy;\n  final ButtonTone tone;\n  final VoidCallback? onPressed;\n"
        "  Widget build(BuildContext c) => Padding(padding: EdgeInsets.all(AppSpacing.md), child: Icon(Icons.check));\n}\n",
        set()),
    # FAIL: Flutter shared atom importing a feature repository.
    "app/lib/design_system/components/status/status_badge.dart": (
        "// Tier: Atom\nimport '../../../features/orders/data/order_repository.dart';\n", {"DS-PRESENTATIONAL"}),
    # FAIL: shared component reading Riverpod state.
    "app/lib/design_system/components/cards/user_card.dart": (
        "// Tier: Molecule\nimport 'package:flutter_riverpod/flutter_riverpod.dart';\n"
        "class UserCard extends ConsumerWidget {}\n", {"DS-PRESENTATIONAL"}),
    "app/lib/design_system/components/cards/loading_card.dart": (
        "import 'package:flutter/material.dart';\n// Tier: Molecule\n", {"DS-TIER"}),
    "app/lib/design_system/components/cards/lower_card.dart": ("// Tier: atom\n", {"DS-TIER"}),
    "app/lib/design_system/components/components.dart": ("export 'buttons/primary_button.dart';\n", set()),
    "app/lib/design_system/components/animation/app_lottie.dart": (
        "// Tier: Atom\nimport 'package:lottie/lottie.dart';\n", set()),
    "app/lib/design_system/tokens/app_colors.dart": ("const primary = Color(0xFF0057B8);\nclass AppSpacing {}\n", set()),
    "app/lib/core/spacing_tokens.dart": ("class SpacingTokens {}\nclass AppSpacingExtension extends ThemeExtension {}\n",
                                         set()),
    # PASS: smart container passing a semantic status.
    "app/lib/features/orders/presentation/order_screen.dart": (
        "Widget build(c, ref) => StatusBadge(tone: StatusTone.warning, label: l10n.pending);\n", set()),
    # FLAG: raw hex passed for a business status; literal spacing.
    "app/lib/features/orders/presentation/legacy_screen.dart": (
        "StatusBadge(color: Color(0xFFE53935));\nPadding(padding: EdgeInsets.all(13));\nText('x', style: TextStyle(fontSize: 18));\n",
        {"DS-COLOR", "DS-SPACING", "DS-TYPE"}),
    "app/lib/features/orders/presentation/exempt_screen.dart": (
        "// ignore-design: partner logo colour fixed by contract\nconst c = Color(0xFF112233);\n"
        "const z = EdgeInsets.all(0);\n// Colors.red in a comment\n", set()),
    "app/lib/features/orders/presentation/short_reason_screen.dart": ("final c = Colors.red; // ignore-design: tmp\n",
                                                                      {"DS-COLOR"}),
    "app/lib/features/home/home_screen.dart": ("import 'package:phosphor_flutter/phosphor_flutter.dart';\n",
                                               {"DS-ICON-ISOLATION"}),
    "app/lib/features/home/celebration.dart": ("import 'package:lottie/lottie.dart';\n", {"DS-ANIM"}),
    "app/lib/features/home/driver_screen.dart": ("import 'package:lottie/lottie.dart';\n", {"DS-ANIM"}),
    "app/lib/features/home/lexicon_screen.dart": ("import 'package:phosphor_flutter/phosphor_flutter.dart';\n",
                                                {"DS-ICON-ISOLATION"}),
    "app/lib/features/home/app_icons_registry.dart": ("import 'package:phosphor_flutter/phosphor_flutter.dart';\n", set()),
    "app/lib/features/home/delete_screen.dart": ("Widget build(c) => Icon(Icons.delete);\n", {"DS-ICON-ISOLATION"}),
    "app/lib/features/home/date_chrome.dart": (
        "Icon(Icons.calendar_today); // ignore-design: Material date-picker chrome uses Icons\n", set()),
    "app/lib/features/home/celebration_animation.dart": ("import 'package:lottie/lottie.dart';\n", {"DS-ANIM"}),
    "app/lib/features/feed/feed_screen.dart": (
        "Widget build(c) => RefreshIndicator(onRefresh: r, child: list);\n", {"DS-REFRESH"}),
    "app/lib/features/feed/news_screen.dart": (
        "// refresh-strategy: pull-to-refresh\nWidget build(c) => RefreshIndicator(onRefresh: r, child: list);\n",
        set()),
    "app/lib/features/feed/static_screen.dart": (
        "// refresh-strategy: background\nWidget build(c) => ListView();\n", set()),
    "rive_app/pubspec.yaml": ("name: rive_app\ndependencies:\n  rive: 0.13.0\n", set()),
    "rive_app/lib/main.dart": ("void main() {}\n", set()),
    # a second colour authority next to design_system/ (project-level DS-AUTHORITY; the file itself is a token file)
    "app/lib/theme/brand_colors.dart": ("const brand = Color(0xFF0A0B0C);\n", set()),
    "app/lib/features/promo/theme/promo_colors.dart": ("const c = Color(0xFF112233);\n", {"DS-COLOR"}),
    "app/lib/features/promo/promo_card.dart": (
        "final c = Color.from(alpha: 1, red: 0, green: 0, blue: 1);\nfinal r = BorderRadius.circular(12);\n"
        "const s = SizedBox.square(dimension: 13);\nfinal z = BorderRadius.circular(AppRadius.md);\n",
        {"DS-COLOR", "DS-SHAPE", "DS-SPACING"}),
    "app/lib/design_system/components/cards/quoted_card.dart": (
        '// Tier: Molecule\nimport "package:flutter_riverpod/flutter_riverpod.dart";\n', {"DS-PRESENTATIONAL"}),
    "app/lib/features/home/home.g.dart": ("final c = Colors.red;\n", set()),
    "app/test/home_test.dart": ("final c = Colors.red;\n", set()),
    # Angular
    "web/package.json": ('{"dependencies": {"@angular/core": "22.3.0"}}\n', set()),
    "web/src/app/shared/components/status-badge/status-badge.component.ts": (
        "// Tier: Atom\nimport { Component, input, output } from '@angular/core';\n"
        "export class StatusBadge { tone = input<'ok' | 'warn'>('ok'); pressed = output<void>(); }\n", set()),
    # FAIL: presentational component injecting a domain service.
    "web/src/app/shared/components/order-summary/order-summary.component.ts": (
        "// Tier: Organism\nimport { inject } from '@angular/core';\nexport class S { private orders = inject(OrderService); }\n",
        {"DS-PRESENTATIONAL"}),
    # FAIL: Angular 22 services have no suffix; PASS: DOM/forms tokens.
    "web/src/app/shared/components/session-chip/session-chip.ts": (
        "// Tier: Atom\nimport { inject } from '@angular/core';\nimport { AuthSession } from '../../../core/auth/auth-session';\n"
        "export class C { private s = inject(AuthSession); }\n", {"DS-PRESENTATIONAL"}),
    "web/src/app/shared/components/text-field/text-field.ts": (
        "// Tier: Molecule\nexport class F { private el = inject(ElementRef); private d = inject(DestroyRef);"
        " private c = inject(NgControl, { self: true, optional: true }); }\n", set()),
    "web/src/app/shared/components/text-field/text-field.html": (
        '<p [style.margin.px]="12">x</p>\n<p class="font-[var(--font-sans)]">y</p>\n', {"DS-INLINE-STYLE"}),
    "web/src/app/shared/components/text-field/text-field.css": (":host { font-family: var(--font-sans); }\n", set()),
    # FAIL: dumb component doing HTTP.
    "web/src/app/shared/components/fetcher/fetcher.component.ts": (
        "// Tier: Molecule\nimport { HttpClient } from '@angular/common/http';\n", {"DS-PRESENTATIONAL"}),
    "web/src/app/shared/components/item-card/item-card.component.ts": ("import { Component } from '@angular/core';\n",
                                                                       {"DS-TIER"}),
    "web/src/app/shared/components/item-card/item-card.component.spec.ts": ("const x = '#fff';\n", set()),
    "web/src/app/features/orders/list.component.html": (
        '<div class="bg-[#123456] p-[13px] text-[15px] text-red-500 text-base-content/40">\n'
        '<input class="input input-bordered">\n<p style="margin: 12px">x</p>\n',
        {"DS-COLOR", "DS-SPACING", "DS-TYPE", "DS-MUTED-TEXT", "DS-DAISYUI4", "DS-INLINE-STYLE"}),
    "web/src/app/features/orders/clean.component.html": (
        '<div class="bg-primary p-4 gap-2 text-sm text-base-content/70 card-border">ok</div>\n', set()),
    # FAIL: constructor injection of a service; PASS: DOM token.
    "web/src/app/shared/components/kpi-card/kpi-card.ts": (
        "// Tier: Molecule\nexport class K {\n  constructor(\n    private readonly api: DashboardApi,\n  ) {}\n}\n",
        {"DS-PRESENTATIONAL"}),
    "web/src/app/shared/components/kpi-card/kpi-chip.ts": (
        "// Tier: Atom\nexport class C { constructor(private el: ElementRef, private r: Renderer2) {} }\n", set()),
    # raw hex passed to a colour input for a business status; anchors are not colours; radius literals; spinner
    "web/src/app/features/orders/order-status.html": (
        '<app-status-badge color="#E53935" label="Late" />\n<app-chip [color]="\'#e53935\'" />\n'
        '<a href="#add">Add</a>\n<span class="loading loading-spinner" aria-hidden="true"></span>\n',
        {"DS-COLOR"}),
    "web/src/app/features/orders/order-status.css": (
        ".a { border-radius: 13px; }\n.b { border-radius: var(--radius-box); --radius-card: 3px; }\n", {"DS-SHAPE"}),
    "web/src/styles.css": (
        '@plugin "daisyui/theme" {\n  --color-primary: oklch(0.6 0.2 250);\n}\nbody { color: #333; padding: 0; }\n'
        "@theme { --spacing-md: 1rem; }\n", {"DS-COLOR", "DS-SPACING-SHADOW"}),
    "web/src/app/features/orders/row.component.scss": (".row { padding: 12px; margin: 0; gap: calc(var(--spacing) * 2); }\n",
                                                       {"DS-SPACING"}),
    # React
    "site/package.json": ('{"dependencies": {"react": "19.3.0", "lucide-react": "1.79.0"}}\n', set()),
    "site/src/shared/ui/badge.tsx": (
        "// Tier: Atom\nexport function Badge({ tone, isBusy, onPress }: BadgeProps) { return null; }\n", set()),
    # FAIL: shared badge importing a global store.
    "site/src/shared/ui/status-badge.tsx": ("// Tier: Atom\nimport { useCartStore } from '@/features/cart/store';\n",
                                            {"DS-PRESENTATIONAL"}),
    "site/src/shared/ui/user-chip.tsx": ("// Tier: Molecule\nimport { useQuery } from '@tanstack/react-query';\n",
                                         {"DS-PRESENTATIONAL"}),
    "site/src/shared/ui/back-link.tsx": ("// Tier: Atom\nexport const Back = () => { const go = useNavigate(); };\n",
                                         {"DS-PRESENTATIONAL"}),
    "site/src/shared/ui/cart-count.tsx": ("// Tier: Atom\nimport { create } from 'zustand';\n", {"DS-PRESENTATIONAL"}),
    "site/src/shared/ui/theme-provider.tsx": ("import { createContext } from 'react';\n", set()),
    "site/src/shared/ui/icon.tsx": ("// Tier: Atom\nimport { Check } from 'lucide-react';\n", set()),
    "site/src/components/ui/button.tsx": ("import { Loader2 } from 'lucide-react';\nconst c = 'text-[13px] bg-red-500';\n",
                                          set()),
    "site/src/features/orders/order-row.tsx": (
        "import { Check } from 'lucide-react';\nexport const Row = () => <p style={{ color: '#ff0000' }} />;\n",
        {"DS-ICON-ISOLATION", "DS-COLOR"}),
    "site/src/features/promo/promo.css": (
        ".promo { --primary: oklch(0.6 0.2 25); --gap: var(--spacing); }\n",
        {"DS-COLOR"}),
    "site/src/features/orders/status-colors.ts": (
        "export const STATUS_COLORS = { overdue: '#E53935', ok: \"#2E7D32\" };\n", {"DS-COLOR"}),
    "site/src/features/orders/late-badge.tsx": (
        "const LATE = '#E53935';\nexport const L = (p: { late: boolean }) => <Badge statusColor={p.late ? LATE : `#2E7D32`} />;\n"
        "export const A = () => <a href=\"#add\">Add</a>;\n", {"DS-COLOR"}),
    "site/src/features/orders/anchors.tsx": (
        "export const A = () => <><a href=\"#add\">Add</a><Link fragment=\"#bad\" /></>;\n", set()),
    "site/src/features/orders/id-hex.ts": ("export const late = { id: 1, hex: '#E53935' };\n", {"DS-COLOR"}),
    "site/src/features/orders/anchor-id.tsx": ("export const A = () => <a href=\"#add\" id=\"feed\">Add</a>;\n", set()),
    "site/src/shared/ui/cart-icon.tsx": (
        "// Tier: Atom\nexport const C = () => { const cart = useContext(CartContext); };\n", {"DS-PRESENTATIONAL"}),
    "site/src/shared/ui/mode-toggle.tsx": (
        "// Tier: Atom\nexport const T = () => { const t = useContext(ThemeContext); };\n", set()),
    "site/src/features/orders/ptr.tsx": (
        "import PullToRefresh from 'react-simple-pull-to-refresh';\nexport const P = () => null;\n", {"DS-REFRESH"}),
    "site/src/features/orders/ptr-ok.tsx": (
        "// refresh-strategy: pull-to-refresh\nimport PullToRefresh from 'react-simple-pull-to-refresh';\n", set()),
    "web/src/app/features/orders/card-radius.css": (".card { border-radius: 13px; }\n", {"DS-SHAPE"}),
    "site/src/index.css": (":root {\n  --background: oklch(1 0 0);\n}\n.dark { --background: oklch(0.145 0 0); }\n"
                           "@media (prefers-reduced-motion: reduce) {\n  .loading { mask-image: none; }\n}\n", set()),
    "site/src/features/orders/order-badge.tsx": (
        'export const B = () => <><StatusBadge color={"#E53935"} /><span className="loading loading-dots" />'
        '<div className="rounded-[13px]" /></>;\n', {"DS-COLOR", "DS-SHAPE"}),
}
PROJECT_EXPECTED = {("app", "DS-ICON-FAMILY"), (".", "DS-SCALE"), (".", "DS-AUTHORITY"), ("web", "DS-REDUCED-MOTION"),
                    ("rive_app", "DS-ANIM-DECISION")}


def selftest(verbose: bool) -> int:
    failures: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="ds-gate-")).resolve()
    try:
        for rel, (content, _) in FIXTURES.items():
            target = tmp / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        findings, scanned, _ = scan(tmp)
        expected_files = sum(1 for rel in FIXTURES if not rel.endswith(("pubspec.yaml", "package.json")))
        # out of scope: home.g.dart, test/home_test.dart, the .spec.ts and the CLI-owned components/ui/button.tsx
        if scanned != expected_files - 4:
            failures.append(f"scan saw {scanned} files, expected {expected_files - 4}")
        got: dict[str, set[str]] = {}
        for f in findings:
            got.setdefault(f.path, set()).add(f.rule)
        for rel, (_, want) in FIXTURES.items():
            have = got.get(rel, set())
            if rel.endswith(("pubspec.yaml", "package.json")):
                continue
            if have != want:
                failures.append(f"{rel}: expected {sorted(want) or 'clean'}, got {sorted(have) or 'clean'}")
        project = {(f.path, f.rule) for f in findings if f.line == 0}
        if project != PROJECT_EXPECTED:
            failures.append(f"project-level findings: expected {sorted(PROJECT_EXPECTED)}, got {sorted(project)}")
        # --files mode judges only the listed file and skips project-level checks.
        one, n_one, _ = scan(tmp, [tmp / "app/lib/features/home/celebration.dart"])
        if n_one != 1 or {f.rule for f in one} != {"DS-ANIM"}:
            failures.append(f"--files mode: expected 1 file with DS-ANIM, got {n_one} file(s) {sorted({f.rule for f in one})}")
        # DESIGN.md discovery: root copy is canonical, worktree copies are ignored, others are reported.
        (tmp / ".worktrees" / "x").mkdir(parents=True)
        (tmp / ".worktrees" / "x" / "DESIGN.md").write_text("stale\n", encoding="utf-8")
        canonical, _ = discover_design_md(tmp)
        if canonical is not None:
            failures.append(f"DESIGN.md discovery: expected none, got {canonical}")
        (tmp / "DESIGN.md").write_text("# Design\n## Motion\nNative/CSS; Lottie decorative only.\n", encoding="utf-8")
        (tmp / "app" / "DESIGN.md").write_text("# Copy\n", encoding="utf-8")
        canonical, others = discover_design_md(tmp)
        if canonical != tmp / "DESIGN.md" or others != [tmp / "app" / "DESIGN.md"]:
            failures.append(f"DESIGN.md discovery: got canonical={canonical} others={others}")
        (tmp / "lottie_app" / "pubspec.yaml").parent.mkdir(parents=True, exist_ok=True)
        (tmp / "lottie_app" / "pubspec.yaml").write_text("name: lottie_app\ndependencies:\n  lottie: 3.0.0\n",
                                                         encoding="utf-8")
        (tmp / "lottie_app" / "lib").mkdir(parents=True, exist_ok=True)
        (tmp / "lottie_app" / "lib" / "main.dart").write_text("void main() {}\n", encoding="utf-8")
        named, _, _ = scan(tmp)
        anim_dec = {(f.path, f.rule) for f in named if f.rule == "DS-ANIM-DECISION"}
        if ("lottie_app", "DS-ANIM-DECISION") in anim_dec:
            failures.append("lottie named in DESIGN.md Motion must not raise DS-ANIM-DECISION")
        if ("rive_app", "DS-ANIM-DECISION") not in anim_dec:
            failures.append("rive dependency without a DESIGN.md Motion mention must raise DS-ANIM-DECISION")
        if verbose:
            print(f"  scanned {scanned} of {expected_files} fixture files, {len(findings)} findings")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        for f in failures:
            print(f"  FAIL {f}")
        print(f"check-design-system selftest FAIL ({len(failures)})")
        return 2
    if verbose:
        print("check-design-system selftest PASS")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--root", default=".", help="project root (DESIGN.md is discovered here)")
    parser.add_argument("--files", nargs="+", help="judge only these files (no project-level checks)")
    parser.add_argument("--require-design-md", action="store_true", help="missing DESIGN.md is an error")
    parser.add_argument("--selftest", action="store_true", help="run the planted-fixture controls only")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest(verbose=True)
    if selftest(verbose=False) != 0:
        print("check-design-system: detector selftest failed; no project file was judged", file=sys.stderr)
        return 2

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"check-design-system: --root {root} is not a directory", file=sys.stderr)
        return 2
    only = [Path(f) if Path(f).is_absolute() else (Path.cwd() / f) for f in args.files] if args.files else None
    findings, scanned, counts = scan(root, only)
    canonical, others = discover_design_md(root)

    if scanned == 0:
        print(f"design-system: NOT APPLICABLE (0 UI source files under {root})")
        return 0
    if canonical:
        print(f"DESIGN.md: {canonical.relative_to(root).as_posix()} (canonical)")
        for other in others:
            print(f"DESIGN.md: WARNING second copy {other.relative_to(root).as_posix()}: one canonical file per project")
    elif args.require_design_md:
        findings.append(Finding(".", 0, "DS-DESIGN-MD", "error",
                                "no DESIGN.md at the project root: generate one (/scaffold-*) or record the decision"))
    else:
        print("DESIGN.md: WARNING missing at the project root; toolkit defaults are unapproved until the project "
              "records its own (see design-system/reference/design-md-governance.md)")
    for f in sorted(findings, key=lambda x: (x.path, x.line, x.rule)):
        print(f.render())
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = len(findings) - errors
    print(f"design-system: scanned {scanned} files (flutter {counts['flutter']}, angular {counts['angular']}, "
          f"react {counts['react']}); {errors} error(s), {warnings} warning(s) -> {'FAIL' if errors else 'PASS'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
