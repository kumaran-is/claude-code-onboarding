---
name: browser-testing
description: Browser automation and testing using playwright-cli (stateful Bash CLI for scripted tests — network inspection, console monitoring, screenshots, tracing) and Browser-Use MCP (autonomous agent flows). Use when the user needs to test web apps, debug browser issues, analyze performance, fill forms, run E2E user flows, or inspect network/console activity.
allowed-tools: Bash, mcp:browser-use
agent: browser-testing
context: fork
metadata:
  triggers: browser testing, playwright, E2E test, browser automation, Browser-Use, UI testing, end-to-end, login flow, form filling, web automation
  related-skills: angular-spa, frontend-design, systematic-debugging
  domain: quality
  role: specialist
  scope: testing
  output-format: report
last-reviewed: "2026-03-29"
---

**Iron Law:** Never claim a UI flow works without running it in a real browser. Use `playwright-cli` (Bash) for inspection and scripted steps; use Browser-Use MCP for autonomous goal-driven flows.

# Browser Automation & Testing Skill

> **Scope:** web targets only. Flutter Android/iOS UI/E2E uses Maestro CLI/MCP (`.claude/rules/testing-tool-selection.md`); never route a Flutter mobile app here, and never substitute a browser when Maestro or a device is unavailable (report BLOCKED/NOT RUN).

This skill combines **two tools** for complete browser automation:

- **playwright-cli** — stateful Bash CLI for deterministic scripted tests (navigation, snapshots, screenshots, network/console inspection, tracing)
- **Browser-Use MCP** — autonomous agent for goal-driven interaction (describe a goal, not steps)

## Install & Setup

```bash
# Install (package name is @playwright/mcp; binary is playwright-cli)
npm install -g @playwright/mcp@latest

# Initialize workspace (downloads browsers)
playwright-cli install

# Verify
playwright-cli --version
```

## Session Model

playwright-cli is **stateful** — each named session persists browser state across commands:

```bash
# Use -s flag to name a session (persists across calls)
playwright-cli -s=login-test goto http://localhost:4200/login
playwright-cli -s=login-test snapshot
playwright-cli -s=login-test fill [email-ref] "user@example.com"
playwright-cli -s=login-test click [submit-ref]

# Without -s: uses a default unnamed session
playwright-cli goto http://localhost:4200
```

## When to Use Which Tool

| Task | playwright-cli (Bash) | Browser-Use MCP |
|------|-----------------------|-----------------|
| Scripted test steps | Preferred | Works |
| Network request list | `playwright-cli network` | Not available |
| Console messages | `playwright-cli console` | Not available |
| Execute JavaScript | `playwright-cli eval <func>` | Not available |
| Performance tracing | `playwright-cli tracing-start/stop` | Not available |
| Accessibility tree | `playwright-cli snapshot` | Not available |
| Autonomous goal completion | Needs scripting | Preferred |
| Real Chrome with existing login | Limited | `--browser real` |

**Rule:** Default to playwright-cli. Use Browser-Use only when describing a goal is better than scripting steps.

## Quick Example: Testing Login Flow

```bash
# Step 1: Navigate and take baseline snapshot
playwright-cli -s=login goto http://localhost:4200/login
playwright-cli -s=login snapshot
# → Returns accessibility tree with [ref] for each element

# Step 2: Fill and submit
playwright-cli -s=login fill [email-ref] "user@example.com"
playwright-cli -s=login fill [password-ref] "password123"
playwright-cli -s=login click [submit-ref]

# Step 3: Verify result
playwright-cli -s=login network
# → Check POST /api/auth/login → 200
playwright-cli -s=login console
# → Check for errors
playwright-cli -s=login screenshot --output login-success.png
```

> For full command reference, Read [reference/playwright-cli-tools.md](reference/playwright-cli-tools.md)

> For combined playwright-cli + Browser-Use workflow patterns, Read [reference/browser-testing-workflows.md](reference/browser-testing-workflows.md)

## Server Lifecycle — `scripts/with_server.py`

Use when the dev server is **not already running** (CI environments, clean machines, automated flows).
Run `--help` first. Treat it as a black box — do NOT read source unless you must customise it.

```bash
python scripts/with_server.py --help
```

### Stack Presets

| Stack | Command |
|-------|---------|
| **Angular** | `python scripts/with_server.py --server "ng serve" --port 4200 -- playwright-cli goto http://localhost:4200` |
| **NestJS** | `python scripts/with_server.py --server "npm run start:dev" --port 3000 -- playwright-cli goto http://localhost:3000` |
| **FastAPI** | `python scripts/with_server.py --server "uvicorn main:app --port 8000" --port 8000 -- playwright-cli goto http://localhost:8000` |
| **Spring Boot** | `python scripts/with_server.py --server "mvn spring-boot:run" --port 8080 -- playwright-cli goto http://localhost:8080` |
| **Flutter Web** (web build only: says nothing about Android/iOS) | `python scripts/with_server.py --server "flutter run -d web-server --web-port 8080" --port 8080 -- playwright-cli goto http://localhost:8080` |

### Multi-server (backend + frontend together)

```bash
python scripts/with_server.py \
  --server "npm run start:dev" --port 3000 \
  --server "ng serve --port 4200" --port 4200 \
  -- playwright-cli -s=e2e goto http://localhost:4200
```

**When server is already running** (default dev workflow) → skip `with_server.py`, use `playwright-cli` directly.

## Decision Quick Reference

| Need to... | Command |
|-----------|---------|
| Navigate to URL | `playwright-cli goto <url>` |
| Test a **local HTML file** (no server) | `playwright-cli goto "file:///$(pwd)/path/to/file.html"` |
| Get element refs | `playwright-cli snapshot` |
| Fill an input | `playwright-cli fill <ref> <text>` |
| Click a button | `playwright-cli click <ref>` |
| Check console errors | `playwright-cli console error` |
| Check network requests | `playwright-cli network` |
| Take a screenshot | `playwright-cli screenshot [--output file.png]` |
| Run JS in page | `playwright-cli eval "<expression>"` |
| Resize viewport | `playwright-cli resize <w> <h>` |
| Start perf trace | `playwright-cli tracing-start` |
| Stop perf trace | `playwright-cli tracing-stop` |
| Run Lighthouse audit | `mcp__chrome-devtools__lighthouse_audit` (via Chrome DevTools MCP) |
| Debug a failing flow end-to-end | Load [Agentic Debug Loop](reference/agentic-debug-loop.md) — observe → diagnose → fix → re-verify |
| Close session | `playwright-cli close-all` |
| Start server then test | `python scripts/with_server.py --server "<cmd>" --port <N> -- <test-cmd>` |
| Autonomous flow | Browser-Use MCP: `browser_navigate` → `browser_get_state` → `browser_input` |

### Static HTML / Wireframe Testing

For local HTML files (wireframes, generated output, prototypes) — no server needed:

```bash
# Absolute path required for file:// URLs
playwright-cli goto "file:///$(pwd)/wireframes/dashboard.html"
playwright-cli snapshot
playwright-cli screenshot --output wireframe-check.png
```

Use this for: sketch-wireframe outputs, premium-wireframe-2026 outputs, any `.html` in the project.

## Critical Rules

1. **NEVER use `browser_get_state({ include_screenshot: true })`** — generates 126K+ tokens. Use `playwright-cli screenshot` instead.
2. **Always close sessions** — run `playwright-cli close-all` when done.
3. **Check network + console after every critical action** — form submissions, navigation, button clicks.
4. **Screenshots as proof** — required for APPROVED verdicts in reality-checker.
5. **Console errors = NEEDS WORK** — any unhandled console error is an automatic failure.
6. **Load reference files only when the Quick Reference table above doesn't answer your question** — each reference file is 150–400 lines. Load selectively, not by default.

## Reference Files

| Resource | When to Load |
|----------|-------------|
| [playwright-cli Tools](reference/playwright-cli-tools.md) | Full command reference, all flags, session management |
| [Browser-Use Tools](reference/browser-use-tools.md) | Browser-Use MCP command reference and best practices |
| [Combined Workflows](reference/browser-testing-workflows.md) | Login flows, performance, E2E journeys, validation, accessibility |
| [Chrome DevTools Tools](reference/chrome-devtools-tools.md) | Core Web Vitals analysis, performance traces, CPU/network throttling, Lighthouse audit |
| [Agentic Debug Loop](reference/agentic-debug-loop.md) | Observe → diagnose → fix → re-verify pattern for AI-driven bug diagnosis on live apps |

## Process

1. **Determine which tool** — See "When to Use Which Tool" above
2. **Load reference files** — Read detailed docs for the tool you're using
3. **For inspection/scripted tasks** — Use playwright-cli Bash
4. **For goal-driven tasks** — Use Browser-Use MCP
5. **For combined testing** — playwright-cli monitors (network/console), Browser-Use acts
6. **Verify results** — Check both user perspective and technical perspective
7. **Report findings** — Present both perspectives
8. **Clean up** — `playwright-cli close-all`
