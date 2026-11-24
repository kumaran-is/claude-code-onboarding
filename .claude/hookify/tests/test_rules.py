#!/usr/bin/env python3
"""Self-test for hookify rule files (.claude/hookify.*.local.md).

Fails (exit 1) when:
  1. any rule file cannot be parsed, has no conditions, or has a regex that Python `re` rejects
     (the engine would otherwise never fire that rule);
  2. a web design rule misses a positive control or fires on a negative control;
  3. the engine stops reporting invalid-regex rules loudly;
  4. load_rules() stops finding the rules when the hook's cwd is not the project root.

Run from anywhere: python3 .claude/hookify/tests/test_rules.py
"""

import glob
import os
import sys

CLAUDE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, CLAUDE_DIR)

from hookify.core.config_loader import Condition, Rule, load_rule_file, load_rules  # noqa: E402
from hookify.core.rule_engine import RuleEngine, invalid_regex_conditions  # noqa: E402

NG = "/w/web/admin/src/app/features/orders"
RX = "/w/apps/site/src"

# rule name -> list of (expect_fire, file_path, content)
CASES = {
    "design-no-hex-angular": [
        (True, f"{NG}/list.component.scss", ".a { color: #ff0000; }"),
        (True, f"{NG}/list.component.scss", ".a { background:#f00; }"),
        (True, f"{NG}/list.component.css", ".a { color: oklch(0.6 0.2 30); }"),
        (True, f"{NG}/list.component.html", '<div class="bg-[#123456]">'),
        (True, f"{NG}/list.component.html", '<div class="ring-[oklch(0.7_0.1_200)]">'),
        (True, "src/app/features/x/x.component.scss", ".a { border-color: rgb(1 2 3); }"),
        (True, f"{RX}/App.tsx", "<p style={{ color: '#ff0000' }} />"),
        (True, f"{RX}/Card.jsx", "<div style={{ backgroundColor: 'hsl(210 80% 55%)' }} />"),
        (True, f"{RX}/index.css", "body { background-color: #fafafa; }"),
        (False, f"{NG}/list.component.scss", ".a { color: var(--color-primary); }"),
        (False, f"{NG}/list.component.scss", ".a { background: color-mix(in oklch, var(--color-primary) 20%, transparent); }"),
        (False, f"{NG}/list.component.ts", "const shadow = 'rgba(0,0,0,.2)';"),
        (False, f"{NG}/list.component.spec.ts", "expect(el.style.color).toBe('rgb(255, 0, 0)');"),
        (False, "/w/web/admin/src/styles/theme.css", "@theme { --color-primary: oklch(0.6 0.2 250); }"),
        (False, "/w/web/admin/src/design-tokens.css", ":root { --brand: #3b82f6; }"),
        (False, "/w/api/src/modules/report/pdf.service.ts", "doc.fillColor('rgb(10,10,10)'); // color: #fff"),
        (False, "/w/api/src/app.module.ts", "const c = { color: 'rgba(0,0,0,1)' };"),
        (False, "/w/svc/src/main/resources/templates/index.html", '<p style="color: #333">x</p>'),
        (False, "/w/svc/src/main/resources/static/site.css", "p { color: #333 }"),
        (False, f"{NG}/list.component.scss", ".a { color: #f00; } /* ignore-design: brand-mandated legal red */"),
    ],
    "design-no-raw-typography-angular": [
        (True, f"{NG}/list.component.html", '<p class="text-[13px]">'),
        (True, f"{NG}/list.component.html", '<p class="text-[0.8rem]">'),
        (True, f"{NG}/list.component.scss", "h1 { font-size: 22px; }"),
        (True, f"{RX}/Hero.tsx", '<h1 className="font-[Arial]">'),
        (True, f"{RX}/Hero.tsx", "<h1 style={{ fontSize: 22 }}>"),
        (False, f"{NG}/list.component.html", '<p class="text-sm font-semibold">'),
        (False, f"{NG}/list.component.html", '<p class="font-[var(--font-display)]">'),
        (False, "/w/api/src/modules/pdf/pdf.service.ts", "doc.font('font-size: 12')"),
        (False, f"{RX}/Hero.test.tsx", '<h1 className="text-[22px]">'),
    ],
    "design-no-raw-spacing-angular": [
        (True, f"{NG}/list.component.html", '<div class="p-[13px]">'),
        (True, f"{NG}/list.component.html", '<div class="gap-x-[1.1rem]">'),
        (True, f"{NG}/list.component.html", '<div class="-mt-[7px]">'),
        (True, f"{NG}/list.component.html", '<div style="margin-top: 12px">'),
        (True, f"{RX}/Card.tsx", '<div className="mt-[7px]" />'),
        (True, f"{RX}/Card.tsx", "<div style={{ padding: 12 }} />"),
        (True, "src/app/features/x/x.component.html", '<div class="px-[3px]">'),
        (False, f"{NG}/list.component.html", '<div class="p-4 gap-2 mt-6 px-4 space-y-2">'),
        (False, f"{NG}/list.component.html", '<div class="w-[320px] grid-cols-[1fr_2fr]">'),
        (False, f"{NG}/list.component.html", '<div class="p-[var(--card-pad)]">'),
        (False, f"{RX}/Card.tsx", '<div className="mt-4 gap-2" />'),
        (False, "/w/svc/src/main/resources/templates/a.html", '<div class="p-[13px]">'),
        (False, f"{NG}/list.component.html", '<div class="p-[13px]"> <!-- ignore-design: third-party embed size -->'),
    ],
    "design-no-raw-form-inputs": [
        (True, f"{NG}/filter.component.html", '<input class="input" (input)="q = $any($event.target).value" />'),
        (True, f"{NG}/filter.component.html", '<select class="select">'),
        (True, "src/app/features/f/f.component.html", "<textarea class=\"textarea\"></textarea>"),
        (False, f"{NG}/filter.component.html", '<input class="input" [formField]="form.email" />'),
        (False, f"{NG}/filter.component.html", '<input class="input" formControlName="email" />'),
        (False, f"{NG}/filter.component.html", '<input [(ngModel)]="q" />'),
        (False, f"{NG}/filter.component.html", '<input type="checkbox" class="checkbox" [checked]="on()" />'),
        (False, f"{NG}/filter.component.html", '<input type="file" (change)="pick($event)" />'),
        (False, "/w/web/admin/src/app/shared/ui/input.component.html", '<input class="input" />'),
    ],
    "design-tier-comment-dart": [
        (True, "/w/packages/shared_ui/lib/src/widgets/task_card.dart", "import 'package:flutter/widgets.dart';\n"),
        (True, "/w/packages/shared_ui/lib/components/atoms/pill.dart", "// Tier: atom\nclass Pill {}\n"),
        (True, "/w/packages/shared_ui/lib/src/widgets/row.dart", "// Copyright\n// Tier: Molecule\n"),
        (False, "/w/packages/shared_ui/lib/src/widgets/task_card.dart", "// Tier: Molecule\nimport 'package:flutter/widgets.dart';\n"),
        (False, "/w/packages/shared_ui/lib/src/widgets/pill.dart", "// Tier: Atom"),
        (False, "/w/packages/shared_ui/lib/src/widgets/task_card.g.dart", "part of 'task_card.dart';\n"),
        (False, "/w/packages/shared_ui/lib/src/widgets/task_card_test.dart", "void main() {}\n"),
        (False, "/w/packages/shared_ui/lib/src/theme/app_spacing.dart", "class AppSpacing {}\n"),
        (False, "/w/apps/mobile/lib/features/home/home_screen.dart", "class HomeScreen {}\n"),
    ],
    "design-tier-comment-angular": [
        (True, f"{NG}/../../shared/components/item-card/item-card.component.ts", "import { Component } from '@angular/core';\n"),
        (True, "/w/web/src/app/shared/components/error-state/error-state.component.ts", "// Tier: Template\n"),
        (False, "/w/web/src/app/shared/components/item-card/item-card.component.ts", "// Tier: Organism\nimport { Component } from '@angular/core';\n"),
        (False, "/w/web/src/app/shared/components/item-card/item-card.component.spec.ts", "describe('x', () => {});\n"),
        (False, "/w/web/src/app/shared/components/item-card/item-card.component.html", "<div></div>\n"),
        (False, f"{NG}/list.component.ts", "import { Component } from '@angular/core';\n"),
    ],
}


def fires(engine: RuleEngine, rule: Rule, path: str, content: str) -> bool:
    result = engine.evaluate_rules([rule], {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": path, "content": content},
    })
    return bool(result)


def main() -> int:
    failures = 0
    engine = RuleEngine()

    files = sorted(glob.glob(os.path.join(CLAUDE_DIR, "hookify.*.local.md")))
    if not files:
        print("  FAIL no hookify rule files found (scan saw nothing)")
        return 1
    rules = {}
    for path in files:
        rule = load_rule_file(path)
        if rule is None or not rule.conditions:
            print(f"  FAIL {os.path.basename(path)}: not parsed or no conditions")
            failures += 1
            continue
        problems = invalid_regex_conditions(rule)
        for p in problems:
            print(f"  FAIL {p}")
        failures += len(problems)
        if not problems:
            print(f"  ok   {rule.name}: {len(rule.conditions)} condition(s) compile")
        rules[rule.name] = rule

    for name, cases in CASES.items():
        rule = rules.get(name)
        if rule is None:
            print(f"  FAIL {name}: rule file missing")
            failures += 1
            continue
        pos = sum(1 for c in cases if c[0])
        neg = len(cases) - pos
        if pos == 0 or neg == 0:
            print(f"  FAIL {name}: needs at least one positive and one negative control")
            failures += 1
        for expect, path, content in cases:
            got = fires(engine, rule, path, content)
            if got != expect:
                failures += 1
                print(f"  FAIL {name}: expected {'fire' if expect else 'silent'} for {path} :: {content}")
        print(f"  ok   {name}: {pos} positive / {neg} negative controls checked")

    # Loud-failure control: a variable-width look-behind is rejected by Python `re`.
    broken = Rule(name="broken-probe", enabled=True, event="file", action="warn",
                  conditions=[Condition(field="content", operator="regex_match", pattern=r"(?<!ignore-design.*)#fff")],
                  message="probe")
    if not invalid_regex_conditions(broken):
        print("  FAIL invalid regex not detected by invalid_regex_conditions")
        failures += 1
    result = engine.evaluate_rules([broken], {"hook_event_name": "PostToolUse", "tool_name": "Write",
                                              "tool_input": {"file_path": f"{NG}/a.component.scss", "content": "a{color:#fff}"}})
    context = result.get("hookSpecificOutput", {}).get("additionalContext", "")
    if "NOT enforced" in context and "broken-probe" in context:
        print("  ok   engine reports an invalid-regex rule as NOT enforced (additionalContext)")
    else:
        print(f"  FAIL engine silent on invalid regex (got: {result})")
        failures += 1

    # cwd control: hooks run in whatever directory the session cd'ed to; rules must still load.
    saved_cwd, saved_env = os.getcwd(), os.environ.get("CLAUDE_PROJECT_DIR")
    try:
        os.environ["CLAUDE_PROJECT_DIR"] = os.path.dirname(CLAUDE_DIR)
        os.chdir(os.path.dirname(os.path.dirname(CLAUDE_DIR)) or "/")
        loaded = len(load_rules())
    finally:
        os.chdir(saved_cwd)
        if saved_env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = saved_env
    enabled = sum(1 for r in rules.values() if r.enabled)
    if loaded == enabled and loaded > 0:
        print(f"  ok   load_rules() finds {loaded} rule(s) from a cwd outside the project")
    else:
        print(f"  FAIL load_rules() from a foreign cwd found {loaded}, expected {enabled}")
        failures += 1

    print("hookify rule selftest " + ("PASS" if failures == 0 else f"FAIL ({failures})"))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
