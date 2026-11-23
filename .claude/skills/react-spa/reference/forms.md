# Forms — React Hook Form + zod, accessible errors, dialog

> RECOMMENDED PRACTICE. Verified with `react-hook-form@7.92.0`, `@hookform/resolvers@7.0.8`
> (peers zod `^3.25 || ^4`), `zod@4.6.7`.

## Form

`src/features/projects/components/ProjectForm.tsx`

```tsx
import { zodResolver } from '@hookform/resolvers/zod'
import { useId } from 'react'
import { useForm } from 'react-hook-form'
import { newProjectSchema, type NewProject } from '../model/project'

type ProjectFormProps = { onSubmit: (values: NewProject) => Promise<void> }

export function ProjectForm({ onSubmit }: ProjectFormProps) {
  const id = useId()
  const {
    register,
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
      <div className="field">
        <label htmlFor={`${id}-name`}>Project name</label>
        <input
          id={`${id}-name`}
          aria-invalid={errors.name ? true : undefined}
          aria-describedby={errors.name ? `${id}-name-error` : undefined}
          {...register('name')}
        />
        {errors.name && (
          <p id={`${id}-name-error`} className="field-error">
            {errors.name.message}
          </p>
        )}
      </div>
      <div className="field">
        <label htmlFor={`${id}-email`}>Owner email</label>
        <input
          id={`${id}-email`}
          type="email"
          autoComplete="email"
          aria-invalid={errors.ownerEmail ? true : undefined}
          aria-describedby={errors.ownerEmail ? `${id}-email-error` : undefined}
          {...register('ownerEmail')}
        />
        {errors.ownerEmail && (
          <p id={`${id}-email-error`} className="field-error">
            {errors.ownerEmail.message}
          </p>
        )}
      </div>
      {errors.root?.server && <p role="alert">Could not create the project: {errors.root.server.message}</p>}
      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Creating…' : 'Create project'}
      </button>
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

describe('ProjectForm', () => {
  it('blocks submit, marks fields invalid and links the error text', async () => {
    const onSubmit = vi.fn(async () => {})
    render(<ProjectForm onSubmit={onSubmit} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Owner email'), 'not-an-email')
    await user.click(screen.getByRole('button', { name: 'Create project' }))

    const name = screen.getByLabelText('Project name')
    expect(name).toHaveAttribute('aria-invalid', 'true')
    expect(name).toHaveAccessibleDescription('Name must be at least 3 characters')
    expect(screen.getByLabelText('Owner email')).toHaveAccessibleDescription('Enter a valid email address')
    expect(name).toHaveFocus()
    expect(onSubmit).not.toHaveBeenCalled()
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

## Accessible dialog (native `<dialog>`)

`src/shared/ui/Dialog.tsx`

```tsx
import { useEffect, useId, useRef, type ReactNode } from 'react'

type DialogProps = { open: boolean; title: string; onClose: () => void; children: ReactNode }

/**
 * Modal built on native <dialog>: showModal() gives focus containment, Escape, an inert background,
 * and focus return to the opener on close. Presentational: no data fetching, no router hooks.
 */
export function Dialog({ open, title, onClose, children }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  // Syncs React state with an imperative browser API: a legitimate effect.
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog ref={ref} aria-labelledby={titleId} onClose={onClose}>
      <h2 id={titleId}>{title}</h2>
      {children}
      <button type="button" onClick={onClose}>
        Cancel
      </button>
    </dialog>
  )
}
```

`showModal()` gives focus containment, Escape to close, an inert background and focus return to the
opener; Playwright asserts Escape closes it and focus returns to "New project" (see `testing.md`).
The form is remounted on each opening (`{dialogOpen && <ProjectForm key=... />}`), so no reset effect.

## Without a query cache

For simple form actions with no shared cache, React 19 `useActionState` and `useOptimistic` are
available (exported by `react@19.3.1`). Do not combine them with TanStack optimistic cache writes for
the same data. **UNVERIFIED pattern in this app — check before use.**
