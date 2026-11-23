# Frontend Design Principles

## Design Thinking Process

Before writing any code, think through these dimensions:

1. **Purpose** -- what problem does this interface solve? Who uses it?
2. **Tone** -- commit to a BOLD aesthetic direction. Options (use for inspiration, don't be mechanical):
   - Brutally minimal / Maximalist chaos / Retro-futuristic / Organic/natural
   - Luxury/refined / Playful/toy-like / Editorial/magazine / Brutalist/raw
   - Art deco/geometric / Soft/pastel / Industrial/utilitarian / Cyberpunk/neon
   - Swiss/grid-based / Memphis/80s-pop / Zen/Japanese-minimalist / Vaporwave

   Pick ONE dominant direction and execute it with conviction. **No two projects should share the same tone.**
3. **Differentiation** -- what makes this unforgettable? What's the one thing someone will remember?
4. **Constraints** -- framework, performance, accessibility, responsive breakpoints

## Aesthetics Rules

### Typography
- Choose fonts that are beautiful, unique, and characterful
- **NEVER** use generic fonts: Arial, Inter, Roboto, system-ui defaults
- Pair a distinctive display font with a refined body font
- Size, weight, and letter-spacing matter -- tune them precisely

### Color & Theme
- Commit to a cohesive palette using CSS variables / SCSS variables / Flutter theme tokens
- Dominant color with sharp accents beats timid, evenly-distributed palettes
- **NEVER** default to purple gradients on white -- the hallmark of AI slop
- Vary between light and dark themes across projects
- Consider the emotional tone: warm, cool, electric, muted, earthy

### Motion & Interaction
- Use animations for delight: page-load reveals, staggered entries, hover surprises
- One well-orchestrated entrance sequence beats scattered micro-interactions
- Scroll-triggered reveals, parallax, and meaningful state transitions
- CSS-only for HTML; Angular animations for web; implicit/explicit animations for Flutter

### Spatial Composition
- Break the grid intentionally: asymmetry, overlap, diagonal flow
- Generous negative space OR controlled density -- both work if intentional
- Unexpected layouts over predictable card grids
- Z-depth through shadows, layering, and transparency

### Backgrounds & Atmosphere
- Create depth: gradient meshes, noise textures, geometric patterns, grain overlays
- Layered transparencies, dramatic shadows, decorative borders
- **NEVER** default to flat solid white/gray backgrounds without purpose

## Anti-Patterns -- What to Avoid

- Overused font families (Inter, Roboto, Arial, Space Grotesk, system fonts)
- Cliche color schemes (purple gradients on white, generic blue-on-gray)
- Predictable card-grid layouts with no spatial personality
- Cookie-cutter components that look like every other AI-generated UI
- Converging on the same choices across different designs -- every project should feel unique

## Quality Checklist

Before delivering any UI, verify:
- Clear aesthetic direction -- can you name the style in 2-3 words?
- No generic fonts or default color schemes
- At least one moment of delight (animation, hover effect, scroll interaction)
- Responsive across mobile to desktop
- Accessible (contrast ratios, focus states, semantic HTML / Flutter semantics)
- Theme tokens / CSS variables for consistency
- Production-ready -- no placeholders or TODOs in shipped UI

## Key Principle

Match implementation complexity to the aesthetic vision. Maximalist designs need elaborate animations and effects. Minimalist designs need restraint, precision, and meticulous spacing. Elegance comes from executing the vision well, not from intensity.

---

## DFII Quick-Score Card

Use this when evaluating a design direction. Score each dimension 1–5 then apply the formula.

```
Project: _______________
Aesthetic Direction: _______________

Aesthetic Impact:           ___ / 5
Context Fit:                ___ / 5
Implementation Feasibility: ___ / 5
Performance Safety:         ___ / 5
Consistency Risk:           ___ / 5  (subtract)

DFII = (Impact + Fit + Feasibility + Performance) − Risk = ___

≥ 8 → proceed | 4–7 → reduce scope | ≤ 3 → rethink
```

---

## Differentiation Anchor Examples

Use these as inspiration. Your anchor must be original.

| Aesthetic Direction | Potential Anchor |
|---|---|
| Editorial Brutalism | Full-bleed typography with raw grid breaks and monochrome photography |
| Luxury Minimal | Extreme whitespace with one gold accent and custom serif display font |
| Retro-futuristic | Scanline texture overlaid on bright neon palette with monospace UI font |
| Industrial Utilitarian | 1px hairline borders, no border-radius, dense data tables, no decoration |
| Organic Natural | Hand-drawn SVG borders, warm earth tones, variable-weight typeface |
| Playful Toy-like | Oversized rounded corners, bold primary palette, bouncy entrance animations |

---

## Anti-Patterns (Immediate Failure — Restart)

If any of these are present, do NOT ship. Restart the design direction:

- **Fonts:** Inter, Roboto, Arial, Space Grotesk, system-ui as primary display font
- **Colors:** Purple-on-white gradient, generic blue-on-gray, flat solid background with no atmosphere
- **Layout:** Symmetrical hero → 3-column features → CTA footer (the AI template)
- **Components:** Default Tailwind card, default ShadCN layout, default Material card
- **Motion:** No animation on a maximalist design, OR decorative micro-motion spam on a minimalist design
- **Differentiation:** Cannot answer "how would someone recognize this without the logo?"

---

## Framework-Specific Execution Notes

### Angular (daisyUI 5.8.2 + Tailwind CSS 4.3.5)
- Use daisyUI semantic tokens for all colors: `bg-primary`, `text-base-content`, `bg-base-100`
- Custom aesthetics: extend daisyUI theme in CSS — do NOT hardcode hex values
- Typography: load custom fonts via `@font-face` in global styles, reference via Tailwind `font-*` utility
- Motion: use `angular-spa/reference/animations.md` timing standards; add CSS `@keyframes` in component SCSS

### Flutter (Theme + AppSpacing tokens)
- All colors via `Theme.of(context).colorScheme.*` — never `Colors.blue` or `Color(0xFF...)`
- All spacing via `AppSpacing.xs/sm/md/lg/xl` — never `EdgeInsets.all(16)`
- Custom aesthetic: extend `ThemeData` in `flutter-design-polish.md` patterns
- Motion: use `flutter-mobile/reference/flutter-performance-ux.md` animation patterns

### HTML/CSS (Standalone)
- Define all design tokens in `:root { --color-primary: ...; --spacing-base: ...; }`
- CSS-first animations; Framer Motion only if already in the project and justified
- Prefer `clamp()` for fluid type scaling; `CSS Grid` + `subgrid` for layout
