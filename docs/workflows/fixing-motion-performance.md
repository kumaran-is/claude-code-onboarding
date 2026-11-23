# Fixing Motion Performance — Angular 22.x

> **When to use**: Angular animations stutter, transitions drop below 60fps, scroll-linked motion is slow, or auditing CSS animation code for performance regressions
> **Skill**: `.claude/skills/fixing-motion-performance/`
> **Stack**: Angular 22.x + TailwindCSS v4 + daisyUI 5.8.2

> **Iron Law**: Default to `transform` and `opacity` only. Resolve compositor vs paint vs layout tier BEFORE writing animation CSS.

---

## The Three Rendering Tiers

Before touching any animation, identify which tier it runs on:

| Tier | Properties | Cost | Rule |
|------|-----------|------|------|
| **Composite** | `transform`, `opacity` | Cheapest — compositor thread | Always prefer |
| **Paint** | `background`, `color`, `box-shadow`, `filter` | Medium — rerasters pixels | Small elements only |
| **Layout** | `width`, `height`, `top`, `left`, `margin` | Most expensive — recalculates flow | Never animate continuously |

---

## Phase 0 — Diagnose Before Fixing

Open Chrome DevTools before changing any code:

1. **Performance tab** → Record while reproducing the jank → Look for long frames (red bars) and "Layout" or "Paint" tasks
2. **Rendering tab** → Enable "Paint flashing" → Animated elements should NOT flash green on every frame
3. **Layers panel** → Check promoted layers — too many = GPU memory pressure
4. **Check for scroll listeners**: `grep -n "window:scroll\|scrollTop\|scrollY" src/`

Only fix what profiling confirms is broken. Do not optimize by instinct.

---

## Phase 1 — Apply Never Patterns Check

Scan files for critical violations first:

```bash
# Find scroll event listeners used for animation
grep -rn "@HostListener.*scroll\|window:scroll\|scrollTop\|scrollY" src/app --include="*.ts"

# Find layout property transitions
grep -rn "transition.*width\|transition.*height\|transition.*top\|transition.*left\|transition.*margin" src/app --include="*.scss" --include="*.css"

# Find will-change on static elements (not in hover/focus handlers)
grep -rn "will-change" src/app --include="*.scss" --include="*.css"
```

Each hit is a **Critical** violation. Fix these before anything else.

---

## Phase 2 — Fix by Category

### Layout thrashing → Use transform

```css
/* BEFORE — causes layout recalculation */
.sidebar { transition: width 0.3s ease; }
.sidebar.open { width: 280px; }

/* AFTER — compositor-only */
.sidebar { transition: transform 0.3s ease; transform: translateX(-280px); }
.sidebar.open { transform: translateX(0); }
```

### Scroll-linked → Use CSS View Timeline

```typescript
// BEFORE — Angular @HostListener (layout read + write per scroll event)
@HostListener('window:scroll')
onScroll() {
  this.opacity = Math.min(window.scrollY / 300, 1);
}
```

```css
/* AFTER — CSS View Timeline (compositor thread, zero JS) */
.fade-in-section {
  animation: fadeUp linear both;
  animation-timeline: view();
  animation-range: entry 0% entry 35%;
}

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(20px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

### Layout-like animation → FLIP

```typescript
// When design requires height/size change animation
flipExpand(el: HTMLElement): void {
  const first = el.getBoundingClientRect();   // READ
  this.isExpanded.set(true);                  // WRITE
  el.offsetHeight;                            // force single reflow
  const last = el.getBoundingClientRect();    // READ
  const dy = first.top - last.top;
  el.style.transform = `translateY(${dy}px)`;
  el.style.transition = 'none';
  requestAnimationFrame(() => {
    el.style.transition = 'transform 0.25s ease-out';
    el.style.transform = 'none';
  });
}
```

### will-change → Use surgically

```typescript
// Add will-change before animation starts, remove after it ends
@HostListener('mouseenter')
onEnter(): void { this.el.nativeElement.style.willChange = 'transform'; }

@HostListener('animationend')
onEnd(): void { this.el.nativeElement.style.willChange = 'auto'; }
```

### Blur → Minimize and scope

```css
/* BAD — large surface, continuous */
.hero { transition: backdrop-filter 0.5s; }

/* OK — modal backdrop, one-shot, small radius */
.modal-backdrop {
  animation: blurIn 200ms ease-out forwards;
}
@keyframes blurIn {
  from { backdrop-filter: blur(0); opacity: 0; }
  to   { backdrop-filter: blur(4px); opacity: 1; }
}
```

---

## Phase 3 — Verify Fix

After each change, re-profile in Chrome DevTools:

- [ ] Performance tab: no "Layout" or "Paint" tasks during animation
- [ ] Paint flashing: no green flashes on the animated element during motion
- [ ] Frame rate: stays at 60fps on throttled CPU (4x slowdown)
- [ ] Layers panel: no unexpected layer explosions
- [ ] `prefers-reduced-motion`: animations disabled with `@media (prefers-reduced-motion: reduce)` (already in `angular-spa/reference/animations.md`)

---

## Phase 4 — File Audit Mode

Use the skill as a file auditor for PR reviews:

```
/fixing-motion-performance src/app/features/dashboard/dashboard.component.scss
```

Output format per violation:
```
VIOLATION [priority]: <rule category>
LINE: <exact quoted snippet>
WHY: <one sentence impact>
FIX: <concrete before/after code>
```

---

## Common Pitfalls

| Pitfall | Correct Approach |
|---------|-----------------|
| `transition: width/height` on panel/sidebar | `transition: transform` + `scaleX/Y` or FLIP |
| `@HostListener('window:scroll')` for reveal | CSS `animation-timeline: view()` |
| `will-change: transform` on all `.card` | Add/remove `will-change` on hover start/end only |
| Animating `backdrop-filter` on hero sections | One-shot modal only, delta <= 8px, use `opacity` first |
| Reading `getBoundingClientRect()` inside rAF loop | FLIP: measure once before state change |
| Mixing Tailwind `transition-*` + Angular Animations module | Pick one per component — never both |
| `transition: all` (catches layout properties) | Explicit: `transition: transform 0.2s, opacity 0.2s` |

---

## Related Workflows

- [feature-angular-spa.md](feature-angular-spa.md) — Full Angular feature lifecycle
- [web-performance-optimization.md](web-performance-optimization.md) — Core Web Vitals, bundle size, loading performance
- [accessibility-audit.md](accessibility-audit.md) — `prefers-reduced-motion` WCAG compliance
- [design-system-compliance.md](design-system-compliance.md) — daisyUI token enforcement
