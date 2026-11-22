# Browser Testing — Combined Workflow Patterns

## Tool Strategy

The most effective testing approach uses **both tools together**:

1. **playwright-cli** (Bash) — scripted steps, network/console inspection, screenshots, tracing
2. **Browser-Use MCP** — autonomous interaction when describing a goal is better than scripting steps

---

## Pattern 1: Login Flow with Full Debugging

**Goal:** Test login while monitoring network requests and console errors.

### Step 1: Navigate and take baseline

```bash
playwright-cli -s=login goto http://localhost:4200/login
playwright-cli -s=login console        # baseline: should be empty
playwright-cli -s=login network        # baseline: no requests yet
playwright-cli -s=login snapshot       # get element refs
```

### Step 2: Fill and submit (scripted)

```bash
# Use refs from snapshot output
playwright-cli -s=login fill [input-email-1] "test@example.com"
playwright-cli -s=login fill [input-password-2] "password123"
playwright-cli -s=login click [button-submit-3]
```

*Alternative: use Browser-Use for autonomous interaction*

```
browser_navigate({ url: "http://localhost:4200/login" })
browser_get_state({ include_screenshot: false })
browser_input({ index: 4, text: "test@example.com" })
browser_input({ index: 5, text: "password123" })
browser_click({ index: 6 })
```

### Step 3: Verify result

```bash
playwright-cli -s=login console error         # any errors after submit?
playwright-cli -s=login network               # POST /api/auth/login → 200?
playwright-cli -s=login eval "localStorage.getItem('authToken')"
playwright-cli -s=login screenshot --output login-success.png
```

### Expected Output

**User Perspective:**
- ✅ Form fields filled successfully
- ✅ Submit clicked, redirected to /dashboard

**Technical Perspective:**
- ✅ POST /api/auth/login → 200 OK
- ✅ No console errors
- ✅ Auth token in localStorage

---

## Pattern 2: Performance Testing

**Goal:** Measure page load performance and identify bottlenecks.

### Core Web Vitals — Pass/Fail Thresholds

Use `mcp__chrome-devtools__performance_analyze_insight` to measure each metric, then compare:

| Metric | Tool insight name | Pass | Warn | Fail |
|--------|------------------|------|------|------|
| LCP (Largest Contentful Paint) | `LCPBreakdown` | < 2.5s | 2.5–4s | > 4s |
| CLS (Cumulative Layout Shift) | `CumulativeLayoutShift` | < 0.1 | 0.1–0.25 | > 0.25 |
| INP (Interaction to Next Paint) | `InteractionToNextPaint` | < 200ms | 200–500ms | > 500ms |
| FCP (First Contentful Paint) | `LCPBreakdown` | < 1.8s | 1.8–3s | > 3s |
| TBT (Total Blocking Time) | `TotalBlockingTime` | < 200ms | 200–600ms | > 600ms |
| TTFB (Time to First Byte) | `playwright-cli network` | < 800ms | 800ms–1.8s | > 1.8s |

**How to check TTFB:** After `playwright-cli network`, look at the first HTML document request — the `timing.responseStart - timing.requestStart` value.

### Step 1: Start trace and navigate

```bash
playwright-cli -s=perf goto http://localhost:4200
playwright-cli -s=perf tracing-start
# wait for page to stabilise
playwright-cli -s=perf network        # check what loaded and how long
playwright-cli -s=perf tracing-stop --output baseline-trace.zip
```

### Step 2: Test under slow conditions

```bash
# Simulate mobile viewport
playwright-cli -s=perf resize 375 812

# Reload to capture slow-network behaviour (hard refresh)
playwright-cli -s=perf goto http://localhost:4200
playwright-cli -s=perf tracing-start
playwright-cli -s=perf network
playwright-cli -s=perf tracing-stop --output mobile-trace.zip
```

### Step 3: Inspect traces

```bash
npx playwright show-trace baseline-trace.zip
npx playwright show-trace mobile-trace.zip
```

Look for:
- Long network waterfall entries → optimize assets, add CDN
- Render-blocking scripts → defer non-critical JS/CSS
- Large images → compress, use WebP

---

## Pattern 3: E2E User Flow Testing

**Goal:** Test complete user journey: signup → email verification → dashboard.

### Step 1: Signup

```bash
playwright-cli -s=e2e goto http://localhost:4200/signup
playwright-cli -s=e2e snapshot        # get refs
playwright-cli -s=e2e fill [input-email] "newuser@example.com"
playwright-cli -s=e2e fill [input-password] "SecurePass123!"
playwright-cli -s=e2e fill [input-confirm] "SecurePass123!"
playwright-cli -s=e2e click [button-submit]
```

### Step 2: Validate API response

```bash
playwright-cli -s=e2e network
# Expected: POST /api/auth/signup → 201 Created
playwright-cli -s=e2e console error
# Expected: no errors
```

### Step 3: Navigate to email verification link

```bash
# Extract token from network response, then navigate directly
playwright-cli -s=e2e goto "http://localhost:4200/verify?token=abc123xyz"
```

### Step 4: Verify completion

```bash
playwright-cli -s=e2e snapshot        # should show /dashboard
playwright-cli -s=e2e eval "localStorage.getItem('authToken')"
playwright-cli -s=e2e screenshot --output dashboard.png
```

### Verification Checklist

- ✅ Signup API returned 201
- ✅ No console errors during flow
- ✅ Verification token navigated to /dashboard
- ✅ Auth token stored in localStorage
- ✅ Authenticated UI visible

---

## Pattern 4: Form Validation Testing

**Goal:** Test client-side and server-side validation feedback.

### Step 1: Submit empty form

```bash
playwright-cli -s=form goto http://localhost:4200/contact
playwright-cli -s=form snapshot
playwright-cli -s=form click [button-submit]    # submit without filling
playwright-cli -s=form snapshot                 # re-snapshot: should show validation errors
playwright-cli -s=form console
# Expected: no JS errors — validation should work without errors
```

### Step 2: Fill with invalid data

```bash
playwright-cli -s=form fill [input-email] "not-an-email"
playwright-cli -s=form fill [input-message] "Hi"          # too short
playwright-cli -s=form click [button-submit]
playwright-cli -s=form snapshot
# Expected: "Invalid email" and "Message too short" errors
```

### Step 3: Submit valid data

```bash
playwright-cli -s=form fill [input-email] "user@example.com"
playwright-cli -s=form fill [input-message] "Hello, I need help with billing."
playwright-cli -s=form click [button-submit]
playwright-cli -s=form network
# Expected: POST /api/contact → 200 OK
playwright-cli -s=form snapshot
# Expected: "Thank you!" success message
```

---

## Pattern 5: Accessibility Testing

**Goal:** Verify page is accessible to screen readers and keyboard navigation.

### Step 1: Get accessibility tree

```bash
playwright-cli -s=a11y goto http://localhost:4200/login
playwright-cli -s=a11y snapshot
# Examine output for:
# - Proper heading hierarchy (h1, h2, h3)
# - Form labels associated with inputs
# - Descriptive button text
# - Image alt text
```

### Step 2: Test keyboard navigation

```bash
playwright-cli -s=a11y press Tab          # move focus to first element
playwright-cli -s=a11y press Tab          # next element
playwright-cli -s=a11y press Tab          # next element
playwright-cli -s=a11y snapshot           # check which element has focus
playwright-cli -s=a11y press Enter        # activate focused element
```

### Step 3: Verify ARIA attributes via eval

```bash
playwright-cli -s=a11y eval "
  const input = document.querySelector('input[type=email]');
  JSON.stringify({
    hasLabel: !!input.labels?.length,
    ariaRequired: input.getAttribute('aria-required'),
    ariaInvalid: input.getAttribute('aria-invalid')
  })
"
# Expected: all fields have proper labels and ARIA attributes
```

---

## Pattern 6: Multi-Device Testing

**Goal:** Test responsive design across mobile, tablet, and desktop.

```bash
# Mobile — iPhone 14
playwright-cli -s=responsive resize 375 812
playwright-cli -s=responsive goto http://localhost:4200
playwright-cli -s=responsive screenshot --output mobile.png
playwright-cli -s=responsive snapshot    # verify hamburger menu present

# Tablet — iPad
playwright-cli -s=responsive resize 768 1024
playwright-cli -s=responsive reload
playwright-cli -s=responsive screenshot --output tablet.png

# Desktop
playwright-cli -s=responsive resize 1280 720
playwright-cli -s=responsive reload
playwright-cli -s=responsive screenshot --output desktop.png
```

Review screenshots to verify:
- ✅ Mobile: Hamburger menu, single-column layout
- ✅ Tablet: Collapsed sidebar, 2-column layout
- ✅ Desktop: Full navigation, 3-column layout

---

## Pattern 7: Error Monitoring During User Flow

**Goal:** Catch JS errors, failed API calls, and warnings during critical flows.

```bash
# Clear state and start fresh
playwright-cli -s=monitor goto http://localhost:4200/checkout
playwright-cli -s=monitor console        # baseline (should be empty)
playwright-cli -s=monitor network        # baseline

# Perform payment flow
playwright-cli -s=monitor snapshot
playwright-cli -s=monitor fill [input-card] "4242424242424242"
playwright-cli -s=monitor fill [input-expiry] "12/25"
playwright-cli -s=monitor fill [input-cvv] "123"
playwright-cli -s=monitor console error  # check after fill — no errors expected
playwright-cli -s=monitor click [button-pay]

# Check after submit
playwright-cli -s=monitor console error  # any JS errors?
playwright-cli -s=monitor network        # POST /api/payments → 200?
playwright-cli -s=monitor screenshot --output payment-result.png
```

If errors found, capture detail:
```bash
playwright-cli -s=monitor eval "window.__lastError || null"
playwright-cli -s=monitor screenshot --output payment-error.png
```

---

## Flutter Web Testing Notes

> Applies only to the Flutter **web** build. It never validates the Android/iOS app; that uses Maestro (`.claude/rules/testing-tool-selection.md`).

### DDC Bootstrap (Development Mode)

Flutter web in DDC mode does NOT auto-start. You must trigger it:

```bash
playwright-cli -s=flutter goto http://localhost:8080
# Wait for DDC to load (network idle), then bootstrap
playwright-cli -s=flutter eval "
  if (typeof window.\$dartRunMain === 'function') {
    window.\$dartRunMain();
    'bootstrapped';
  } else {
    'dartRunMain not available yet';
  }
"
# Wait ~6 seconds for Flutter to render
playwright-cli -s=flutter screenshot --output flutter-app.png
```

### Pixel-Coordinate Interaction

Flutter web renders to a canvas — there are no HTML form elements. All interaction is via coordinates:

```bash
playwright-cli -s=flutter screenshot --output flutter-screen.png
# Inspect screenshot to find button coordinates
playwright-cli -s=flutter mousemove 200 400   # move to button center
playwright-cli -s=flutter mousedown
playwright-cli -s=flutter mouseup
playwright-cli -s=flutter type "input text here"
```

To clear text fields (triple-click does not exist):
```bash
playwright-cli -s=flutter press "Control+a"
playwright-cli -s=flutter press Backspace
```

---

## Best Practices Summary

1. **Always run `snapshot` before interact** — refs change between renders, never hard-code them
2. **Check `console error` and `network` after every critical action** — form submit, navigation, API call
3. **Use named sessions** (`-s=<name>`) for multi-step flows — keeps browser open between commands
4. **Never use `browser_get_state({ include_screenshot: true })`** — 126K+ token overflow
5. **Use `playwright-cli screenshot` for visual evidence** — required for APPROVED verdicts
6. **Always close sessions** — `playwright-cli close-all` when done
7. **Save auth state** for flows requiring login: `playwright-cli state-save ./auth.json` after login, `state-load` to restore

## Workflow Decision Tree

```
Need to test a feature?
  │
  ├─ Know the exact steps? → playwright-cli (scripted)
  │
  ├─ Need network/console inspection? → playwright-cli
  │
  ├─ Just describe a goal? → Browser-Use MCP
  │
  └─ Need both inspection + interaction?
     → playwright-cli monitors, Browser-Use acts
```

---

## Pattern 8: Pre-Ship Browser QA

**When:** Before merging any PR that touches Angular frontend code. Run against staging URL.

**Tools:** playwright-cli + mcp__chrome-devtools__* + (optionally) mcp__chrome-devtools__lighthouse_audit

### Phase 1 — Smoke Test

```bash
playwright-cli -s=qa goto $STAGING_URL
playwright-cli -s=qa console error          # Must be 0 critical errors
playwright-cli -s=qa network                # All requests must be 200/304, no 4xx/5xx
playwright-cli -s=qa screenshot --output smoke-desktop.png
playwright-cli -s=qa resize 375 812
playwright-cli -s=qa screenshot --output smoke-mobile.png
```

### Phase 2 — Interaction Test

```bash
# Nav links — click each and verify no dead links
playwright-cli -s=qa snapshot               # Get all nav link refs
playwright-cli -s=qa click [nav-link-ref]
playwright-cli -s=qa console error          # Check for errors after each nav

# Form: valid submission
playwright-cli -s=qa fill [email-ref] "test@example.com"
playwright-cli -s=qa click [submit-ref]
playwright-cli -s=qa network               # Verify POST → 200/201

# Form: invalid submission
playwright-cli -s=qa fill [email-ref] "notanemail"
playwright-cli -s=qa click [submit-ref]
playwright-cli -s=qa snapshot              # Verify error state is visible
```

### Phase 3 — Core Web Vitals

```bash
# Using Chrome DevTools MCP
mcp__chrome-devtools__navigate_page url=$STAGING_URL
mcp__chrome-devtools__performance_start_trace
# (wait 3 seconds for page activity)
mcp__chrome-devtools__performance_stop_trace outputPath=qa-trace.json
mcp__chrome-devtools__performance_analyze_insight insight=LCPBreakdown
mcp__chrome-devtools__performance_analyze_insight insight=CumulativeLayoutShift
mcp__chrome-devtools__performance_analyze_insight insight=InteractionToNextPaint
mcp__chrome-devtools__performance_analyze_insight insight=TotalBlockingTime
```

Compare results against the thresholds in the CWV table above.

### Phase 4 — Accessibility Snapshot

```bash
playwright-cli -s=qa snapshot              # Check heading hierarchy (h1→h2→h3)
playwright-cli -s=qa eval "document.querySelectorAll('img:not([alt])').length"
# Must be 0 — all images need alt text
playwright-cli -s=qa eval "document.querySelectorAll('button:not([aria-label]):not(:has(span[class*=label]))').length"
playwright-cli -s=qa press Tab             # Tab through interactive elements — all must be reachable
```

### Phase 5 — Multi-Breakpoint Screenshots

```bash
playwright-cli -s=qa resize 375 812        # Mobile
playwright-cli -s=qa screenshot --output qa-375.png
playwright-cli -s=qa resize 768 1024       # Tablet
playwright-cli -s=qa screenshot --output qa-768.png
playwright-cli -s=qa resize 1440 900       # Desktop
playwright-cli -s=qa screenshot --output qa-1440.png
```

### QA Report Output Template

After completing all phases, output this report:

```markdown
## Browser QA Report — [URL] — [timestamp]

### Phase 1: Smoke Test
- Console errors: [N] critical, [N] warnings
- Network: [all 200/304] OR [list failures]
- Screenshots: smoke-desktop.png, smoke-mobile.png

### Phase 2: Interactions
- [ ] Nav links: [N/N] working
- [ ] Form valid submit: [200/201 ✓ or ✗ describe issue]
- [ ] Form invalid submit: [error state visible ✓ or ✗]
- [ ] Auth flow: [working ✓ or ✗]

### Phase 3: Core Web Vitals
- LCP: [value] [✓ PASS / ⚠ WARN / ✗ FAIL] (target < 2.5s)
- CLS: [value] [✓ / ⚠ / ✗] (target < 0.1)
- INP: [value] [✓ / ⚠ / ✗] (target < 200ms)
- TBT: [value] [✓ / ⚠ / ✗] (target < 200ms)

### Phase 4: Accessibility
- Images without alt: [N] (must be 0)
- Keyboard navigation: [all elements reachable ✓ or list issues]
- Heading hierarchy: [valid ✓ or describe issue]

### Phase 5: Visual
- Mobile (375px): qa-375.png — [no overflow ✓ or describe issue]
- Tablet (768px): qa-768.png — [no overflow ✓ or describe issue]
- Desktop (1440px): qa-1440.png — [no overflow ✓ or describe issue]

### Verdict: [SHIP ✅ | SHIP WITH FIXES ⚠️ | DO NOT SHIP ❌]
- Blockers (DO NOT SHIP): [list or "none"]
- Issues to fix: [list or "none"]
```

### Cleanup

```bash
playwright-cli close-all
```
