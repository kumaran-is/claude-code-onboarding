# Tailwind CSS v4 + shadcn/ui (Base UI)

> RECOMMENDED PRACTICE. Validated 2026-11-24 in a disposable app built from `/scaffold-react-app`'s steps on
> Node 26.13.1: `tsc -b`, `eslint .`, `vitest run` (59 tests), `vite build`, `playwright test` (54 tests: 27 ×
> 375 and 1280 px) and `npm audit --audit-level=high` all exit 0. Planted faults fail each gate (table at the
> end). Sources: ui.shadcn.com (installation/vite, cli, components-json, theming, dark-mode/vite, forms,
> changelog 2026-07 "Base UI as the default"), tailwindcss.com (v4.3 docs, upgrade guide), the installed
> `node_modules/*/package.json` and `.d.ts`. The official `shadcn` skill is vendored at `.claude/skills/shadcn/`:
> load it for component rules, CLI commands and registries; this file holds what that skill does not cover
> (the toolkit's pins, the SPA wiring, the tests and the evidence).

## Decisions

| Topic | Decision | Why |
|---|---|---|
| Primitive library | **Base UI** (`@base-ui/react` 1.9.0, `-b base`) for new apps | shadcn default since 2026-07 ("Radix is still fully supported"); one component family keeps a11y behaviour uniform |
| Radix | only in a project that already uses it (`-b radix`, unified `radix-ui` package) | never mix primitives in one app: two focus-trap, portal and `asChild`/`render` models |
| React Aria (`-b aria`) | not evaluated | no validation run; check before use |
| Style / base colour / icons | `base-nova` / `neutral` / `lucide` (what `init -p nova` writes) | change only through the CLI (`apply --only theme`); `style` cannot change after `init` |
| Toast | shadcn `toast` (Base UI) | the `shadcn` skill's rule for Base UI projects; `sonner` is for Radix/Aria projects and its generated wrapper imports `next-themes` |
| Data table | shadcn `Table` + `@tanstack/react-table` 9.3.1 | the v9 API differs from v8 (below) |
| Forms | shadcn `FieldGroup` + `Field` + React Hook Form `Controller` + zod 4 | the forms page's current recommendation; `Form`/`FormField` are not on the current pages |
| Official shadcn skill | **adopted, vendored** (`.claude/skills/shadcn/`, MIT, commit 4233ed1, CLI pinned to 4.23.0, load-time shell command removed) | measured: the reference app, written without it, broke 8 of its rules (sonner on Base UI, items outside groups, hand-rolled empty state and callouts, icons without `data-icon`, `isPending` button text instead of `Spinner`, looped buttons instead of `ToggleGroup`, a form without `FieldGroup`); all fixed and re-verified |
| shadcn MCP server | **not adopted (DEFER)** | its 7 tools (list/search/view items, examples, add command, audit checklist) duplicate the pinned CLI (`search`, `view`, `docs`, `add --dry-run`/`--diff`) that the skill already drives; adopting it means a new `.mcp.json` entry and allowlist review for no new capability |
| TypeScript | 6.0.3 | TS 7.0.2 type-checks this app (`tsc -b` exit 0) but `typescript-eslint@8.74.0` peers `<6.1.0` (`tooling.md`) |

## Versions (exact pins, verified together)

| Package | Version | Kind |
|---|---|---|
| `tailwindcss`, `@tailwindcss/vite` | `4.3.5` | dev |
| `tw-animate-css` | `1.4.0` | dev (CSS import) |
| `shadcn` (CLI; also provides `shadcn/tailwind.css`) | `4.23.0` | dev |
| `@base-ui/react` | `1.9.0` | runtime |
| `cn` (class merging, replaces `clsx` + `tailwind-merge`; published from the shadcn-ui repo) | `0.5.2` | runtime |
| `class-variance-authority` | `0.7.1` | runtime |
| `lucide-react` | `1.79.0` | runtime |
| `@fontsource-variable/geist` | `5.3.0` | runtime |
| `@tanstack/react-table` | `9.3.1` | runtime |

The CLI writes caret ranges and puts build-only packages in `dependencies`: pin every one exactly and move
`shadcn`, `tailwindcss`, `@tailwindcss/vite` and `tw-animate-css` to `devDependencies`. Full `package.json`:
`tooling.md`.

## Install (after the scaffold's TypeScript and Vite steps)

```bash
npm i -DE tailwindcss@4.3.5 @tailwindcss/vite@4.3.5
printf '@import "tailwindcss";\n' > src/index.css   # init exits 1 "No Tailwind CSS configuration found" without it
# vite.config.ts: plugins: [react(), tailwindcss(), babel({ presets: [reactCompilerPreset()] })]  (tooling.md)
# root tsconfig.json: "compilerOptions": { "paths": { "@/*": ["./src/*"] } }  (the CLI reads the ROOT file)
npx shadcn@4.23.0 init --base base -p nova --yes --no-monorepo </dev/null
npx shadcn@4.23.0 add button card input label field dialog dropdown-menu table skeleton toast empty alert spinner toggle-group </dev/null
npm i -E @base-ui/react@1.9.0 cn@0.5.2 class-variance-authority@0.7.1 lucide-react@1.79.0 @fontsource-variable/geist@5.3.0
npm i -DE shadcn@4.23.0 tw-animate-css@1.4.0
```

- `init --base base --yes` alone still prompts for a preset; without a TTY it exits 0 having written
  nothing. Pass `-p <preset>` and redirect stdin. Re-running needs `--force --no-reinstall`.
- Never pass `-t/--template` to an existing app: it creates a new project.
- The `src/index.css` line comes first: on the `create-vite` template stylesheet `init` exits 1 (reproduced
  2026-11-24 by an independent review); with only `@import "tailwindcss";` it exits 0 and writes a
  `components.json` byte-identical to the reference app's.
- After `init`: re-pin the new dependencies (the two `npm i -E` lines above), then merge the scaffold's base layer into
  `src/index.css` (`tooling.md` holds the full file).

As written by `init` (`tailwind.config` stays empty for v4):

`components.json`

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "base-nova",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/index.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "iconLibrary": "lucide",
  "rtl": false,
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "menuColor": "default",
  "menuAccent": "subtle",
  "registries": {}
}
```

## Tailwind v4 rules

- CSS-first: `@import "tailwindcss"` and the Vite plugin. No `tailwind.config.js`, no `@tailwind base`
  directives, no `postcss` + `autoprefixer` setup.
- Tokens: shadcn variables in `:root` / `.dark` (OKLCH), mapped with `@theme inline` so utilities read the
  variable's value (`bg-background`, `text-muted-foreground`). Use `@theme` (not `inline`) for new tokens
  that should also be emitted as theme variables.
- Dark mode: `@custom-variant dark (&:is(.dark *));` plus the `.dark` class on `<html>`. Components use
  semantic tokens; no raw palette colours and no manual `dark:` colour overrides (shadcn styling rule).
- Container queries: `@container` on the parent, `@lg:inline` on the child (the header's text labels in
  `AppLayout`, `routing.md`). Named containers: `@container/main` + `@lg/main:…`.
- v3 names removed or renamed: `shadow-sm`→`shadow-xs`, `shadow`→`shadow-sm`, `rounded-sm`→`rounded-xs`,
  `outline-none`→`outline-hidden`, `ring`→`ring-3` (1 px default), `bg-opacity-*`→`bg-black/50`,
  `flex-shrink-*`→`shrink-*`, important modifier at the end (`flex!`). Browser floor: Safari 16.4, Chrome 111,
  Firefox 128.
- 4.3 additions worth knowing: `@container-size`, `scrollbar-*` utilities, stacked/compound `@variant`,
  `--default(...)` in functional `@utility`. Use them only when the browser floor allows.

## Components are app-owned source: update strategy

`src/components/ui/*` is code the CLI copied into the app; the app owns it, reviews it and tests it.

1. Record the CLI version (`shadcn` in `devDependencies`) and the primitive (`npx shadcn@4.23.0 info --json` →
   `base`).
2. To pick up upstream changes: `npx shadcn@4.23.0 add <name> --dry-run`, then `--diff <file>` per file.
   Files without local edits can be overwritten; files with local edits are merged by hand. `--overwrite`
   (or `add --all --overwrite`) only with the human's explicit approval, after a commit.
3. Moving the CLI version: change the pin, run the diff loop, then the full gate (`tsc -b`, ESLint, Vitest,
   build, Playwright + axe in both themes).
4. A token that fails contrast is fixed in `src/index.css`, not per component. The light `--destructive`
   default (`oklch(0.577 0.245 27.325)`) fails axe `color-contrast`; this app uses `oklch(0.505 0.2 27.5)`.
5. `migrate radix` / `migrate cn` / `migrate icons` are CLI codemods; there is no Base UI migrate command
   (upstream ships a separate `migrate-radix-to-base` agent skill, not vendored here).

Lint: the `src/components/ui/**` override in `eslint.config.js` (`tooling.md`) turns off only
`react-refresh/only-export-components` and `jsx-a11y-x/label-has-associated-control` for generated files.

## Theme: provider, hook and menu

Class strategy from ui.shadcn.com/docs/dark-mode/vite. The hook lives in its own file because
`react-refresh/only-export-components` rejects a hook and a component exported from one file. The choice is
a UI preference, not a secret, so `localStorage` is acceptable here (never for tokens).

`src/shared/ui/theme-context.ts`

```ts
import { createContext, use } from 'react'
import { logger } from '@/shared/lib/logger'

export type Theme = 'light' | 'dark' | 'system'
export const themes: readonly Theme[] = ['light', 'dark', 'system']

export type ThemeContextValue = { theme: Theme; setTheme: (theme: Theme) => void }

export const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)

/** Reads the theme choice. Throws outside <ThemeProvider> so a missing provider fails loudly. */
export function useTheme(): ThemeContextValue {
  const value = use(ThemeContext)
  if (!value) throw new Error('useTheme must be used within a ThemeProvider')
  return value
}

/** Stored choice if it is a valid theme, else `fallback`. A UI preference, not a secret: localStorage is fine. */
export function readStoredTheme(storageKey: string, fallback: Theme): Theme {
  try {
    const stored = window.localStorage.getItem(storageKey)
    return themes.find((theme) => theme === stored) ?? fallback
  } catch (error) {
    logger.error('theme preference could not be read', { error: String(error) })
    return fallback
  }
}

/** Puts `light` or `dark` on <html> for a theme choice (`system` resolves through prefers-color-scheme). */
export function applyTheme(theme: Theme): void {
  const resolved = theme === 'system' ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : theme
  document.documentElement.classList.remove('light', 'dark')
  document.documentElement.classList.add(resolved)
}

/** Call before the first render so the stored theme is on <html> before paint (no flash); the provider handles later changes. */
export function applyStoredTheme(storageKey = 'vite-ui-theme'): void {
  applyTheme(readStoredTheme(storageKey, 'system'))
}
```

`src/shared/ui/theme-provider.tsx`

```tsx
import { useEffect, useState, type ReactNode } from 'react'
import { logger } from '@/shared/lib/logger'
import { applyTheme, readStoredTheme, ThemeContext, type Theme } from './theme-context'

type ThemeProviderProps = { children: ReactNode; defaultTheme?: Theme; storageKey?: string }

/**
 * Class strategy from ui.shadcn.com/docs/dark-mode/vite: `light` or `dark` on <html>, `system` follows
 * prefers-color-scheme. The effect syncs React state with an external system (the DOM class and a media query).
 */
export function ThemeProvider({ children, defaultTheme = 'system', storageKey = 'vite-ui-theme' }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(() => readStoredTheme(storageKey, defaultTheme))

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => applyTheme(theme)
    apply()
    if (theme !== 'system') return
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [theme])

  function setTheme(next: Theme) {
    try {
      window.localStorage.setItem(storageKey, next)
    } catch (error) {
      logger.error('theme preference could not be saved', { error: String(error) })
    }
    setThemeState(next)
  }

  return <ThemeContext value={{ theme, setTheme }}>{children}</ThemeContext>
}
```

`src/shared/ui/icons.ts`: the one place the app imports the icon package (`check-design-system.py` DS-ICON-ISOLATION);
feature and app code import from here.

```ts
export { ArrowDownIcon, ArrowUpDownIcon, ArrowUpIcon, FolderIcon, MenuIcon, MonitorIcon, MoonIcon, SunIcon } from 'lucide-react'
```

`src/shared/ui/mode-toggle.tsx`

```tsx
// Tier: Atom
import { MonitorIcon, MoonIcon, SunIcon } from './icons'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { themes, useTheme, type Theme } from './theme-context'

function isTheme(value: unknown): value is Theme {
  return themes.some((theme) => theme === value)
}

/**
 * Light / Dark / System menu (ui.shadcn.com/docs/dark-mode/vite). Presentational: reads only the theme context.
 * Radio items expose the selected theme (aria-checked) to assistive technology.
 */
export function ModeToggle() {
  const { theme, setTheme } = useTheme()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="outline" size="icon" />}>
        <SunIcon className="scale-100 dark:scale-0" aria-hidden="true" />
        <MoonIcon className="absolute scale-0 dark:scale-100" aria-hidden="true" />
        <span className="sr-only">Toggle theme (current: {theme})</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuRadioGroup
          value={theme}
          onValueChange={(value) => {
            if (isTheme(value)) setTheme(value)
          }}
        >
          <DropdownMenuRadioItem closeOnClick value="light">
            <SunIcon data-icon="inline-start" aria-hidden="true" /> Light
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem closeOnClick value="dark">
            <MoonIcon data-icon="inline-start" aria-hidden="true" /> Dark
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem closeOnClick value="system">
            <MonitorIcon data-icon="inline-start" aria-hidden="true" /> System
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
```

`main.tsx` wraps the router in `<ThemeProvider>` and renders the `<Toaster />` from
`@/components/ui/toast` (`routing.md`). Unit tests: `src/shared/ui/mode-toggle.test.tsx` asserts the menu
opens with ArrowDown/Enter, each item sets or removes the `dark` class and persists the choice, and
`system` follows a stubbed `matchMedia`.

## Forms with `Field`, dialogs, menus, table and toast

- `Field` does not link ids. `FieldError` renders `role="alert"`, but `aria-invalid` and `aria-describedby`
  (hint id + error id) go on the control by hand; `data-invalid` goes on `Field`. `Controller` passes
  `field.ref`, so React Hook Form still focuses the first invalid field. Code: `forms.md` (`ProjectForm`).
- Submit buttons show progress with `Spinner` (`aria-hidden`) + `disabled`, and keep a text label
  ("Creating…"), never an `isPending` prop.
- Base UI composes custom triggers with `render={<Button />}` (no `asChild`). Menu items sit inside
  `DropdownMenuGroup`; every dialog has a `DialogTitle`.
- Toast: `toast.add({ title, type: 'success' })` from `@/components/ui/toast`; it has `role="dialog"`
  (`aria-modal="false"`), so tests query a dialog by name. State lives in the provider, so tests need no
  cleanup between cases.
- TanStack Table v9: `tableFeatures({ rowSortingFeature, sortedRowModel: createSortedRowModel(), sortFns })`,
  `createColumnHelper<typeof features, T>()`, `useTable({ features, columns, data })`, `<table.FlexRender>`.
  Keep `features` and `columns` at module scope. Sort headers are buttons and the header cell carries
  `aria-sort`. Code: `server-state-and-api.md` (`ProjectList`). The package ships its own agent docs in
  `node_modules/@tanstack/react-table/skills`.

## Browser tests for themes, dialog and menu

Shared helpers (`signIn`, `mockProjects`, `axeViolations` that waits for finite animations): `testing.md`
(`e2e/support.ts`).

Base UI's modal focus trap wraps through a focus-guard `<span data-base-ui-focus-guard>` and moves focus back
**asynchronously**. A test that reads `document.activeElement` straight after `Tab` sees the guard or `<body>`
and skips a field: the first version of the trap test failed under `--fail-on-flaky-tests` that way. The spec
below waits for focus to settle, then requires every stop to be inside the dialog and all four controls to be
reached (60/60 runs, retries off). Control: `<Dialog modal={false}>` fails it ("Tab 4 left the dialog").
Known limitation (Base UI 1.9.0): a `Tab` pressed before the dialog's initial focus lands (the first frames
after opening) can reach a control behind it; the test waits for initial focus, as a user effectively does.

`e2e/themes-a11y.spec.ts`

```ts
import { expect, test } from './fixtures.ts'
import { axeViolations, chooseTheme, mockProjects, openNavIfCollapsed, signIn } from './support.ts'

for (const mode of ['Light', 'Dark'] as const) {
  test.describe(`axe in ${mode} mode`, () => {
    test(`projects page, dialog open, and theme menu open`, async ({ page }) => {
      await mockProjects(page)
      await signIn(page)
      await expect(page.getByRole('table', { name: 'Projects' })).toBeVisible()
      await chooseTheme(page, mode)
      await expect(page.locator('html')).toHaveClass(mode === 'Dark' ? /\bdark\b/ : /\blight\b/)

      expect(await axeViolations(page), `${mode}: page`).toEqual([])

      // Dialog open, with validation errors showing.
      await page.getByRole('button', { name: 'New project' }).click()
      const dialog = page.getByRole('dialog', { name: 'New project' })
      await expect(dialog).toBeVisible()
      await dialog.getByRole('button', { name: 'Create project' }).click()
      await expect(dialog.getByLabel('Project name')).toHaveAttribute('aria-invalid', 'true')
      expect(await axeViolations(page), `${mode}: dialog open`).toEqual([])
      await page.keyboard.press('Escape')
      await expect(dialog).toBeHidden()

      // Menu open.
      await page.getByRole('button', { name: /Toggle theme/ }).click()
      await expect(page.getByRole('menu')).toBeVisible()
      expect(await axeViolations(page), `${mode}: menu open`).toEqual([])
      await page.keyboard.press('Escape')
      await expect(page.getByRole('menu')).toBeHidden()

      // Settings page with the danger zone open (destructive button colours).
      await page.route('**/api/announcement', (route) => route.fulfill({ json: { html: '<b>Notice</b>' } }))
      await page.route('**/api/release-notes', (route) => route.fulfill({ json: ['Faster search'] }))
      await openNavIfCollapsed(page)
      await page.getByRole('link', { name: 'Settings' }).click()
      await page.getByRole('button', { name: 'Danger zone' }).click()
      await expect(page.getByRole('button', { name: 'Delete account' })).toBeFocused()
      expect(await axeViolations(page), `${mode}: settings, danger zone open`).toEqual([])
    })
  })
}

test.describe('dark mode', () => {
  test('toggle persists after reload', async ({ page }) => {
    await mockProjects(page)
    await signIn(page)
    await chooseTheme(page, 'Dark')
    await expect(page.locator('html')).toHaveClass(/\bdark\b/)
    expect(await page.evaluate(() => window.localStorage.getItem('vite-ui-theme'))).toBe('dark')

    await page.reload()
    // The in-memory demo session is gone after a reload: sign in again, the theme must still be dark.
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
    await expect(page.locator('html')).toHaveClass(/\bdark\b/)
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme)).toBe('dark')

    await page.getByLabel('Name').fill('Dana')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()
    await chooseTheme(page, 'Light')
    await page.reload()
    await expect(page.locator('html')).not.toHaveClass(/\bdark\b/)
  })

  test('System follows the emulated OS colour scheme', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'dark' })
    await mockProjects(page)
    await signIn(page)
    await chooseTheme(page, 'System')
    await expect(page.locator('html')).toHaveClass(/\bdark\b/)
    await page.emulateMedia({ colorScheme: 'light' })
    await expect(page.locator('html')).not.toHaveClass(/\bdark\b/)
  })
})

for (const mode of ['Light', 'Dark'] as const) {
  test(`keyboard focus indicator is a visible outline in ${mode} mode`, async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
    if (mode === 'Dark') await page.evaluate(() => window.localStorage.setItem('vite-ui-theme', 'dark'))
    await page.reload()
    await expect(page.locator('html')).toHaveClass(mode === 'Dark' ? /\bdark\b/ : /\blight\b/)

    const outline = (locator: ReturnType<typeof page.locator>) =>
      locator.evaluate((el) => {
        const style = getComputedStyle(el)
        return { style: style.outlineStyle, width: parseFloat(style.outlineWidth) }
      })

    // Tab order on /login: the Name input, then the Sign in button.
    await page.keyboard.press('Tab')
    const input = page.getByLabel('Name')
    await expect(input).toBeFocused()
    expect(await outline(input), 'input focus outline').toMatchObject({ style: 'solid' })
    expect((await outline(input)).width).toBeGreaterThanOrEqual(2)

    await page.keyboard.press('Tab')
    const button = page.getByRole('button', { name: 'Sign in' })
    await expect(button).toBeFocused()
    expect(await outline(button), 'button focus outline').toMatchObject({ style: 'solid' })
    expect((await outline(button)).width).toBeGreaterThanOrEqual(2)
  })
}
```

`e2e/dialog-menu.spec.ts`

```ts
import { expect, test } from './fixtures.ts'
import { mockProjects, signIn } from './support.ts'

test.describe('keyboard-only flow', () => {
  test('Tab to "New project", Enter, fill, submit; Escape returns focus to the trigger', async ({ page }) => {
    await mockProjects(page)
    await signIn(page)
    await expect(page.getByRole('table', { name: 'Projects' })).toBeVisible()

    // Walk the tab order from the document start until "New project" is focused (bounded: header controls come first).
    await page.locator('body').click({ position: { x: 1, y: 1 } })
    const opener = page.getByRole('button', { name: 'New project' })
    for (let i = 0; i < 12 && !(await opener.evaluate((el) => el === document.activeElement)); i++) {
      await page.keyboard.press('Tab')
    }
    await expect(opener).toBeFocused()

    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: 'New project' })
    await expect(dialog).toBeVisible()
    // Focus moves into the dialog on open.
    await expect.poll(() => dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true)

    await page.getByLabel('Project name').fill('Keyboard')
    await page.keyboard.press('Tab')
    await page.keyboard.type('k@example.com')
    await page.keyboard.press('Enter') // submits the form from the email field
    await expect(page.getByText('Project "Keyboard" created')).toBeVisible()
    await expect(dialog).toBeHidden()
    await expect(opener).toBeFocused()

    // Escape on a re-opened dialog closes it and returns focus again.
    await page.keyboard.press('Enter')
    await expect(dialog).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(opener).toBeFocused()
  })

  test('Tab is trapped inside the open dialog and never reaches the page behind it', async ({ page }) => {
    await mockProjects(page)
    await signIn(page)
    await page.getByRole('button', { name: 'New project' }).click()
    const dialog = page.getByRole('dialog', { name: 'New project' })
    await expect(dialog).toBeVisible()
    await expect.poll(() => dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true)

    // Base UI wraps focus through a focus-guard <span> and redirects it asynchronously, so a reading taken right
    // after the key press can see the guard or <body>. Wait for focus to settle, then require it inside the dialog.
    const settled = () =>
      expect
        .poll(() =>
          page.evaluate(() => {
            const active = document.activeElement
            return !!active && active !== document.body && !active.hasAttribute('data-base-ui-focus-guard')
          }),
        )
        .toBe(true)
    const visited = new Set<string>()
    for (let i = 0; i < 12; i++) {
      await page.keyboard.press('Tab')
      await settled()
      const where = await page.evaluate(() => {
        const active = document.activeElement
        return {
          inside: !!document.querySelector('[role="dialog"]')?.contains(active),
          label: active?.getAttribute('aria-label') || active?.id || active?.textContent?.trim() || active?.tagName || '',
        }
      })
      expect(where.inside, `Tab ${i + 1} left the dialog (focus on "${where.label}")`).toBe(true)
      visited.add(where.label)
    }
    expect(visited.size).toBe(4) // name, email, create, close: every stop, and nothing else
  })

  test('theme menu: ArrowDown/ArrowUp move between items, Enter selects, focus returns to the trigger', async ({ page }) => {
    await mockProjects(page)
    await signIn(page)
    const trigger = page.getByRole('button', { name: /Toggle theme/ })
    await trigger.focus()
    await page.keyboard.press('ArrowDown')
    await expect(page.getByRole('menuitemradio', { name: 'Light' })).toBeFocused()
    // house target size (44 px): the base layer must list every menu item role the components render.
    // offsetHeight is the layout size; getBoundingClientRect would include the menu's scale-in transform.
    const heights = await page
      .getByRole('menuitemradio')
      .evaluateAll((items) => items.map((i) => (i instanceof HTMLElement ? i.offsetHeight : 0)))
    expect(heights).toHaveLength(3)
    for (const height of heights) expect(height).toBeGreaterThanOrEqual(44)
    await page.keyboard.press('ArrowDown')
    await expect(page.getByRole('menuitemradio', { name: 'Dark' })).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('menu')).toBeHidden()
    await expect(page.locator('html')).toHaveClass(/\bdark\b/)
    await expect(trigger).toBeFocused()
    await trigger.click()
    await expect(page.getByRole('menuitemradio', { name: 'Dark', checked: true })).toBeVisible()
    await expect(page.getByRole('menuitemradio', { name: 'Light', checked: false })).toBeVisible()
    await page.keyboard.press('Escape')
  })
})
```

`e2e/responsive-security.spec.ts` (not reproduced) asserts no horizontal overflow at 375 px
(`scrollWidth <= innerWidth`), the collapsible mobile navigation, and that `/login?returnUrl=//evil.example`,
`/\evil.example`, `https://evil.example` and `javascript:` all land on an in-app path while an in-app
`returnUrl` is kept (the control).

## Build assertions: Tailwind and the React Compiler really ran

jsdom cannot see compiled CSS, so a node-environment test reads `dist/` after `vite build` (the file
lives in `build-tests/`, included by `tsconfig.node.json` and `vitest.config.ts`).

`build-tests/tailwind-build.test.ts`

```ts
// @vitest-environment node
import { mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { build } from 'vite'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

/**
 * Runs the real Vite build (vite.config.ts) into a temp dir and inspects the output. This is the guard that fails when
 * the `tailwindcss()` plugin is missing from the Vite config (the CSS would not be compiled) or the React Compiler preset is dropped.
 */
const outDir = mkdtempSync(join(tmpdir(), 'tw-build-'))
let css = ''
let js = ''

beforeAll(async () => {
  await build({ configFile: 'vite.config.ts', logLevel: 'silent', build: { outDir, emptyOutDir: true } })
  const assets = join(outDir, 'assets')
  const files = readdirSync(assets)
  css = files.filter((f) => f.endsWith('.css')).map((f) => readFileSync(join(assets, f), 'utf8')).join('\n')
  js = files.filter((f) => f.endsWith('.js')).map((f) => readFileSync(join(assets, f), 'utf8')).join('\n')
}, 60_000)

afterAll(() => rmSync(outDir, { recursive: true, force: true }))

describe('production build', () => {
  it('compiles Tailwind: used utilities are generated and no @tailwind/@apply/@theme directive is left', () => {
    expect(css).toContain('.bg-background{')
    expect(css).toMatch(/\.sm\\:hidden\{/)
    expect(css).not.toMatch(/@tailwind|@apply|@theme/)
  })

  it('keeps the oklch design tokens and the .dark variant', () => {
    expect(css).toMatch(/--background:oklch\(/)
    expect(css).toMatch(/\.dark\{[^}]*--background:oklch\(/)
    expect(css).toMatch(/:is\(\.dark \*\)|\.dark \*/) // @custom-variant dark compiled into dark: utilities
  })

  it('emits a container query for the @container example', () => {
    expect(css).toContain('@container{container-type:inline-size}')
    expect(css).toMatch(/@container \(width>=32rem\)\{\.\\@lg\\:inline\{display:inline\}/)
  })

  it('keeps the scaffold base styles merged into the layer (44px targets, reduced motion)', () => {
    expect(css).toContain('min-height:44px')
    expect(css).toContain('prefers-reduced-motion')
  })

  it('runs the React Compiler (memo cache in the bundle)', () => {
    expect(js).toContain('react.memo_cache_sentinel')
  })
})
```

## Evidence (2026-11-24)

| Check | Result |
|---|---|
| `tsc -b` / `eslint .` / `vite build` / `npm audit --audit-level=high` | exit 0 each |
| `vitest run` | exit 0, 59 executed, 0 failed |
| `playwright test` | exit 0, 54 executed (375 + 1280 px), 0 flaky, 0 skipped, `retries: 0` |
| React Compiler in the bundle | `react.memo_cache_sentinel` 43× with the preset, 1× without |
| Tailwind in the bundle | `.bg-background{`, 62 `oklch(` values, `.dark{`, `@container (width>=32rem)`, `min-height:44px` |
| TypeScript 7.0.2 probe | `tsc -b --noEmit` exit 0; planted TS2322 exit 1; not adopted (lint) |
| `/verify` web gate (`MODE=pre-pr`, CI, `--fail-on-flaky-tests`) | PASS: typecheck, lint, unit, build, e2e 54, audit |
| E2E stress (`--repeat-each=5 --retries=0`) | 270/270 passed, 0 flaky |

Positive controls (each fails its gate, then passes after revert):

| Planted fault | Failing check |
|---|---|
| `FieldError` id dropped from `aria-describedby` | `ProjectForm.test.tsx` (1 of 4) |
| dialog close button loses its `sr-only` "Close" | axe `button-name` in `themes-a11y.spec.ts` |
| dark `--muted-foreground: oklch(0.32 0 0)` | axe `color-contrast`, the 2 dark tests only |
| `safeReturnPath` returns the raw value | `security.test.tsx` (4) and the open-redirect E2E (10) |
| `tailwindcss()` removed from the Vite plugins | `tailwind-build.test.ts` (2 of 5) |
| `:focus-visible` rule moved back into `@layer base` (shadcn `outline-none` wins) | focus-outline test in `themes-a11y.spec.ts` (4 of 4) |
| `sessionStorage.setItem('token', …)` in `session.signIn` | web-storage test in `responsive-security.spec.ts` (2 of 2) |
| `[role="menuitemradio"]` removed from the 44 px rule | `dialog-menu.spec.ts` theme-menu test (28 px < 44) |
| `<Dialog modal={false}>` | `dialog-menu.spec.ts` trap test ("Tab 4 left the dialog") |
| API request refused (`route.abort('connectionrefused')`) | the `fixtures.ts` network-failure check |

Automated results mean "no automated violations; manual checks required" (keyboard, screen reader, zoom),
never a WCAG conformance claim.
