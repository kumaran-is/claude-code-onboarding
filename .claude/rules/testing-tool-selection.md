# Testing tool selection (authoritative)

Choose the test tool from the **application target under test**, never from the repository's overall stack. In a hybrid repo (Flutter app + Angular/React site) each target gets its own tool. Other files link here instead of restating this table.

| Target under test | UI / E2E tool | Never use |
|---|---|---|
| Flutter app on an Android emulator, iOS simulator or physical device | **Maestro CLI** (`maestro test`) and **Maestro MCP** (`list_devices` → `inspect_screen` → `run`) — exclusively | Playwright, Chrome DevTools, claude-in-chrome, or any browser automation |
| Flutter unit, widget, golden and accessibility-guideline tests | `flutter test` | — |
| Flutter static validation | `flutter analyze`, `dart format --output=none --set-exit-if-changed .` | — |
| Angular website or web app (E2E, responsive-viewport, a11y, visual) | Playwright: `@playwright/test` suites (CI) and `playwright-cli` (interactive); Chrome DevTools MCP (default interactive debugging, performance) | Maestro device flows |
| React website or web app (E2E, responsive-viewport, a11y, visual) | Same as Angular: `@playwright/test`, `playwright-cli`, Chrome DevTools MCP | Maestro device flows |
| Angular unit and component tests | `ng test` (Vitest via `@angular/build:unit-test`, jsdom by default; CI: `ng test --no-watch`) — or the runner the `angular.json` test builder already names | a browser E2E tool for logic a unit test can cover |
| React unit and component tests | Vitest + React Testing Library + user-event (`vitest run`) | snapshot-only tests as the sole assertion |
| Flutter **web** build served in a browser | browser tools are allowed (it is a web target) | treating the result as proof about the Android/iOS app |

**Rules**

1. Flutter Android/iOS UI and E2E automation uses Maestro only. Detail, flow conventions and `integration_test` vs Maestro: `.claude/skills/flutter-mobile/reference/flutter-e2e-maestro.md`.
2. If Maestro, an emulator, a simulator or a device is unavailable, report **BLOCKED** (cannot run: say what is missing) or **NOT RUN** (skipped by choice: say why). Never silently substitute a browser, a Flutter Web screenshot or a resized viewport. Status words: `.claude/rules/flutter-verification.md`.
3. A mobile *viewport* in a browser tests a web layout. It is never evidence about a mobile app.
4. Selecting tools for a mobile QA task is automatic: Flutter Android/iOS target → Maestro. Do not ask which tool to use and do not offer a browser as a fallback.
5. Hybrid repos (for example a Flutter app plus an Angular or React site): route **per target**. `apps/mobile` → `flutter test` + Maestro; `web/` → `ng test` or `vitest run` + Playwright. One target's green run is never evidence for the other.
6. Maestro's Chromium web mode may drive a **web** target; it is web evidence only, never evidence about the mobile app.
7. jsdom-based unit/component tests cannot compute colour contrast or layout. Contrast, overflow and viewport checks run in a real browser (Playwright + `@axe-core/playwright`). Web suite guidance: `.claude/skills/browser-testing/reference/playwright-test-suite.md`.

**Enforcement:** `bash .claude/scripts/lint-testing-tools.sh` (static; run it after editing skills, agents, commands, rules or docs) and the advisory hook `pre-browser-tool-advisory.sh`, which reminds Claude of this rule when a browser tool is invoked in a workspace that contains a Flutter mobile app.
