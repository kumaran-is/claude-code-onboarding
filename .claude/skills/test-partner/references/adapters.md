# Partner testing — target adapters

Canonical tool table: `.claude/rules/testing-tool-selection.md`. This file only says how a **paired manual walk** uses those tools. Do not add Playwright MCP or Browser Use MCP.

```bash
python3 .claude/skills/test-partner/scripts/check-test-partner.py --detect-target --root .
python3 .claude/skills/test-partner/scripts/check-test-partner.py --select-tools --target <target>
```

`--target` wins over auto-detect. Unknown target → BLOCKED (ask, or add a row below). Hybrid repos: detect **per app directory**, not the repo root.

## Flutter Android / iOS

UI observation: **Maestro CLI/MCP only** (`inspect_screen`, screenshot, flow). Never a browser, never Playwright, never Chrome DevTools.

Device logs: `adb -s <serial> logcat` (Android) or `xcrun simctl spawn <udid> log stream` (iOS), plus `flutter logs` when a debug run is attached. Prefer a Dart / widget-inspector MCP when it is already configured; fall back to logs and say which channel produced the evidence.

Resolve the **current** device id every session (`adb devices -l`, `xcrun simctl list`, Maestro `list_devices`). A pasted serial from yesterday is a claim about the past.

Physical Android does not have `10.0.2.2`. Prove the device can reach the backend before the first tap (first authenticated request in the owning service log, or an HTTP probe to the host the app is actually configured to use).

Offline/online: airplane mode / disable Wi-Fi on the **device under test**, then restore. Record radio state in the ledger. Android emulator radios are independent of the host — inherited airplane mode is a device signature, not an auth bug.

If Maestro or a device is missing: **BLOCKED / NOT RUN**. Do not substitute Flutter web.

## Angular / React / other web

UI observation: **Playwright CLI** for the live walk (`open`, `snapshot`, `screenshot`, `console`, `requests`). Committed regression of a finding becomes `@playwright/test`. Diagnostics (performance, Lighthouse, deep console/network): **Chrome DevTools MCP**.

`open --mobile` is a web viewport. It is never evidence about a native app.

Offline/online: Playwright context `offline: true` / `false`, or Chrome DevTools network throttling. Capture both the UI and the failed/queued request.

## Flutter web

Treated as a **web** target (Playwright + Chrome DevTools MCP). Say so in the ledger. That evidence does not speak for Android/iOS.

## Backend logs (any target)

Discover process names from the repo — `docker compose ps`, `docker ps`, Procfile, README — never from memory. Watermark UTC time before each step. Grep logs **since the watermark**. Direct SQL is read-only. Prefer a product read API when it is the actor-visible truth.

No stack running → record `backend-logs: N/A` and continue UI-only; do not invent containers.

## Extending

Add a target key to `check-test-partner.py` (`UI_E2E`, `DIAGNOSTICS`, `FORBIDDEN_FOR_TARGET`) and one short subsection here. Keep the spine skill unchanged. New mobile native stacks still must not use a browser as a stand-in for a device.
