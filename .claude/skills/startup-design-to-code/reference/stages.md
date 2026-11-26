# G0–G10 procedures

Load this file when running a stage. Dispatch existing skills; do not re-implement them.

| Gate | Outcome | Load | Command / gate |
|---|---|---|---|
| G0 Idea / brief | `PRODUCT_BRIEF.md`, `USER_JOURNEYS.md`, `VALIDATION_PLAN.md` | this skill; optional `feature-forge` for a later backlog | manifest `--set-stage G0` |
| G1 Stitch preflight | MCP connected, tools listed | [stitch-preflight.md](stitch-preflight.md) | G1 BLOCKED if no server |
| G2 Screen briefs | 3–6 briefs, inventory rows `draft` | this skill; `mobile-ux-principles.md` | |
| G3 Screens + variants | Approved Stitch IDs | discovered Stitch tools only | never fake IDs |
| G4 DESIGN.md | Google Labs format + toolkit sections | `design-system/reference/design-md-governance.md` | `npx @google/design.md lint` when installed; `/lint-design-system` |
| G5 Prototype + users | Clickable pilot, `g5` decision | [prototype.md](prototype.md) | human PROCEED / ITERATE / STOP |
| G6 Architecture | Platform + token ownership | `architecture-design`; Angular `ui-mode-selection.md` | no scaffold yet |
| G7 Translate screens | Idiomatic Flutter / Angular / React | [production-handoff.md](production-handoff.md) | existing `/scaffold-*` after approval |
| G8 Behaviour | Async/refresh/offline truth | `interaction-contracts.md` §6b–6c | |
| G9 Verify | a11y, visual, E2E | `accessibility-auditor`, `browser-testing`, Maestro for Flutter devices | `/lint-design-system`, `/verify` |
| G10 Evolve | Traceability, DESIGN.md diffs | `design-system` | `npx @google/design.md diff` when installed |

## G0

Fill the product-brief template. A reviewer can state user, problem, one task, success criterion and test plan without guessing. Do not generate UI.

## G2

One screen, one job. Include persona, primary action, realistic example data, navigation, states (cold, cached, empty, filtered-empty, error, offline, success), a11y, device, acceptance task. Formula is in the parent SKILL.md.

## G3

Three to six screens. At most two or three variants of the highest-impact screen. Record chosen variant and why. Targeted edits, not full regenerations. Inventory IDs are stable.

## G4

Ten Google Labs sections in order: Overview; Colors; Typography; Layout; Elevation & Depth; Shapes; Motion & Micro-interaction; Voice & Content Strategy; Components; Do's and Don'ts. Then toolkit addenda (Icons, States, Refresh, Accessibility, Gap policy, Approved screens) from `design-md-governance.md` §5. Semantic tokens, `{path.to.token}` references. CLI lint is structural; it is not WCAG certification.

## G5

See [prototype.md](prototype.md). The human records PROCEED / ITERATE / STOP. ITERATE returns to G2/G3. STOP leaves the manifest; do not start G6.

## G6–G10

See [production-handoff.md](production-handoff.md). Production code requires `decisions.production_approved`.
