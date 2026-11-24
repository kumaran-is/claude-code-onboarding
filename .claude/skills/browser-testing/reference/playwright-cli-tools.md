# playwright-cli — Tool Reference

Playwright CLI is the stateful Bash CLI Claude uses for interactive browser automation of **web targets** (Angular, React, marketing sites, any served site). It ships two ways, with the same commands:

- inside Playwright >= 1.59: `npx --no-install playwright cli <command>` (preferred: same version as the project's pinned `@playwright/test`);
- as the standalone package `@playwright/cli` (binary `playwright-cli`) for projects without Playwright.

The commands below were re-run on 2026-11-24 with `npx playwright cli` from `@playwright/test@1.65.1` (Node 26.13.1) and spot-checked on `@playwright/cli@0.1.25`. Re-check with `--help <command>` after upgrading; the version-matched upstream skill is at `node_modules/playwright-core/lib/tools/skills/playwright-cli/SKILL.md`. In the examples, `playwright-cli` stands for either form.

For CI test suites use `@playwright/test` instead: [playwright-test-suite.md](playwright-test-suite.md). Flutter Android/iOS apps are never tested here: `.claude/rules/testing-tool-selection.md`.

## Install

```bash
npm i -D --save-exact @playwright/test@1.65.1      # project with a web E2E suite: the CLI comes with it
npx --no-install playwright cli --version          # Version 1.65.1

npm i -D --save-exact @playwright/cli@0.1.25       # project without Playwright
npx --no-install playwright-cli --version          # 0.1.25 (runs on playwright-core 1.66.0-alpha-2026-11-18)

playwright-cli install-browser firefox            # only for a browser the machine lacks; --dry-run first
playwright-cli install-browser ffmpeg             # only if you record video (video-start fails without it)
```

The CLI is an interactive tool: it is never a CI dependency, and never installed from a floating `@latest`. A per-project default config lives in `.playwright/cli.config.json` (`--config` overrides).

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

## Commands

Names from `--help` on 1.65.1 (first verified in full on 0.1.25). Re-run on 2026-11-24: `open`, `snapshot`, `fill`, `click`, `find`, `requests`, `console`, `screenshot`, `route` / `unroute`, `network-state-set`, `tracing-*`, `state-save`, `resize`, `eval --raw`, `list`, `close-all`, `attach`, `step-over`, `resume`.

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
| Code | `run-code "async page => ..."`, `recording-start` / `recording-stop` (prints Playwright code), `generate-locator <target>`, `highlight [target]` |
| Test debugging (1.59+) | `attach <session>` to a test started with `npx playwright test --debug=cli`, then `step-over`, `pause-at <file:line>`, `resume`; `detach` |
| Sessions | `list`, `close`, `close-all`, `kill-all`, `delete-data`, `tab-list`, `tab-new [url]`, `tab-select <i>`, `tab-close [i]`; `open --idle-timeout <ms>` |
| Output | `--raw` (result value only, pipe-friendly), `--json` (machine-readable, errors as `{"isError": true}`) |
| Other | `show` (session dashboard), `video-chapter <title>`, `webmcp-list` / `webmcp-call` (pages that register WebMCP tools; experimental, defer) |

Exit codes (verified): a missing ref or locator, an unopened session, a blocked `file://` URL and an unknown command exit **1**. `find` exits **0** when nothing matches; read `No matches found`, not the exit code.

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

## playwright-cli vs Chrome DevTools MCP

| Task | playwright-cli | Chrome DevTools MCP |
|------|---------------|---------------------|
| Drive the page: navigate, fill forms, click, snapshot, evidence | Default | Possible |
| Quick console / network check after an action | Default (`console`, `requests`) | Possible |
| Deep JS debugging, heap snapshots, logpoints, CSS inspection | Possible | Preferred ([chrome-devtools-tools.md](chrome-devtools-tools.md)) |
| Request mocking, offline, saved sessions | `route`, `network-state-set`, `-s=<session>` | No mocking |
| Performance traces, throttling, Lighthouse | Traces only | Preferred |
| Traces / video files as evidence | `tracing-*`, `video-*` | Performance trace only |
| Repeatable, gates a PR | No: write a `@playwright/test` spec ([playwright-test-suite.md](playwright-test-suite.md)) | No |

**Rule** (`.claude/rules/testing-tool-selection.md`): Playwright CLI is the default for interactive browser automation; Chrome DevTools MCP is for performance traces, Lighthouse and deep diagnostics; anything that must run again becomes a `@playwright/test` spec.
