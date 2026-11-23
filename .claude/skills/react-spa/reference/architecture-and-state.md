# Architecture, components, hooks, effects and state

> RECOMMENDED PRACTICE. Snippets marked "tested" were exercised by unit tests in the validation app
> (Vitest, `tsc -b`, ESLint: exit 0, 2026-11-23); those tests are not reproduced here. Short fragments
> (the context example) show usage and are not standalone modules.

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
  in the `recommended-latest` preset flags it).

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
