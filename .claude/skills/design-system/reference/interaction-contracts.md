# Interaction Contracts

Cross-stack behavioral contracts for common UI surfaces. Every surface listed below must follow its contract regardless of framework (Flutter, Angular or React; the "Angular" column is plain HTML and applies to any web stack). Accessibility criteria referenced here are defined in `.claude/skills/accessibility-audit/reference/wcag22-checklist.md`.

---

## 1. Modals / Dialogs

| Requirement | Flutter | Angular |
|-------------|---------|---------|
| Open as modal | `showDialog` | Native `<dialog class="modal">` opened with `dialog.showModal()`. This gives initial focus inside, an inert background, Esc to close and focus return to the opener (verified in Chromium). It is not a strict trap: Tab can leave to the browser chrome, which is allowed. `dialog.show()` is non-modal and leaves the background focusable |
| Background inert while open | `ModalBarrier` (default) | Automatic with `showModal()`. Use `cdkTrapFocus` only for non-native overlays |
| Close on backdrop click | `GestureDetector` on barrier OR `barrierDismissible: true` | `<form method="dialog" class="modal-backdrop"><button>close</button></form>` |
| Close on Escape key | Default in `showDialog` | Default with `showModal()` |
| Announce to screen readers | `semanticsLabel` on dialog | `aria-labelledby` pointing to the dialog title. Do **not** add `role="dialog"` to `<dialog>`; set `aria-modal` only on non-native overlays |
| Return focus to trigger on close | Automatic in Flutter `Navigator.pop` | Automatic with `showModal()`/`close()`. Hand-rolled restore only for non-native overlays. Test: Tab, Shift+Tab, Esc, then assert `document.activeElement` is the opener |
| Max width constraint | `ConstrainedBox(maxWidth: 480)` | `max-w-lg` or `max-w-xl` on dialog box |
| Scroll internal content, not the dialog shell | `SingleChildScrollView` inside dialog body | `overflow-y-auto` on body div, not on dialog element |

**NEVER:**
- Open a modal from inside another modal (use navigation or inline expansion instead)
- Use a modal for content that requires comparison with the page behind it (use a slide-over or inline panel)

---

## 2. Forms

| Requirement | Flutter | Angular |
|-------------|---------|---------|
| Every input has a visible label (a placeholder is not a label) | `InputDecoration(labelText:)` | daisyUI 5: `<fieldset class="fieldset"><label class="label" for="email">Email</label><input id="email" class="input" …>` (`form-control` and `label-text` are daisyUI 4 and emit no CSS in v5) |
| Validation errors show inline below the field | `InputDecoration(errorText:)` | `<p id="email-err">` in body text colour with an "Error:" prefix (daisyUI 5 light `text-error` on `base-100` is 2.87:1, an AA failure), linked with `aria-describedby="email-err"` and `[attr.aria-invalid]="invalid"` on the input |
| Error summary on submit | Scroll to and focus the first invalid field | Summary linking to each field; move focus to the summary or the first invalid field |
| Do not re-ask for data (WCAG 3.3.7) | Pre-fill from earlier steps | Pre-fill, or offer "same as billing" |
| Allow paste and password managers (WCAG 3.3.8) | `autofillHints` | `autocomplete="username"`, `"current-password"`, `"one-time-code"`; never block `paste` |
| Submit button shows loading state during async | `ElevatedButton` with `CircularProgressIndicator` swap | `<button class="btn btn-primary" [disabled]="loading()"><span class="loading loading-spinner" aria-hidden="true"></span>Save</button>` (v5: the spinner is a child span, not a `loading` class on the button) |
| Disable submit when form is invalid | `onPressed: formValid ? submit : null` | `[disabled]="form.invalid"` |
| Show success feedback after submit | `SnackBar` or inline success message | daisyUI `alert alert-success` or toast |
| Show error feedback on submit failure | `SnackBar` with error + retry option | daisyUI `alert alert-error` with retry action |
| Preserve form state on validation error | Never clear fields on failed submit | Never reset form on failed submit |
| Tab order follows visual order | Default in Flutter (top-to-bottom) | Ensure DOM order matches visual order (no CSS reordering) |

**NEVER:**
- Submit a form without client-side validation first
- Show only a generic "Something went wrong" — include the specific field or reason
- Clear the form on error — only clear on successful submit
- Use `alert()` or `window.confirm()` for form feedback

---

## 3. Lists / Tables

| Requirement | Flutter | Angular |
|-------------|---------|---------|
| Empty state — message when no data, only after a settled load (§6b) | Dedicated empty state widget with icon + message + optional CTA | Empty branch only when the load succeeded and `items().length === 0`; never before the first load settles |
| Loading state — cold read only (see §6b) | `Shimmer` placeholder mirroring the loaded layout, or `CircularProgressIndicator` | daisyUI `skeleton` divs with `aria-hidden="true"`, region `aria-busy` |
| Error state — retry action | Error widget with "Retry" button calling reload | No data: blocking `alert alert-error` + retry. Data already shown: keep it and add an inline retry (§6b) |
| Pagination or virtual scroll for 50+ items | `ListView.builder` (virtual by default) | `@for (item of items(); track item.id)` with CDK virtual scroll or a paginated API |
| Row actions (edit, delete) | `Dismissible` or trailing icon buttons | Icon buttons in last column or dropdown menu |
| Delete confirmation | `showDialog` with confirm/cancel | daisyUI modal with confirm/cancel buttons |
| Sortable columns (tables) | Custom sort state + header tap handler | Click handler on `<th>` with sort indicator icon |
| Responsive — table → card on mobile | `LayoutBuilder` switching between `DataTable` and `Card` list | `hidden lg:table` for table, `lg:hidden` for card layout; or fold secondary columns into the primary cell (`hidden md:table-cell` plus an `md:hidden` sub-line). Do not rely on sideways scrolling for core data; check at 320 CSS px |
| Reorder by drag (WCAG 2.5.7) | `ReorderableListView` plus move up/down actions | Drag handle plus move up/down buttons or arrow keys |

**NEVER:**
- Show a blank page when data is loading — always show a loading state for a cold read
- Replace usable (cached/partial) content with a loader — see §6b
- Show a blank page when data fails to load — always show error + retry
- Render 100+ items without virtual scrolling or pagination
- Delete without confirmation on destructive actions

---

## 4. Navigation / Page Transitions

| Requirement | Flutter | Angular |
|-------------|---------|---------|
| Active link highlighted | `NavigationBar` with `selectedIndex` | `routerLinkActive="active"` with active class styling |
| Loading indicator on route change | `NavigatorObserver` or global loading overlay | Router events subscription showing `loading loading-spinner` |
| Title and focus on route change (WCAG 2.4.2, 2.4.3) | `Semantics(namesRoute: true)` on the route title | Unique title per route (route `title`/`TitleStrategy` in Angular; `document.title` in React). After navigation ends, focus the view's `<h1 tabindex="-1">` or `<main>`. Do not move focus for query-string or fragment-only changes |
| Sticky header does not hide focus (WCAG 2.4.11) | Scroll the focused field into view above the keyboard | `scroll-padding-top` equal to the sticky header height |
| Preserve scroll position on back navigation | `PageStorageKey` on scrollable widgets | `scrollPositionRestoration: 'enabled'` in router config |
| 404 / not-found route | Wildcard route to `NotFoundScreen` | Wildcard route `**` to `NotFoundComponent` |
| Breadcrumbs for nested routes (3+ levels) | Custom breadcrumb widget from route data | Component reading `ActivatedRoute` chain |

---

## 5. Feedback / Notifications

| Requirement | Flutter | Angular |
|-------------|---------|---------|
| Success feedback | `SnackBar` with green theme, ~4 s auto-dismiss | daisyUI `toast` with `alert-success`, auto-dismiss that pauses on hover and focus |
| Error feedback | `SnackBar` with error theme, manual dismiss + retry | daisyUI `toast` with `alert-error`, manual dismiss + retry |
| Toast with an action (Undo, Retry) — WCAG 2.2.1 | `SnackBar(action:, persist: true)` or a long duration | No auto-dismiss, or pause on hover and focus; the action is keyboard reachable |
| Warning feedback | `SnackBar` with warning theme | daisyUI `toast` with `alert-warning` |
| Position | Bottom center (Flutter default) | Bottom right (`toast` default) |
| Max visible | 1 at a time (queue others) | Max 3 stacked |
| Screen reader announcement | `SnackBar` uses `Semantics` automatically | `aria-live="polite"` on a toast container that exists in the DOM **before** the first message is inserted (a region created together with its message is often not announced) |
| Focus not obscured (WCAG 2.4.11) | Snack bars float above the bottom inset | Toasts never cover the focused element; keep them out of the focus path |

**NEVER:**
- Put the only copy of important information in a toast
- Use `print()` or `console.log()` as user feedback — always use visible UI
- Show success and error at the same time
- Auto-dismiss error messages — user must acknowledge errors

---

## 6. Responsive Breakpoints

Consistent across both stacks:

| Name | Width | Target |
|------|-------|--------|
| `sm` | 640px | Large phones (landscape) |
| `md` | 768px | Tablets |
| `lg` | 1024px | Small laptops |
| `xl` | 1280px | Desktops |
| `2xl` | 1536px | Large desktops |

- **Mobile-first:** Default styles target mobile, use breakpoint prefixes to add desktop behavior
- **Flutter:** Use `LayoutBuilder` or `MediaQuery` with `AppBreakpoints` constants
- **Angular:** Use Tailwind responsive prefixes (`sm:`, `md:`, `lg:`)

---

## 6b. Async-State Contract (loading / empty / error / refresh)

Applies to every screen or section that reads remote data.

**Classify before building any loading UI:**

| Class | Meaning | Treatment |
|---|---|---|
| A | Cold read, nothing usable to show yet | Skeleton mirroring the loaded layout |
| B | Existing loading UX already meets this contract | Leave unchanged |
| C | Action/mutation (submit, save, pay) | Inline progress on the control; never a page skeleton |
| D | Local, static or already hydrated content | No loader |

**State model.** Model each remote region as one discriminated union, not several booleans: `idle | loading | refreshing | success | empty | error | offline`, plus "has data" (cached or partial content is present). Render in this order, so cached content always wins (stale-while-error):

| State | Has data? | Render |
|---|---|---|
| loading | no | Skeleton (class A) after the delay below |
| loading / refreshing | yes | The content, plus a compact refresh indicator. Never a skeleton |
| error | no | Blocking error state with Retry |
| error | yes | The content, plus an inline "Couldn't refresh" notice with Retry and a "last updated" time |
| offline | yes / no | Cached content with an "Offline" notice / an offline empty state. Say "offline" only when it is known |
| success, zero items | — | Empty state (only after the load settled) |
| success | yes | Content |

```html
<!-- web sketch (Angular control flow; the same order applies in React/Flutter) -->
@if (state() === 'loading' && !hasData()) { <app-skeleton-list /> }
@else if (state() === 'error' && !hasData()) { <app-error-state (retry)="reload()" /> }
@else if (state() === 'success' && items().length === 0) { <app-empty-state /> }
@else {
  @if (state() === 'error') { <app-inline-retry (retry)="reload()" /> }
  <app-item-list [items]="items()" />
}
```

**Skeleton vs spinner**

| Situation | Indicator |
|---|---|
| Cold read of a region with known layout (lists, cards, detail pages) | Skeleton mirroring the loaded layout |
| Mutation / action (save, pay, submit) | Inline spinner on the control; the control is disabled while in flight. Never a page skeleton |
| Short unknown-layout wait inside a component (< ~1 s typical) | Small spinner |
| Streamed or generated text | "Analyzing" indicator, then the streamed text; never a skeleton or fake determinate progress |
| Known-length long task (upload, export) | Determinate progress bar with a percentage |

**Loading and refresh**
- Never replace usable (cached/partial) content with a loader on refresh, refresh failure, next-page load or reconnect. Pull-to-refresh keeps content visible and never renders a skeleton.
- Flash guard: show nothing for the first ~150 ms, then the skeleton; once shown, hold it at least ~400 ms so it never flashes. Implement this once in a shared async-view host, not per screen.
- Every loading state needs a terminal exit: content, empty, cached-offline or explicit error. Fetches have bounded timeouts. After ~10 s of loading, show a presentation-only "Taking longer than usual" message with Retry; it does not blame the network and gives way to the real error.
- Under reduced motion, keep the skeleton geometry and drop the shimmer (daisyUI 5 `.skeleton` already stops animating under `prefers-reduced-motion: reduce`).

**Announcements (web `aria-*` / Flutter `Semantics`)**
- The loading region gets `aria-busy="true"` and one visually hidden label ("Loading orders"); skeleton bars get `aria-hidden="true"`. Flutter: exclude shimmer from semantics and give the region one label.
- Announce completion or failure once through a persistent `aria-live="polite"` region (or `SemanticsService.announce` once). Never put the whole content in a live region, and never re-announce on a background refresh.
- Errors that block the task may use `role="alert"`; use it sparingly.
- Streamed/generated text is not class A; show an "analyzing → streaming" state, and keep partial text visible if the stream fails mid-answer.
- Choose a refresh strategy per remote-read screen (background, automatic, realtime, pull-to-refresh, explicit action or none); pull-to-refresh is not a default wrapper.

**Empty vs error**
- A successful zero result is the empty state; a failure is the error state. Never let `[]`, `null` or an unchanged loading state stand for both, and never render the error string on the empty path (assert it is absent in a test).
- Every runtime-sized collection (`ListView.builder`/`separated`, `SliverList`, `GridView.builder`) renders a purposeful empty state at zero: icon + title naming what is absent; subtitle only if it adds information; a CTA only if the action is not already one tap away in persistent navigation. A muted one-line `Text` is not an empty state. Collections that cannot be empty (fixed chips, wizard steps) carry `// empty-state-na: <reason>`.
- A filtered-empty state names the active filter and offers to clear it.
- Never gate the empty state on `data.isEmpty` alone when data may still be loading; use a "has ever loaded/synced" discriminator.
- A widget test that overrides the provider with `[]` proves only that the widget renders an empty state. It says nothing about whether the real data path can produce one.

**Retry**
- Retry is a fresh read (new fetch/re-subscription), single-flight (repeated taps → one request; the guard clears on success, empty, failure and cancel).
- A slow retry keeps the error on screen with its action disabled and compact progress; it does not re-enter the skeleton.
- Copy is contextual and non-technical; exception text and stack traces are debug-only. Say "offline" only when offline is actually known.

**State coverage to design per screen:** loaded · cold loading · cached refresh · empty · filtered-empty · pending · syncing · stale · offline · degraded network (slow ≠ offline, timeout ≠ failure) · permission denied (offer the system settings path) · partial (names what did not load) · error · success. No false success: nothing reads as paid/sent/complete before authoritative confirmation; optimistic UI only for reversible low-risk actions.

**Never:** a full-screen spinner over content the user already has · a skeleton on refresh, retry, next page or reconnect · clear-then-refetch (wipe, blank, scroll reset) · an error that replaces cached content · "offline" for a slow or failed request · empty rendered before the first load settles · raw exception text · a shimmer without a reduced-motion stop · fake typing or fake determinate progress for AI output · two banners for one condition (one shell-owned status slot: write failure outranks offline) · a toast as the only error for a blocking failure.

### 6b.1 Who owns the state (smart host, dumb view)

The smart container (screen, route component, feature hook) owns the fetch, the cache, connectivity and the derived view state. It passes ONE value down. A shared presentational async view (`AsyncView` / `<app-async-view>` / `AsyncSection`) only renders the surface for that value and emits `retry`; it never fetches, never reads a store, and its skeleton, empty and error slots are inputs. Use each framework's own state type; do not port one stack's type to another.

| Stack | Native source | Content-first mapping (keep the last good value) |
|---|---|---|
| Flutter (Riverpod 3) | `AsyncValue<T>` | `value` is the cached content (it keeps the previous data while refreshing or after a refresh error; `asData` is `null` on error and drops it; `valueOrNull` no longer exists in Riverpod 3); `isLoading` / `isRefreshing` / `hasError` are modifiers. Carry an explicit `hasEverLoaded` flag for empty vs never-fetched |
| Angular 22 | `resource()` / `httpResource()` | `status()` is `idle \| loading \| reloading \| resolved \| error \| local`. `reloading` keeps `value()`; `loading` after a params change clears it and `error` makes `value()` throw, so keep the last good value in a `linkedSignal` fed by `hasValue() ? value() : undefined` and derive the surface in a `computed`. `reload()` is ignored while `loading` and starts another request while `reloading`: guard Retry with your own in-flight flag, and give a cold stall a new request (change a params signal), not `reload()` |
| React 19 + TanStack Query 5 | `useQuery` | `data` with `placeholderData: keepPreviousData` keeps content across key changes; `isPending` (no data yet) → cold, `isFetching && data` → refreshing modifier, `isError && data` → inline error; pass the query's `signal` to `fetch` so a superseded request is cancelled. A refetch after a cold error resets `isError`, so a retrying cold error is `isFetching && errorUpdatedAt > 0` (keep the error surface with a busy Retry, not the skeleton); Retry/Refresh call `refetch({ cancelRefetch: false })` so repeated taps join the request in flight (the default cancels and restarts it) |

**Races:** newest request wins. A response for a superseded key or an older request id is dropped (abort signal, request id or the library's cancellation), and a refresh/retry already in flight is reused (single flight) rather than duplicated. A stale response never overwrites newer content.

**Required transition tests** (unit/widget level, fake clock for the timers): cold → skeleton after 150 ms, never before · skeleton held ≥ 400 ms once shown · content + refresh failure → content stays with inline error · content + offline → content stays with offline notice · cold + error → blocking error with Retry · settled zero → empty (and the error text is absent) · retry ×3 rapid taps → one request (render between taps: frameworks may merge same-tick calls and hide a missing guard) · older response arriving after a newer one → newer content kept · 10 s stall → "taking longer" with Retry · reduced motion → no shimmer animation. Riverpod 3 delivers provider changes to widgets on a zero-length timer: pump twice (or `pumpAndSettle` where no loop runs) before asserting.

### 6b.2 Mutations, pagination and AI streams

- Mutation progress lives in the control: label kept, width preserved, control disabled, determinate only with real progress. Consequential actions stay pending until the server confirms; failure restores the control and says what did not happen.
- Pagination status is separate from the region state: a fixed-height footer with load-more / loading / error-with-retry / end. A page-N failure never touches pages already shown.
- AI output is a stream with explicit states (`submitted → thinking → streaming → done | stopped | failed`) advanced only by real events; partial text stays on failure, and Stop is always available while streaming.

## 6c. Refresh Strategy Decision Record

Every screen that reads remote data records its refresh strategy (in the screen's doc comment, the feature README or the project's DESIGN.md screen table). No strategy is added "by default"; pull-to-refresh is never a default wrapper. Gate rule `DS-REFRESH`: a file that uses `RefreshIndicator`, `CupertinoSliverRefreshControl` or a pull-to-refresh package must contain `refresh-strategy:` plus one of the six names below. A screen with no pull-to-refresh control is not a finding.

| Strategy | Use when | Not when |
|---|---|---|
| Background (stale-while-revalidate on focus/resume/reconnect) | Data changes outside the user's action and a short lag is fine | The user needs to confirm freshness explicitly |
| Automatic interval | Time-bound data (status boards) with a known change rate | Battery- or quota-sensitive data; hidden tabs/backgrounded apps (pause it) |
| Realtime (socket/stream subscription) | Multi-user or live state where seconds matter | One-shot reads; it still needs a reconnect and a resync read |
| Pull-to-refresh | Mobile list/feed, top-anchored scroll, read-only, user expects fresher data, an accessible equivalent exists | Forms, chat, maps, wizards, confirmation and payment screens, desktop web, nested scrollers |
| Explicit action (Refresh button / menu) | Desktop web, reports, any screen where a gesture is unavailable or ambiguous | When background refresh already guarantees freshness |
| None | Static, local or immediately-consistent content | Remote data that can change |

Record (one block per screen): `screen · data source · change rate · freshness need · strategy(ies) · trigger(s) · scope (whole screen or sections) · failure behaviour (content stays + inline error) · accessible equivalent (or n/a with reason)`.

Refresh rules: a refresh awaits the real work of every section it covers (all-settled, per-section isolation, indicator outlives the slowest section); it reconciles the leading page and keeps load-more pages separate; it never skeletons, blanks or resets scroll; offline refresh says so immediately instead of spinning; one pull = one refresh (no double fetch). Test each of those as a transition test (§6b.1).

---

## Applying These Contracts

When building any UI surface:

1. **Identify which contract applies** (modal, form, list, navigation, feedback)
2. **Check every row** in the requirement table for that contract
3. **Implement all requirements** — not just the happy path
4. **Test the unhappy paths:** empty, loading, error, edge cases
5. **If a requirement doesn't apply**, add `// ignore-design: [reason]` with explanation
