---
name: fixing-motion-performance
description: "Audit and fix animation performance issues in Angular 22.x — layout thrashing, compositor properties, scroll-linked motion, will-change, blur effects, FLIP technique, and View Transitions API. Use when Angular animations stutter, transitions jank, scroll-linked motion is slow, or reviewing CSS/WAAPI animation code for performance. Works as a file auditor: /fixing-motion-performance <file> reports violations with exact line quotes and concrete fixes."
risk: low
source: community (adapted for Angular 22.x)
date_added: "2026-03-15"
allowed-tools: Read, Grep, Bash
metadata:
  triggers: animation jank, stutter, transition performance, layout thrashing, will-change, compositor, scroll-linked animation, scroll reveal, FLIP, CSS animation performance, frame drop, 60fps, blur performance, view transitions, janky scroll
  related-skills: angular-spa, web-performance-optimization, tailwind-patterns, accessibility-audit
  domain: frontend
  role: specialist
  scope: performance
  output-format: document
last-reviewed: "2026-03-15"
---

## Iron Law

**NEVER ANIMATE LAYOUT PROPERTIES (width, height, top, left, margin) ON LARGE SURFACES. Default to `transform` and `opacity` only. Resolve compositor vs paint vs layout tier BEFORE writing any animation CSS.**

# Fixing Motion Performance — Angular 22.x

## When to Use

Load this skill when:
- Angular CSS transitions or animations stutter or drop below 60fps
- Implementing scroll-linked motion or reveal-on-scroll in Angular templates
- Animating layout, filters, masks, gradients, or CSS variables
- Reviewing Angular component styles that use `will-change`, transforms, or DOM measurement
- Refactoring janky interactions in existing Angular components

## How to Use as File Auditor

```
/fixing-motion-performance <file>
```

Review the file against all rules below and report:
- **violations** — quote the exact line or snippet
- **why it matters** — one short sentence
- **concrete fix** — code-level suggestion with before/after

Do not migrate animation libraries unless explicitly requested. Apply rules within the existing Angular/TailwindCSS/daisyUI stack.

---

## Rendering Steps Glossary

Understanding which browser rendering step an animation triggers determines its performance cost:

| Step | Triggered By | Cost |
|------|-------------|------|
| **composite** | `transform`, `opacity` | Cheapest — runs on compositor thread, never blocks main thread |
| **paint** | `color`, `background`, `border`, `box-shadow`, `filter`, gradients | Medium — rerasters pixels |
| **layout** | `width`, `height`, `top`, `left`, `margin`, `padding`, `flex`, `grid` | Most expensive — recalculates entire document flow |

**Rule:** Always animate at the cheapest tier that achieves the design intent.

---

## Diagnose, Scan, Verify

Profile before changing code; fix only what the profile confirms.

1. **Diagnose** in Chrome DevTools (or the Chrome DevTools MCP performance trace): **Performance** — record while reproducing the jank, look for long frames and Layout/Paint tasks; **Rendering → Paint flashing** — animated elements must not flash green every frame; **Layers** — check promoted layers (too many = GPU memory pressure).
2. **Scan** for Critical never-patterns; each hit is fixed first:

```bash
grep -rn "@HostListener.*scroll\|window:scroll\|scrollTop\|scrollY" src/app --include="*.ts"
grep -rn "transition.*width\|transition.*height\|transition.*top\|transition.*left\|transition.*margin" src/app --include="*.scss" --include="*.css"
grep -rn "will-change" src/app --include="*.scss" --include="*.css"   # flag static (non-hover/focus) use
```

3. **Verify** after each fix, re-profiling:
   - [ ] Performance: no Layout or Paint tasks during the animation
   - [ ] Paint flashing: no green flashes on the animated element during motion
   - [ ] Frame rate holds 60fps with 4x CPU throttling
   - [ ] Layers: no unexpected layer explosion
   - [ ] `prefers-reduced-motion: reduce` disables or reduces the motion (§8b)

---

## Rule Categories by Priority

| Priority | Category | Impact |
|----------|----------|--------|
| 1 | Never patterns | Critical |
| 2 | Choose the mechanism | Critical |
| 3 | Measurement | High |
| 4 | Scroll | High |
| 5 | Paint | Medium-High |
| 6 | Layers | Medium |
| 7 | Blur and filters | Medium |
| 8 | View transitions | Low |
| 9 | Tool boundaries | Critical |

---

## 1. Never Patterns (Critical)

These always cause jank. Zero exceptions.

- Do not interleave layout reads and writes in the same frame
- Do not animate layout properties continuously on large or meaningful surfaces
- Do not drive animation from `scrollTop`, `scrollY`, or `scroll` events
- No `requestAnimationFrame` loops without a stop condition
- Do not mix multiple animation systems that each measure or mutate layout

---

## 2. Choose the Mechanism (Critical)

- Default to `transform` and `opacity` for all motion
- Use JS-driven animation only when interaction requires it
- Paint or layout animation is acceptable only on small, isolated surfaces
- One-shot effects are acceptable more often than continuous motion
- Prefer downgrading technique over removing motion entirely

### Angular + Tailwind mapping

| Intent | Wrong (causes layout/paint) | Correct (compositor) |
|--------|----------------------------|----------------------|
| Slide open panel | `transition: width 0.3s` | `transition: transform 0.3s` + `scaleX()` |
| Fade in element | `transition: display` | `transition: opacity 0.2s` + `visibility` |
| Card hover lift | `transition: margin-top` | `transition: transform 0.2s` + `translateY(-4px)` |
| Alert shake | `transition: left` | `@keyframes` with `translateX` |
| Expand accordion | `transition: height 0.3s` | FLIP technique (see §3) or `grid-template-rows` |

---

## 3. Measurement (High)

- Measure once, then animate via `transform` or `opacity`
- Batch all DOM reads before writes — never interleave
- Do not read layout (`getBoundingClientRect`, `offsetHeight`, `scrollTop`) during an animation
- Prefer FLIP-style transitions for layout-like effects

### FLIP Technique — Angular example

```typescript
// Angular component: FLIP for expanding card
flipExpand(el: HTMLElement): void {
  // FIRST — measure before state change
  const first = el.getBoundingClientRect();

  // Apply the state change (add class, toggle signal)
  this.isExpanded.set(true);

  // Force style recalc synchronously
  el.offsetHeight; // force reflow once, intentionally

  // LAST — measure after state change
  const last = el.getBoundingClientRect();

  // INVERT — animate from first to last position
  const deltaY = first.top - last.top;
  const deltaScale = first.height / last.height;

  el.style.transform = `translateY(${deltaY}px) scaleY(${deltaScale})`;
  el.style.transition = 'none';

  // PLAY — release to natural position
  requestAnimationFrame(() => {
    el.style.transition = 'transform 0.3s ease-out';
    el.style.transform = '';
  });
}
```

---

## 4. Scroll (High)

- Prefer CSS `animation-timeline: view()` or `scroll()` for scroll-linked motion
- Use `IntersectionObserver` for visibility-triggered animations and pausing
- Do not poll `scrollTop` / `scrollY` for animation in Angular components
- Pause or stop animations when off-screen (use `IntersectionObserver`)
- Scroll-linked motion must not trigger continuous layout or paint on large surfaces

### Angular scroll-reveal pattern

```typescript
// BAD — scroll event listener causes layout thrash
@HostListener('window:scroll')
onScroll() {
  const scrollY = window.scrollY; // forces layout read
  this.opacity = Math.min(scrollY / 300, 1); // mutation in same frame
}
```

```css
/* GOOD — CSS View Timeline, runs on compositor thread */
.reveal-card {
  animation: slideUp linear both;
  animation-timeline: view();
  animation-range: entry 0% entry 40%;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(24px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

```typescript
// GOOD — IntersectionObserver for class-based reveal
ngAfterViewInit(): void {
  const observer = new IntersectionObserver(
    (entries) => entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('animate-slide-up');
        observer.unobserve(e.target); // one-shot
      }
    }),
    { threshold: 0.15 }
  );
  this.cards().forEach(card => observer.observe(card.nativeElement));
}
```

---

## 5. Paint (Medium-High)

- Paint-triggering animation is allowed only on small, isolated elements
- Do not animate paint-heavy properties on large containers
- Do not animate CSS variables that control `transform`, `opacity`, or `position`
- Do not animate inherited CSS variables (the inheritance causes full repaint)
- Scope animated CSS variables locally and avoid inheritance

### Angular + daisyUI context

```css
/* BAD — animating background triggers paint on full container */
.hero { transition: background-color 1s; }

/* OK — small indicator badge, paint cost is acceptable */
.badge { transition: background-color 0.2s; }

/* BAD — animating inherited CSS variable causes subtree repaint */
:root { --card-bg: oklch(0.9 0 0); }
.card { transition: --card-bg 0.3s; } /* inherits, repaints all children */

/* GOOD — scope locally, no inheritance */
.card { transition: opacity 0.2s, transform 0.2s; }
```

---

## 6. Layers (Medium)

- Compositor motion requires layer promotion — never assume it happens automatically
- Use `will-change` temporarily and surgically (add before animation, remove after)
- Avoid many or large promoted layers — each costs GPU memory
- Validate layer behavior with Chrome DevTools → Layers panel when performance matters

```css
/* BAD — permanent will-change on all cards wastes GPU memory */
.card { will-change: transform; }

/* GOOD — add surgically before animation, remove after */
/* In Angular component: */
```

```typescript
onHoverStart(el: HTMLElement): void {
  el.style.willChange = 'transform';
}
onHoverEnd(el: HTMLElement): void {
  el.style.willChange = 'auto'; // release layer after animation
}
```

---

## 7. Blur and Filters (Medium)

- Keep blur animation radius small (`backdrop-blur` changes ≤ 8px delta)
- Use blur only for short, one-time effects (modal open, not continuous hover)
- Never animate `blur()` or `backdrop-blur` continuously
- Never animate blur on large surfaces (full-page overlays)
- Prefer `opacity` and `translate` over `blur` for reveal effects

```css
/* BAD — continuous blur on large surface */
.hero-overlay { transition: backdrop-filter 0.5s; }
.hero-overlay:hover { backdrop-filter: blur(20px); } /* GPU-expensive on large area */

/* OK — one-shot modal open, small delta */
.modal-backdrop {
  animation: blurIn 200ms ease-out forwards;
}
@keyframes blurIn {
  from { opacity: 0; backdrop-filter: blur(0px); }
  to   { opacity: 1; backdrop-filter: blur(4px); } /* <= 8px delta */
}
```

---

## 8. View Transitions (Low)

Angular 22.x has native View Transition support via the router.

- Use view transitions only for navigation-level page changes
- Avoid view transitions for interaction-heavy UI (tabs, toggles, accordions)
- Avoid view transitions when interruption or cancellation is required
- Treat size changes in view transitions as potentially layout-triggering

```typescript
// app.config.ts: enable view transitions, skipped under reduced motion
import { ApplicationConfig } from '@angular/core';
import { provideRouter, withViewTransitions } from '@angular/router';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes, withViewTransitions({
      onViewTransitionCreated: ({ transition }) => {
        // skipTransition is a method; calling it skips the animation, navigation still completes
        if (matchMedia('(prefers-reduced-motion: reduce)').matches) transition.skipTransition();
      },
    })),
  ],
};
```

## 8b. Reduced Motion (High)

Reduced motion removes movement, not meaning.

- Gate each animation: `motion-safe:animate-…` / `motion-reduce:transition-none` in Tailwind, or `@media (prefers-reduced-motion: no-preference) { … }` around the keyframes. Avoid a global `* { animation-duration: 0.01ms !important }` hammer: it also breaks code that waits for `animationend`/`transitionend` timing and removes meaningful state changes.
- Keep opacity changes and final-state geometry; drop translation, scaling, parallax and auto-playing loops.
- Skeletons keep their shape and lose the shimmer (daisyUI 5 `.skeleton` already stops animating under `reduce`; `.loading` spinners are gated behind `no-preference`).
- Wrap animation engines (Lottie and similar) in one shared component with a mandatory static fallback for reduced motion and for load failure.
- WCAG: anything moving for more than 5 s needs a pause control (2.2.2, A); nothing flashes more than 3 times per second (2.3.1, A). 2.3.3 Animation from Interactions is AAA: treat it as a goal, not an AA gate.

---

## 9. Tool Boundaries (Critical)

- Do not migrate or rewrite animation libraries unless explicitly requested
- Apply these rules within the existing Angular/TailwindCSS/daisyUI animation system
- Never partially migrate APIs or mix Tailwind `transition-*` and Angular Animations API in the same component
- Do not introduce `framer-motion`, `GSAP`, or other JS animation libraries — workspace uses CSS/WAAPI

---

## Common Fixes (Angular Context)

```css
/* layout thrashing: animate transform instead of width */
/* BEFORE */ .panel { transition: width 0.3s; }
/* AFTER  */ .panel { transition: transform 0.3s; transform-origin: left; }
/* Use scaleX() to simulate width expansion without layout */

/* scroll-linked: use CSS View Timeline instead of JS scroll listener */
/* BEFORE (Angular @HostListener scroll) */
/* AFTER */
.reveal {
  animation: fadeUp linear both;
  animation-timeline: view();
  animation-range: entry 0% entry 30%;
}

/* Tailwind: prefer translate over top/left */
/* BEFORE */ .dropdown { transition: top 0.2s; }
/* AFTER  */ .dropdown { transition: translate 0.2s; }
/* Tailwind v4: translate-y-2 → translate-y-0 with transition-transform */
```

```typescript
// FLIP measurement pattern — batch reads before writes
flipTransition(el: HTMLElement): void {
  const first = el.getBoundingClientRect(); // read
  this.expanded.set(true);                  // write (state change)
  el.offsetHeight;                          // force single reflow
  const last = el.getBoundingClientRect();  // read after write
  const dy = first.top - last.top;
  el.style.transform = `translateY(${dy}px)`;
  el.style.transition = 'none';
  requestAnimationFrame(() => {
    el.style.transition = 'transform 0.25s ease-out';
    el.style.transform = 'none';
  });
}
```

---

## Review Guidance

- Enforce critical rules first (never patterns, tool boundaries)
- Choose the least expensive rendering work that matches the design intent
- For any non-default choice, state the constraint that justifies it (surface size, duration, or interaction requirement)
- When reviewing, prefer actionable notes and concrete alternatives over theory
- Angular-specific: check whether `@HostListener('window:scroll')` is being used for animation — always flag for replacement with CSS View Timeline or IntersectionObserver

---

## Related Skills

- `angular-spa` — Angular component patterns; `reference/animations.md` covers timing standards and keyframes
- `web-performance-optimization` — Core Web Vitals, bundle size, lazy loading (loading performance, not animation runtime)
- `tailwind-patterns` — Tailwind v4 `@theme` config and utility patterns
- `accessibility-audit` — WCAG 2.2 motion criteria (2.2.2 Pause/Stop/Hide and 2.3.1 Three Flashes are A; 2.3.3 Animation from Interactions is AAA) and `prefers-reduced-motion` checks
