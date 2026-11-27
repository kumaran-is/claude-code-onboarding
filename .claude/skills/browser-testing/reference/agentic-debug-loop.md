# Agentic Debug Loop

The pattern for using live browser runtime data — console errors, network responses, actual error codes — to drive diagnosis and verify fixes, rather than guessing from static source alone.

## Core Principle

Static code analysis guesses at runtime behavior. The agentic debug loop observes actual runtime behavior first, then reads source only to understand what it saw. The sequence is always: **observe → diagnose → fix → re-verify in browser.** Never guess from code alone when you can run the flow and read the real error. After diagnosing a Playwright **test** defect (stale locator, timing), dispatch the product `playwright-test-healer` if it exists (`playwright-test-agents.md`); an application bug is a production-code fix, never `test.fixme` / skip / a weaker `expect()`.

## When to Use

- A reported bug cannot be reproduced from reading source code
- An error code or message appears in the UI but its cause is not obvious from the code
- A form, auth flow, or API call fails in a way that needs network + console evidence
- You fixed a bug and need to confirm the fix works in the real browser, not just in tests
- An AI agent is tasked with "debug and fix X" on a running web app

## The Four-Phase Loop

### Phase 1 — Observe (get runtime evidence)

Do not read source first. Load the page and reproduce the failure.

```bash
# 1a. Navigate to the failing flow
playwright-cli -s=debug open http://localhost:4200/signup

# 1b. Snapshot to get element refs
playwright-cli -s=debug snapshot

# 1c. Trigger the failing action (form submit, button click, navigation)
playwright-cli -s=debug fill [email-ref] "test@example.com"
playwright-cli -s=debug fill [password-ref] "1234"
playwright-cli -s=debug click [submit-ref]

# 1d. Capture runtime evidence immediately after
playwright-cli -s=debug console          # All console output
playwright-cli -s=debug console error    # Errors only
playwright-cli -s=debug requests          # All network requests + status codes
playwright-cli -s=debug screenshot --filename before-fix.png
```

**What to capture and why:**

| Signal | Tool | What It Tells You |
|--------|------|-------------------|
| Console errors | `playwright-cli console error` | JavaScript exceptions, unhandled rejections, framework errors |
| Console logs | `playwright-cli console` | App-level logging, state at failure point |
| Network requests | `playwright-cli requests`, then `request <n>` | API responses, status codes, request payloads, error bodies |
| Page state | `playwright-cli snapshot` | What the DOM actually shows vs. what you expect |
| Screenshot | `playwright-cli screenshot` | Visual proof of failure state |

**Rule:** Do not proceed to Phase 2 until you have at least one console output AND one network capture. Evidence before diagnosis.

### Phase 2 — Diagnose (root cause from evidence)

Read the runtime evidence. Then — and only then — read source to understand why.

**Evidence → hypothesis mapping:**

| Runtime Evidence | Likely Root Cause | Where to Look in Source |
|-----------------|-------------------|------------------------|
| HTTP 4xx from API | Client sending invalid data | Request construction, validation logic |
| HTTP 5xx from API | Server-side error | Backend logs, server error handler |
| Cryptic error code in UI (e.g. `APP_ERR_1003`) | Missing error message mapping | Error handler, i18n/message map |
| Console: uncaught TypeError | Null/undefined access | The function named in the stack trace |
| Console: CORS error | Missing header or wrong origin config | Server CORS config, proxy config |
| Network request never fires | Event handler not wired up | Component event binding |
| Network fires but UI doesn't update | State not propagating | State management layer |
| 200 response but UI shows error | Response parsing or mapping bug | Response handler |

**Read source only after evidence points to a specific location:**

```bash
# Read only the file the evidence points to — not the whole codebase
# Example: network showed 422 from /api/auth/register
# → read the registration validation logic
```

Apply [Five Whys](../../systematic-debugging/SKILL.md) to chain from symptom to root cause if the first read does not make the cause obvious.

**Diagnosis output (write this before touching code):**

```
Evidence:
- Console: [exact error message]
- Network: [endpoint] → [status] → [response body]

Root cause: [specific line/function/condition causing the failure]

Issues found (rank by impact):
1. [Primary issue — what breaks the flow]
2. [Secondary issue — what degrades UX even if flow works]
```

### Phase 3 — Fix (minimal, targeted)

Fix exactly what the diagnosis identified. One issue at a time.

**Rules:**
- Fix the root cause, not the symptom (see `systematic-debugging` Iron Law)
- Smallest change that addresses the issue — no opportunistic refactoring
- If two issues were found, fix the blocking one first, verify, then fix the secondary
- Write or update a test that would have caught this before touching the fix

**Common fix patterns from agentic debug sessions:**

| Root Cause | Fix Pattern |
|-----------|-------------|
| API requires longer input than client validates | Add client-side validation matching API contract |
| Cryptic error code shown to user | Map error codes to user-friendly messages in error handler |
| Missing null check before render | Guard with conditional or default value |
| Wrong HTTP method or endpoint | Fix request construction |
| Response field name mismatch | Fix response mapping (camelCase vs snake_case) |
| Missing await on async call | Add await, update caller signature if needed |

### Phase 4 — Re-Verify (close the loop in the browser)

Run the same flow that failed in Phase 1. Do not claim fixed until the browser confirms it.

```bash
# Re-run the exact same failing flow
playwright-cli -s=debug goto http://localhost:4200/signup
playwright-cli -s=debug snapshot
playwright-cli -s=debug fill [email-ref] "test@example.com"
playwright-cli -s=debug fill [password-ref] "1234"          # Same bad input — should now show helpful error
playwright-cli -s=debug click [submit-ref]
playwright-cli -s=debug console error                        # Should be clean
playwright-cli -s=debug screenshot --filename after-fix-bad-input.png

# Then verify the happy path works too
playwright-cli -s=debug fill [password-ref] "Password123!"  # Valid input
playwright-cli -s=debug click [submit-ref]
playwright-cli -s=debug requests                              # Should show 200/201
playwright-cli -s=debug screenshot --filename after-fix-success.png
```

**Re-verify checklist:**
- [ ] The original failing case now produces a helpful error (not a broken state)
- [ ] The happy path succeeds end-to-end
- [ ] No new console errors introduced by the fix
- [ ] Network calls complete with expected status codes
- [ ] Screenshots captured as proof for both cases

**Done only when:** Re-verify passes. "The fix looks right in code" is not done.

## Chrome DevTools MCP — When to Add It

playwright-cli covers most agentic debug loops. Add Chrome DevTools MCP when you need deeper runtime introspection:

| Need | Chrome DevTools MCP Tool |
|------|--------------------------|
| Monitor console in real time | `mcp__chrome-devtools__get_console_message` |
| Inspect specific network request body | `mcp__chrome-devtools__get_network_request` |
| Execute JS in page context | `mcp__chrome-devtools__evaluate_script` |
| Measure performance (LCP, CLS) | `mcp__chrome-devtools__lighthouse_audit` |
| Inspect specific DOM element | `mcp__chrome-devtools__take_snapshot` |

See `reference/chrome-devtools-tools.md` for full Chrome DevTools MCP reference.

## Full Loop Example: Signup Bug

```
Bug report: "Registration fails with APP_ERR_1003 when submitting signup form"

Phase 1 — Observe:
  playwright-cli goto localhost:4321/signup
  playwright-cli fill [password] "1234"
  playwright-cli click [submit]
  playwright-cli console error
  → "Registration failed: APP_ERR_1003"
  playwright-cli requests
  → POST /api/auth/register → 422 {"code":"APP_ERR_1003","message":"Password minimum 8 characters"}

Phase 2 — Diagnose:
  Evidence: API returns 422 with APP_ERR_1003 = password too short
  Root cause 1: No client-side password length validation — invalid input reaches API
  Root cause 2: Error handler maps APP_ERR_1003 to raw code string, not user message

Phase 3 — Fix:
  1. Add minLength=8 validation to password field (blocks short passwords before API call)
  2. Add APP_ERR_1003 → "Password must be at least 8 characters" to error message map

Phase 4 — Re-Verify:
  playwright-cli fill [password] "1234" → click submit
  → UI shows "Password must be at least 8 characters" (no API call made)
  playwright-cli fill [password] "Password123!" → click submit
  → network: POST /api/auth/register → 201
  → UI shows "User registered successfully!"
  playwright-cli console error → clean
  playwright-cli screenshot → saved as proof
```

## Cleanup

```bash
playwright-cli close-all
```

Always close sessions when the debug loop is complete.

## Related

> For root cause methodology: `systematic-debugging` skill — Five Whys, hypothesis ranking, 3-attempt stop.
> For Chrome DevTools MCP deep reference: `reference/chrome-devtools-tools.md`.
> For full playwright-cli command reference: `reference/playwright-cli-tools.md`.
