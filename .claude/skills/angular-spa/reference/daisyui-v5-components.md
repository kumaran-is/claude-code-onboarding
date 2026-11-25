# daisyUI 5.8.2 Component Reference

## Quick Reference

### Tailwind CSS 4.3.5 Setup

```css
/* src/styles.css (NOT .scss — Tailwind CSS 4.3.5 directives conflict with Sass) */
@import "tailwindcss";

/* light is the default; dark applies under prefers-color-scheme: dark until data-theme is set */
@plugin "daisyui" {
  themes: light --default, dark --prefersdark;
}

/* Customise a built-in theme (or add one: a new name plus every --color-*). Unlisted variables are
   inherited. The default light error colour is below 4.5:1 on base-100, so error text fails WCAG 1.4.3. */
@plugin "daisyui/theme" {
  name: "light";
  default: true;
  --color-error: oklch(50% 0.2 27);
  --color-error-content: oklch(98% 0.01 27);
}

/* App tokens: each --color-* generates bg-*/text-*/border-* utilities (bg-brand, text-brand) */
@theme {
  --color-brand: oklch(58% 0.19 255);
}

/* daisyUI loading indicators animate through SMIL inside mask-image, which ignores prefers-reduced-motion:
   under reduced motion they become a static dot (the status text carries the meaning). Gate: DS-REDUCED-MOTION. */
@media (prefers-reduced-motion: reduce) {
  .loading { mask-image: none; -webkit-mask-image: none; border-radius: var(--radius-selector); opacity: 0.6; }
}
```
> **Note:** Do NOT add `@import "daisyui"` — daisyUI is loaded via the `@plugin` directive in Tailwind CSS 4.3.5.
> Verified on Angular 22.3 + Tailwind 4.3.5 + daisyUI 5.8.2 (2026-11-24): the built CSS contains
> `.btn`, `[data-theme=dark]`, `@media (prefers-color-scheme:dark){:root:not([data-theme])…}`, the
> overridden `--color-error` after the built-in light block, and `.border-brand`; axe reports 0
> violations in both themes. Component classes and options: the official `daisyui` skill.

### daisyUI 5.8.2 Modal (required pattern)

```html
<dialog id="my_modal" class="modal">
  <div class="modal-box">
    <h3 class="text-lg font-bold">Title</h3>
    <p class="py-4">Content</p>
    <div class="modal-action">
      <form method="dialog"><button class="btn">Close</button></form>
    </div>
  </div>
  <!-- backdrop click closes; out of the Tab order and named, or it is an unlabelled tab stop -->
  <form method="dialog" class="modal-backdrop"><button tabindex="-1" aria-label="Close">close</button></form>
</dialog>
```

Open it with `viewChild<ElementRef<HTMLDialogElement>>()` and `showModal()`: the native dialog traps
focus, closes on Esc and returns focus to the trigger (Chromium). Add `aria-labelledby` pointing at the
heading. A button inside `<form method="dialog">` with a `value` sets `dialog.returnValue`
(`'confirm'` / `'cancel'`). jsdom 31 has no `showModal()`/`close()`: stub them in unit tests.

### daisyUI 5.8.2 Drawer (required pattern)

```html
<div class="drawer lg:drawer-open">
  <input id="drawer" type="checkbox" class="drawer-toggle" />
  <div class="drawer-content"><!-- page content --></div>
  <div class="drawer-side">
    <label for="drawer" aria-label="close sidebar" class="drawer-overlay"></label>
    <ul class="menu bg-base-200 min-h-full w-80 p-4"><!-- nav items --></ul>
  </div>
</div>
```

### Color System Quick Reference

```
bg-base-100/200/300     — backgrounds
bg-primary/secondary/accent — brand colors
bg-info/success/warning/error — states
text-base-content       — primary text
text-base-content/60    — secondary text
border-base-300         — default borders
```

## Theme System

```html
<!-- index.html: no data-theme, so `--prefersdark` applies until the app sets one -->
<html lang="en">
```

`<html>` is outside the Angular root, so it cannot be template-bound. Canonical service (`core/theme/theme.ts`;
tested: 7 unit tests and Playwright first-load dark, toggle, reload persistence). Initialise from the stored
choice, else the system preference: a hard-coded `signal('light')` plus an effect that always writes
`data-theme` switches off a user's dark preference on first load.

```typescript
import { DOCUMENT, Service, effect, inject, signal } from '@angular/core';
import { Logger } from '../logging/logger';

export type ThemeName = 'light' | 'dark';
const STORAGE_KEY = 'app-theme';
const isThemeName = (value: unknown): value is ThemeName => value === 'light' || value === 'dark';

@Service()
export class Theme {
  private readonly document = inject(DOCUMENT); // SSR-safe: no global document/window
  private readonly logger = inject(Logger);

  readonly current = signal<ThemeName>(this.readStored() ?? this.systemPreference());

  constructor() {
    // effect() pushes state OUT to the DOM: its legitimate use.
    effect(() => this.document.documentElement.setAttribute('data-theme', this.current()));
  }

  toggle(): void {
    const next: ThemeName = this.current() === 'dark' ? 'light' : 'dark';
    this.current.set(next);
    this.persist(next);
  }

  private systemPreference(): ThemeName {
    return this.document.defaultView?.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  // Storage throws in privacy modes or with blocked site data: log, then fall back (a preference, never a secret).
  // Even the `localStorage` getter throws (SecurityError) when site data is blocked, so it is read inside the
  // try, never in a field initializer: an initializer that touches it stops the app from booting.
  private readStored(): ThemeName | null {
    try {
      const stored = this.document.defaultView?.localStorage.getItem(STORAGE_KEY);
      return isThemeName(stored) ? stored : null;
    } catch (error) {
      this.logger.warn('theme: localStorage read failed, using system preference', { error });
      return null;
    }
  }

  private persist(theme: ThemeName): void {
    try {
      this.document.defaultView?.localStorage.setItem(STORAGE_KEY, theme);
    } catch (error) {
      this.logger.warn('theme: localStorage write failed, choice kept for this session', { error });
    }
  }
}
```

Toggle button: [angular-ui-feedback-components.md](angular-ui-feedback-components.md#theme-toggle). First-paint
flash when the stored choice differs from the system preference: `tailwind-patterns` skill §5 (inline script,
CSP hash). Unit tests stub `window.matchMedia` (absent in jsdom) and make `getItem`/`setItem` **and the
`localStorage` getter itself** throw; the E2E suite blocks storage in an init script and asserts the app boots.

## Color System

```css
/* Backgrounds — USE ONLY THESE */
bg-base-100       /* Primary background */
bg-base-200       /* Secondary background */
bg-base-300       /* Tertiary background */
bg-neutral        /* Dark neutral */
bg-primary        /* Brand primary */
bg-secondary      /* Brand secondary */
bg-accent         /* Accent color */
bg-info           /* Informational */
bg-success        /* Success state */
bg-warning        /* Warning state */
bg-error          /* Error state */

/* Text */
text-base-content        /* Primary text */
text-base-content/70     /* Secondary text (on base-200/300 too) */
text-base-content/60     /* Muted text on base-100 — the lowest opacity that keeps 4.5:1; never /40 */
/* text-error on the default light theme measures 2.87:1 on base-100 — fails AA for body text.
   Override --color-error with @plugin "daisyui/theme" (Tailwind setup above), or use
   text-base-content with an error icon. */
text-primary-content     /* Text on primary bg */

/* Borders */
border-base-300          /* Default border */
border-base-content/20   /* Subtle border */
border-primary           /* Primary border */
border-error             /* Error border */

/* NEVER use hardcoded hex: bg-[#3b82f6] */
```

## Changes from v4 to v5

| Component | v4 | v5.8.2 | Notes |
|-----------|-----|--------|-------|
| Button soft | N/A | `btn-soft` | New: subtle background variant |
| Button XL | N/A | `btn-xl` | New size |
| Modal backdrop | Auto | Explicit | Add `modal-backdrop` form |
| Drawer overlay | Auto | Explicit | Requires `drawer-overlay` label |
| Loading | `loading` | `loading loading-spinner` | Must specify loader type |
| Input / select / textarea / file-input borders | `input-bordered` etc. | removed (bordered by default) | Use `input-ghost` for no border |
| Form wrapper | `form-control`, `label-text`, `label-text-alt` | `fieldset`, `fieldset-legend`, `label` | `label` is a real class in v5 |
| Field validation | manual | `validator` on the input + `validator-hint` | Native constraint validation styling |
| Button group | `btn-group` | `join` + `join-item` | |
| Tabs | `tabs-boxed`, `tabs-bordered`, `tabs-lifted` | `tabs-box`, `tabs-border`, `tabs-lift` | |
| Card | `card-bordered`, `card-compact` | `card-border`, `card-sm` | |
| Bottom navigation | `btm-nav` | `dock` | |
| Avatar placeholder | `avatar placeholder` | `avatar avatar-placeholder` | |

## Required Patterns (v5.8.2)

### Modal
Required pattern and focus behaviour: [daisyUI 5.8.2 Modal](#daisyui-582-modal-required-pattern) above.

### Drawer
Required pattern: [daisyUI 5.8.2 Drawer](#daisyui-582-drawer-required-pattern) above.

### Menu items at 44px
daisyUI `menu` items are `display:grid`, so `items-center` does not centre a `min-h-11` link vertically: use
`content-center` (`<li><a class="min-h-11 content-center">`). Keep `routerLinkActive="menu-active"` with
`ariaCurrentWhenActive="page"`.

### Loading States
```html
<button class="btn btn-primary">
  <span class="loading loading-spinner loading-sm"></span>
  Loading...
</button>

<!-- Variants: loading-spinner, loading-dots, loading-ring, loading-ball, loading-bars, loading-infinity -->
<!-- Sizes: loading-xs, loading-sm, loading-md, loading-lg -->
```

### Theme Controller (CSS-only theme switching)
Not used in Angular apps here: `theme-controller` inputs switch the theme in CSS only, so the `Theme` service,
the stored choice and the rendered theme drift apart. Use the service and toggle in [Theme System](#theme-system).

## Complete Component Listing

### Actions
`btn`, `dropdown`, `fab` (new), `modal`, `swap`, `theme-controller`

### Data Display
`accordion`, `avatar`, `badge`, `card`, `carousel`, `chat`, `collapse`, `countdown`, `diff`, `hover-3d` (new), `hover-gallery` (new), `kbd`, `list` (new), `stat`, `status` (new), `table`, `text-rotate` (new), `timeline`

### Navigation
`breadcrumbs`, `dock` (new), `link`, `menu`, `navbar`, `pagination`, `steps`, `tabs`

### Feedback
`alert`, `loading`, `progress`, `radial-progress`, `skeleton`, `toast`, `tooltip`

### Data Input
`checkbox`, `fieldset` (new), `file-input`, `filter` (new), `label` (new), `radio`, `range`, `rating`, `select`, `input`, `textarea`, `toggle`, `validator` (new)

### Layout
`divider`, `drawer`, `footer`, `hero`, `indicator`, `join`, `mask`, `stack`

## Common Patterns

```html
<!-- Buttons -->
<button class="btn btn-primary">Primary</button>
<button class="btn btn-outline btn-primary">Outline</button>
<button class="btn btn-ghost">Ghost</button>
<button class="btn btn-soft">Soft (v5)</button>

<!-- Card -->
<div class="card bg-base-100 shadow-xl">
  <div class="card-body">
    <h2 class="card-title">Title</h2>
    <p>Content</p>
    <div class="card-actions justify-end">
      <button class="btn btn-primary">Action</button>
    </div>
  </div>
</div>

<!-- Alert -->
<div class="alert alert-info"><span>Info message</span></div>
<div class="alert alert-soft alert-info">Soft style (v5)</div>

<!-- Skeleton -->
<div class="skeleton h-4 w-full"></div>
<div class="skeleton h-4 w-3/4"></div>
<div class="skeleton h-32 w-full"></div>

<!-- Fieldset (v5) -->
<fieldset class="fieldset bg-base-100 border-base-300 rounded-box border p-4">
  <legend class="fieldset-legend">Account</legend>
  <label class="label">Email</label>
  <input type="email" class="input" />
</fieldset>

<!-- Validator (v5): the class goes on the input. It turns red on :user-invalid OR [aria-invalid="true"],
     so with Signal Forms bind aria-invalid yourself (FormField sets no aria-* attributes). -->
<input type="email" class="input validator" required
       [attr.aria-invalid]="email().touched() && email().invalid()"
       [attr.aria-describedby]="email().invalid() ? 'email-error' : null" />
<!-- validator-hint is visibility:hidden until invalid and coloured with --color-error: override that
     colour (above) or the hint fails contrast in the default light theme -->
<p id="email-error" class="validator-hint">Please enter a valid email</p>

<!-- Filter (v5) -->
<div class="filter">
  <input type="radio" name="filter" class="filter-btn" aria-label="All" />
  <input type="radio" name="filter" class="filter-btn" aria-label="Active" />
  <button class="filter-reset">x</button>
</div>

<!-- Dock (v5) -->
<div class="dock">
  <button class="dock-item dock-active"><span class="dock-label">Home</span></button>
  <button class="dock-item"><span class="dock-label">Search</span></button>
</div>

<!-- List (v5) -->
<ul class="list bg-base-100 rounded-box shadow-md">
  <li class="list-row">
    <div><img class="size-10 rounded-box" src="avatar.jpg" /></div>
    <div>
      <div>Title</div>
      <div class="text-xs opacity-60">Subtitle</div>
    </div>
  </li>
</ul>

<!-- Status (v5) -->
<div class="status status-success"></div>
<div class="status status-error"></div>

<!-- Tabs -->
<div role="tablist" class="tabs tabs-box">
  <a role="tab" class="tab tab-active">Tab 1</a>
  <a role="tab" class="tab">Tab 2</a>
</div>

<!-- Steps -->
<ul class="steps">
  <li class="step step-primary">Register</li>
  <li class="step step-primary">Choose plan</li>
  <li class="step">Purchase</li>
</ul>

<!-- Dropdown: native <details>/<summary> gives keyboard and screen-reader semantics for free.
     Avoid <div role="button" tabindex="0">: it needs hand-written Enter/Space handling. -->
<details class="dropdown">
  <summary class="btn m-1">Options</summary>
  <ul class="dropdown-content menu bg-base-100 rounded-box z-10 w-52 p-2 shadow">
    <li><a routerLink="/settings">Settings</a></li>
  </ul>
</details>

<!-- Toast -->
<div class="toast toast-end">
  <div class="alert alert-success">Message sent!</div>
</div>

<!-- Breadcrumbs -->
<div class="breadcrumbs text-sm">
  <ul><li><a>Home</a></li><li><a>Docs</a></li><li>Current</li></ul>
</div>

<!-- Avatar group -->
<div class="avatar-group -space-x-6">
  <div class="avatar"><div class="w-12"><img src="1.jpg" /></div></div>
  <div class="avatar avatar-placeholder"><div class="bg-neutral text-neutral-content w-12"><span>+99</span></div></div>
</div>

<!-- Form inputs -->
<input type="text" class="input w-full" placeholder="Text" />
<select class="select w-full"><option>Option</option></select>
<textarea class="textarea w-full"></textarea>
<input type="checkbox" class="checkbox" />
<input type="radio" name="r" class="radio" />
<input type="checkbox" class="toggle" />
<input type="range" class="range" min="0" max="100" />
<input type="file" class="file-input w-full" />

<!-- Rating -->
<div class="rating">
  <input type="radio" name="rating" class="mask mask-star" />
  <input type="radio" name="rating" class="mask mask-star" checked />
  <input type="radio" name="rating" class="mask mask-star" />
</div>
```
