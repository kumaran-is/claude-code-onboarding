# Angular 21.2 Animations — Canonical Reference

> Official guide: https://angular.dev/guide/animations (v21: "Migrating away from Angular's
> Animations package"). Snippets compiled against `@angular/*@21.2.26` with `strictTemplates`.

## Which system

| System | Status in 21.x | Use |
|---|---|---|
| `animate.enter` / `animate.leave` (built into `@angular/core`) + CSS | Current | All new enter/leave animations |
| Native CSS transitions / `@keyframes` / Tailwind `transition-*` | Current | Hover, press, state changes (open/closed, expanded) |
| `@angular/animations` (`trigger`, `state`, `transition`, `query`, `stagger`) + `provideAnimations*()` | **Deprecated since v20.2** | Existing code only; migrate when touched. Do not add the package to new apps |

## `animate.enter` / `animate.leave`

```typescript
import { AnimationCallbackEvent, ChangeDetectionStrategy, Component, signal } from '@angular/core';

@Component({
  selector: 'app-notice',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button type="button" class="btn" (click)="open.set(!open())" [attr.aria-expanded]="open()">Toggle</button>

    <!-- Static classes: added on insert / before removal; Angular waits for the CSS animation -->
    @if (open()) {
      <div class="alert" animate.enter="fade-in" animate.leave="fade-out">Saved</div>
    }

    <!-- Bound class, and an event binding for JS-driven leave animations -->
    @if (open()) {
      <div class="card" [animate.enter]="enterClass()" (animate.leave)="onLeave($event)">Card</div>
    }
  `,
})
export class Notice {
  readonly open = signal(false);
  readonly enterClass = signal('slide-up');

  onLeave(event: AnimationCallbackEvent): void {
    const anim = (event.target as HTMLElement).animate([{ opacity: 1 }, { opacity: 0 }], { duration: 150 });
    // Must be called, or the element is removed only after MAX_ANIMATION_TIMEOUT.
    anim.onfinish = () => event.animationComplete();
  }
}
```

- `AnimationCallbackEvent` is imported from **`@angular/core`** (`{ target: Element; animationComplete }`).
- The event form is `(animate.leave)="handler($event)"`; there is no arrow-function string form.
- No provider is needed; do not add `provideAnimations()` / `provideAnimationsAsync()` for this.

```css
/* styles.css */
@keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes fade-out { from { opacity: 1; } to { opacity: 0; } }
@keyframes slide-up { from { opacity: 0; transform: translateY(1rem); } to { opacity: 1; transform: none; } }

.fade-in  { animation: fade-in 200ms ease-out; }
.fade-out { animation: fade-out 150ms ease-in; }
.slide-up { animation: slide-up 250ms ease-out; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

## State changes without the animations package

Bind a class to a signal and put the transition in the component stylesheet, for example an
accordion panel: `<div class="panel" [class.is-open]="open()">` with
`.panel { display: grid; grid-template-rows: 0fr; transition: grid-template-rows 200ms ease-in-out; } .panel.is-open { grid-template-rows: 1fr; }`.
List stagger: set `style.animation-delay` per item from `$index` (cap it, e.g. `min($index, 10) * 30ms`).
Route transitions: the router's View Transitions support (`withViewTransitions()`) with CSS.

## Timing standards

| Type | Duration | Easing | Use |
|---|---|---|---|
| Instant | 50–100ms | `ease-out` | Hover, press feedback |
| Quick | 100–200ms | `ease-out` | Dropdown, tooltip, toast |
| Standard | 200–300ms | `ease-in-out` | Modal, drawer, accordion |
| Emphasis | 300–500ms | `ease-in-out` | Onboarding, celebration |

Most interactions: 150–250ms. Exit faster than enter.

## Rules

- Animate `transform` and `opacity` only; avoid animating layout properties on large trees.
- Respect `prefers-reduced-motion` (global rule above). WCAG 2.2 SC 2.3.3 (AAA) and 2.2.2 (pause,
  stop, hide for auto-moving content, AA) — checklist in the `accessibility-audit` skill.
- Never block interaction until an animation ends; never animate focus away from where the user is.
- daisyUI/Tailwind transition utilities (`transition-transform duration-150 active:scale-95`) are
  fine for feedback on stateless elements.
- Migrating `@angular/animations`: replace `:enter`/`:leave` transitions with `animate.enter`/`animate.leave`,
  replace `state()` styles with signal-bound classes + CSS transitions, then remove the package and
  its `provideAnimations*()` call. Motion performance audit: `fixing-motion-performance` skill.
