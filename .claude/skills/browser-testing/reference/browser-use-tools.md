# Browser-Use MCP — Tool Reference

The configured `browser-use` MCP server exposes **four tools only**. Older docs named `browser_navigate`, `browser_get_state`, `browser_input`, `browser_click`, `mcp__browser-use__fill` and similar: those tools do not exist on this server. Do not call them.

| Tool | Purpose |
|---|---|
| `mcp__browser-use__browser_exec` | Run Python in a persistent browser session. Pre-imported helpers include `new_tab(url)`, `goto_url(url)`, `page_info()`, `click_at_xy(x, y)`, `type_text(text)`, `js(code)`, `cdp(method, ...)`, `wait_for_load()`, `list_tabs()`. The namespace persists across calls; the call returns what the code prints. |
| `mcp__browser-use__browser_screenshot` | Capture the current page as an image (`full: true` for the whole page, `max_dim` to downscale). Prefer this over screenshot code inside `browser_exec`. |
| `mcp__browser-use__browser_login` | Sign in to Browser Use Cloud before starting a cloud browser (`start_remote_daemon()` inside `browser_exec`). Not needed for the local browser. |
| `mcp__browser-use__browser_feedback` | Send feedback to the Browser Use team about the integration. Never include secrets, credentials or customer data. |

Source: the tool schemas the server advertises in the session tool list. Helper behaviour beyond these names is **UNVERIFIED — check before use** (print `page_info()` first).

## When to use it

- Exploratory, goal-driven checks where writing deterministic steps is not worth it.
- A cloud browser (after `browser_login`), e.g. to reach a deployed preview from a clean IP.

Everything repeatable (network inspection, mocking, console, traces, CI) belongs in `playwright-cli` ([playwright-cli-tools.md](playwright-cli-tools.md)) or `@playwright/test` ([playwright-test-suite.md](playwright-test-suite.md)). Browser-Use evidence (a screenshot of an exploratory run) is supporting evidence only; a reality-checker APPROVED for a web target needs a Playwright screenshot or trace.

Web targets only. Never use Browser-Use for a Flutter Android/iOS app: `.claude/rules/testing-tool-selection.md`.

## Pattern

```python
# browser_exec, call 1: first navigation opens a tab
new_tab("http://127.0.0.1:4200/orders")
wait_for_load()
print(page_info())
```

```python
# browser_exec, call 2: read state with JS instead of a giant DOM dump
print(js("document.querySelector('[role=alert]')?.textContent ?? 'no alert'"))
```

Then call `browser_screenshot` for the visual. Keep one working tab per task; reuse it with `list_tabs()` instead of opening duplicates.

## Rules

1. Test accounts only. Never type real user credentials into a browser session driven by an agent.
2. Report what was executed: the code you ran and what it printed. A goal "completed" by the agent without a printed check is NOT RUN, not PASS.
3. A cloud browser ends after its timeout (30 min default). When calls fail after that, start a new one; do not silently fall back to the local browser and report the result as if it came from the cloud.
