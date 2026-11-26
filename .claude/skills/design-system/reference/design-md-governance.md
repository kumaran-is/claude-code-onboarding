# DESIGN.md Governance

A project's `DESIGN.md` is the canonical, human-readable design contract for every UI target it ships (phone, tablet, web; light and dark). The toolkit never ships brand values: it ships the procedure for finding, reading, applying and checking the project's own.

## 1. Discovery (every UI task, before writing code)

1. Look for `DESIGN.md` at the repository root, then `docs/DESIGN.md`, then `design/DESIGN.md`. The first hit is canonical. Copies inside `.worktrees/`, `worktrees/`, `node_modules/` or a package folder are not authoritative; a second copy is a drift finding, never a second source.
2. `python3 .claude/scripts/check-design-system.py --root .` prints the canonical path (or that it is missing) before its findings.
3. Read ONLY the sections the task touches (use the section index in §4 and `grep -n '^#' DESIGN.md`); never load the whole file into context "just in case". Follow links from those sections to the project's supplementary standards (colour, type, spacing, icons, motion, async states) only for the parts you change.
4. Inspect the token code that implements the sections you read (see §2) and the shared components that already solve the job. Reuse before creating.
5. Apply, then validate: run the gate, the project's contrast/golden tests if present, and the async transition tests for any data screen.

## 2. Precedence (one ordered list)

| Rank | Source | Role |
|---|---|---|
| 1 | Project token code (Flutter `ThemeData` + `ThemeExtension`s; web CSS variables in the Tailwind `@theme` / daisyUI theme / shadcn `:root` + `.dark` block) | The values that actually render. Implements DESIGN.md |
| 2 | DESIGN.md token front matter (when the project uses the machine-readable format) | Generated from rank 1 or checked against it in CI; never hand-edited to disagree |
| 3 | DESIGN.md prose (rules, recipes, component contracts, screen decisions) | Usage rules and intent |
| 4 | Supplementary standards the DESIGN.md links (colour, type, spacing, icon, motion, async/refresh docs) | Detail for one domain; they never override DESIGN.md |
| 5 | Wireframes, mocks, acceptance criteria | Own WHAT the screen shows; DESIGN.md owns HOW. Never copy a raw value from a mock: map it to the closest token |
| 6 | Toolkit defaults (`ui-standards-tokens`, the scaffolds) | Used only when the project has no authority for that value, and reported as "toolkit default, not project-approved" |

Disagreement between ranks 1–4 is a **drift finding**: report both citations and stop for that value. Never resolve it silently in either direction, and never "fix" DESIGN.md to match code (or code to match DESIGN.md) without the human's decision.

## 3. Missing or incomplete DESIGN.md

| Situation | Behaviour |
|---|---|
| Existing project, no DESIGN.md | Flag it once at the start of the UI task ("no canonical DESIGN.md: following existing token code; toolkit defaults are unapproved"). Do not block. Follow the project's existing tokens and components; do not invent a palette, type scale or spacing scale |
| New project from a `/scaffold-*` command | The scaffold writes a DESIGN.md skeleton (§5) whose values are the scaffold's token defaults, each marked `status: toolkit-default`. The human replaces or approves them |
| The task needs a value DESIGN.md does not define (gap) | Reuse the closest documented rule or token. If none fits, STOP and ask; propose the DESIGN.md addition first, code second |
| Non-UI work | Not applicable: never block backend, data or infra work on DESIGN.md |

Never invent brand values (colours, fonts, logos, product names, illustrations). A missing value is a question, not a creative opportunity.

## 4. What DESIGN.md governs (section index)

Use these headings (or the project's own equivalents) to find the part you need:

`Tokens` (colour roles light/dark, typography roles, spacing scale, shape/radius, elevation, sizes and breakpoints, opacity, motion durations and curves) · `Icons` (one family, wrapper, sizes, semantic registry, labels, RTL) · `Components` (tier, variants, states, recipes) · `States` (loading, skeleton, refresh, empty, error, offline, pagination, mutation, AI streaming) · `Refresh` (per-screen decision table) · `Motion` (engine rule, reduced motion) · `Accessibility` (contrast targets, target size, text scaling, focus, semantics) · `Responsive` (window classes, layout per class) · `Localisation` (RTL, formatting, text expansion) · `Screens` (per-screen decisions) · `Gap policy` and `Change log`.

Each domain gets one invariant sentence in DESIGN.md; the detail lives in the linked standard or the toolkit reference. Rules, hooks and messages name tokens by reference to DESIGN.md and never restate values.

## 5. Generating a DESIGN.md for a new project

The scaffold writes this skeleton; fill values from the generated token files (rank 1), not from memory:

```markdown
# DESIGN.md — <app name>
> Canonical design contract. Token code implements it; disagreement is a drift finding.
> status: toolkit-default (replace with approved values)

## Tokens
Colour roles: <list roles from the token file, light and dark>  · Type roles: <role → size/weight/line height>
Spacing scale: <names → values> · Radius: <names> · Elevation: <names> · Motion: <durations, curves>
## Icons
Family: <one library> via <wrapper path>; sizes <ramp>; decorative icons hidden from assistive tech.
## Components
Shared library: <path>. Tiers: Atom / Molecule / Organism (line-1 `// Tier:` marker).
## States
Follow the async-state contract (loading, skeleton, refresh, empty, error, offline) — link.
## Refresh
| Screen | Source | Strategy | Accessible equivalent |
## Motion
Native/CSS for everyday motion (default). Name Lottie and/or Rive here before adding the package; Lottie decorative only; Rive interactive only; reduced motion collapses durations. Gate: `DS-ANIM-DECISION`.
## Accessibility
Contrast ≥ 4.5:1 text / 3:1 large text and UI; targets ≥ 44 px web / 48 dp Flutter; 200% text.
## Gap policy
No token fits → stop and propose a DESIGN.md change first.
```

## 6. Drift checks a project should run in CI (recommended, project-owned)

- Token drift: the front matter (or a token table) equals the values exported from token code.
- Name existence: every component, widget key and path DESIGN.md names exists in code.
- Contrast: a test that reads the live theme for BOTH modes and asserts each text/background pair against its target (not a hand-maintained list).
- Co-change: a PR that changes token or shared-component files also changes DESIGN.md (or states why not).
- The toolkit gate: `python3 .claude/scripts/check-design-system.py --root . [--require-design-md]`.
