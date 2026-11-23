# playwright-cli — Tool Reference

`playwright-cli` is the stateful Bash CLI for interactive browser QA of **web targets** (Angular, React, any served site). The npm package is `@playwright/cli`; its binary is `playwright-cli`. (`@playwright/mcp` is a different package whose binary is `playwright-mcp`.) Every command below was run against `@playwright/cli@0.1.25` in real Chromium; re-check with `playwright-cli --help <command>` after upgrading.

For CI test suites use `@playwright/test` instead: [playwright-test-suite.md](playwright-test-suite.md). Flutter Android/iOS apps are never tested here: `.claude/rules/testing-tool-selection.md`.

## Install

```bash
npm install -g @playwright/cli@0.1.25    # pin; check the current version with: npm view @playwright/cli version
playwright-cli install-browser chromium  # once per machine
playwright-cli install-browser ffmpeg    # only if you record video (video-start fails without it)
playwright-cli --version                 # 0.1.25
```

Per project, `npm i -D @playwright/cli@0.1.25` and `npx playwright-cli ...` keeps the version in the lockfile.

## Session model

A named session keeps one browser open between commands: `playwright-cli -s=<name> <command>`. Without `-s`, commands use the default session. Open first, then drive:

```bash
playwright-cli -s=qa open http://127.0.0.1:4200/
playwright-cli -s=qa snapshot            # accessibility tree with refs: e9, e10, ...
playwright-cli -s=qa close
```

`file://` URLs are blocked ("Access to \"file:\" protocol is blocked"). Serve static HTML first, e.g. `npx http-server ./dist -p 4310 -s` or `python3 -m http.server 4310`.

## Targets

`click`, `fill`, `hover`, `select`, `check`, `screenshot`, `eval` and `snapshot` take a **ref from the latest snapshot** (`e9`) or a **unique selector** (`"button[type=submit]"`). Refs change after re-renders: re-run `snapshot` (or `find <text>`) before acting.

## Commands (verified in 0.1.25)

| Group | Commands |
|---|---|
| Navigation | `open [url]` (`--browser chrome\|firefox\|webkit\|msedge`, `--device "iphone 15"`, `--headed`, `--persistent`), `goto <url>`, `reload`, `go-back`, `go-forward` |
| Read the page | `snapshot [target]` (`--filename`, `--depth`, `--boxes`), `find <text>` / `find --regex <re>`, `eval <func> [target]` (`--filename`), `generate-locator <target>` |
| Interact | `click <target>`, `dblclick`, `fill <target> <text>` (`--submit`), `type <text>`, `press <key>`, `keydown`/`keyup`, `hover`, `select <target> <val>`, `check`/`uncheck`, `drag <from> <to>`, `upload <files...>`, `dialog-accept [text]`, `dialog-dismiss`, `mousemove`/`mousedown`/`mouseup`/`mousewheel` |
| Evidence | `screenshot [target]` (`--filename`, `--full-page`, `--type png\|jpeg\|webp`, `--hires`), `pdf --filename <f>`, `tracing-start` / `tracing-stop`, `video-start [file]` / `video-stop` |
| Console | `console [min-level]` (levels: `error`, `warning`, `info` default, `debug`; `--all`, `--clear`) |
| Network | `requests` (`--filter <regexp>`, `--static`, `--all`, `--clear`), `request <n>`, `request-headers <n>`, `request-body <n>`, `response-headers <n>`, `response-body <n>` |
| Mocking | `route <pattern>` (`--status`, `--body`, `--content-type`, `--header`), `route-list`, `unroute [pattern]`, `network-state-set offline\|online` |
| Storage | `state-save [file]`, `state-load <file>`, `cookie-list/get/set/delete/clear`, `localstorage-*`, `sessionstorage-*` |
| Emulation | `resize <w> <h>`, `set-color-scheme`, `set-reduced-motion reduce`, `set-forced-colors`, `set-contrast`, `set-media` (and matching `clear-*`) |
| Code | `run-code "async page => ..."`, `recording-start` / `recording-stop` (prints Playwright code) |
| Sessions | `list`, `close`, `close-all`, `kill-all`, `delete-data`, `tab-list`, `tab-new [url]`, `tab-select <i>`, `tab-close [i]` |

Renamed or removed versus older docs: there is no `network` command (use `requests` / `request <n>`); there is no `--output` flag (use `--filename`); `tracing-stop` takes no file argument and prints the trace path (under `.playwright-cli/traces/`).

## Recipes

### Check a flow: network + console after each critical action

```bash
playwright-cli -s=qa fill e9 "A-1"
playwright-cli -s=qa click e10
playwright-cli -s=qa requests --filter "/api/"   # e.g. 2. [GET] http://127.0.0.1:4310/api/orders.json => [200] OK
playwright-cli -s=qa request 2                    # headers + body of request #2
playwright-cli -s=qa console error                # any error = NEEDS WORK unless explained
```

### Error, empty and offline states (mock the API, do not monkey-patch fetch)

```bash
playwright-cli -s=qa route "**/api/orders*" --status 500 --body '{"error":"boom"}' --content-type application/json
playwright-cli -s=qa reload
playwright-cli -s=qa find "Could not load"        # the user-visible error state must exist
playwright-cli -s=qa screenshot --filename evidence/error-500.png
playwright-cli -s=qa unroute
playwright-cli -s=qa network-state-set offline    # runs context.setOffline(true)
playwright-cli -s=qa click "button[type=submit]"  # the action must surface an error, not fake success
playwright-cli -s=qa network-state-set online
```

`reload` while offline exits 1 (`net::ERR_INTERNET_DISCONNECTED`); that is expected. Test offline behaviour on an in-page action instead.

### Responsive check (web layout only)

```bash
playwright-cli -s=qa resize 390 844              # phone-sized viewport: web layout, never evidence about a mobile app
playwright-cli -s=qa eval "document.documentElement.scrollWidth <= document.documentElement.clientWidth"   # true = no horizontal overflow
playwright-cli -s=qa screenshot --filename evidence/phone-viewport.png
playwright-cli -s=qa resize 1280 800
```

### Evidence

```bash
playwright-cli -s=qa screenshot --filename evidence/desktop.png --full-page
playwright-cli -s=qa tracing-start
playwright-cli -s=qa goto http://127.0.0.1:4310/
playwright-cli -s=qa tracing-stop                 # prints .playwright-cli/traces/trace-<ts>.trace
playwright-cli -s=qa video-start evidence/flow.webm   # needs: playwright-cli install-browser ffmpeg
playwright-cli -s=qa video-stop
```

### Auth state (test accounts only)

```bash
playwright-cli -s=qa state-save .auth/qa.json    # after signing in with a TEST account; gitignore .auth/
playwright-cli -s=qa2 state-load .auth/qa.json
```

Prove sign-in by what the user and server see (the protected page renders; `requests --filter /api/me` shows 200; after sign-out the API returns 401), never by reading a token from `localStorage`. A token in `localStorage` is an XSS exfiltration risk, not a success criterion.

### Clean up

```bash
playwright-cli close-all     # kill-all for zombie sessions
```

## playwright-cli vs Browser-Use

| Task | playwright-cli | Browser-Use MCP |
|------|---------------|-----------------|
| Scripted, repeatable steps | Preferred | Possible (Python in `browser_exec`) |
| Network list, mocking, offline | `requests`, `route`, `network-state-set` | Write CDP code yourself |
| Console messages | `console` | Write CDP code yourself |
| Traces / video | `tracing-*`, `video-*` | No |
| Exploratory goal-driven flow, cloud browser | No | Preferred ([browser-use-tools.md](browser-use-tools.md)) |

**Rule:** default to playwright-cli; use Browser-Use only when exploration or a cloud browser is the point.
