# Performance

> RECOMMENDED PRACTICE. Correct first, profile, then optimise the proven bottleneck
> (`.claude/rules/code-standards.md` Performance). Core Web Vitals: `web-performance-optimization` skill.

## React Compiler 1.0 (stable)

```ts
// vite.config.ts (verified: build output contains react.memo_cache_sentinel, i.e. compiled components)
import babel from '@rolldown/plugin-babel'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({ plugins: [react(), babel({ presets: [reactCompilerPreset()] })] })
```

- `babel-plugin-react-compiler@1.0.0`, `@vitejs/plugin-react@6.3.0` (peer `babel-plugin-react-compiler ^1.0.0`,
  `@rolldown/plugin-babel ^0.1.7 || ^0.2.0 || ^0.3.0`), `@rolldown/plugin-babel@0.3.1`.
- Adoption decision (2026-11-23, React 19.3.1 build): **on**. `vite build` exit 0 and every app chunk
  (`index`, `LoginPage`, `ProjectsPage`, `SettingsPage`) contains `react.memo_cache_sentinel`; the
  compiler-powered `react-hooks/immutability` rule caught a real use-before-declaration in an Action
  (`forms.md`). Existing `useMemo`/`useCallback` stays until the component has tests (policy below).
- `react({ compiler: true })` (native port) is experimental in plugin-react 6: not the default.
- The compiler assumes the Rules of React; `eslint-plugin-react-hooks` 7 (`recommended` preset) reports
  code it cannot compile safely. Fix the reported code rather than disabling the rule.

## Memoization policy

- New code: no `useMemo`/`useCallback`/`memo` unless (a) a value is an effect dependency whose identity
  matters, or (b) a React DevTools Profiler trace shows the win.
- Existing memoization: keep it until the component has tests; removing it can change effect timing.

## Rendering

- Keys from stable ids. Index keys on reorderable lists move state to the wrong row.
- Lists beyond ~100 rows: virtualize (`@tanstack/react-virtual` 3.14.x —
  **UNVERIFIED in this app; check before use**). Threshold is a starting point; measure.
- Expensive non-urgent updates (filtering a large list while typing): `useDeferredValue` for the derived
  value or `startTransition` for the state update, instead of debouncing render work.
- `<Activity mode="hidden">` (React 19.2+) keeps hidden tab state without unmounting
  (export verified in 19.3.1; behaviour **UNVERIFIED here**).

## Animating with `<ViewTransition>` (React 19.3, stable) — tested

`ViewTransition` and `addTransitionType` are exported by `react@19.3.1` (`@types/react` marks both
`@version 19.3.0`). Only updates marked as Transitions animate (`startTransition`, `useDeferredValue`,
Actions, a `<Suspense>` reveal); urgent updates commit immediately.

`src/features/settings/components/SettingsTabs.tsx`

```tsx
import { addTransitionType, startTransition, useState, ViewTransition } from 'react'

const tabs = ['Profile', 'Notifications', 'Privacy'] as const
type Tab = (typeof tabs)[number]

/**
 * React 19.3 <ViewTransition>: animates only updates marked as Transitions. addTransitionType picks the
 * direction; the CSS classes `slide-from-right` etc. live in index.css. Without View Transition support
 * the update simply commits.
 */
export function SettingsTabs({ panels }: { panels: Record<Tab, string> }) {
  const [active, setActive] = useState<Tab>('Profile')

  function select(next: Tab) {
    startTransition(() => {
      addTransitionType(tabs.indexOf(next) > tabs.indexOf(active) ? 'forward' : 'back')
      setActive(next)
    })
  }

  return (
    <section aria-label="Settings sections">
      <div role="group" aria-label="Section">
        {tabs.map((tab) => (
          <button key={tab} type="button" aria-pressed={tab === active} onClick={() => select(tab)}>
            {tab}
          </button>
        ))}
      </div>
      <ViewTransition
        key={active}
        enter={{ forward: 'slide-from-right', back: 'slide-from-left', default: 'none' }}
        exit={{ forward: 'slide-to-left', back: 'slide-to-right', default: 'none' }}
      >
        <div>
          <h2>{active}</h2>
          <p>{panels[active]}</p>
        </div>
      </ViewTransition>
    </section>
  )
}
```

CSS appended to `src/index.css` (classes chosen by transition type; reduced motion respected):

```css
::view-transition-old(.slide-to-left) { animation: 180ms ease-in both vt-out-left; }
::view-transition-new(.slide-from-right) { animation: 180ms ease-out both vt-in-right; }
::view-transition-old(.slide-to-right) { animation: 180ms ease-in both vt-out-right; }
::view-transition-new(.slide-from-left) { animation: 180ms ease-out both vt-in-left; }
@keyframes vt-out-left { to { transform: translateX(-2rem); opacity: 0; } }
@keyframes vt-in-right { from { transform: translateX(2rem); opacity: 0; } }
@keyframes vt-out-right { to { transform: translateX(2rem); opacity: 0; } }
@keyframes vt-in-left { from { transform: translateX(-2rem); opacity: 0; } }
@media (prefers-reduced-motion: reduce) { ::view-transition-group(*), ::view-transition-old(*), ::view-transition-new(*) { animation: none !important; } }
```

`src/features/settings/components/SettingsTabs.test.tsx`

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { SettingsTabs } from './SettingsTabs'

const panels = { Profile: 'Name and avatar', Notifications: 'Email digests', Privacy: 'Data export' }

describe('SettingsTabs (ViewTransition + addTransitionType)', () => {
  it('switches panels inside a Transition; jsdom has no startViewTransition, so React just commits', async () => {
    expect('startViewTransition' in document).toBe(false)
    render(<SettingsTabs panels={panels} />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Privacy' }))
    expect(await screen.findByRole('heading', { name: 'Privacy' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Privacy' })).toHaveAttribute('aria-pressed', 'true')
  })
})
```

- Chromium: the Playwright spec wraps `document.startViewTransition` and asserts React called it on the
  tab switch (`security.md`). Control: calling `setActive(next)` outside `startTransition` → 0 view
  transitions, test fails.
- Wrap a `<Suspense>` boundary in `<ViewTransition update="auto" default="none">` to animate only the
  fallback → content reveal (react.dev blog guidance); not exercised here.
- Keep animations short, and remove them under `prefers-reduced-motion` (WCAG 2.2 2.3.3 guidance in
  `accessibility-audit`).

## Loading

- Route-level code splitting with `lazy` (see `routing.md`); the validation build emitted
  `LoginPage-*.js` and `ProjectsPage-*.js` chunks separate from `index-*.js`.
- Read the `vite build` size table on every change that adds a dependency; investigate any chunk that
  grows by more than a few kB gzip. For a treemap, `rollup-plugin-visualizer` (7.1.x —
  **UNVERIFIED with Vite 8 here**).
- Avoid request waterfalls: start route data early (a route `loader` can call
  `queryClient.ensureQueryData(...)`), and fetch independent queries in parallel (sibling `useQuery`s,
  not nested components that each wait for the parent).
- Set a deliberate `staleTime` so navigation does not refetch everything.

## Profiling

1. React DevTools Profiler: record the interaction, find components with long or repeated renders.
2. Chrome Performance panel (or the Chrome DevTools MCP `performance_start_trace`) for long tasks, layout
   and INP.
3. Change one thing, measure again, report numbers ("list filter: 180 ms → 35 ms per keystroke").
