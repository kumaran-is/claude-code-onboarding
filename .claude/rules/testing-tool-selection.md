# Testing tool selection (authoritative)

Choose the test tool from the **application target under test**, never from the repository's overall stack. In a hybrid repo (Flutter app + Angular/React site) each target gets its own tool. Other files link here instead of restating this table.

| Target under test | UI / E2E tool | Never use |
|---|---|---|
| Flutter app on an Android emulator, iOS simulator or physical device | **Maestro CLI** (`maestro test`) and **Maestro MCP** (`list_devices` → `inspect_screen` → `run`) — exclusively | Playwright, Chrome DevTools, Browser-Use, claude-in-chrome, or any browser automation |
| Flutter unit, widget, golden and accessibility-guideline tests | `flutter test` | — |
| Flutter static validation | `flutter analyze`, `dart format --output=none --set-exit-if-changed .` | — |
| Angular / React website or web app (including responsive-viewport checks) | Playwright (`playwright-cli`), Chrome DevTools MCP, Browser-Use MCP | Maestro device flows |
| Flutter **web** build served in a browser | browser tools are allowed (it is a web target) | treating the result as proof about the Android/iOS app |

**Rules**

1. Flutter Android/iOS UI and E2E automation uses Maestro only. Detail, flow conventions and `integration_test` vs Maestro: `.claude/skills/flutter-mobile/reference/flutter-e2e-maestro.md`.
2. If Maestro, an emulator, a simulator or a device is unavailable, report **BLOCKED** (cannot run: say what is missing) or **NOT RUN** (skipped by choice: say why). Never silently substitute a browser, a Flutter Web screenshot or a resized viewport. Status words: `.claude/rules/flutter-verification.md`.
3. A mobile *viewport* in a browser tests a web layout. It is never evidence about a mobile app.
4. Selecting tools for a mobile QA task is automatic: Flutter Android/iOS target → Maestro. Do not ask which tool to use and do not offer a browser as a fallback.

**Enforcement:** `bash .claude/scripts/lint-testing-tools.sh` (static; run it after editing skills, agents, commands, rules or docs) and the advisory hook `pre-browser-tool-advisory.sh`, which reminds Claude of this rule when a browser tool is invoked in a workspace that contains a Flutter mobile app.
