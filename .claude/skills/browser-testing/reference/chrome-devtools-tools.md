# Chrome DevTools MCP — Tool Reference

## When to Use Chrome DevTools MCP

Use chrome-devtools when the task involves looking under the hood:

- Performance tracing and Core Web Vitals (LCP, CLS, TBT)
- Console error monitoring
- Network request inspection
- JavaScript execution in page context
- DOM and CSS debugging
- CPU/Network throttling
- Connecting to user's running Chrome session (`--autoConnect`)

## Navigation & Page Control

### navigate_page
Navigate to a URL, go back/forward, or reload.

```typescript
navigate_page({
  type: "url",
  url: "https://example.com"
})

navigate_page({ type: "back" })
navigate_page({ type: "forward" })
navigate_page({ type: "reload", ignoreCache: true })
```

**Parameters:**
- `type`: "url", "back", "forward", or "reload"
- `url`: Target URL (required when type="url")
- `ignoreCache`: Clear cache on reload (optional)
- `timeout`: Max wait time in ms (optional)

### new_page
Create a new browser page/tab.

```typescript
new_page({
  url: "https://example.com",
  background: false  // false = bring to front
})
```

### list_pages
Get all open pages with their URLs and titles.

### select_page
Switch focus to a specific page by ID.

### close_page
Close a page by its ID (cannot close the last page).

## Inspection & Debugging

### take_snapshot
Get accessibility tree snapshot of the page with unique IDs (uid) for elements.

```typescript
take_snapshot({
  verbose: false  // true = include full a11y tree details
})
```

**Returns:** Text-based page structure with `uid=X_Y` identifiers for each element.

**Use this instead of screenshots when possible** — more efficient, no token overflow.

### take_screenshot
Capture visual screenshot of page or specific element.

```typescript
take_screenshot({
  fullPage: true,      // true = entire page, false = viewport only
  format: "png",       // "png", "jpeg", "webp"
  quality: 90,         // JPEG/WebP quality (0-100)
  filePath: "./out.png"  // Save to file instead of response
})
```

**Tip:** save large screenshots with `filePath` instead of returning them inline.

### list_console_messages
Get all console output (errors, warnings, logs, etc.) since last navigation.

```typescript
list_console_messages({
  types: ["error", "warn"],  // Filter by type (optional)
  pageSize: 50,              // Limit results (optional)
  pageIdx: 0,                // Page number for pagination (optional)
  includePreservedMessages: false  // Include last 3 navigations
})
```

**Message types:** log, debug, info, error, warn, dir, dirxml, table, trace, clear, startGroup, startGroupCollapsed, endGroup, assert, profile, profileEnd, count, timeEnd, verbose, issue

### get_console_message
Get detailed console message by ID.

```typescript
get_console_message({ msgid: 1 })
```

### list_network_requests
Get all network requests since last navigation.

```typescript
list_network_requests({
  resourceTypes: ["xhr", "fetch", "document"],  // Filter by type
  pageSize: 100,
  pageIdx: 0,
  includePreservedRequests: false  // Include last 3 navigations
})
```

**Resource types:** document, stylesheet, image, media, font, script, texttrack, xhr, fetch, prefetch, eventsource, websocket, manifest, signedexchange, ping, cspviolationreport, preflight, fedcm, other

### get_network_request
Get detailed network request/response by ID.

```typescript
get_network_request({
  reqid: 1,
  requestFilePath: "./request.json",   // Save request body
  responseFilePath: "./response.json"  // Save response body
})
```

**Returns:** Full request/response headers, body, status, timing.

## Interaction

### click
Click an element by its uid from snapshot.

```typescript
click({
  uid: "1_5",
  includeSnapshot: true  // Return updated snapshot
})
```

### fill
Type into input/textarea or select dropdown option.

```typescript
fill({
  uid: "1_6",
  value: "text to type",
  includeSnapshot: false
})
```

### fill_form
Fill multiple form fields at once.

```typescript
fill_form({
  elements: [
    { uid: "1_6", value: "username" },
    { uid: "1_8", value: "password123" }
  ],
  includeSnapshot: true
})
```

### hover
Trigger hover effects on an element.

```typescript
hover({ uid: "1_10" })
```

### press_key
Send keyboard input or shortcuts.

```typescript
press_key({ key: "Enter" })
press_key({ key: "Control+A" })
press_key({ key: "Control+Shift+R" })
```

**Modifiers:** Control, Shift, Alt, Meta

### drag
Drag from one element to another.

```typescript
drag({
  fromUid: "1_5",
  toUid: "1_10"
})
```

### upload_file
Upload file(s) to a file input.

```typescript
upload_file({
  uid: "1_12",
  filePaths: ["/absolute/path/to/file.pdf"]
})
```

## JavaScript Execution

### evaluate_script
Execute JavaScript in the page context. Parameters (from the server's tool schema): `pageId` (required), `function` (JS source, e.g. `() => document.title`) or `sourcePath`, optional `args` (element uids), `format` (`function` default, or `script`), `filePath`.

```typescript
evaluate_script({ pageId: 2, function: "() => document.title" })
evaluate_script({ pageId: 2, function: "(el) => el.innerText", args: ["<uid from take_snapshot>"] })
```

**Use cases:** query DOM state, read computed values, `performance.getEntriesByType('navigation')`. Do not use it to "prove" sign-in by reading a token from `localStorage`: prove sign-in by the protected page and the API status. A token readable by page script is an XSS exfiltration target.

## Performance Analysis

### performance_start_trace
Navigate first (`new_page` / `navigate_page`), then start. With `reload: true` and `autoStop: true` (defaults) it reloads, records the load and returns the summary.

```typescript
performance_start_trace({ pageId: 2, reload: true, autoStop: true, ignoreCache: true })
```

The result lists LCP (with TTFB and render-delay subparts), CLS, the **insight set ids** (e.g. `NAVIGATION_0`) and the **insight names available for that trace**.

### performance_stop_trace
Only needed with `autoStop: false` (e.g. to record an interaction for INP).

```typescript
performance_stop_trace({ pageId: 2, filePath: "./trace.json.gz" })
```

### performance_analyze_insight
Drill into one insight of one insight set. Use only names the trace summary listed.

```typescript
performance_analyze_insight({ pageId: 2, insightSetId: "NAVIGATION_0", insightName: "LCPBreakdown" })
```

Insight names observed in a real trace this toolkit ran: `LCPBreakdown`, `CLSCulprits`, `DocumentLatency`, `NetworkDependencyTree`. Others (for example `RenderBlocking`, `INPBreakdown`) appear only when the trace contains them. There is no `CumulativeLayoutShift`, `InteractionToNextPaint` or `TotalBlockingTime` insight name; read those metrics from the trace summary.

## Emulation & Testing

### emulate_cpu
Throttle CPU to simulate slower devices.

```typescript
emulate_cpu({ rate: 4 })  // 4x slowdown
```

### emulate_network
Throttle network to simulate slow connections.

```typescript
emulate_network({ profile: "Slow 3G" })
emulate_network({ profile: "Fast 3G" })
emulate_network({ profile: "Offline" })
```

**Custom throttling:**
```typescript
emulate_network({
  downloadThroughput: 750000,  // bytes/sec
  uploadThroughput: 250000,
  latency: 100  // ms
})
```

### resize_page
Change viewport size.

```typescript
resize_page({
  width: 375,
  height: 667
})
```

**Common sizes:**
- Mobile: 375x667 (iPhone SE)
- Tablet: 768x1024 (iPad)
- Desktop: 1920x1080

### wait_for
Wait for element, navigation, or timeout.

```typescript
wait_for({
  type: "selector",
  selector: "#submit-button"
})

wait_for({
  type: "navigation",
  timeout: 5000
})

wait_for({
  type: "timeout",
  timeout: 2000
})
```

### handle_dialog
Accept or dismiss browser dialogs (alert, confirm, prompt).

```typescript
handle_dialog({
  action: "accept",
  promptText: "optional input for prompt()"
})

handle_dialog({ action: "dismiss" })
```

## Advanced Features

### Connecting to Running Chrome

Use `--autoConnect` to attach to your local Chrome instance with existing logins:

```bash
mcp-server-chrome-devtools --autoConnect
```

**Benefits:**
- Test with real logged-in sessions
- Debug local development servers
- Inspect production sites with cookies/auth

**Limitations:**
- Can only attach to one tab at a time
- Requires Chrome to be running with remote debugging enabled

## Best Practices

1. **Use take_snapshot before interactions** — Get element UIDs before clicking/filling
2. **Monitor console after every action** — Check for JavaScript errors
3. **Check network requests for API failures** — Verify response codes
4. **Take screenshots sparingly** — Use snapshots for structure, screenshots for visuals
5. **Emulate slow conditions for performance testing** — Test on 3G, slow CPU
6. **Use evaluate_script for state inspection** — DOM state and computed values; never treat a stored token as proof of sign-in
7. **Preserve requests across navigations** — Use `includePreservedRequests: true`
8. **Save large responses to files** — Use `responseFilePath` to avoid token overflow
