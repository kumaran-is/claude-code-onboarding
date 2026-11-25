# Forms — React Hook Form + zod, accessible errors, dialog

> RECOMMENDED PRACTICE. Verified with `react-hook-form@7.92.0`, `@hookform/resolvers@7.0.8`
> (peers zod `^3.25 || ^4`), `zod@4.6.7`, `react@19.3.1` (`tsc -b`, ESLint, Vitest, Playwright: 2026-11-23).

## Form

`src/features/projects/components/ProjectForm.tsx`

```tsx
import { zodResolver } from '@hookform/resolvers/zod'
import { useId } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { newProjectSchema, type NewProject } from '../model/project'

type ProjectFormProps = { onSubmit: (values: NewProject) => Promise<void> }

export function ProjectForm({ onSubmit }: ProjectFormProps) {
  const id = useId()
  const {
    control,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<NewProject>({ resolver: zodResolver(newProjectSchema), defaultValues: { name: '', ownerEmail: '' } })

  async function submit(values: NewProject) {
    try {
      await onSubmit(values)
    } catch (error) {
      // Logged by the MutationCache; shown to the user here. Never swallowed.
      setError('root.server', { message: error instanceof Error ? error.message : 'Saving failed' })
    }
  }

  return (
    <form onSubmit={handleSubmit(submit)} noValidate>
      <FieldGroup>
        {/* Controller hands RHF the Input's ref (field.ref), so a failed submit focuses the first invalid field. */}
        <Controller
          name="name"
          control={control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor={`${id}-name`}>Project name</FieldLabel>
              <Input
                {...field}
                id={`${id}-name`}
                aria-invalid={fieldState.invalid ? true : undefined}
                aria-describedby={fieldState.invalid ? `${id}-name-hint ${id}-name-error` : `${id}-name-hint`}
              />
              <FieldDescription id={`${id}-name-hint`}>Shown in the project list.</FieldDescription>
              {fieldState.invalid && <FieldError id={`${id}-name-error`} errors={[fieldState.error]} />}
            </Field>
          )}
        />
        <Controller
          name="ownerEmail"
          control={control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor={`${id}-email`}>Owner email</FieldLabel>
              <Input
                {...field}
                id={`${id}-email`}
                type="email"
                autoComplete="email"
                aria-invalid={fieldState.invalid ? true : undefined}
                aria-describedby={fieldState.invalid ? `${id}-email-hint ${id}-email-error` : `${id}-email-hint`}
              />
              <FieldDescription id={`${id}-email-hint`}>Receives access notices.</FieldDescription>
              {fieldState.invalid && <FieldError id={`${id}-email-error`} errors={[fieldState.error]} />}
            </Field>
          )}
        />
        {errors.root?.server && (
          <Alert variant="destructive">
            <AlertDescription>Could not create the project: {errors.root.server.message}</AlertDescription>
          </Alert>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Spinner data-icon="inline-start" aria-hidden="true" />}
          {isSubmitting ? 'Creating…' : 'Create project'}
        </Button>
      </FieldGroup>
    </form>
  )
}
```

- `noValidate`: the schema is the single validator, so browser bubbles and app messages do not compete.
- `aria-invalid` + `aria-describedby` → the error text is the field's accessible description.
- RHF moves focus to the first invalid field on submit (`shouldFocusError` default; asserted by the test).
- Server failure: `setError('root.server', ...)` + `role="alert"`. Never swallow; the `MutationCache` logs.
- `defaultValues` are set so inputs stay controlled-by-RHF from the first render.

`src/features/projects/components/ProjectForm.test.tsx`

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ProjectForm } from './ProjectForm'

describe('ProjectForm (shadcn Field + React Hook Form Controller)', () => {
  it('blocks submit, marks fields invalid, links the error text and focuses the first invalid field', async () => {
    const onSubmit = vi.fn(async () => {})
    render(<ProjectForm onSubmit={onSubmit} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Owner email'), 'not-an-email')
    await user.click(screen.getByRole('button', { name: 'Create project' }))

    const name = screen.getByLabelText('Project name')
    expect(name).toHaveAttribute('aria-invalid', 'true')
    // The hint (FieldDescription) and the FieldError are both part of the accessible description.
    expect(name).toHaveAccessibleDescription(/Name must be at least 3 characters/)
    const describedBy = name.getAttribute('aria-describedby')?.split(' ') ?? []
    expect(describedBy).toHaveLength(2)
    expect(document.getElementById(describedBy[1] ?? '')).toHaveTextContent('Name must be at least 3 characters')
    expect(screen.getByLabelText('Owner email')).toHaveAccessibleDescription(/Enter a valid email address/)
    expect(name).toHaveFocus()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('a field without an error is described by its hint only and is not invalid', () => {
    render(<ProjectForm onSubmit={async () => {}} />)
    const name = screen.getByLabelText('Project name')
    expect(name).not.toHaveAttribute('aria-invalid')
    expect(name).toHaveAccessibleDescription('Shown in the project list.')
  })

  it('submits parsed, trimmed values', async () => {
    const onSubmit = vi.fn(async () => {})
    render(<ProjectForm onSubmit={onSubmit} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Project name'), '  Delta  ')
    await user.type(screen.getByLabelText('Owner email'), 'd@example.com')
    await user.click(screen.getByRole('button', { name: 'Create project' }))
    expect(onSubmit).toHaveBeenCalledWith({ name: 'Delta', ownerEmail: 'd@example.com' })
  })

  it('shows a server failure instead of swallowing it', async () => {
    render(<ProjectForm onSubmit={async () => { throw new Error('HTTP 500') }} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Project name'), 'Delta')
    await user.type(screen.getByLabelText('Owner email'), 'd@example.com')
    await user.click(screen.getByRole('button', { name: 'Create project' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not create the project: HTTP 500')
  })
})
```

## Accessible dialog (shadcn `Dialog`, Base UI)

The create form opens in the shadcn `Dialog` (`src/components/ui/dialog.tsx`, generated by
`npx shadcn@4.23.0 add dialog`, imports `@base-ui/react/dialog`). Base UI supplies the focus trap, Escape,
the inert background and focus return; the trigger is composed with `render={<Button />}` (Base UI has no
`asChild`). Every dialog has a `DialogTitle` (use `className="sr-only"` if it must be hidden); the close
button keeps its `sr-only` "Close" label, or axe fails `button-name` (planted and verified). Wiring:
`ProjectsPage` in `server-state-and-api.md`.

The form is remounted on each opening (`{dialogOpen && <ProjectForm key=... />}`), so no reset effect.
Playwright asserts Tab stays inside the dialog, Escape closes it and focus returns to "New project"
(`e2e/dialog-menu.spec.ts` in `tailwind-shadcn.md`). A Base UI toast also has `role="dialog"`, so tests
query the dialog by name: `getByRole('dialog', { name: 'New project' })`.

An app without a component library can use native `<dialog>` + `showModal()` (focus containment, Escape,
inert background) behind an effect that follows the `open` prop.

## React 19 Actions (no shared cache)

Use Actions when a form's result is local to the component (a profile field, a settings toggle) and no
query cache holds the same data. Use React Hook Form + a TanStack mutation (above) when the data lives in
the cache or the form needs field-level live validation. Do not combine `useOptimistic` and TanStack
optimistic cache writes for the same data.

| API (from `react` / `react-dom`, 19.3.1) | Role |
|---|---|
| `<form action={fn}>` | runs `fn(formData)` in a Transition; React resets the uncontrolled form afterwards |
| `useActionState(action, initial)` | returns `[state, dispatch, isPending]`; the action returns the next state (result, error) |
| `useOptimistic(value)` | temporary value shown while the Action runs; falls back to `value` when it settles |
| `useFormStatus()` (`react-dom`) | `pending` etc. of the parent `<form>`, read by a child such as the submit button |

`src/features/settings/components/DisplayNameForm.tsx`

```tsx
import { useActionState, useId, useOptimistic } from 'react'
import { useFormStatus } from 'react-dom'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { logger } from '@/shared/lib/logger'

const displayNameSchema = z.string().trim().min(2, 'Name must be at least 2 characters').max(40, 'Name must be at most 40 characters')

type FormState = { name: string; draft: string; error: string | null }
type DisplayNameFormProps = { initialName: string; save: (name: string) => Promise<string> }

/** useFormStatus reads the parent <form>'s pending state, so the button needs no props. */
function SubmitButton() {
  const { pending } = useFormStatus()
  return (
    <Button type="submit" disabled={pending}>
      {pending && <Spinner data-icon="inline-start" aria-hidden="true" />}
      {pending ? 'Saving…' : 'Save name'}
    </Button>
  )
}

/** React 19 Actions for a form with no shared cache: useActionState + useOptimistic + useFormStatus. */
export function DisplayNameForm({ initialName, save }: DisplayNameFormProps) {
  const id = useId()
  const [state, formAction] = useActionState<FormState, FormData>(
    async (previous, formData) => {
      const draft = String(formData.get('displayName') ?? '')
      const parsed = displayNameSchema.safeParse(draft)
      if (!parsed.success) return { ...previous, draft, error: parsed.error.issues[0]?.message ?? 'Invalid name' }
      try {
        const saved = await save(parsed.data)
        return { name: saved, draft: saved, error: null }
      } catch (error) {
        logger.error('display name save failed', { error: String(error) })
        return { ...previous, draft, error: 'Could not save the name. Try again.' }
      }
    },
    { name: initialName, draft: initialName, error: null },
  )
  const [optimisticName, setOptimisticName] = useOptimistic(state.name)

  // The form's action: runs inside a Transition, so the optimistic value lives until the Action settles,
  // then falls back to state.name (the saved name, or the old one on failure).
  function submit(formData: FormData) {
    const parsed = displayNameSchema.safeParse(formData.get('displayName'))
    if (parsed.success) setOptimisticName(parsed.data)
    formAction(formData)
  }

  return (
    <form action={submit} noValidate>
      <FieldGroup>
      <p>
        Current name: <strong data-testid="current-name">{optimisticName}</strong>
      </p>
      <Field data-invalid={!!state.error}>
        <FieldLabel htmlFor={`${id}-name`}>Display name</FieldLabel>
        {/* React resets an uncontrolled form after the Action; defaultValue={draft} keeps the user's input on error. */}
        <Input
          id={`${id}-name`}
          name="displayName"
          defaultValue={state.draft}
          aria-invalid={state.error ? true : undefined}
          aria-describedby={state.error ? `${id}-error` : undefined}
        />
        {state.error && <FieldError id={`${id}-error`}>{state.error}</FieldError>}
      </Field>
      <SubmitButton />
      </FieldGroup>
    </form>
  )
}
```

- Errors come back as action state and render in `role="alert"`, linked with `aria-describedby`; the
  catch logs and returns an error state, never swallows.
- The optimistic setter is called in `submit` (the form action), not inside the `useActionState`
  callback: calling it from the callback reads `setOptimisticName` before its declaration, and
  `eslint-plugin-react-hooks` 7.1.1 (`recommended` preset, rule `react-hooks/immutability`) fails the lint
  (control run: exit 1).
- React resets the form after the Action; `defaultValue={state.draft}` keeps the user's text after a
  failure (asserted below).
- Zod validates in the action too: never trust `FormData`.

`src/features/settings/components/DisplayNameForm.test.tsx`

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DisplayNameForm } from './DisplayNameForm'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

async function submitName(value: string) {
  const user = userEvent.setup()
  const input = screen.getByLabelText('Display name')
  await user.clear(input)
  await user.type(input, value)
  await user.click(screen.getByRole('button', { name: 'Save name' }))
}

describe('DisplayNameForm (useActionState + useOptimistic + useFormStatus)', () => {
  it('shows the optimistic name and a pending button, then the saved name', async () => {
    const pending = deferred<string>()
    render(<DisplayNameForm initialName="Dana" save={() => pending.promise} />)
    await submitName('Robin')

    expect(screen.getByTestId('current-name')).toHaveTextContent('Robin')
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled()

    pending.resolve('Robin')
    expect(await screen.findByRole('button', { name: 'Save name' })).toBeEnabled()
    expect(screen.getByTestId('current-name')).toHaveTextContent('Robin')
  })

  it('rolls the optimistic name back and keeps the input when saving fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const pending = deferred<string>()
    render(<DisplayNameForm initialName="Dana" save={() => pending.promise} />)
    await submitName('Robin')
    expect(screen.getByTestId('current-name')).toHaveTextContent('Robin')

    pending.reject(new Error('HTTP 500'))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save the name')
    expect(screen.getByTestId('current-name')).toHaveTextContent('Dana')
    expect(screen.getByLabelText('Display name')).toHaveValue('Robin')
    expect(screen.getByLabelText('Display name')).toHaveAccessibleDescription('Could not save the name. Try again.')
  })

  it('validates with the schema and never calls save for invalid input', async () => {
    const save = vi.fn(async (name: string) => name)
    render(<DisplayNameForm initialName="Dana" save={save} />)
    await submitName('R')
    expect(await screen.findByRole('alert')).toHaveTextContent('Name must be at least 2 characters')
    expect(screen.getByLabelText('Display name')).toHaveAttribute('aria-invalid', 'true')
    expect(save).not.toHaveBeenCalled()
  })
})
```

Control: returning `{ name: draft, ... }` from the catch (no rollback) fails the second test.

## Settings page (wires the React 19 examples)

`src/features/settings/api/settings.api.ts`

```ts
import { queryOptions } from '@tanstack/react-query'
import { z } from 'zod'
import { apiRequest } from '@/shared/lib/http'

export const settingsApi = {
  releaseNotes: () => apiRequest('/api/release-notes', z.array(z.string())),
  saveDisplayName: async (name: string) => {
    const saved = await apiRequest('/api/me/display-name', z.object({ name: z.string() }), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    return saved.name
  },
}

export const announcementQuery = queryOptions({
  queryKey: ['settings', 'announcement'],
  queryFn: ({ signal }) => apiRequest('/api/announcement', z.object({ html: z.string() }), { signal }),
})
```

`src/features/settings/routes/SettingsPage.tsx`

```tsx
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { session } from '@/app/session'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FocusFirst } from '@/shared/ui/FocusFirst'
import { SafeHtml } from '@/shared/ui/SafeHtml'
import { announcementQuery, settingsApi } from '../api/settings.api'
import { DisplayNameForm } from '../components/DisplayNameForm'
import { ReleaseNotes } from '../components/ReleaseNotes'
import { SettingsTabs } from '../components/SettingsTabs'

const panels = { Profile: 'Name and avatar.', Notifications: 'Email digests.', Privacy: 'Data export and deletion.' }

export function SettingsPage() {
  // Created once per mount (lazy initializer), not on every render: use() needs a stable promise.
  const [notesPromise, setNotesPromise] = useState(settingsApi.releaseNotes)
  const [dangerOpen, setDangerOpen] = useState(false)
  const announcement = useQuery(announcementQuery)

  return (
    <div className="flex flex-col gap-4">
      {/* React 19 hoists <title> into <head>; no helmet library needed. */}
      <title>Settings · Projects app</title>
      <h1>Settings</h1>
      {announcement.isError && (
        <Alert variant="destructive">
          <AlertDescription>The announcement could not be loaded.</AlertDescription>
        </Alert>
      )}
      {announcement.data && <SafeHtml html={announcement.data.html} />}
      <DisplayNameForm initialName={session.get()?.userName ?? ''} save={settingsApi.saveDisplayName} />
      <SettingsTabs panels={panels} />
      <h2>Release notes</h2>
      <ReleaseNotes notesPromise={notesPromise} onRetry={() => setNotesPromise(settingsApi.releaseNotes())} />
      <Button variant="outline" aria-expanded={dangerOpen} onClick={() => setDangerOpen((open) => !open)}>
        Danger zone
      </Button>
      {dangerOpen && (
        <FocusFirst active={dangerOpen}>
          <p>These actions cannot be undone.</p>
          <Button variant="destructive">Delete account</Button>
        </FocusFirst>
      )}
    </div>
  )
}
```

`<title>` rendered by a component is hoisted into `<head>` by React 19 (Playwright asserts the page title).
For resource hints, `react-dom` 19.3.1 exports `preconnect`, `prefetchDNS`, `preload`, `preloadModule`,
`preinit` and `preinitModule` (runtime exports checked; not exercised in the validation app).
