# Flutter web E2E with Playwright: CanvasKit locator and boot traps

> **Scope:** a Flutter **web** build served in a browser. It is never evidence about the Android/iOS app, which is verified with Maestro (`.claude/rules/testing-tool-selection.md`). Basic build-and-serve notes: [browser-testing-workflows.md](browser-testing-workflows.md) §Flutter web build notes.
>
> **Evidence level:** SOURCE-PROVEN. Each trap below was observed in a production Flutter 3.4x web suite driven by `@playwright/test`. The APIs named here (`SemanticsBinding.ensureSemantics`, `Semantics.explicitChildNodes`, the `flt-semantics-identifier` attribute, `usePathUrlStrategy`) were checked against the Flutter 3.44.2 SDK source. The behaviours were not re-run in this repository; confirm against your Flutter version before relying on one.

## 1. No DOM until semantics is on

Flutter web paints the whole app into a `<canvas>` (CanvasKit or skwasm). `getByRole` and `getByText` see nothing until Flutter builds its semantics tree, which it exposes as `<flt-semantics>` nodes.

- **Enable semantics from Dart in test builds**, not by clicking the "Enable accessibility" placeholder: guard `SemanticsBinding.instance.ensureSemantics()` behind a test-only `--dart-define` (for example `E2E_MODE=true`), so the tree exists from the first frame. Clicking the placeholder is slow and flaky.
- Give every control under test a `Semantics(label:)`, and give non-text controls a stable `Semantics(identifier:)`. The identifier appears as `[flt-semantics-identifier="..."]`.
- A purely visual check (a screenshot diff) does not need semantics. Boot it without the enable step, so semantics flakiness cannot fail a test that never queries a node.

## 2. Pick the matcher by how Flutter exposes the string

A `getByText` that returns 0 is usually a **matcher-type** bug, not a pattern bug: turning it into a regex does not help. Flutter exposes many strings as an **accessible name** (`aria-label` or role name), which `getByText` cannot see. Only plain `Text` leaves and headings are text content.

| Widget or situation | How it is exposed | Works | Never matches |
|---|---|---|---|
| Text field label | The textbox's accessible name | `getByRole('textbox', { name: 'Email' })` | `getByText('Email')` |
| Open dropdown options | `menu` → `menuitem "<label>"` | `getByRole('menuitem', { name: /Español/ })` | `getByText('Español')` |
| Closed dropdown | `button` whose name joins label and value | `getByRole('button', { name: /Language/ })` (unanchored) | An exact name match |
| Non-interactive labelled chip or badge | An accessible name on a node that is not a button | `getByLabel(/Coming soon/)` | `getByText`, `getByRole('button')` |
| `Text` with `semanticsLabel:` / `SelectableText` | The `semanticsLabel` replaces the visible text and is often merged into the parent group's name | Match the label inside the group name | The visible string, for example a `#` prefix |
| Interactive chip (`ActionChip` with a tooltip) | Often a `checkbox` role, name doubled by the tooltip. The section may merge differently from run to run | The merge-tolerant matcher below | `getByText` or `getByRole('button')` on its own |

For dynamic, chip or labelled content, default to a merge-tolerant matcher:

```ts
import type { Locator, Page } from "@playwright/test";

/** Match a string however the semantics tree surfaces it: text, aria-label or a role name. */
export function anyText(page: Page, re: RegExp): Locator {
  return page.getByText(re)
    .or(page.getByLabel(re))
    .or(page.getByRole("heading", { name: re }))
    .or(page.getByRole("button", { name: re }))
    .or(page.getByRole("checkbox", { name: re }))
    .or(page.getByRole("group", { name: re }))
    .first();
}
```

After the **first** failing locator, stop and read `test-results/<test>/error-context.md`. Its page snapshot shows the real role/name tree. Change the locator from that, never by guessing.

## 3. A button that never becomes "stable": the merged `Semantics` container

**Symptom:** `.click()` hangs with `waiting for element to be visible, enabled and stable`, and the locator resolved to one large `role=button` whose name contains the whole section's text plus the button label.

**Cause:** a parent `Semantics(label: ..., container: true)` without `explicitChildNodes: true` absorbs every descendant into one node. If anything in that subtree animates, the node's box never settles. `force: true` alone clicks the centre of the section, not the button.

**Fix, on both sides:**

1. **Widget:** add `explicitChildNodes: true` to that `Semantics`, so the control becomes its own small, stable node. This is also better for screen readers.
2. **Spec:** keep `click({ force: true })` on the now-discrete control when a scroll or page layer paints an empty semantics node over it and trips the receives-events check.

Authoring rule: never wrap an interactive control in a labelled `Semantics(container: true)` without `explicitChildNodes: true`.

## 4. Things the web semantics tree cannot see or do

| Situation | What happens | What to do instead |
|---|---|---|
| Non-interactive shell chrome outside the active route (a global offline banner, a status strip) | It is painted but has **no semantics node** at all. `identifier`, a Scaffold wrapper or moving it app-level does not help | Assert visually: a screenshot before and after must differ. Check the screen-reader announcement on a device with Maestro, not here |
| A control below the fold | The node exists, but its box is off-screen, so a forced click lands outside the canvas and is dropped | Scroll with real wheel events over the Flutter scrollable (`page.mouse.move(x, y)`, then `page.mouse.wheel(0, 500)`), then click inside `expect(...).toPass()`. `scrollIntoViewIfNeeded()` does not scroll a Flutter scrollable |
| The new route after an in-app `go()` / `push()` | The new screen's nodes may not be exposed in the same test | Prove navigation by asserting the old screen is gone, and test the new screen in its own spec that boots directly to it |
| A small overlay button that ignores every activation method | Its node resolves and is attached, but `onPressed` never fires | Assert that it is present in E2E, and cover its action with a widget test (`tester.tap`) |

## 5. Routing and boot

- **Hash routing is Flutter web's default.** Without `usePathUrlStrategy()`, a path deep link such as `/settings` is ignored and the app shows its initial route. Boot at `/`, then change the route in-app: `await page.evaluate(() => { location.hash = '#/settings'; })`. Every `page.goto` is a fresh page load.
- **An async `build()` that awaits an auth or remote future** never finishes when the test build bypasses real auth, so the screen shows a spinner forever and the boot check times out with a blank screenshot. Read the value without blocking (`ref.watch(authProvider).value`) in any build that must render first. This is also more robust in production.
- **Screens that need a local database or plugin with no web implementation** may render but cannot run their logic in the browser. Prove the render with a screenshot and a console-error check, and cover the behaviour with widget and unit tests.

## 6. Offline on Flutter web

Before you depend on `context.setOffline(true)`, check that the app reacts to it. Web connectivity plugins (for example `connectivity_plus`) read `navigator.onLine` and the window `online`/`offline` events. If the app's offline UI does not appear after `setOffline`, drive those signals directly:

```ts
async function setBrowserOnline(page: Page, online: boolean): Promise<void> {
  await page.evaluate((isOnline) => {
    Object.defineProperty(window.navigator, "onLine", { configurable: true, get: () => isOnline });
    window.dispatchEvent(new Event(isOnline ? "online" : "offline"));
  }, online);
}
```

Combine it with `setOffline` when the test also needs network requests to fail. UNVERIFIED: whether `setOffline` alone updates `navigator.onLine` depends on the browser and Playwright version. Assert the app's offline state; do not assume it.

## 7. Build once, serve statically, iterate on one spec

Build once with the test defines (`flutter build web --release --dart-define=E2E_MODE=true`), serve the output statically, and point `baseURL` at it. To iterate on one spec, keep the static server running and re-run only that spec. Rebuild whenever Dart code changes, or the server keeps serving the old bundle (check a build stamp).

## 8. Process rule

When a spec for the feature you changed fails, find the root cause (error-context snapshot, a focused run). Do not mark it `test.fixme` as "pre-existing". Check whether it passes on the base branch: a spec that fails only on your branch is a regression you introduced.
