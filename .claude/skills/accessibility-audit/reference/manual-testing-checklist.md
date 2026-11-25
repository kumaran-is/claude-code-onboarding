# Manual Accessibility Testing Checklist

Manual checks that automated tools cannot catch. Run after automated scan confirms baseline. Works for both Angular and Flutter.

> **Existing platform checklists** (load these too):
> - Angular: `.claude/skills/angular-spa/reference/accessibility-checklist.md`
> - Flutter: `.claude/skills/flutter-mobile/reference/accessibility-audit-checklist.md`

---

## Keyboard Navigation

| Check | Angular | Flutter |
|-------|---------|---------|
| Tab reaches all interactive elements | ✓ | Tab key in integration test |
| Enter/Space activates buttons | ✓ | `LogicalKeyboardKey.enter` |
| Escape closes modals/drawers | ✓ | `LogicalKeyboardKey.escape` |
| Focus indicator always visible | No `outline: none` without replacement | Focus decoration visible |
| No keyboard traps | Tab does not get stuck | Focus does not get stuck |
| Logical tab order | DOM order or tabindex | `FocusTraversalGroup` order |
| Skip link at top of page | first focusable element; in an SPA with `<base href="/">` a bare `href="#main-content"` resolves to `/#main-content` and navigates: handle the click (`preventDefault`) and focus `<main tabindex="-1">` | Not applicable (native nav) |

**Manual test steps:**
1. Open page, press Tab — first focusable element should receive focus
2. Continue tabbing — every interactive element must be reachable
3. At each element: Enter or Space should activate it
4. Open a modal — focus must move inside; Tab must stay inside; Esc must close
5. After modal closes — focus must return to the trigger element

---

## Screen Reader Testing

**Tools:** VoiceOver (macOS/iOS), NVDA or JAWS (Windows), TalkBack (Android)

**Testing priority:**
- Minimum: NVDA + Firefox → VoiceOver + Safari (macOS) → VoiceOver + Safari (iOS)
- Comprehensive: + JAWS + Chrome → TalkBack + Chrome (Android)

| Check | Angular | Flutter |
|-------|---------|---------|
| Page title is descriptive | `<title>` tag | App bar title or route |
| Headings create logical outline | h1 → h2 → h3, no skips | Semantics with `header: true` |
| All images have alt text | `alt` attribute or `alt=""` for decorative | `Semantics(label:...)` or `ExcludeSemantics` |
| Form fields have labels | `<label for>` or `aria-label` | `InputDecoration(labelText:)` |
| Error messages announced | `role="alert"` or `aria-live="polite"` | `Semantics(liveRegion: true)` |
| Dynamic updates announced | `aria-live="polite"` region | `SemanticsService.announce()` |
| Buttons have meaningful names | `aria-label` on icon-only buttons | `Semantics(label:)` on `IconButton` |

**Manual test steps:**
1. Enable screen reader (VoiceOver: Cmd+F5, TalkBack: hold both volume keys)
2. Navigate by headings — does structure make sense?
3. Navigate to each form — are labels read before field?
4. Submit form with error — is error message announced immediately?
5. Trigger a status update — is the live region read?

### VoiceOver Commands (macOS) — VO = Ctrl+Option

```
Navigation:
VO + Right/Left Arrow   Next/previous element
VO + Shift + Down/Up    Enter/exit group
VO + U                  Open Rotor (navigate by Headings/Links/Forms/Landmarks)
  Left/Right Arrow        Change rotor category
  Up/Down Arrow           Navigate within category

Reading:
VO + A                  Read all from cursor
Ctrl                    Stop speaking
VO + Cmd + H            Next heading
VO + Cmd + J            Next form control
VO + Cmd + L            Next link

Interaction:
VO + Space              Activate element
Tab / Shift+Tab         Next/previous focusable element
```

### NVDA Commands (Windows) — Insert = NVDA modifier

```
Navigation (Browse mode — default):
H / Shift+H             Next/previous heading
1–6                     Heading level 1–6
D / Shift+D             Next/previous landmark
F                       Next form field
B                       Next button
K / U / V               Next link / unvisited / visited

Reading:
NVDA + Down Arrow       Say all
Ctrl                    Stop speech
NVDA + Space            Toggle Browse ↔ Focus mode

Elements List:
NVDA + F7               All links, headings, form fields, landmarks

Note: NVDA auto-switches to Focus mode when entering form fields.
Manual override: NVDA + Space
```

### JAWS Commands (Windows)

```
Navigation:
H                       Next heading
F                       Next form field
B                       Next button
G                       Next graphic
;                       Next landmark
T                       Next table
Ctrl+Alt+Arrows         Table cell navigation

Lists:
Insert + F7             Link list
Insert + F6             Heading list
Insert + F5             Form field list

Forms Mode:
Enter                   Enter forms mode
Numpad +                Exit forms mode
```

### TalkBack Gestures (Android)

```
Explore by touch:       Drag finger across screen
Next element:           Swipe right
Previous element:       Swipe left
Activate:               Double tap
Scroll:                 Two-finger swipe
Reading controls:       Swipe up then right → choose Headings/Links/Controls
```

### NVDA Step-by-Step Test Script

```
1. Navigate to page → Insert+Down to read all → note title and main content
2. Press D repeatedly → verify all main areas reachable and labeled
3. Insert+F7 → Headings → verify logical structure
4. Press F → find first form field → verify label is read
5. Enter invalid data → submit → verify error announced, focus moves to error
6. Tab through all interactive elements → verify role and state announced
7. Trigger content update → verify change announced
8. Open modal → verify focus trapped → close → verify focus returns to trigger
```

### Common ARIA Fixes

```html
<!-- Icon-only button missing label -->
<button aria-label="Close dialog"><svg aria-hidden="true">...</svg></button>

<!-- Dynamic content not announced -->
<div role="status" aria-live="polite">Search returned 12 results</div>

<!-- Form error not read -->
<input type="email" aria-invalid="true" aria-describedby="email-error" />
<span id="email-error" role="alert">Invalid email address</span>
```

---

## Visual Checks

| Check | Threshold | Tools |
|-------|-----------|-------|
| Text contrast (light and dark themes) | >= 4.5:1 normal, >= 3:1 large (>= 24px, or >= 18.66px bold) | Browser DevTools, Colour Contrast Analyser |
| UI component contrast | >= 3:1 against adjacent colors | Same |
| Text resizes to 200% | No truncation, no overlap | Browser zoom |
| Zoom to 400% / content reflows at 320 CSS px | No two-dimensional scroll (data tables, maps, code excepted) | Browser zoom, responsive mode |
| Forced colours (Windows High Contrast) | Focus rings, borders and icons stay visible | DevTools → Rendering → Emulate `forced-colors: active` |
| Focus not obscured (2.4.11) | Sticky header, toast or cookie bar never fully hides the focused element | Tab through with sticky UI visible |
| Target size (2.5.8) | Every target ≥ 24×24 CSS px or adequately spaced | axe `target-size` + visual check |
| Focus indicators visible | Min 2px, high contrast | Visual inspection |
| Color not sole indicator | Error icons, patterns, text | Grayscale mode (DevTools) |
| Animations can be paused | Prefers-reduced-motion honored | OS reduced motion setting |

**Manual test steps:**
1. Browser zoom to 200% — check text does not clip or overlap
2. Resize to 320px width — check no horizontal scroll appears
3. Enable grayscale (DevTools → Rendering → Emulate CSS media) — check all info still conveyed
4. Enable OS reduced motion — check animations stop or reduce
5. Emulate `forced-colors: active` — check focus rings and control borders remain visible
6. Tab through every page with sticky UI present — the focused element is never fully covered
7. New 2.2 criteria: every drag has a button or keyboard alternative (2.5.7); help links sit in the same place on every page (3.2.6); no data is re-asked in a flow (3.3.7); login allows paste and password managers (3.3.8)

---

## Cognitive Accessibility

Checks automated tools cannot catch. Applies to both Angular and Flutter.

| Check | What Good Looks Like |
|-------|---------------------|
| Instructions are clear | "Enter your email address" not "Input required" |
| Error messages are helpful | "Password must be 8+ characters" not "Invalid password" |
| No time limits on forms | Or user can extend/disable the timer |
| Navigation is consistent | Same nav items in same order on every page |
| Important actions are reversible | Undo or confirm dialog before destructive action |
| Predictable behavior | Links do not open unexpected new windows; clicks do expected things |
| No moving content distracts | Carousels, auto-play videos can be paused |
| Form fields have visible labels | Labels visible, not just placeholder (placeholder disappears on focus) |

**Manual test steps:**
1. Complete a key user journey (create order, login, checkout) — note any confusion points
2. Trigger every error message — is it clear what went wrong and how to fix it?
3. Find the most destructive action (delete, cancel order) — is there a confirmation step?
4. Navigate away and back — are inputs preserved or is data lost without warning?

---

## Mobile-Specific (Flutter)

| Check | How to Test |
|-------|-------------|
| TalkBack (Android) | Settings → Accessibility → TalkBack → On |
| VoiceOver (iOS) | Settings → Accessibility → VoiceOver → On |
| 200% font scale | Settings → Display → Font Size → Largest |
| High contrast mode | Settings → Accessibility → High Contrast → On |
| Sufficient touch target spacing | Visually check — targets should not be adjacent without padding |

---

## ARIA Patterns Reference

### Modal Dialog — Focus Trap

```html
<div role="dialog" aria-modal="true" aria-labelledby="dialog-title" aria-describedby="dialog-desc">
  <h2 id="dialog-title">Confirm Delete</h2>
  <p id="dialog-desc">This action cannot be undone.</p>
  <button>Cancel</button>
  <button>Delete</button>
</div>
```

```javascript
function openModal(modal) {
  lastFocus = document.activeElement;       // store trigger
  modal.querySelector('h2').focus();        // move focus in
  modal.addEventListener('keydown', trapFocus);
}

function closeModal(modal) {
  modal.removeEventListener('keydown', trapFocus);
  lastFocus.focus();                        // return focus to trigger
}

function trapFocus(e) {
  const focusable = modal.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  const first = focusable[0];
  const last  = focusable[focusable.length - 1];

  if (e.key === 'Tab') {
    if (e.shiftKey && document.activeElement === first) {
      last.focus(); e.preventDefault();
    } else if (!e.shiftKey && document.activeElement === last) {
      first.focus(); e.preventDefault();
    }
  }
  if (e.key === 'Escape') closeModal(modal);
}
```

### Live Regions

```html
<!-- Status (polite — waits for current speech to finish) -->
<div role="status" aria-live="polite" aria-atomic="true">
  <!-- inject: "3 results found", "Saved", etc. -->
</div>

<!-- Alert (assertive — interrupts current speech) -->
<div role="alert" aria-live="assertive">
  <!-- inject: validation errors, critical warnings -->
</div>

<!-- Progress bar -->
<div role="progressbar" aria-valuenow="75" aria-valuemin="0" aria-valuemax="100" aria-label="Upload progress"></div>

<!-- Log (appended messages only, order matters) -->
<div role="log" aria-live="polite" aria-relevant="additions">
  <!-- new chat messages, activity feed entries -->
</div>
```

### Tab Interface (Angular / Web)

```html
<div role="tablist" aria-label="Product information">
  <button role="tab" id="tab-1" aria-selected="true"  aria-controls="panel-1">Description</button>
  <button role="tab" id="tab-2" aria-selected="false" aria-controls="panel-2" tabindex="-1">Reviews</button>
</div>
<div role="tabpanel" id="panel-1" aria-labelledby="tab-1">...</div>
<div role="tabpanel" id="panel-2" aria-labelledby="tab-2" hidden>...</div>
```

```javascript
// Arrow-key navigation within tablist (WCAG APG pattern)
tablist.addEventListener('keydown', (e) => {
  const tabs = [...tablist.querySelectorAll('[role="tab"]')];
  const index = tabs.indexOf(document.activeElement);
  const map = { ArrowRight: 1, ArrowLeft: -1, Home: -index, End: tabs.length - 1 - index };
  if (!(e.key in map)) return;
  const newIndex = (index + map[e.key] + tabs.length) % tabs.length;
  tabs[newIndex].focus();
  activateTab(tabs[newIndex]);
  e.preventDefault();
});
```

---

## Output Template

```
Manual Audit — [Date] — [Component/Page]
Tester: [Name]
Tools: [VoiceOver / NVDA / TalkBack / DevTools]

Keyboard: PASS / FAIL
- [Finding, if any]

Screen Reader: PASS / FAIL
- [Finding, if any]

Visual: PASS / FAIL
- [Finding, if any]

Cognitive: PASS / FAIL
- [Finding, if any]

Mobile (Flutter only): PASS / FAIL
- [Finding, if any]

Each row: PASS / FAIL / NOT RUN (a check not performed is NOT RUN, never PASS)

Overall: manual checks against WCAG 2.2 AA — all PASS | FAIL (list) | INCOMPLETE (rows NOT RUN)
Automated results are reported separately as "no automated violations"; they never make this section PASS.
```
