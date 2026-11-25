# Angular UI modes — selection, setup and component ownership (canonical)

One reference for every skill, agent and command that builds or reviews Angular UI. An Angular
workspace has exactly one **UI mode**, recorded in its `package.json`:

```json
{ "config": { "uiMode": "daisyui" } }
```

Set it with `npm pkg set config.uiMode=<mode>` (npm's per-package `config` field: no new file, no global
rule). Read it, and check it against the installed packages, with
`bash .claude/scripts/angular-ui-mode.sh detect <workspace>` (exit 1 = inconsistent).

| Mode | Stack (verified 2026-11-24) | Best for |
|---|---|---|
| `daisyui` (**recommended default**) | Angular 22.3 + Tailwind CSS 4.3.5 + daisyUI 5.8.2 | Standard SaaS, admin dashboards, CRUD, marketing sites, fast delivery |
| `spartan` | Angular 22.3 + Tailwind CSS 4.3.5 + Spartan UI 1.10.1 (Brain + Helm) + `@angular/cdk` 22.3.0 | A custom design system you own, complex accessible Angular-native controls |
| `hybrid` | Angular 22.3 + Tailwind CSS 4.3.5 + daisyUI 5.8.2 + Spartan UI 1.10.1 | daisyUI's ready styling plus Spartan's dialogs, menus, popovers, select/combobox |
| `none` | Angular 22.3, plain CSS | The legacy opt-out (no Tailwind, no UI library). Accepted as `--ui=none`, never offered |

Common to all modes: Angular CLI 22.3.0, TypeScript ~6.0 (Angular 22 requires `>=6.0 <6.1`), Node 26 LTS,
zoneless, standalone, OnPush default, Signal Forms, Vitest. Official skills: `daisyui` (daisyUI
5.8.2 component classes) and `spartan` (Spartan CLI, Brain/Helm rules); MCP: `spartan-ui`
(`@spartan-ng/mcp@1.10.1`, component code/API/a11y notes). Load only the ones the mode uses.

## 1. Choosing a mode

Recommend from the requirements, then let the user decide. Never pick `hybrid` because it "has more".

| Requirement | Recommend |
|---|---|
| Marketing site, standard admin dashboard, CRUD SaaS, forms and tables | `daisyui` |
| Team ships its own design system; every component's markup and tokens are owned in-repo | `spartan` |
| Complex accessible comboboxes, menus, dialogs, popovers are central to the product | `spartan` |
| Mostly standard screens, but a few complex interactions (command menu, combobox, nested dialogs) | `hybrid` |

Cost, measured on the reference apps (same feature set: shell, orders list, order form, confirm dialog):

| | daisyUI | Spartan | Hybrid |
|---|---|---|---|
| Initial bundle (raw / transfer) | 349.9 kB | 461.8 kB / 118.4 kB with the menu and toaster deferred (552.4 kB, over the 500 kB warning budget, without) | 500.7 kB / 120.9 kB with the account menu deferred (549.5 kB without); budget warning 550 kB (§6) |
| Runtime deps added | 1 (CSS-only plugin) | brain, cdk, cva, cn, ng-icons, tw-animate-css | both |
| Generated code you own | none | `libs/ui/**` (copied Helm sources) | `libs/ui/**` for Spartan-owned parts |
| Dark mode switch | `data-theme` on `<html>` | `.dark` class on `<html>` (`:root.dark`) | `data-theme` drives both (§6) |
| Form a11y wiring | bind `aria-invalid` / `aria-describedby` yourself | `hlm-field` + Brain wire them | per control owner |

## 2. Selection flow (`/scaffold-angular-app`)

1. Resolve before generating anything:
   `bash .claude/scripts/angular-ui-mode.sh resolve --args "$ARGUMENTS" [--project <dir>] [--noninteractive]`

   | Output | Meaning | Next |
   |---|---|---|
   | `MODE=<m>` `SOURCE=flag` | `--ui=<m>` was given | no question |
   | `MODE=<m>` `SOURCE=project` | existing workspace already has a mode | keep it; no question |
   | `MODE=daisyui` `SOURCE=default-noninteractive` | headless (`claude -p`, `CI` set, or `--noninteractive`) | say "defaulted to daisyUI" in the summary |
   | `ACTION=ask` | interactive, nothing chosen | ask once (below) |
   | exit 2 | invalid or contradictory `--ui` | show the message (it lists the modes); stop |
   | exit 3 | `--ui` differs from the existing project's mode | stop: changing mode is a migration, not a scaffold option |

2. Ask **once**, with the AskUserQuestion tool (no AskUserQuestion tool available = non-interactive:
   re-run resolve with `--noninteractive`):

   > **Which UI component system would you like?**
   > 1. **daisyUI (Recommended)** — Tailwind CSS v4 + daisyUI v5. Fast development, dashboards, standard forms, themes, common components.
   > 2. **Spartan UI** — Tailwind CSS v4 + Spartan UI. Accessible Angular-native interactive controls, fully customised design systems.
   > 3. **Hybrid** — Tailwind CSS v4 + daisyUI v5 + Spartan UI. Rapid styling plus sophisticated Angular-native interactions.

   The tool's free-text "Other" answer covers "tell me more / help me choose": answer from §1, recommend
   one mode with a one-line reason, and ask the same question again (still one selection question).
3. Record the answer immediately after `ng new`: `npm pkg set config.uiMode=<mode>`. Every later step,
   test and summary uses that value; never ask again in the same scaffold or in later feature work.

Feature and component generation in an existing workspace (`angular-spa` agent, `/add-feature`,
`ng generate`): run `detect` first and follow the reported mode. `MODE=none` with no record in a workspace that
has Tailwind but no UI library → ask once, then record it.

## 3. Setup per mode

All modes start with `/scaffold-angular-app` steps 1–2 (`ng new`, tilde ranges), then
`npm exec --no -- ng add angular-eslint@22.8.0 --skip-confirmation` and
`npm exec --no -- ng add tailwindcss --skip-confirmation` (writes `.postcssrc.json`, `@import 'tailwindcss';`,
caret ranges), then `npm install --save-exact tailwindcss@4.3.5 @tailwindcss/postcss@4.3.5 postcss@8.5.33`.

### daisyui

`npm install --save-exact daisyui@5.8.2`, then `src/styles.css` from `daisyui-v5-components.md` →
Tailwind CSS 4.3.5 Setup (themes, `@plugin "daisyui/theme"` override, `@theme` app tokens). Theme service and
toggle: `daisyui-v5-components.md` → Theme System.

### spartan

Verified with `@spartan-ng/cli` and `@spartan-ng/brain` 1.10.1 (the 1.10.0 → 1.10.1 diff changed one generated
file: the card's `index.ts`). Never install daisyUI in this mode.

```bash
npm install --save-dev --save-exact @spartan-ng/cli@1.10.1
# 1. Init ONCE with the theme. Do not also run ui-theme: it is not idempotent and appends a second copy
#    of the layer imports, the preset and every :root/:root.dark variable (+88 lines).
npm exec --no -- ng g @spartan-ng/cli:init --project=<name> --theme=neutral < /dev/null; echo "exit=$?"
# 2. Write components.json BEFORE the first `ui` run. Without it `ui` prompts, and with no terminal it
#    exits 0 and writes nothing (a silent no-op in agents and CI). Omitting "style" falls back to vega,
#    while the interactive default is nova.
printf '%s\n' '{"componentsPath":"libs/ui","importAlias":"@spartan-ng/helm","style":"nova"}' > components.json
# 3. Generate only what the app uses (name positional or --name=). Names in 1.10.1: field (not form-field),
#    sonner (not toast), dropdown-menu, dialog, alert-dialog, select, popover, button, input, label, card...
npm exec --no -- ng g @spartan-ng/cli:ui button < /dev/null; echo "exit=$?"
# 4. Pin what the generators added with ranges (init pins @angular/cdk to 22.0.0: raise it to the core minor).
#    @ng-icons stays <34: the Helm code declares ">=32.0.0 <34.0.0".
npm install --save-exact @angular/cdk@22.3.0 @spartan-ng/brain@1.10.1 cn@0.5.2 class-variance-authority@0.7.1 \
  @ng-icons/core@33.4.0 @ng-icons/lucide@33.4.0
npm install --save-dev --save-exact tw-animate-css@1.4.0
```

What the generators change (commit it knowingly): `src/styles.css` becomes the layered Tailwind imports +
`@import '@spartan-ng/brain/hlm-tailwind-preset.css'` + `:root` / `:root.dark` OKLCH variables + `@layer base`;
each component lands in `libs/ui/<name>/src/`; `tsconfig.json` gains one `paths` entry per component
(`@spartan-ng/helm/<name>`) **and loses its comments**; `tsconfig.app.json` includes `libs/ui/**/src/**/*.ts`;
`init` creates `.nx/workspace-data` (add `.nx/` to `.gitignore`). Wire `provideSpartanHlm()` in
`app.config.ts`. App tokens: add `--warning` to `:root` and `:root.dark`, map it in `@theme inline`
(`--color-warning: var(--warning)`); the compiled utility references `var(--warning)` directly, so grep for
`--warning`, not `--color-warning`, when proving compilation.

After generation, edit the copied Helm sources (they are yours):

| Generated (1.10.1) | Problem | Change |
|---|---|---|
| button `default h-8`, `lg h-9`, `icon size-8` | below the 44 px house target (AA's 24 px passes) | `h-11`, `h-12`, `size-11` |
| input `h-8`; menu item no min height; dialog close `icon-sm` (28 px) | same | `h-11`; `min-h-11`; `size="icon"` |
| destructive alert description `text-destructive/90` on `bg-card` | fails axe color-contrast in the light neutral theme | `text-destructive` |
| `hlmAlert` hard-codes `role="alert"` | wrong for a success message | `role="status"` on the host overrides it |
| Helm code under `libs/ui/**` | not linted by default (`ng lint` looks at `src/**`); once included, 69 errors from exactly four rules: 56 `directive-selector`, 8 `component-selector`, 3 `no-input-rename`, 2 `consistent-type-definitions` | add `"libs/ui/**/*.ts"` to the lint target's `lintFilePatterns` and the override below; every other rule still applies (a planted unused `any` in `libs/ui` fails `ng lint`) |

```js
// eslint.config.js — appended block
{
  // Spartan Helm (copied in by @spartan-ng/cli): hlm-/brn- selectors, aliased host-directive inputs and
  // `type` aliases are the library's own conventions.
  files: ['libs/ui/**/*.ts'],
  rules: {
    '@angular-eslint/directive-selector': 'off',
    '@angular-eslint/component-selector': 'off',
    '@angular-eslint/no-input-rename': 'off',
    '@typescript-eslint/consistent-type-definitions': 'off',
  },
},
```

Updating Helm later: `ng g @spartan-ng/cli:ui <name>` skips an installed component (exit 0, "already
installed"); use `npm exec --no -- ng g @spartan-ng/cli:migrate-helm-libraries --libraries=<name>` (without
`--libraries` it prompts and can overwrite your edited Helm files). Project facts:
`ng g @spartan-ng/cli:info --json`; health: `ng g @spartan-ng/cli:healthcheck --dry-run`.

The CLI is a generation-time tool. Nothing at build or run time imports it (Helm imports only `@spartan-ng/brain`,
Angular, the CDK, cva and cn), and its tree (Nx 24.0.6, 351 packages) carries dev-only high advisories with no
fix, so `npm audit --audit-level=high` fails while it is installed. After generating:
`npm uninstall @spartan-ng/cli && rm -rf .nx` (audit then exits 0; build, lint, tests unchanged). To add or migrate
Helm later: `npm install --save-dev --save-exact @spartan-ng/cli@<the brain version>`, run the generator, uninstall
again. Keep `components.json`. With the CLI absent, `ng g @spartan-ng/cli:…` fails loudly (exit 127), never silently.

Bundle budget: Spartan's shell (brain sonner, CDK menu, Helm dropdown) put the initial bundle at 552 kB, over
the 500 kB warning. Wrap the small-screen menu and `<hlm-toaster>` in `@defer (on idle)` (the menu with an inert
`@placeholder` button of the same size) and import those Helm pieces **as classes** (`HlmDropdownMenu`,
`HlmDropdownMenuTrigger`, `HlmDropdownMenuItem`, `HlmToaster`…): through the `Hlm*Imports` arrays `@defer`
splits out nothing and the bundle grows (560 kB). Result 461.8 kB. The CDK overlay (47 kB) stays in `main`
because `provideSpartanHlm()` needs it. Keep the default budget. Unit tests of a component with `@defer` use
`DeferBlockBehavior.Manual` and render `DeferBlockState.Complete` before asserting on the deferred part; test that
the placeholder is inert and not a button.

`ng g @spartan-ng/cli:init --stylesEntryPoint=…` is rejected as an unknown argument in 1.10.1 although the schema
lists it: let `init` find `src/styles.css`.

Dark mode: the preset declares `@custom-variant dark (&:is(.dark *))` and the variables switch on
`:root.dark`, so the theme service toggles the `dark` class on `<html>` (same storage and
system-preference logic as the daisyUI service; `classList.toggle('dark', isDark)` instead of
`setAttribute('data-theme', …)`). Toaster: `<hlm-toaster [theme]="theme.current()">`.

## 4. Component map per mode

| Need | daisyui | spartan | hybrid owner |
|---|---|---|---|
| Layout, spacing, typography, responsive, transitions | Tailwind | Tailwind | **Tailwind** |
| Button | `btn` | `hlmBtn` | **daisyUI** `btn` (also on Spartan triggers: `<button class="btn" hlmDialogTrigger>`) |
| Card, badge, alert, loading/skeleton, table, stat | `card`, `badge`, `alert`, `loading`/`skeleton`, `table` | `hlm-card`, `hlmBadge`, `hlmAlert`, `hlmSkeleton`, `hlmTable` | **daisyUI** |
| Text input, textarea, checkbox, radio, toggle, fieldset | `input`, `textarea`, `checkbox`, `fieldset` + `validator` | `hlmInput`, `hlm-field` | **daisyUI** |
| Dialog / alert dialog | native `<dialog class="modal">` | `hlm-dialog`, `hlm-alert-dialog` | **Spartan** |
| Dropdown / account menu | `dropdown` (`<details>`) | `hlmDropdownMenuTrigger` + `hlm-dropdown-menu` (CDK menu: arrows, Esc, focus return) | **Spartan** |
| Select / combobox | native `<select class="select">` | `hlm-select`, combobox | **Spartan** |
| Popover, tooltip | `dropdown`, `tooltip` | `hlm-popover`, `hlm-tooltip` | **Spartan** |
| Toast | `toast` + `alert` in a `role="status"` region | `hlm-toaster` (sonner) | **daisyUI** `toast` |
| Theme foundation | daisyUI themes (`data-theme`) | Spartan variables (`.dark`) | **daisyUI** themes; Spartan variables mapped onto them |

Never ship two implementations of one control. Do not wrap daisyUI CSS classes in Angular components just
to have a component (a `btn` is a class, not a component); create a shared component only when it adds
behaviour or a slot contract (`smart-dumb-components.md`).

## 5. Enforcement

- Edit-time advisory: `post-edit-angular-ui-mode-advisory.sh` runs `angular-ui-mode.sh check-file` on every
  edited `.ts`/`.html`/`.css` in an Angular workspace: unselected-library imports and classes, hybrid
  ownership (daisyUI `modal`/`dropdown`/`select`/`tooltip`; helm card/badge/alert/skeleton/table/spinner),
  a `.dark` class toggle in hybrid, Tailwind 3 `@tailwind` / `@config` and `@import "daisyui"`.
  Exempt one line with `ui-mode-ok: <reason>` on it or the line above. Generated `libs/ui/**` is skipped.
- Workspace check (`/verify`, reviewers, CI): `angular-ui-mode.sh detect <workspace>` — the declared
  mode matches the packages, the global stylesheet matches the packages, `components.json` exists iff Spartan
  is installed, hybrid declares the `data-theme` dark variant, and `--border` is never a colour while daisyUI is
  installed (§6). `<hlm-alert-dialog>` is Spartan-owned and is not flagged as the daisyUI-owned alert.

## 6. Hybrid: tokens, dark mode and collisions

daisyUI's theme is the single source of truth; Spartan's variables are mapped onto it, so a Spartan
overlay and a daisyUI card use the same colours, radius and focus ring in both themes.

Set up: the daisyUI step, then the Spartan steps (§3) with `init --theme=neutral` and only the Spartan-owned
components (`dropdown-menu`, `popover`, `select`, `alert-dialog`; alert-dialog pulls in the Helm button, which stays
unrendered). Then replace the `:root` / `:root.dark` palette `init` wrote with the mapping below. Verified on
Angular 22.3.0, Tailwind 4.3.5, daisyUI 5.8.2, Spartan 1.10.1 (66/66 Playwright twice, axe 0 violations with each
overlay open in both themes).

```css
/* src/styles.css (hybrid) */
@layer theme, base, components, utilities;
@import 'tailwindcss/theme.css' layer(theme);
@import 'tailwindcss/preflight.css' layer(base);
@import 'tailwindcss/utilities.css';                    /* unlayered, as spartan init writes it */
@import '@spartan-ng/brain/hlm-tailwind-preset.css';
/* One dark switch for both libraries: redefine the preset's `.dark` variant onto daisyUI's data-theme. */
@custom-variant dark (&:where([data-theme='dark'], [data-theme='dark'] *));
@plugin 'daisyui' { themes: light --default, dark --prefersdark; }
@plugin 'daisyui/theme' { name: 'light'; default: true; --color-error: oklch(50% 0.2 27); --color-error-content: oklch(98% 0.01 27); }

/* Spartan variables read daisyUI's theme: set once, both themes follow data-theme. */
:root {
  --radius: var(--radius-box);
  --background: var(--color-base-100);   --foreground: var(--color-base-content);
  --card: var(--color-base-100);         --card-foreground: var(--color-base-content);
  --popover: var(--color-base-100);      --popover-foreground: var(--color-base-content);
  --primary: var(--color-primary);       --primary-foreground: var(--color-primary-content);
  --secondary: var(--color-base-200);    --secondary-foreground: var(--color-base-content);
  --muted: var(--color-base-200);        --muted-foreground: color-mix(in oklab, var(--color-base-content) 70%, transparent);
  --accent: var(--color-base-200);       --accent-foreground: var(--color-base-content);
  --destructive: var(--color-error);
  --input: color-mix(in oklab, var(--color-base-content) 20%, transparent); /* = daisyUI .input border */
  --ring: var(--color-base-content);
  /* NO --border here: daisyUI 5 uses --border as the border WIDTH (1px). */
}
@theme inline { --color-border: var(--color-base-300); }
@layer base { * { @apply border-border outline-ring/50; } body { @apply bg-background text-foreground; } }
```

| Finding (measured in the reference app) | Rule |
|---|---|
| `--border` means width in daisyUI and colour in Spartan; mapping it to a colour gave `.input`, `.btn` and fieldsets a 0 px border | never set `--border`; Spartan's border colour goes through `--color-border` (a computed-style test guards it) |
| `--color-primary`: daisyUI's value (`@layer base`) beats Spartan's `@theme inline` alias (`@layer theme`), so `--primary: var(--color-primary)` does not loop | keep the mapping one-way, daisyUI → Spartan |
| Tailwind colour utilities follow Spartan names: `bg-secondary` / `bg-accent` resolve to the neutral `base-200` above | daisyUI's brand secondary/accent are reached through daisyUI component classes (`btn-secondary`), not the utilities |
| The preset's `.dark` variant | redefined after the preset: compiled CSS has no `.dark` selector; never toggle a `dark` class (`check-file` flags it) |
| `spartan init` leaves utilities unlayered, so daisyUI becomes a top-level layer | keep the official form: utilities still beat daisyUI and the CDK overlay CSS; the `* { border-color }` base rule loses to daisyUI components |
| Class names: 75 daisyUI class names vs 61 Helm files, and every class on open overlays at runtime | 0 collisions; no prefix |

**Budget.** The deferred account menu (§3 rule: import Helm classes, not `Hlm*Imports`) took the initial bundle from
549.5 to 500.7 kB. The rest is the CDK overlay `provideSpartanHlm()` pulls into `main` (84.5 kB measured: 416 kB
without it); it is what stacks overlays in the CDK container, so keep it and set the initial `maximumWarning` to
`550kB` in `angular.json` with that reason recorded (error stays at `1MB`). Playwright reads of overlay styles use
`expect.poll` (highlight transitions and CDK repositioning after scroll are asynchronous).

**No daisyUI prefix.** `prefix: 'd-'` renames classes only; the one real collision is a CSS variable
(`--border`), which a prefix does not touch. Add a prefix only if a class collision is measured.

**Ownership in practice:** daisyUI `btn` goes on every trigger (`<button class="btn" hlmAlertDialogTrigger>`) and in
the dialog footer; no `.modal`, `.dropdown` or native `<dialog>` and no `hlmBtn` render in a hybrid page (an
ownership E2E counts them). Overlays render in the CDK container (z-index 1000) above a sticky `z-10` navbar.

**Spartan select in forms (Helm edits):** forward an `aria-describedby` input from `hlm-select-trigger` to its inner
button so the error text is announced:

```ts
// libs/ui/select/src/lib/hlm-select-trigger.ts (app edit): on the inner <button> add
//   [aria-describedby]="ariaDescribedBy()"
public readonly ariaDescribedBy = input<string | null>(null, { alias: 'aria-describedby' });
```

Signal Forms `focusBoundControl()` focuses the element carrying `[formField]`, which for the select is the
non-focusable `<hlm-select>` host, so `onInvalid` focuses the trigger button for that field:

```ts
private readonly productTrigger = viewChild.required(HlmSelectTrigger, { read: ElementRef<HTMLElement> });
// form(..., { submission: { action: ..., onInvalid: (f) => this.focusFirstInvalid(f().errorSummary()[0]?.fieldTree) } })
private focusFirstInvalid(fieldTree: ReadonlyFieldTree<unknown> | undefined): void {
  if (!fieldTree) return;
  if (fieldTree === this.orderForm.product) this.productTrigger().nativeElement.querySelector('button')?.focus();
  else fieldTree().focusBoundControl();
}
```

Unit tests of the Brain select stub
`ResizeObserver` and `scrollIntoView` (absent in jsdom); E2E type-ahead waits for the highlighted option (the CDK
buffers keys for 200 ms).

**Guards to keep in a hybrid app:** a computed-style test that Spartan surfaces equal the daisyUI tokens
(background, text, radius, border width) in both themes; a static probe of daisyUI class names in `libs/ui`;
axe and keyboard runs with each overlay open; the `check-file` ownership rules.

## 7. Verification per mode

Every mode: `ng test --watch=false`, `ng build`, `ng lint`, `tsc` (app, spec, e2e), Playwright + axe
(wcag2a/2aa/21a/21aa/22aa) in light **and** dark, keyboard, 375/768/1280 without horizontal scroll,
`angular-ui-mode.sh detect` exit 0.

- **spartan / hybrid:** run axe and keyboard tests with each overlay open (menu, select listbox, popover,
  dialog). Overlays render in the CDK container on `document.body`: unit tests query `[role=dialog]` there.
  In a page spec, `fixture.whenStable()` waits on a pending `rxResource` request: flush it first.
  The dialog's `(closed)` output emits `unknown`; type the handler parameter as `unknown` and narrow.
  Never disable the button that opens a confirm dialog while it is open: the CDK cannot return focus to it.
- **Dependency audit:** `npm audit --audit-level=high` is the gate. For Spartan, uninstall `@spartan-ng/cli`
  after generating (§3) so the gate stays green.
- **Theme storage:** unit and E2E tests make the `localStorage` **getter** throw (site data blocked) and assert the
  app boots and the theme still toggles; a mocked `getItem` alone misses the boot failure.
