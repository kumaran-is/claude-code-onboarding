# Server state and the typed API client

> RECOMMENDED PRACTICE. Every block below is copied from the validation app and passed `tsc -b`,
> ESLint and Vitest (2026-11-23; re-run with React 19.3.1, `@tanstack/react-query@5.108.4`). Paths are
> relative to the app root.

## API client: runtime validation at the boundary, credentials only to allow-listed origins

`src/shared/lib/http.ts`

```ts
import type { z } from 'zod'

// VITE_* values are compiled into the public bundle: configuration only, never secrets.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? window.location.origin
// Credentials are attached only to these origins, never to third-party URLs.
const ALLOWED_API_ORIGINS = new Set([new URL(API_BASE_URL, window.location.origin).origin])

// Access token lives in memory only (never localStorage/sessionStorage). Prefer an HttpOnly cookie set by a BFF.
let accessToken: string | null = null
export function setAccessToken(token: string | null): void {
  accessToken = token
}

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Fetches JSON and validates it at the boundary: a response that does not match `schema` throws. */
export async function apiRequest<T>(path: string, schema: z.ZodType<T>, init: RequestInit = {}): Promise<T> {
  const url = new URL(path, API_BASE_URL)
  const headers = new Headers(init.headers)
  const trusted = ALLOWED_API_ORIGINS.has(url.origin)
  if (accessToken && trusted) headers.set('Authorization', `Bearer ${accessToken}`)
  const response = await fetch(url, { ...init, headers, credentials: trusted ? 'same-origin' : 'omit' })
  if (!response.ok) {
    throw new ApiError(response.status, `${init.method ?? 'GET'} ${url.pathname} failed with HTTP ${response.status}`)
  }
  const body: unknown = response.status === 204 ? undefined : await response.json()
  return schema.parse(body)
}
```

- A body that fails `schema.parse` throws, so the query lands in its **error** state (tested:
  `ProjectList.test.tsx` "treats a response that fails schema validation as an error").
- `fetch` already sends cookies only same-origin by default; `credentials: 'omit'` for other origins
  makes the intent explicit. If the API is cross-origin and uses cookies, add its origin to the
  allow-list and use `credentials: 'include'` for it only.
- Logging goes through one sink:

`src/shared/lib/logger.ts`

```ts
// Single logging sink for the app. Swap the body for your telemetry SDK; call sites stay unchanged.
type LogContext = Record<string, unknown>

export const logger = {
  error(message: string, context: LogContext = {}): void {
    console.error(JSON.stringify({ level: 'error', message, ...context, at: new Date().toISOString() }))
  },
}
```

## Schemas shared by API and form

`src/features/projects/model/project.ts`

```ts
import { z } from 'zod'

export const projectSchema = z.object({ id: z.string(), name: z.string(), ownerEmail: z.email() })
export const projectListSchema = z.array(projectSchema)
export type Project = z.infer<typeof projectSchema>

// One schema drives the form (UX) and the request body; the server validates again (security).
export const newProjectSchema = z.object({
  name: z.string().trim().min(3, 'Name must be at least 3 characters').max(80, 'Name must be at most 80 characters'),
  ownerEmail: z.email('Enter a valid email address'),
})
export type NewProject = z.infer<typeof newProjectSchema>
```

`src/features/projects/api/projects.api.ts`

```ts
import { apiRequest } from '@/shared/lib/http'
import { projectListSchema, projectSchema, type NewProject } from '../model/project'

export const projectsApi = {
  list: (signal: AbortSignal) => apiRequest('/api/projects', projectListSchema, { signal }),
  create: (input: NewProject) =>
    apiRequest('/api/projects', projectSchema, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }),
}
```

## Query client: log once, centrally

`src/app/query-client.ts`

```ts
import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { logger } from '@/shared/lib/logger'

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { staleTime: 30_000 } },
    queryCache: new QueryCache({
      onError: (error, query) => logger.error('query failed', { queryKey: query.queryKey, error: String(error) }),
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _result, mutation) =>
        logger.error('mutation failed', { mutationKey: mutation.options.mutationKey, error: String(error) }),
    }),
  })
}
```

`staleTime` is a deliberate choice per app (the library default is `0`: data is stale immediately and
refetches on mount/focus). Default `retry` is 3 with exponential backoff: in Chromium the error state
appeared after ~7.7 s. Tests turn retries off.

## Key factory, queryOptions, AbortSignal, optimistic mutation with rollback

`src/features/projects/api/projects.queries.ts`

```ts
import { queryOptions, useMutation } from '@tanstack/react-query'
import type { NewProject, Project } from '../model/project'
import { projectsApi } from './projects.api'

// Key factory: every variable the queryFn reads is part of the key.
export const projectKeys = {
  all: ['projects'] as const,
  list: () => [...projectKeys.all, 'list'] as const,
}

export const projectQueries = {
  list: () =>
    queryOptions({
      queryKey: projectKeys.list(),
      // Forward the signal so TanStack Query can abort superseded or unused requests.
      queryFn: ({ signal }) => projectsApi.list(signal),
    }),
}

export function useCreateProject() {
  return useMutation({
    mutationKey: ['projects', 'create'],
    mutationFn: (input: NewProject) => projectsApi.create(input),
    onMutate: async (input, context) => {
      await context.client.cancelQueries({ queryKey: projectKeys.list() })
      const previous = context.client.getQueryData<Project[]>(projectKeys.list())
      const optimistic: Project = { id: `optimistic-${crypto.randomUUID()}`, ...input }
      context.client.setQueryData<Project[]>(projectKeys.list(), (old = []) => [...old, optimistic])
      return { previous }
    },
    onError: (_error, _input, onMutateResult, context) => {
      // Roll back; the caller shows the error to the user and the MutationCache logs it.
      context.client.setQueryData(projectKeys.list(), onMutateResult?.previous)
    },
    onSettled: (_data, _error, _input, _onMutateResult, context) =>
      context.client.invalidateQueries({ queryKey: projectKeys.list() }),
  })
}
```

Mutations vs React 19 Actions: when the data lives in this cache, mutate with `useMutation` and keep the
optimistic write in the cache (above). React's `useActionState` + `useOptimistic` (`forms.md`) suit
results that no cache shares; mixing both for the same data shows two optimistic copies.

TanStack v5 callback signatures (from `@tanstack/query-core` types): `onMutate(variables, context)`,
`onError(error, variables, onMutateResult, context)`, `onSettled(data, error, variables, onMutateResult, context)`;
`context.client` is the `QueryClient`. `invalidateQueries` refetches only queries that have an observer;
an unobserved query is only marked stale. The test therefore mounts a list observer:

`src/features/projects/api/projects.queries.test.tsx`

```tsx
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { server } from '@/test/msw-server'
import type { Project } from '../model/project'
import { projectKeys, projectQueries, useCreateProject } from './projects.queries'

const url = `${window.location.origin}/api/projects`
const alpha: Project = { id: '1', name: 'Alpha', ownerEmail: 'a@example.com' }
const input = { name: 'Gamma', ownerEmail: 'g@example.com' }

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  client.setQueryData(projectKeys.list(), [alpha])
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  // Mount a list observer as the page does: invalidateQueries only refetches queries that are observed.
  const hook = renderHook(
    () => {
      useQuery(projectQueries.list())
      return useCreateProject()
    },
    { wrapper },
  )
  return { client, ...hook }
}

describe('useCreateProject optimistic update', () => {
  it('shows the item immediately and rolls back when the server fails', async () => {
    server.use(http.post(url, async () => { await delay(50); return new HttpResponse(null, { status: 500 }) }))
    // Slow refetch: if the GET were fast, onSettled's invalidation would restore [alpha] by itself and
    // the test would pass with the onError rollback deleted. Only the rollback can win this race.
    server.use(http.get(url, async () => { await delay(2000); return HttpResponse.json([alpha]) }))
    const { client, result } = setup()

    act(() => result.current.mutate(input))
    await waitFor(() => expect(client.getQueryData<Project[]>(projectKeys.list())).toHaveLength(2))

    await waitFor(() => expect(client.getQueryData<Project[]>(projectKeys.list())).toEqual([alpha]), { timeout: 1000 })
    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 4000 })
  })

  it('keeps the created item when the server succeeds (control)', async () => {
    const created = { id: '3', ...input }
    server.use(http.post(url, () => HttpResponse.json(created, { status: 201 })))
    server.use(http.get(url, () => HttpResponse.json([alpha, created])))
    const { client, result } = setup()

    act(() => result.current.mutate(input))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    await waitFor(() => expect(client.getQueryData<Project[]>(projectKeys.list())).toEqual([alpha, created]))
  })
})
```

## The four UI states

`src/features/projects/components/ProjectList.tsx`

```tsx
import { useQuery } from '@tanstack/react-query'
import {
  createColumnHelper,
  createSortedRowModel,
  rowSortingFeature,
  sortFn_alphanumeric,
  tableFeatures,
  useTable,
  type Column,
} from '@tanstack/react-table'
import { ArrowDownIcon, FolderIcon, ArrowUpDownIcon, ArrowUpIcon } from '@/shared/ui/icons'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { projectQueries } from '../api/projects.queries'
import type { Project } from '../model/project'

// TanStack Table v9: features are registered explicitly. Module scope keeps `features` and `columns` stable.
const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { alphanumeric: sortFn_alphanumeric },
})
const columnHelper = createColumnHelper<typeof features, Project>()

function SortButton({ column, label }: { column: Column<typeof features, Project, string>; label: string }) {
  const sorted = column.getIsSorted()
  const Icon = sorted === 'asc' ? ArrowUpIcon : sorted === 'desc' ? ArrowDownIcon : ArrowUpDownIcon
  return (
    <Button variant="ghost" className="-ml-2.5" onClick={column.getToggleSortingHandler()}>
      {label}
      <Icon data-icon="inline-end" aria-hidden="true" />
    </Button>
  )
}

const columns = columnHelper.columns([
  columnHelper.accessor('name', {
    header: ({ column }) => <SortButton column={column} label="Name" />,
    sortFn: 'alphanumeric',
  }),
  columnHelper.accessor('ownerEmail', {
    header: ({ column }) => <SortButton column={column} label="Owner" />,
    sortFn: 'alphanumeric',
    cell: (info) => <span className="break-all">{info.getValue()}</span>,
  }),
])

const ariaSort = { asc: 'ascending', desc: 'descending' } as const

function ProjectTable({ projects }: { projects: Project[] }) {
  const table = useTable({ features, columns, data: projects, getRowId: (project) => project.id })
  return (
    <Table aria-label="Projects">
      <TableHeader>
        {table.getHeaderGroups().map((group) => (
          <TableRow key={group.id}>
            {group.headers.map((header) => {
              const sorted = header.column.getIsSorted()
              return (
                <TableHead key={header.id} aria-sort={sorted ? ariaSort[sorted] : 'none'}>
                  {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                </TableHead>
              )
            })}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.map((row) => (
          <TableRow key={row.id}>
            {row.getAllCells().map((cell) => (
              <TableCell key={cell.id}>
                <table.FlexRender cell={cell} />
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function ProjectList() {
  // Minimal form. Screens with real latency use the content-first model (150 ms delay / 400 ms hold, keepPreviousData,
  // single-flight Retry): design-system/reference/interaction-contracts.md §6b.1.
  const { data, isPending, isError, isFetching, refetch } = useQuery(projectQueries.list())

  // Persistent live region: it is mounted before its text changes, so screen readers announce the update.
  const status = (
    <p role="status" className="sr-only">
      {isFetching ? 'Refreshing…' : ''}
    </p>
  )

  if (isPending)
    return (
      <div role="status" className="flex flex-col gap-2">
        <span className="sr-only">Loading projects…</span>
        <Skeleton className="h-10 w-full" aria-hidden="true" />
        <Skeleton className="h-10 w-full" aria-hidden="true" />
        <Skeleton className="h-10 w-full" aria-hidden="true" />
      </div>
    )
  if (isError)
    return (
      <Alert variant="destructive" className="flex flex-col items-start gap-2">
        <AlertDescription>Projects could not be loaded.</AlertDescription>
        <Button variant="outline" onClick={() => refetch()}>
          Retry
        </Button>
      </Alert>
    )
  if (data.length === 0)
    return (
      <>
        {status}
        <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <FolderIcon aria-hidden="true" />
          </EmptyMedia>
          <EmptyTitle>No projects yet</EmptyTitle>
          <EmptyDescription>Create the first one with the New project button.</EmptyDescription>
        </EmptyHeader>
        </Empty>
      </>
    )

  return (
    <>
      {status}
      <ProjectTable projects={data} />
    </>
  )
}
```

`isPending` = no data yet; `isFetching` = any request in flight (including background refetch), shown as
a small status instead of blanking the list. Never return `[]`/`null` on error.

`src/features/projects/components/ProjectList.test.tsx`

```tsx
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { server } from '@/test/msw-server'
import { renderWithQuery } from '@/test/render'
import { ProjectList } from './ProjectList'

const url = `${window.location.origin}/api/projects`
const rows = [
  { id: '2', name: 'Beta', ownerEmail: 'b@example.com' },
  { id: '3', name: 'Gamma', ownerEmail: 'g@example.com' },
  { id: '1', name: 'Alpha', ownerEmail: 'a@example.com' },
]

function projectNames() {
  const table = screen.getByRole('table', { name: 'Projects' })
  return within(table)
    .getAllByRole('row')
    .slice(1) // header row
    .map((row) => within(row).getAllByRole('cell')[0]?.textContent)
}

describe('ProjectList', () => {
  it('shows a skeleton loading state, then the projects', async () => {
    server.use(http.get(url, () => HttpResponse.json([{ id: '1', name: 'Alpha', ownerEmail: 'a@example.com' }])))
    renderWithQuery(<ProjectList />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading projects')
    expect(await screen.findByRole('table', { name: 'Projects' })).toHaveTextContent('Alpha')
  })

  it('keeps a persistent live region: empty at rest, "Refreshing…" during a background refetch', async () => {
    server.use(http.get(url, () => HttpResponse.json(rows)))
    const { client } = renderWithQuery(<ProjectList />)
    await screen.findByRole('table', { name: 'Projects' })
    const region = screen.getByRole('status')
    expect(region).toBeEmptyDOMElement()
    let release!: () => void
    const gate = new Promise<void>((resolve) => (release = resolve))
    server.use(http.get(url, async () => { await gate; return HttpResponse.json(rows) }))
    void client.invalidateQueries()
    await vi.waitFor(() => expect(region).toHaveTextContent('Refreshing…'))
    expect(screen.getByRole('status')).toBe(region) // same node: the region was not re-inserted
    release()
    await vi.waitFor(() => expect(region).toBeEmptyDOMElement())
  })

  it('shows an empty state for an empty list', async () => {
    server.use(http.get(url, () => HttpResponse.json([])))
    renderWithQuery(<ProjectList />)
    expect(await screen.findByText(/No projects yet/)).toBeInTheDocument()
  })

  it('shows a visible error with a working retry', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    server.use(http.get(url, () => new HttpResponse(null, { status: 500 }), { once: true }))
    renderWithQuery(<ProjectList />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Projects could not be loaded')

    server.use(http.get(url, () => HttpResponse.json([{ id: '2', name: 'Beta', ownerEmail: 'b@example.com' }])))
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('table', { name: 'Projects' })).toHaveTextContent('Beta')
  })

  it('treats a response that fails schema validation as an error, not as data', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    server.use(http.get(url, () => HttpResponse.json([{ id: 1, title: 'wrong shape' }])))
    renderWithQuery(<ProjectList />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Projects could not be loaded')
  })

  it('aborts the request when the list unmounts before the response arrives', async () => {
    let seenSignal: AbortSignal | undefined
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      seenSignal = init?.signal ?? undefined
      return new Promise<Response>(() => {})
    }))
    const { unmount } = renderWithQuery(<ProjectList />)
    await vi.waitFor(() => expect(seenSignal).toBeDefined())
    unmount()
    await vi.waitFor(() => expect(seenSignal?.aborted).toBe(true))
    vi.unstubAllGlobals()
  })

  it('sorts by a column header button: ascending, descending, then back to the data order', async () => {
    server.use(http.get(url, () => HttpResponse.json(rows)))
    renderWithQuery(<ProjectList />)
    await screen.findByRole('table', { name: 'Projects' })
    const user = userEvent.setup()
    const nameHeader = screen.getByRole('columnheader', { name: /Name/ })
    expect(projectNames()).toEqual(['Beta', 'Gamma', 'Alpha'])
    expect(nameHeader).toHaveAttribute('aria-sort', 'none')

    await user.click(screen.getByRole('button', { name: 'Name' }))
    expect(projectNames()).toEqual(['Alpha', 'Beta', 'Gamma'])
    expect(nameHeader).toHaveAttribute('aria-sort', 'ascending')

    await user.click(screen.getByRole('button', { name: 'Name' }))
    expect(projectNames()).toEqual(['Gamma', 'Beta', 'Alpha'])
    expect(nameHeader).toHaveAttribute('aria-sort', 'descending')

    await user.click(screen.getByRole('button', { name: 'Name' }))
    expect(projectNames()).toEqual(['Beta', 'Gamma', 'Alpha'])
    expect(nameHeader).toHaveAttribute('aria-sort', 'none')
  })

  it('sorts by the owner column and moves aria-sort with it', async () => {
    server.use(http.get(url, () => HttpResponse.json(rows)))
    renderWithQuery(<ProjectList />)
    await screen.findByRole('table', { name: 'Projects' })
    await userEvent.setup().click(screen.getByRole('button', { name: 'Owner' }))
    expect(screen.getByRole('columnheader', { name: /Owner/ })).toHaveAttribute('aria-sort', 'ascending')
    expect(screen.getByRole('columnheader', { name: /Name/ })).toHaveAttribute('aria-sort', 'none')
    expect(projectNames()).toEqual(['Alpha', 'Beta', 'Gamma'])
  })
})
```

The abort test is the positive control for `signal` forwarding: remove `signal` from `projectsApi.list`
and `seenSignal` is `undefined`, so it fails.

## Page: mutation + dialog + form, no reset effect

`src/features/projects/routes/ProjectsPage.tsx`

```tsx
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { toast } from '@/components/ui/toast'
import { useCreateProject } from '../api/projects.queries'
import { ProjectForm } from '../components/ProjectForm'
import { ProjectList } from '../components/ProjectList'
import type { NewProject } from '../model/project'

export function ProjectsPage() {
  const [dialogOpen, setDialogOpen] = useState(false)
  const createProject = useCreateProject()

  async function create(values: NewProject) {
    await createProject.mutateAsync(values)
    setDialogOpen(false)
    toast.add({ title: `Project "${values.name}" created`, type: 'success' })
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1>Projects</h1>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          {/* The trigger is how Base UI returns focus to the opener when the dialog closes. */}
          <DialogTrigger render={<Button />}>New project</DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>New project</DialogTitle>
              <DialogDescription>Name the project and say who owns it.</DialogDescription>
            </DialogHeader>
            {/* Rendered only while open: the form unmounts on close and remounts on the next opening, so it starts clean (no reset effect). */}
            {dialogOpen && <ProjectForm onSubmit={create} />}
          </DialogContent>
        </Dialog>
      </div>
      <ProjectList />
    </div>
  )
}
```

