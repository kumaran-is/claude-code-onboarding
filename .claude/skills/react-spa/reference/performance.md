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

- `babel-plugin-react-compiler@1.0.0`, `@vitejs/plugin-react@6.3.0`, `@rolldown/plugin-babel@0.3.1`.
- `react({ compiler: true })` (native port) is experimental in plugin-react 6: not the default.
- The compiler assumes the Rules of React; `eslint-plugin-react-hooks` 7 `recommended-latest` reports
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
