# Architecture, components, hooks, effects and state

> RECOMMENDED PRACTICE. Snippets marked "tested" were exercised by unit tests in the validation app
> (React 19.3.1; Vitest, `tsc -b`, ESLint: exit 0, 2026-11-23). Blocks with a file path are copied from
> that app with their tests; short fragments (the context example) show usage only.

## Choose the architecture by app complexity

No library is mandatory. Add one when the app shows the need, not in advance.

| App shape | Server data | Client state | Forms |
|---|---|---|---|
| Few screens, little shared data | `use()` with a promise from the parent/loader, or a route `loader` | `useState`/`useReducer`, context | React 19 Actions (`forms.md`) |
| Many screens reading and mutating the same server data | TanStack Query (cache, dedupe, refetch, optimistic + rollback) | local state + URL | React Hook Form + zod + mutations |
| Cross-route client workflows (wizard, editor, offline drafts) | TanStack Query | a small store (Zustand) or Redux Toolkit for large, event-heavy domains | as above |

Rules that hold at every size: server data has one owner (never copied into a store), URL state lives in
the URL, effects only synchronise with external systems, every async path renders pending, error and
empty states, and every request is cancellable (`AbortSignal`).

## Feature layout

See the tree in `SKILL.md`. Rules that make it hold:

- `features/<f>/api/` is the only place that knows URLs; components call query hooks or `queryOptions`.
- `features/<f>/model/` holds zod schemas; types are `z.infer<>` of them (one source for form, parse and type).
- `shared/ui/` components are presentational: no `useQuery`, `useMutation`, `useNavigate`, `useParams`,
  `fetch`. A quick check: `grep -rnE "useQuery|useMutation|useNavigate|useParams|fetch\(" src/shared/ui`
  must print nothing.
- Cross-feature reuse goes through `shared/` (Rule of Three) or a feature's public `index.ts`.

## Components and composition — tested (`src/shared/ui/Card.tsx` + `Card.test.tsx`)

```tsx
import { useId, type ComponentProps, type ReactNode } from 'react'

type CardProps = { title: string; actions?: ReactNode; children: ReactNode }

/** Slot props (title, actions, children) instead of a configuration object. Presentational. */
export function Card({ title, actions, children }: CardProps) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId}>{title}</h2>
      {children}
      {actions && <div>{actions}</div>}
    </section>
  )
}

/** React 19: `ref` is an ordinary prop, so no forwardRef wrapper. */
export function TextInput({ ref, ...props }: ComponentProps<'input'>) {
  return <input ref={ref} {...props} />
}
```

- Keep components small enough that each state branch is readable; extract by responsibility, not by line count.
- Avoid defining components inside components (state resets every render; `react-hooks/static-components`
  in the `recommended` preset of `eslint-plugin-react-hooks` 7 flags it).

## Context (React 19) — tested

```tsx
const ThemeContext = createContext('light')

function ThemeLabel() {
  return <span>{use(ThemeContext)}</span> // use() may also be called conditionally, unlike useContext
}

<ThemeContext value="dark">
  <ThemeLabel />
</ThemeContext>
```

Split contexts by change rate (theme vs current user); a context value that changes re-renders every
consumer. Server data stays in the query cache.

## Reading a promise with `use()` + Suspense + error boundary — tested

`src/features/settings/components/ReleaseNotes.tsx`

```tsx
import { Suspense, use } from 'react'
import { ErrorBoundary, type FallbackProps } from 'react-error-boundary'
import { logger } from '@/shared/lib/logger'

type ReleaseNotesProps = { notesPromise: Promise<string[]>; onRetry: () => void }

function NotesList({ notesPromise }: { notesPromise: Promise<string[]> }) {
  const notes = use(notesPromise) // suspends until resolved; a rejection goes to the nearest error boundary
  if (notes.length === 0) return <p>No release notes yet.</p>
  return (
    <ul aria-label="Release notes">
      {notes.map((note) => (
        <li key={note}>{note}</li>
      ))}
    </ul>
  )
}

function NotesError({ resetErrorBoundary }: FallbackProps) {
  return (
    <div role="alert">
      <p>Release notes could not be loaded.</p>
      <button type="button" onClick={resetErrorBoundary}>
        Retry
      </button>
    </div>
  )
}

/**
 * use(promise) + Suspense + error boundary. The promise is created by the parent (or a route loader),
 * never inside this component's render: a promise created during render is new on every render.
 */
export function ReleaseNotes({ notesPromise, onRetry }: ReleaseNotesProps) {
  return (
    <ErrorBoundary
      FallbackComponent={NotesError}
      onError={(error) => logger.error('release notes failed', { error: String(error) })}
      onReset={onRetry}
      resetKeys={[notesPromise]}
    >
      <Suspense fallback={<p role="status">Loading release notes…</p>}>
        <NotesList notesPromise={notesPromise} />
      </Suspense>
    </ErrorBoundary>
  )
}
```

`src/features/settings/components/ReleaseNotes.test.tsx`

```tsx
import { act, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ReleaseNotes } from './ReleaseNotes'

function Host({ load }: { load: () => Promise<string[]> }) {
  const [notesPromise, setNotesPromise] = useState(load)
  return <ReleaseNotes notesPromise={notesPromise} onRetry={() => setNotesPromise(load())} />
}

// A component that suspends must be rendered inside an awaited act(); a plain render() stays on the fallback.
const renderAsync = (ui: React.ReactElement) => act(async () => void render(ui))

describe('ReleaseNotes (use + Suspense + error boundary)', () => {
  it('shows the Suspense fallback, then the data', async () => {
    // Promise.withResolvers needs lib ES2024; the app targets ES2023.
    let resolve!: (notes: string[]) => void
    const promise = new Promise<string[]>((res) => (resolve = res))
    await renderAsync(<Host load={() => promise} />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading release notes')

    await act(async () => resolve(['Faster search']))
    expect(screen.getByRole('list', { name: 'Release notes' })).toHaveTextContent('Faster search')
  })

  it('shows the error boundary for a rejected promise and recovers on Retry', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const load = vi
      .fn<() => Promise<string[]>>()
      .mockRejectedValueOnce(new Error('HTTP 503'))
      .mockResolvedValue(['Dark mode'])
    await renderAsync(<Host load={load} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Release notes could not be loaded')

    // Retry suspends again, so it also runs in an awaited act().
    await act(async () => screen.getByRole('button', { name: 'Retry' }).click())
    expect(screen.getByRole('list', { name: 'Release notes' })).toHaveTextContent('Dark mode')
  })
})
```

- Create the promise outside the component that reads it (parent state initializer, route loader, or a
  cache such as TanStack Query). A promise created during render is new each render and never settles
  for that render.
- `resetKeys={[notesPromise]}` + `onReset` give the error boundary a real retry (a new promise).
- In tests, render a suspending tree inside an awaited `act()`; a plain `render()` stays on the fallback
  ("A component suspended inside an `act` scope, but the `act` call was not awaited").
- `Promise.withResolvers` needs `lib` ES2024; with the ES2023 lib the test failed `tsc -b` (TS2550).

## DOM access without a wrapper: Fragment refs (React 19.3) — tested

`src/shared/ui/FocusFirst.tsx`

```tsx
import { Fragment, useEffect, useRef, type FragmentInstance, type ReactNode } from 'react'

/**
 * React 19.3 Fragment ref: focuses the first focusable descendant of `children` when `active` turns true,
 * without a wrapper element and without the children exposing a ref prop.
 */
export function FocusFirst({ active, children }: { active: boolean; children: ReactNode }) {
  const ref = useRef<FragmentInstance>(null)
  useEffect(() => {
    if (active) ref.current?.focus()
  }, [active])
  return <Fragment ref={ref}>{children}</Fragment>
}
```

`<Fragment ref>` gives a `FragmentInstance` (`react-dom` augments it): `focus`, `focusLast`, `blur`,
`addEventListener`/`removeEventListener`/`dispatchEvent`, `observeUsing`/`unobserveUsing`
(IntersectionObserver, ResizeObserver), `getClientRects`, `getRootNode`, `compareDocumentPosition`,
`scrollIntoView` (react.dev blog "React 19.3" and `@types/react-dom@19.3.0`). Use it to add behaviour to
children you do not own; keep a plain element `ref` when there is one element.

`src/shared/ui/FocusFirst.test.tsx`

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FocusFirst } from './FocusFirst'

describe('FocusFirst (Fragment ref)', () => {
  it('focuses the first focusable child without a wrapper element', () => {
    const { container } = render(
      <FocusFirst active>
        <p>Intro</p>
        <button type="button">First action</button>
        <button type="button">Second action</button>
      </FocusFirst>,
    )
    expect(screen.getByRole('button', { name: 'First action' })).toHaveFocus()
    expect(container.children).toHaveLength(3) // no extra DOM node
  })

  it('control: does nothing while inactive', () => {
    render(
      <FocusFirst active={false}>
        <button type="button">First action</button>
      </FocusFirst>,
    )
    expect(screen.getByRole('button', { name: 'First action' })).not.toHaveFocus()
  })
})
```

Playwright also asserts focus lands on "Delete account" when the danger zone opens (`security.md` spec).

## Effects

### Derived values and resets (no effect)

```tsx
// Wrong: extra render, transient inconsistent state (react-hooks/set-state-in-effect flags it)
const [fullName, setFullName] = useState('')
useEffect(() => setFullName(`${first} ${last}`), [first, last])

// Right
const fullName = `${first} ${last}`

// Reset on identity change: key, not an effect
<ProfileEditor key={userId} userId={userId} />
```

### Fetching without a query library — tested (with a control)

```tsx
function useDocument(id: string, load: (id: string, signal: AbortSignal) => Promise<string>) {
  const [doc, setDoc] = useState<string | null>(null)
  const [error, setError] = useState<Error | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    load(id, controller.signal)
      .then((d) => {
        if (!controller.signal.aborted) setDoc(d) // a loader may ignore the signal: drop stale results
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err : new Error(String(err)))
      })
    return () => controller.abort()
  }, [id, load])
  return { doc, error }
}
```

Control: the same hook without the cleanup shows `doc 1` after switching from id 1 (slow) to id 2 (fast)
— the stale response wins. In application code prefer TanStack Query, which does this for you when the
`queryFn` forwards `signal`.

### Non-reactive values inside an effect: `useEffectEvent` — tested

```tsx
function useConnection(roomId: string, theme: string, onLog: (msg: string) => void) {
  const onConnected = useEffectEvent(() => onLog(`connected ${roomId} (${theme})`))
  useEffect(() => {
    onConnected()
    return () => onLog(`disconnected ${roomId}`)
  }, [roomId, onLog]) // theme change does not reconnect; the event still reads the latest theme
}
```

Never call an effect event from render or pass it to children; never silence `exhaustive-deps` instead.

### Legitimate effects in the validation app

- `Dialog`: `showModal()`/`close()` follow the `open` prop (imperative browser API).
- `AppLayout`: focus `<main>` after the pathname changes.

## State ownership

| Value | Home | Example |
|---|---|---|
| Local UI | `useState`/`useReducer` | dialog open, draft text |
| URL | `useSearchParams` | filters, sort, page, tab |
| Server data | TanStack Query | lists, details, mutations |
| Shared client state | small store (Zustand 5, Redux Toolkit 2 for large domains) | multi-step wizard across routes |
| App-wide config | context | theme, locale |

Never copy server data into `useState` or a store "to edit it": edit a form's own state seeded from the
query result (remount with `key` when the record changes), then mutate and invalidate.
Store library versions: `zustand` 5.x, `@reduxjs/toolkit` 2.x — **UNVERIFIED in this app (not installed); check before use.**

React 19.3 renders independent Transitions separately instead of entangling them into one render, so a
slow Transition no longer holds up unrelated ones (react.dev blog "React 19.3" changelog, #37290).
