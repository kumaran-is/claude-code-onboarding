# Browser E2E Testing

> **Scope:** web targets (Angular, React, websites, Flutter web builds). Flutter Android/iOS UI/E2E is Maestro-only, see Phase 7 and `.claude/rules/testing-tool-selection.md`.

> **When to use**: Validating critical user journeys end-to-end in a running browser — login flows, checkout, core feature workflows
> **Time estimate**: 30 min per E2E scenario; 2–4 hours for full critical path suite
> **Prerequisites**: App running locally or on staging; Chrome DevTools MCP and Browser-Use MCP configured

## Overview

E2E browser testing using the dual-MCP pattern: Chrome DevTools MCP for inspection, debugging, and network analysis — and Browser-Use MCP for human-like interactions (form fills, clicks, navigation). Covers critical path identification, test scenario design, and the `browser-testing` skill Iron Law.

---

## Iron Law (from `skills/browser-testing/SKILL.md`)

> **READ THE BROWSER-TESTING SKILL BEFORE WRITING ANY E2E CODE**
> Chrome DevTools MCP and Browser-Use MCP have distinct roles — confusing them wastes time.

---

## Dual-MCP Architecture

| MCP Server | Role | When to Use |
|------------|------|------------|
| **Chrome DevTools MCP** | Inspect, debug, analyze | Network requests, console errors, performance traces, DOM inspection |
| **Browser-Use MCP** | Interact, automate | Form fills, clicks, navigation, user journey automation |

**Pattern**: Use both simultaneously — Browser-Use drives the user journey while Chrome DevTools monitors the technical behavior.

---

## Phases

### Phase 1 — Load Skill and Identify Critical Paths

**Skill**: Load `browser-testing` (`.claude/skills/browser-testing/SKILL.md`)
**Agent**: `browser-testing` agent

**Critical path identification**:
```
Which user journeys, if broken, would block the user completely?
    |
    +-- Authentication? → Login → authenticated state → logout
    +-- Core feature? → The primary value action (create, search, purchase)
    +-- Data entry? → Form submission → confirmation → persistence
    +-- Navigation? → Deep links, back navigation, redirects
```

**Prioritize by impact**:
1. Authentication and authorization
2. Core feature happy path
3. Data persistence (create/read/update/delete)
4. Error states (invalid input, server errors, empty states)

---

### Phase 2 — Set Up Browser Environment

**Open a new page** (Chrome DevTools MCP):
```
mcp__chrome-devtools__new_page
mcp__chrome-devtools__navigate_page → http://localhost:4200  (or staging URL)
```

**Start network monitoring** (before any interaction):
```
mcp__chrome-devtools__list_network_requests  → baseline
mcp__chrome-devtools__list_console_messages  → baseline (should be empty)
```

**Set viewport** (for responsive testing):
```
mcp__chrome-devtools__resize_page → 1440x900 (desktop)
mcp__chrome-devtools__resize_page → 390x844  (mobile)
```

---

### Phase 3 — Execute User Journeys (Browser-Use MCP)

**Example: Login flow**

```
Step 1 — Navigate to login
  mcp__browser-use__navigate → /login

Step 2 — Fill credentials
  mcp__browser-use__fill → [email field] → test@example.com
  mcp__browser-use__fill → [password field] → TestPassword123!

Step 3 — Submit
  mcp__browser-use__click → [Login button]

Step 4 — Verify redirect
  mcp__browser-use__wait_for → URL contains /dashboard
```

**Example: Form submission flow**

```
Step 1 — Navigate to feature
  mcp__browser-use__navigate → /orders/new

Step 2 — Fill form
  mcp__browser-use__fill_form → {
    itemId: "item-1",
    quantity: "2",
    notes: "Test order"
  }

Step 3 — Submit
  mcp__browser-use__click → [Submit button]

Step 4 — Wait for confirmation
  mcp__browser-use__wait_for → [confirmation message visible]
```

---

### Phase 4 — Inspect and Assert (Chrome DevTools MCP)

After each user action, verify the technical behavior:

**Network assertions**:
```
mcp__chrome-devtools__list_network_requests
→ Expect: POST /api/orders → 201 Created
→ Expect: No 4xx or 5xx responses
→ Expect: Response time < 2000ms
```

**Console assertions**:
```
mcp__chrome-devtools__list_console_messages
→ Expect: No ERROR level messages
→ Expect: No unhandled promise rejections
```

**DOM assertions**:
```
mcp__chrome-devtools__take_snapshot
→ Inspect element presence and content
```

**Screenshot evidence**:
```
mcp__chrome-devtools__take_screenshot → login-success.png
mcp__chrome-devtools__take_screenshot → order-confirmation.png
```

---

### Phase 5 — Error Path Testing

Test what happens when things go wrong:

**Invalid inputs**:
```
Fill form with invalid data → submit → expect validation message
→ mcp__chrome-devtools__take_snapshot → verify error displayed
→ mcp__chrome-devtools__list_network_requests → verify NO API call made
```

**Server error handling**:
```
# Use Chrome DevTools to simulate network failure
mcp__chrome-devtools__evaluate_script →
  "fetch = () => Promise.reject(new Error('Network error'))"
→ Trigger form submit
→ Expect user-visible error message (not silent failure)
→ mcp__chrome-devtools__take_screenshot → error-state.png
```

**Empty states**:
```
Navigate to empty list → verify empty state message displayed
→ Not a blank page, not an error — intentional empty state UI
```

---

### Phase 6 — Performance Snapshot

For critical paths, capture performance baseline:

```
mcp__chrome-devtools__performance_start_trace
→ Execute critical user action (page load, form submit, search)
mcp__chrome-devtools__performance_stop_trace
mcp__chrome-devtools__performance_analyze_insight
→ Expected: LCP < 2.5s, INP < 200ms, CLS < 0.1
```

**Lighthouse audit** (for page-level quality):
```
mcp__chrome-devtools__lighthouse_audit → /dashboard
→ Performance score >= 80
→ Accessibility score >= 90
→ Best Practices score >= 90
```

---

### Phase 7 — Flutter Mobile E2E (Maestro)

For Flutter, E2E uses Maestro CLI (from `flutter-mobile` skill), not Chrome DevTools:

```yaml
# .maestro/login_flow.yaml
appId: com.example.app
---
- launchApp
- tapOn: "Email"
- inputText: "test@example.com"
- tapOn: "Password"
- inputText: "TestPassword123!"
- tapOn: "Login"
- assertVisible: "Dashboard"
```

**Run**:
```bash
maestro test .maestro/login_flow.yaml
maestro test .maestro/  # Run all flows
```

**Dart MCP alternative** (for running app inspection):
```
mcp__dart-mcp-server__get_widget_tree       → inspect current widget tree
mcp__dart-mcp-server__get_runtime_errors    → check for runtime errors
mcp__dart-mcp-server__get_app_logs          → inspect logs during test
```

---

## Quick Reference

| Phase | Tool | Action | Gate |
|-------|------|--------|------|
| 1 — Identify | Manual | List critical paths | Happy path + 2 error paths per journey |
| 2 — Setup | Chrome DevTools MCP | Open page, start monitoring | Page loads, no baseline errors |
| 3 — Execute | Browser-Use MCP | Drive user journey | Each step completes without JS error |
| 4 — Inspect | Chrome DevTools MCP | Assert network + console | No 4xx/5xx, no console errors |
| 5 — Error paths | Both MCPs | Test failure scenarios | Errors shown to user, no silent failures |
| 6 — Performance | Chrome DevTools MCP | Lighthouse + trace | LCP < 2.5s, score >= 80 |
| 7 — Mobile | Maestro | Flutter E2E | All flows pass |

---

## Common Pitfalls

- **Testing only happy paths** — error states are where users actually get stuck
- **No network inspection** — a "successful" UI action can mask a 500 from the server
- **Screenshot without assertion** — screenshots are evidence, not assertions; explicitly check what happened
- **Flaky tests from timing** — use `wait_for` to wait for specific conditions, not `sleep`
- **Wrong viewport** — test at mobile AND desktop; layout bugs are viewport-specific
- **Missing baseline** — capture network/console state before interaction to diff against after

## Related Workflows

- [`test-driven-development.md`](test-driven-development.md) — unit and integration test layer below E2E
- [`api-testing.md`](api-testing.md) — API contract and integration testing
- [`feature-flutter-mobile.md`](feature-flutter-mobile.md) — Maestro E2E for Flutter
- [`feature-angular-spa.md`](feature-angular-spa.md) — Angular E2E context
