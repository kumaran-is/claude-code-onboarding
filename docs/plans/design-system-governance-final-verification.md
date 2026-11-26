# Design-System Governance: Final Independent Verification

Date: 2026-11-25 · Branch: `feat/flutter-mobile-engineering-best-practices` (uncommitted, 41 files, +1292/-172 per `git diff HEAD --stat`)
Auditor stance: no implementer claim accepted; doc text is not evidence of enforcement. A row is PASS only with file:line evidence plus, where enforceable, a check run in this session that fails on a violation.

**Current verdict (second re-verification, §7): READY.**
- All 4 original P1 findings are now FIXED. F1, F3 and F4 were fixed in the first round (§6); F2 in the second (§7).
- No P0 or P1 is open.
- Caveats:
  - The Flutter 3.50 scaffold is still BLOCKED, because the local SDK is 3.44.2. The toolkit's own review policy says a BLOCKED required check caps a merge verdict at NEEDS_REVIEW until it runs on a 3.50 SDK.
  - The P2 follow-ups listed in §4 stay open.

History: original audit NEEDS FIXES (4 P1s) → §6 NEEDS FIXES (F2 open) → §7 READY. Sections 2 and 4 show the latest statuses and outcomes.

---

## 1. Scope, method, sources, commands

### Method
1. I read all 10 SOURCE standards in full. SOURCE was used read-only: `git status --short` in SOURCE shows 0 lines.
2. I took every brand-neutral rule from the SOURCE standards and looked for where TARGET places it: skill, agent, command, rule, hook, gate.
3. I ran the gate's selftest and the hookify tests.
4. I ran the gate against all five runtime apps.
5. I planted 27 probe files in two ways: in a fresh scratch tree (`<scratchpad>/audit-probe-tree`, `<scratchpad>/audit-probe2`), and as copies inside `ng-daisy` and `react-app`. The in-app plants were removed afterwards, and the gate was green again after the revert.
6. I re-ran the unit tests for every app and the Playwright suites for all four web apps.
7. Brand leakage was checked by grepping the `+` lines of the diff and comparing the fixture hex values against the SOURCE palette (0 matches).

### Sources read (each to its last line)
| # | SOURCE file | Lines | Last line read | Reader |
|---|---|---|---|---|
| 1 | `DESIGN.md` (root; worktree copies ignored) | 3017 | 3017 | delegated read-only sub-agent, chunked |
| 2 | `docs/design-system/property-harbor-color-system.md` | 2240 | 2240 | delegated read-only sub-agent |
| 3 | `…/property-harbor-icon-system.md` | 1987 | 1987 | delegated read-only sub-agent |
| 4 | `…/property-harbor-typography.md` | 1421 | 1421 | delegated read-only sub-agent |
| 5 | `…/property-harbor-spacing-system.md` | 1601 | 1601 | delegated read-only sub-agent |
| 6 | `…/propertyharbor-loading-refresh-empty-error-offline-skeleton-standard.md` | 1034 | 1034 | delegated read-only sub-agent |
| 7 | `…/propertyharbor-mobile-refresh-strategy-standard.md` | 1156 | 1156 | delegated read-only sub-agent |
| 8 | `…/animation-strategy.md` | 349 | 349 | auditor |
| 9 | `…/atomic-decision-tree.md` | 180 | 180 | auditor |
| 10 | `…/ph-mobile-ui-ux-vision.md` | 772 | 773 (Read shows the final line as 773) | auditor |

The SOURCE enforcement surface was inspected only to judge what is portable:
- 11 hookify design rules (`.claude/hookify.design-*`, `require-tier-comment-*`);
- the scripts `check-loading-states.sh`, `check-pull-to-refresh.sh`, `check-flutter-empty-states.sh`, `check-offline-banner-singleton.sh`, `check-staleness-label-host.sh` and `check-animation-libs.sh`.

### Commands run (each tool's own exit code)
| Command (from the TARGET root unless noted) | Exit | Result |
|---|---|---|
| `python3 .claude/scripts/check-design-system.py --selftest` (Python 3.14.3) | 0 | 43 of 47 fixtures scanned (4 are out of scope by design), 42 findings, PASS |
| `python3 .claude/hookify/tests/test_rules.py` | 0 | 11 rules, positive and negative controls, PASS |
| `bash .claude/scripts/check-context-budget.sh --strict` | 0 | 60342 ≤ 62000, 22/22 canaries |
| `git check-ignore --no-index -v` on the design rules and on a personal `*.local.md` | 0 | design rules re-included by `.gitignore:24`; the personal file is still ignored by the global `*.local.md` |
| gate `--root <scratchpad>/rt/flutter-ds` | 0 | 13 files, DESIGN.md canonical, PASS |
| gate `--root …/ng-daisy` · `ng-spartan` · `ng-hybrid` | 0 · 0 · 0 | 29 files each, PASS |
| gate `--root …/react-app` | 0 | 38 files, PASS |
| gate on probe tree 1 (21 planted violations) | 1 | only 2 of 21 flagged (n3, n15); details in §4 |
| gate on probe tree 2: `[color]="'#…'"`, `color={"#…"}`, cross-package `AppSpacing`, a 10-character reason | 1 | only the 10-character-reason line is flagged |
| gate on probe tree 2, React app with no DESIGN.md · same with `--require-design-md` · `--files` with no arguments | 0 · 1 · 2 | missing file is a warning by default, an error with `--require-design-md`; empty `--files` is a usage error |
| in-app plants with revert (6 plants) | 1, 0, 0, 0, 0, 1 | the 2 controls are caught; the 4 probes are missed (§4) |
| `flutter test` in `flutter-ds` (Flutter 3.44.2) | 0 | 17 passed |
| `npx vitest run` in `react-app` | 0 | 53 passed |
| `npx ng test --watch=false` in `ng-daisy` · `ng-spartan` · `ng-hybrid` | 0 · 0 · 0 | 42 · 18 · 18 passed |
| `npx playwright test` in `ng-daisy` | 0 | 12 passed |
| `UI_MODE=spartan npx playwright test` in `ng-spartan` | 0 | 9 passed |
| `UI_MODE=hybrid PW_PORT=4391 npx playwright test` in `ng-hybrid` | **1** | 10 passed, **1 failed**: reduced motion, `smilInCss: 1` (also failed in the implementers' own last log `ng-hybrid.pw.out`) |
| `npx playwright test` in `react-app` | 0 | 54 passed |

The Flutter 3.50 scaffold is **BLOCKED** because the local SDK is 3.44.2. `flutter-ds` is a hand-written package; its own files note that it substitutes `package:flutter/material.dart` for `material_ui`.

---

## 2. Main table

| Requirement | Source section | Flutter | Angular | React | Skills | Agents | Commands | Rules/hooks | Runtime proof | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| DESIGN.md discovery, precedence, missing-file behaviour, no whole-file loading | DESIGN.md 181–200, 1248–1253, 2801–2804, 3014 | `scaffold-flutter-app.md:41` writes the skeleton | `scaffold-angular-app.md:139` | `scaffold-react-app.md:89` | `design-system/reference/design-md-governance.md:5-35` (root → docs → design; worktrees ignored; read only the needed sections; 6-rank precedence; gap = stop) | `ui-standards-expert.md:34-37`, `design-system-reviewer.md:29` | `lint-design-system.md:16-17`, `verify.md:466-469` | `web-frontend.md:18`, `flutter-engineering.md:20`; gate `check-design-system.py:324-334`, selftest `:536-546` | All 5 apps print `DESIGN.md: DESIGN.md (canonical)`. Missing → WARNING, exit 0; `--require-design-md` → `DS-DESIGN-MD`, exit 1 | PASS |
| Three tiers, line-1 `// Tier:` marker | atomic-decision-tree 38–81, 150–169; DESIGN.md 1585–1600 | `DART_LIB` `check-design-system.py:76-82` | `NG_LIB :83-84` | `RX_LIB :85-86` | `atomic-decision-tree.md:5-32` | `design-system-reviewer.md:38-49` | `lint-design-system.md:33` | `hookify.design-tier-comment-{dart,angular,react}` (tests pass); `DS-TIER :277-280`; fixtures `:407-409, :466` | Governed files in all 5 apps carry markers (gate PASS) | PASS (path caveat: F7) |
| Dumb button with isBusy/tone/onPressed → PASS | color-system 1079–1155; DESIGN.md 1656–1668 | fixture `:394-399` | fixture `:446-448` | fixture `:482-483` | `atomic-decision-tree.md:53` | `design-system-reviewer.md:54-56` | — | `DS-PRESENTATIONAL` | selftest clean on all three | PASS |
| Dumb component doing HTTP → FAIL | DESIGN.md 1585–1587 | regex `dio\|http` `:145-146` | fixture `HttpClient` `:464-465` | regex `fetch(\|axios` `:155-156` | `atomic-decision-tree.md:54` | same | same | hookify presentational `:12` | selftest flags it | PASS |
| Angular component injecting a domain service → FAIL | DESIGN.md 1634–1635 | — | `inject()` caught: fixtures `:450-456`, probes n3 and n15. Constructor parameter properties are now caught (`check-design-system.py:162-164`; fixture `kpi-card.ts :524`) | — | `atomic-decision-tree.md:42, 55` | same | same | hook gained a constructor branch but still diverges (F11) | Re-verification: probe n1 and the multi-line / `@Inject` probes → `DS-PRESENTATIONAL`. Mutating the constructor branch away makes the selftest exit 2. Residual misses: generic, union and plain constructor parameters (F1r) | PASS (re-verified) |
| React shared badge importing a global store → FAIL | DESIGN.md 1585 | — | — | fixtures `:485-491`; in-app `zustand` plant → exit 1 | `atomic-decision-tree.md:56` | same | same | same | `useContext(CartContext)` plant → exit 0 (F6) | PASS (F6 advisory) |
| Flutter atom importing feature repositories → FAIL | DESIGN.md 1587 | fixture `:400-402` | — | — | `atomic-decision-tree.md:57` | same | same | same | Probe n7 (repository outside `features/`) → missed (F6) | PASS (F6 advisory) |
| Smart container passing a semantic status → PASS | color-system 1079–1155 | fixture `:416-418` | — | `react-plant.log`: feature passes `tone="warning"` → exit 0 | `atomic-decision-tree.md:45, 58` | — | — | — | selftest clean | PASS |
| Raw hex for a business status → FLAG | color-system 368–405; DESIGN.md 390–420 | `Color(0x…)` fixture `:419-422` | `color="#…"` / `[color]="'#…'"` caught (`:117-118`); a ternary binding and a `.ts` status map caught by the hex-string detector (`:123`) | `color={"#…"}`, `statusColor="#…"`, a hex const and a ternary all caught (`:117-123`; fixtures `status-colors.ts`, `late-badge.tsx`, `anchors.tsx`) | `atomic-decision-tree.md:59` | `ui-standards-expert.md` | `lint-design-system.md:26` | `DS-COLOR :97-123` | §7: probes F2a–F2d → `DS-COLOR` exit 1; removing the detector → selftest exit 2; 5 apps exit 0. Residuals F2r (P2) and F22 (P3) | PASS (re-verified ×2) |
| Token governance, no parallel authorities | DESIGN.md 551–557, 673, 2497–2566; spacing 904–935 | `DS-SCALE` covers Dart spacing/radius/motion classes in one app root (`:172-174, :381-386`) | colour vars re-declared outside the global sheet caught (`:113-114`) | same | `token-governance.md:18` now states what is and is not enforced | `ui-standards-expert.md:34-37` | `lint-design-system.md:28, 37-39` | `DS-SCALE` is workspace-wide (`:408`); `DS-AUTHORITY` (`:183, :422`); web `DS-SHAPE` (`:131-134`) | Re-verification: `brand_colors.dart` → `DS-AUTHORITY`; cross-package `AppSpacing` → `DS-SCALE`; `border-radius: 13px` → `DS-SHAPE`. No false positives on the 5 apps. Residual: `--spacing: 0.3rem` in a feature stylesheet is missed (F3r); `calc(var(--radius) - 4px)` is a false positive (F21) | PASS (re-verified) |
| Icons: one library behind a wrapper; Phosphor not mandated | icon-system 134–170, 1855; DESIGN.md 1565–1580 | Package imports isolated (`:159-162`); **Material `Icons.x` in feature code is not flagged** (`:312-313` only counts the family) (F5) | `ng-spartan`/`ng-hybrid` `shared/components/icon/icon.ts` is the only importer (gate PASS) | `lucide-react` isolation fixtures `:493-498` | `token-governance.md:26-33` ("does not mandate a family") | `ui-standards-expert.md:73-76` | `scaffold-angular-app.md:136-138` | `DS-ICON-ISOLATION`/`DS-ICON-FAMILY`; `PROJECT_EXPECTED :504` | selftest; probe n9 (`Icon(Icons.delete)` in a feature) → missed | PARTIAL |
| Async states: content-first, smart host owns state, framework-native types, transition tests | loading std §0–§5, §13–§15, §26; DESIGN.md 1246–1367 | `flutter-ds` `AsyncView` (Organism) and `items_screen_test.dart` | ng-daisy `async-view`; ng-spartan/hybrid dashboards use a cold-read spinner and have no refresh transition tests (F12) | `OrdersPage.tsx` with `async-section.tsx` | `interaction-contracts.md:126-213` (state model, flash guard, stall, Riverpod 3 / `resource()` / TanStack mapping, 10 required transition tests) | `ui-standards-expert.md:66-69` | — | not gated (review only; SOURCE `check-loading-states.sh` pattern not ported) | Re-run: flutter 17/17; ng-daisy 42/42; react 53/53; `react-test-controls.log` mutation controls caught (C8 single-flight, C9 empty vs failure) | PARTIAL |
| Refresh decision record: six strategies, no default PTR, none on desktop web | refresh std §3 (80–157), §6 (234–266), §13 (473–495) | `items_screen.dart` record | `ng-daisy` `dashboard-page.ts:15-18`; spartan/hybrid DESIGN.md Refresh table | `OrdersPage.tsx:30-34` | `interaction-contracts.md:221-236` (exactly 6 strategies; `:223` no default; `:230` not desktop web) | `ui-standards-expert.md:74` | DESIGN.md skeleton has a Refresh table (`design-md-governance.md:63-64`) | `web-frontend.md:18`; **no gate** (probes n20 `react-simple-pull-to-refresh` and n21 `RefreshIndicator` → no finding) (F8) | records present in 5/5 apps | PARTIAL |
| Animation: native / Lottie / Rive; no automatic installs | animation-strategy §2 (30–60), §11 (281–298), §14 (326–335) | `DS-ANIM` fixtures `:411-431` | `ANIM_PKG web :170` | `react-plant.log`: `lottie-react` in a feature → `DS-ANIM` exit 1 | `token-governance.md:35-45` | `ui-standards-expert.md:76` | `lint-design-system.md:36` | `DS-ANIM`; **no dependency check** and a wrapper-name loophole (F9) | probe `features/x/presentation/celebration_animation.dart` importing lottie → missed | PARTIAL |
| Reduced motion | animation-strategy §12 (302–314); DESIGN.md 1453–1454 | `app_motion_test.dart` passes | `.loading` reduced-motion override in the stylesheet templates (`daisyui-v5-components.md:30-34`, `ui-mode-selection.md:255-259`) and in the `ng-hybrid`/`ng-daisy` `src/styles.css` | `motion-reduce:animate-none` on skeletons; PW 54/54 | `token-governance.md:46` | `accessibility-auditor.md:44` | `scaffold-angular-app.md:102` takes daisy `styles.css` from the template | new `DS-REDUCED-MOTION` (`:186, :427`) | Re-verification: ng-hybrid PW **11/11 exit 0** (reduced-motion test and its control both green; was exit 1). ng-daisy PW 12/12. Removing the override in copies of ng-hybrid / ng-daisy `styles.css` → `DS-REDUCED-MOTION` exit 1; restored → exit 0 | PASS (re-verified) |
| Reusable mobile UX principles | ph-mobile-ui-ux-vision 1–773 | see §3 | see §3 | see §3 | `design-system/SKILL.md:92-103`, `interaction-contracts.md:187-219` | `ui-standards-expert.md:66-69` | — | — | n/a (guidance) | PARTIAL (F13) |
| daisyUI / Spartan / hybrid and React + shadcn modes preserved | DESIGN.md 2880–2912 (role mapping) | n/a | gate excludes CLI-owned `libs/ui`, helm, brain (`:64`); `ui-mode-selection.md` | gate excludes `src/components/ui` (`:64`) | `token-governance.md:9` (hybrid: daisyUI owns the variables) | `ui-standards-expert.md:58` | `scaffold-angular-app.md:134-139`, `scaffold-react-app.md:87-89` | — | gate PASS on all 4 web apps; unit tests 42/18/18/53; PW daisy 12/12, spartan 9/9, react 54/54 (hybrid reduced-motion failure counted in the row above) | PASS |
| Enforcement only where reliable, with positive and negative tests | SOURCE scripts (ratchet, reasoned hatches, self-test controls) | selftest exits 2 when a detector breaks (`:571-573`) | same | same | `token-governance.md:48-58` | reviewers quote gate IDs | `lint-design-system.md:8-20` | hooks are `action: warn` (advisory, now stated in `SKILL.md:107, 141`); the hook regex still diverges from the gate (F11); reason length fixed to 12 characters (`:58`) | Re-verification: selftest exit 0 (49/53 files, 51 findings); hookify exit 0. Mutation: removing the constructor, prop-hex, `DS-AUTHORITY` or `DS-REDUCED-MOTION` logic makes the selftest exit 2. §7: removing the hex-string detector, the web `border-radius:` branch (now with its own fixture `card-radius.css`) or the anchor skip also makes the selftest exit 2. Still PARTIAL: hook/gate drift (F11) and the remaining P2 heuristic gaps | PARTIAL |
| Context budget | — | — | — | — | — | — | — | `check-context-budget.sh --strict` | exit 0, 60342/62000, 22/22 canaries | PASS |
| Committed design rules not silently ignored | — | — | — | — | — | — | — | `.gitignore:22-24` `!.claude/hookify.design-*.local.md` | `check-ignore --no-index`: design rules matched by the `!` rule; personal `*.local.md` still ignored by the global rule; 11 design rules tracked (`git ls-files`) | PASS |
| No SOURCE branding, secrets or business terms copied | all | — | — | — | — | — | — | — | diff `+` lines: no product, persona or brand names; fixture hexes (`0xFF0057B8`, `0xFFE53935`, `0xFF112233`) appear 0 times in the SOURCE colour docs | PASS |
| Flutter 3.50 scaffold end to end | — | `scaffold-flutter-app.md` | — | — | — | — | — | — | local Flutter is 3.44.2 | BLOCKED |

**Counts after the second re-verification (22 rows):** PASS 15 · PARTIAL 6 · FAIL 0 · BLOCKED 1 · NOT APPLICABLE 0 · NOT RUN 0.
- First re-verification: PASS 14 · PARTIAL 7 · FAIL 0 · BLOCKED 1.
- Original audit: PASS 11 · PARTIAL 9 · FAIL 1 · BLOCKED 1.
- Moved to PASS: the Angular domain-service row, token governance, and reduced motion.

---

## 3. Mobile UX principles (ph-mobile-ui-ux-vision)

The "Apply First" block (lines 7–32, 13 items) condenses principles 1–55, so each of its items maps onto the rows below. Applied means the principle has a generic statement in TARGET. None of these is machine-enforced; they are review or guidance only.

| # | Principle (source line) | Applied where / why not |
|---|---|---|
| 1 | Remove before adding (42) | `design-system/SKILL.md:101` (added chrome, nested cards) · partial |
| 2 | Global quality bar, no copying other apps (49) | `SKILL.md:244-257` (AI-slop table) · partial |
| 3 | Value and next action obvious; progressive disclosure (55) | **not transferred** (no "primary task dominant / progressive disclosure" guidance) |
| 4 | Do fewer things well (67) | **not transferred** |
| 5 | Role-aware, not role-identical (74) | not reusable as written (the four roles are product-specific); the generic idea "shared grammar, role-specific density" is **not transferred** |
| 6 | Prioritise what matters now (87) | **not transferred** |
| 7 | Minimise effort safely, ≤3 taps for frequent low-risk tasks (93) | **not transferred** |
| 8 | Safety and truth beat conversion (105) | `interaction-contracts.md:197` (no false success), `:217` |
| 9 | Complexity into simple decisions (126) | **not transferred** |
| 10 | Personalise; never ask what is known (136) | partial: `accessibility-auditor.md:55` (WCAG redundant entry) |
| 11 | Frictionless onboarding (156) | **not transferred** |
| 12 | One-handed use (163) | pre-existing `mobile-design/reference/touch-psychology.md:3` (thumb zones); not linked from design-system |
| 13 | Simple navigation; no duplicate destination CTA (170) | `SKILL.md:101`, `ui-standards-expert.md:69` |
| 14 | Glanceable status, never colour alone (180) | `token-governance.md:22`, `atomic-decision-tree.md:129` |
| 15 | Reduce anxiety while waiting (195) | `interaction-contracts.md:169, 175` (stall message, no fake progress) |
| 16 | No false urgency (216) | **not transferred** |
| 17 | Reuse before inventing (227) | `SKILL.md:95`, `design-md-governance.md:10` |
| 18 | Visual chunking over chrome (241) | `SKILL.md:101` |
| 19 | Desirability without decoration (256) | `SKILL.md:244-257` |
| 20 | Intentional illustration (267) | partial: `token-governance.md:40` (Lottie decorative only); "no illustration in operational flows" missing |
| 21 | Immediate feedback, safe optimistic UI, haptics (283) | `interaction-contracts.md:217`; haptics in `flutter-mobile/reference/flutter-performance-ux.md` |
| 22 | Motion must earn its place (293) | `SKILL.md:102`, `token-governance.md:45` |
| 23 | Respect native behaviour (300) | partial: `flutter-mobile/SKILL.md:129` (Android Back, deep links) |
| 24 | Protect in-progress work (311) | **not transferred** into design guidance (offline-sync drafts only) |
| 25 | Offline-first (325) | `interaction-contracts.md:147, 173`; `flutter-mobile` offline references |
| 26 | Degraded networks (348) | `interaction-contracts.md:175, 197` |
| 27 | Optimistic only when safe (359) | `interaction-contracts.md:197, 217` |
| 28 | Canonical state owns the lifecycle (373) | partial: `interaction-contracts.md:219`; the domain entity list is not reusable |
| 29 | Never trade truth for speed (387) | `interaction-contracts.md:197` |
| 30 | Skeletons correctly (402) | `interaction-contracts.md:134-176, 199` |
| 31 | Design every state (414) | `interaction-contracts.md:197`, `ui-standards-expert.md:66` |
| 32 | Purposeful empty states (433) | `interaction-contracts.md:187-188` |
| 33 | Concise human copy, no enums or UUIDs (440) | partial: `interaction-contracts.md:195` (non-technical copy) |
| 34 | Show time and effort (458) | **not transferred** |
| 35 | Accessibility, 200% text (470) | `accessibility-audit` skill, `accessibility-auditor.md:69` |
| 36 | Never colour alone (482) | `token-governance.md:22` |
| 37 | Dynamic text reflow (491) | `SKILL.md:99`, `ui-standards-expert.md:69` |
| 38 | Forms usable with the keyboard open (499) | `SKILL.md:99`, `ui-standards-expert.md:69` |
| 39 | One destructive-action pattern (506) | partial: `interaction-contracts.md:69` (confirmation) |
| 40 | Consistent bulk selection (516) | **not transferred** |
| 41 | Safe areas and system UI (524) | `SKILL.md:99` (system insets) |
| 42 | Light and dark equal (537) | `token-governance.md:19` |
| 43 | Responsive, not device-specific (547) | `interaction-contracts.md:108-122` |
| 44 | Secure re-authentication (557) | `flutter-mobile/reference/flutter-security-hardening.md:34` (biometric gate) |
| 45 | Privacy-aware surfaces (572) | partial: `flutter-security-client-trust.md:227` (notification payload) |
| 46 | Contextual permission timing (589) | **not transferred** |
| 47 | Deep links land on current truth (602) | partial: flutter navigation reference; "reload canonical state, never trust payload" missing |
| 48 | AI transparency without theatre (612) | `interaction-contracts.md:182, 199, 219` |
| 49 | Action recoverability (630) | partial: `interaction-contracts.md:93` (Undo toast) |
| 50 | Interruptibility (636) | **not transferred** |
| 51 | Auditable state changes (649) | **not transferred** |
| 52 | Localisation beyond translation (658) | `design-system/reference/i18n-rtl-intl.md` |
| 53 | Performance is UX (670) | partial: `code-standards.md` "Performance"; `flutter-architecture-patterns.md:486` |
| 54 | Eliminate small annoyances (682) | partial: `interaction-contracts.md:199` (scroll reset, clear-then-refetch) |
| 55 | Micro-consistency: hierarchy, radius scale, optical alignment (699) | partial: one scale per family (`token-governance.md:18`); hierarchy and optical alignment missing |

Summary: 26 applied, 15 partial, 13 not transferred, 1 not reusable as written (#5).

---

## 4. Findings

### Outcome after re-verification (2026-11-25, §6)
| ID | Sev | Outcome | Evidence |
|---|---|---|---|
| F1 | P1 | **FIXED** | `check-design-system.py:162-164`. Probe n1, multi-line and `@Inject` constructors → `DS-PRESENTATIONAL`; mutation → selftest exit 2. Residual misses are F1r (P2) |
| F2 | P1 | **FIXED** (§7) | §6 left it open: `statusColor="#…"`, a ternary, a `.ts` status map and a hex const all passed. §7: a second web `DS-COLOR` detector (`check-design-system.py:123`) flags any quoted string that is exactly a 3/4/6/8-digit hex. All four probes (F2a–F2d) now → `DS-COLOR` exit 1, plus an Angular `.ts` status map, a TSX ternary and a template literal. Removing the detector → selftest exit 2 (`status-colors.ts`, `late-badge.tsx`). Negatives stay clean: `href="#add"`, `fragment="#add"`. Residuals: F2r (P2), F22 (P3) |
| F3 | P1 | **FIXED** | `DS-AUTHORITY` (`:183, :422`), workspace-wide `DS-SCALE` (`:408`), web `DS-SHAPE` (`:131-134`), honest `token-governance.md:18`. Probes `brand_colors.dart`, cross-package `AppSpacing`, `border-radius: 13px` all caught; no false positives on the 5 apps. Residual: F3r (P2), F21 (P3) |
| F4 | P1 | **FIXED** | ng-hybrid PW 11/11 exit 0 (was exit 1); the override is in both stylesheet templates; `DS-REDUCED-MOTION` fires in ng-hybrid / ng-daisy copies with the override removed and clears when restored. Residual: F18 (P3) |
| F5 | P2 | OPEN | probe n9 (`Icon(Icons.delete)` in a feature) still clean |
| F6 | P2 | PARTIAL | `flutter_bloc`/`bloc`/`provider`/`get_it` added (`:154`; probe n8 now flagged). React `useContext` store (n5), custom hook (n6) and a Flutter repository outside `features/` (n7) still missed |
| F7 | P2 | OPEN | probes n16–n18 still silently ungoverned |
| F8 | P2 | OPEN | probes n20 and n21 still clean |
| F9 | P2 | OPEN | probe `celebration_animation.dart` still clean |
| F10 | P3 | **FIXED** | web `DS-SHAPE` (`:131-134`) |
| F11 | P2 | PARTIAL | the hook gained constructor and full `inject()` logic, but its constructor branch lacks the gate's `^\s*` and decorator alternatives. Multi-line constructor and `@Inject(X) private y: Api` → hook silent, gate flags (pattern tested directly) |
| F12 | P2 | OPEN | Spartan/hybrid dashboards unchanged (cold-read spinner, no refresh transition tests) |
| F13 | P2 | OPEN | no new UX guidance |
| F14 | P3 | **FIXED** | `:58` `\S.{11,}`; an 11-character reason is now flagged, a 12-character reason exempts |
| F15 | P3 | OPEN | `lint-design-system.md:15` recipe unchanged |
| F16 | P3 | **FIXED** | `design-system/SKILL.md:107, 141` say "advisory" |
| F17 | P3 | OPEN | `ng-spartan` status 0 → "offline" unchanged |
| F1r | P2 | NEW | constructor variants missed: `private store: Store<AppState>` (generic), `@Optional() private api: OrderApi \| null` (union), plain `constructor(api: OrderApi)` assigned to a field. NgRx itself is still caught by the `@ngrx/` import rule |
| F3r | P2 | NEW | `.a { --spacing: 0.3rem; }` in a feature stylesheet is not flagged; `DS-COLOR` covers only colour variables and `DS-SPACING-SHADOW` only `--spacing-xs…2xl` |
| F18 | P3 | NEW | `DS-REDUCED-MOTION`: a commented-out override still counts (`/* @media … .loading { mask-image: none } */` → clean), and an override in an `@import`ed `src/styles/motion.css` is not recognised (false positive). `RM_LOADING_OVERRIDE :186` searches the raw text of `src/styles.css` only |
| F19 | P3 | **FIXED** (§7) | new fixture `web/src/app/features/orders/card-radius.css` (`border-radius: 13px` alone). Removing the `border-radius:` branch → selftest exit 2 (`card-radius.css: expected ['DS-SHAPE'], got clean`). In §6 the same mutation gave exit 0 |
| F20 | P3 | NEW | constructor rule false positives: `private ref: MatDialogRef`, `@Inject(DIALOG_DATA) public data: ConfirmData`, and a plain value class `constructor(public readonly x: Num)` in a shared component folder → `DS-PRESENTATIONAL`. Fix: add `MatDialogRef`/`DialogRef<…>` and `@Inject(DIALOG_DATA)`-style tokens to `UI_INJECTABLES`; skip classes without `@Component`/`@Directive` |
| F21 | P3 | NEW | `border-radius: calc(var(--radius) - 4px)` in a component stylesheet → `DS-SHAPE` false positive (a token-derived radius). Fix: skip `calc(` expressions that contain `var(--radius` |
| F2r | P2 | NEW (§7) | The hex-string detector skips any line that contains the word `id`, `href`, `fragment`, `routerLink`, `xlink:href` or `anchor` (`:123` negative lookahead). So `late: { id: 1, hex: '#E53935' },` → exit 0. A colour-named key on such a line is still caught by the first detector (`{ id: 'late', color: '#E53935' }` → `DS-COLOR`). Fix: skip only the matched attribute's own value (`href="#…"`, `fragment="#…"`), not the whole line |
| F22 | P3 | NEW (§7) | Hex-string false positives: `document.querySelector('#feed')` and `{'#123'}` (an order-number-style string) → `DS-COLOR`. `ignore-design:` exempts them; consider skipping `querySelector`/`getElementById` arguments |

### P0
None. No rule was broken unsafely, SOURCE is unmodified, and no secrets or brand data were copied.

### P1

**F1 — `DS-PRESENTATIONAL` false negative: Angular constructor injection of a domain service.**
- Where: `.claude/scripts/check-design-system.py:149-153`. It matches only `inject(...)` and imports from `.service`/`.store` or `features/` paths.
- Evidence: I planted `src/app/shared/components/status-badge/audit-plant.ts` in `ng-daisy` with `// Tier: Atom` and `constructor(private api: DashboardApi)`, importing from `../../../core/dashboard-api`. Gate exit 0. The control (same file importing from `features/`) gave exit 1.
- Impact: a presentational component can inject a domain service through the constructor and pass the gate.
- Fix: flag constructor parameters whose type is not in `UI_INJECTABLES`, for example `constructor\s*\([^)]*\b(private|public|protected|readonly)\s+\w+\s*:\s*(?!(ElementRef|…)\b)[A-Z]`. Add a fixture and confirm it fails when reverted.

**F2 — `DS-COLOR` false negative: raw hex passed as a component input or prop on the web.**
- Where: `check-design-system.py:108-115`. It needs `color:` / `background:` or a Tailwind arbitrary value.
- Evidence (all gave exit 0):
  - plant `<app-status-badge color="#E53935" label="Overdue" />` in `ng-daisy/src/app/features/dashboard/`;
  - plant `<StatusBadge color="#E53935" />` in `react-app/src/features/orders/`;
  - probe tree 2: `[color]="'#E53935'"`, `color={"#E53935"}`, `tone="#E53935"`.
- The Flutter equivalent is caught (fixture `:419-422`).
- Fix: in `.html`/`.tsx`/`.jsx`, flag any attribute or binding value that is a hex or a colour function (`=\s*[{"'\[]*\s*['"]?#[0-9a-fA-F]{3,8}\b`). Add positive and negative fixtures.

**F3 — "No parallel token authorities" is claimed blocking but is enforced only for Dart spacing, radius and motion classes in one app root, plus web colour variables.**
- Where:
  - claim: `token-governance.md:18` ("…and so is an app-local theme/token folder beside the shared one");
  - detector: `SCALE_CLASS :172-174`, per-root comparison `:381-386`;
  - token-file exemption: `:269-270`, `:295-298`.
- Evidence:
  - `fl/lib/theme/brand_colors.dart` with a literal, beside `lib/design_system/tokens/app_colors.dart`: no finding;
  - `ws/apps/a/lib/theme/app_spacing.dart` and `ws/packages/shared_ui/lib/tokens/app_spacing.dart`: no finding;
  - `border-radius: 13px; --radius-box: 3px;` in `ng/src/app/features/x/n13.component.css`: no finding.
- Fix, either:
  - (a) add colour classes to `SCALE_CLASS`, compare scales across workspace roots, flag a token directory outside the canonical library, and add web radius/spacing variable re-declarations outside the global sheet; or
  - (b) reword `token-governance.md:18` so it says this is a review item and not a gate.

**F4 — Reduced motion fails at runtime in Angular hybrid mode, and toolkit templates still emit the cause.**
- Evidence:
  - `UI_MODE=hybrid npx playwright test` in `<scratchpad>/rt/ng-hybrid` exited 1. `e2e/ui.spec.ts:124` expected `smilInCss: 0` and received `1`.
  - The implementers' last run `ng-hybrid.pw.out` shows the same failure. The files edited after it (`dashboard-page.ts/.css`, `icon.ts`) did not fix it.
  - Cause: `src/app/features/dashboard/dashboard-page/dashboard-page.html:17` uses `loading loading-spinner` without `motion-reduce:hidden`.
- `token-governance.md:46` documents this exact daisyUI 5 SMIL trap and its fix, but the toolkit templates that agents copy still emit bare spinners:
  - `angular-spa/reference/angular-templates.md:74`;
  - `angular-ui-lists.md:35`;
  - `angular-ui-data-components.md:49`;
  - `angular-ui-form-components.md:301, 526, 675, 867`;
  - `angular-forms-*.md`;
  - `angular-ui-tables.md:187`.
- `ng-daisy/src/app/shared/components/async-view/async-view.html:28, 60` also uses spinners without the reduced-motion hide. Its PW suite covers only the skeleton.
- Fix:
  - add `motion-reduce:hidden` plus visible text to every spinner in the templates;
  - fix the hybrid dashboard and re-run the suite;
  - optionally add a gate warning for `loading-(spinner|dots|ring|ball|bars|infinity)` without `motion-reduce:hidden` on the same element.

### P2

- **F5 — Flutter icon wrapper bypass is not detected.** `check-design-system.py:312-313` only records the `material` family. `Icon(Icons.delete)` in feature code (probe n9) passes, although `token-governance.md:29` requires semantic names through the wrapper. Fix: flag `Icons.`/`CupertinoIcons.` outside the icon wrapper/registry and the governed library.
- **F6 — `DS-PRESENTATIONAL` heuristic gaps.**
  - Gaps: React `useContext(SomeStoreContext)` and custom data hooks (in-app plant → exit 0); Flutter repository imports outside `features|data|repositories|providers|services` (probe n7); `flutter_bloc` / `provider` (probe n8).
  - Where: `check-design-system.py:143-157`.
  - Fix: add `_repository.dart`/`_api.dart` file-name imports and `flutter_bloc|provider|get` packages; document `useContext` as a review item in `atomic-decision-tree.md:43`.
- **F7 — Non-default library paths are silently ungoverned.** Tier and presentational rules apply only to the toolkit's default paths (`:76-86`). Probes `src/app/ui/…`, `src/components/common/…` and `packages/design_system/lib/…` scanned with zero findings and no warning. `design-system-reviewer.md:29` says the project's DESIGN.md can name other directories, but the gate cannot read them. Fix: print "governed library files: N" and warn at 0; or accept library paths from a config or from DESIGN.md.
- **F8 — No deterministic check for refresh strategy or pull-to-refresh.** Probes n20 (`react-simple-pull-to-refresh`) and n21 (`RefreshIndicator`) produce no finding. SOURCE `check-pull-to-refresh.sh` is portable: one wrapper, a package deny-list, and a two-way allowlist. Fix: port it as an allowlist-plus-record check (for example, a `// refresh-strategy:` marker is required wherever `RefreshIndicator` or a PTR package is used).
- **F9 — "No automatic installs" of animation runtimes is not checked, and the wrapper-name exemption can be bypassed.**
  - `DS-ANIM` inspects imports only. Nothing compares `pubspec.yaml`/`package.json` dependencies against a DESIGN.md decision.
  - `ANIM_WRAPPER_NAME :88-89` exempts any feature file named `*_animation*`/`motion*`. Probe `features/x/presentation/celebration_animation.dart` importing lottie → no finding.
  - Fix: restrict the exemption to the governed library, and flag lottie/rive dependencies that the DESIGN.md Motion section does not name.
- **F11 — The hook re-implements the detector, and the two have drifted.**
  - `hookify.design-presentational-imports.local.md:12` matches `inject(\w*(Service|Store|…))`, while the gate (`:153`) flags any non-UI `inject()`. So `inject(AuthSession)` is flagged by the gate (fixture `:454-456`) but not by the hook pattern.
  - This contradicts `.claude/rules/hook-and-gate-authoring.md` ("One detector, three callers… a second copy… drifts").
  - Fix: have the hook call `check-design-system.py --files <path>`, or add a parity test.
- **F12 — Spartan and hybrid runtime apps fall short of the §6b async contract, and so does the template they come from.**
  - The dashboards use a cold-read spinner for a list (`ng-hybrid dashboard-page.html:17`). §6b requires a skeleton for a cold read of a known layout (`interaction-contracts.md:166`).
  - The specs have no refresh or content-first transition tests (`ng-spartan/.../dashboard-page.spec.ts:29-62`).
  - The source template `angular-templates.md:74` shows the same spinner pattern.
- **F13 — Mobile UX principles are partly transferred.** 13 of 55 are not transferred: #3, 4, 6, 7, 9, 11, 16, 24, 34, 40, 46, 50, 51 (see §3). These are generic and reusable. Fix: add a short brand-free "Mobile UX checklist" reference under `design-system/reference/` and link it from the SKILL pre-flight.

### P3

- **F10 — Web radius has no `DS-SHAPE` equivalent.** Covered by F3; listed separately for clarity.
- **F14 — Off-by-one in the reason length.** `REASON = ignore-design:\s*(\S.{10,})` (`check-design-system.py:56`) accepts 11 characters, but `lint-design-system.md:57`, `SKILL.md:189` and the docstring say 12. In probe tree 2 the 10-character reason was flagged; an 11-character reason (`abcdefghijk`) passed in probe tree 1. Fix: `\S.{11,}`.
- **F15 — `--files` with no changed files exits 2, which reads as BROKEN.** The `lint-design-system.md:15` recipe `--files $(git diff …)` hits an argparse usage error (exit 2) when nothing changed. Fix: guard for an empty list, or allow `--files` with zero arguments.
- **F16 — SKILL overstates the hooks.** `design-system/SKILL.md:107` says "Violations are caught by hookify rules at write-time", but every design hook is `action: warn` (advisory). `token-governance.md:52` says "advisory" correctly.
- **F17 — `ng-spartan` maps HTTP status 0 to "offline".** The dashboard spec, `it('treats a network failure (status 0) as offline')`, contradicts `interaction-contracts.md:195` ("say offline only when it is actually known").

---

## 5. Verdict (original audit; superseded by §6): NEEDS FIXES

**What works:**
- DESIGN.md discovery, precedence and missing-file behaviour are documented consistently across the skill, rules, agents, scaffolds and screenshot skills. The gate enforces them (proven by selftest, all 5 runtime apps, and the `--require-design-md` probe).
- Tier markers and the core smart/dumb cases are gated, with positive and negative fixtures. Every one of the user's named cases has a selftest fixture.
- The async-state and refresh standards were transferred in depth and without SOURCE branding. Their framework-native mappings are proven by passing transition tests in Flutter (17), ng-daisy (42) and React (53, plus mutation controls).
- The gate is green on all five apps. The design hookify rules are committed and not ignored. The context budget passes.

**What is broken:**
- F1 and F2: two of the required smart/dumb and raw-hex cases have gate false negatives in common variants (constructor injection; hex passed as an input or prop).
- F3: "no parallel authorities" is claimed as blocking but is only partly enforced.
- F4: reduced motion fails at runtime in Angular hybrid mode, and the toolkit's Angular templates still emit the cause, even though `token-governance.md:46` documents it.
- Flutter 3.50 end to end is BLOCKED (local SDK 3.44.2).

Clearing F1–F4 and re-running this report's probe set would move the verdict to READY, with P2 items tracked as follow-ups.

---

## 6. Re-verification (2026-11-25, after the implementers' F1–F4 fix round)

### Scope
The implementers made claims about F1–F4, F6, F11, F14 and F16. The change set I checked was 8 files with unstaged edits (`git diff --stat`, +101/-19):
- `check-design-system.py`, `hookify.design-presentational-imports.local.md`, `hookify/tests/test_rules.py`;
- `daisyui-v5-components.md`, `ui-mode-selection.md`;
- design-system `SKILL.md`, `token-governance.md`;
- `lint-design-system.md`.

The runtime apps' `src/styles.css` (ng-hybrid, ng-daisy) also gained the `.loading` override.

I applied the same rules as the original audit:
- my only repo write is this report;
- plants went only into scratch trees or into copies inside the scratchpad apps, and were reverted;
- after each revert the file hash was unchanged and the gate exited 0.

### Commands (each tool's own exit code)
| Command | Exit | Result |
|---|---|---|
| `check-design-system.py --selftest` | 0 | 49/53 fixtures, 51 findings |
| `hookify/tests/test_rules.py` | 0 | 11 rules, PASS (adds `inject(AuthSession)`, a single-line constructor, and a DOM-token negative) |
| `check-context-budget.sh --strict` | 0 | 60342 ≤ 62000, 22/22 canaries |
| gate on `flutter-ds` · `ng-daisy` · `ng-spartan` · `ng-hybrid` · `react-app` | 0 · 0 · 0 · 0 · 0 | 13 / 29 / 29 / 29 / 38 files; 0 errors and 0 warnings: no false positives from the new rules on real apps |
| original probe tree 1 (21 plants) | 1 | now flags n1, n2, n4, n8, n10 (`DS-AUTHORITY`), the 11-character reason, and n13, plus the earlier n3 and n15. Still clean: n5, n6, n7, n9, n11, n14, n16–n21 |
| re-verification probe set (32 isolated projects, `<scratchpad>/audit_reprobe.py`) | — | 21 as expected; 11 not: F1c/d/e, F2a/b/c/d, three false positives (F20 ×2, F21), F4d, F4f |
| override removed in copies of `ng-hybrid` / `ng-daisy` `src/styles.css` | 1 / 1 | `DS-REDUCED-MOTION` names `dashboard-page.html:17` / `sign-in-page.html:13`; restored → 0 / 0 |
| gate mutation (5 copies in `<scratchpad>/mut`, `--selftest`) | 2, 2, 2, 2, **0** | constructor / prop-hex / authority / reduced-motion mutations are caught; the web `border-radius:` mutation is not (F19) |
| `UI_MODE=hybrid npx playwright test` (ng-hybrid) | 0 | 11 passed, incl. the reduced-motion test and its "spinner animates" control |
| `npx playwright test` (ng-daisy) · `UI_MODE=spartan` (ng-spartan) | 0 · 0 | 12 · 9 passed |

### Outcome
- **F1: FIXED.** Residual F1r (P2) and F20 (P3).
- **F3: FIXED.** Residual F3r (P2) and F21 (P3).
- **F4: FIXED.** Residual F18 (P3).
- **F10, F14, F16: FIXED.**
- **F6, F11: PARTIAL.**
- **F2: still OPEN (P1).** The literal attribute and prop forms are fixed. A raw hex for a business status still passes the web gate when written in any of these forms:
  - as a camelCase prop;
  - in a ternary;
  - as a status map in TypeScript;
  - as a named constant.

  Only the Flutter form (`Color(0x…)` anywhere) is complete. Suggested fix:
  - In web `.ts`/`.tsx`/`.html` outside token files, flag any quoted string that is exactly a hex colour (`['"\`]#[0-9a-fA-F]{3,8}['"\`]`). Exclude `href`/`fragment`/`routerLink` values, because `#add` is valid hex.
  - Widen the prop-name match to camelCase suffixes (`\w*(?:[Cc]olou?r|Tone|Tint|Bg|Background|Fill|Stroke|Accent)\b`).
  - Add one fixture per form.

### Verdict (§6, superseded by §7): NEEDS FIXES
- **Open P0:** none.
- **Open P1:** F2 (narrowed).
- **Status counts:** PASS 14 · PARTIAL 7 · FAIL 0 · BLOCKED 1 (the Flutter 3.50 scaffold; local SDK is 3.44.2).

Fixing F2 and adding the F19 control would make the verdict READY, with F1r, F3r, F5–F9, F11–F13 and the P3s tracked as follow-ups.

---

## 7. Second re-verification (2026-11-25, F2 and F19 fix)

### Claimed change
- A second web `DS-COLOR` detector (`check-design-system.py:123`): any quoted string that is exactly a 3/4/6/8-digit hex, outside token files. Lines containing `href|fragment|routerLink|xlink:href|id|anchor` are skipped.
- New fixtures: `site/src/features/orders/status-colors.ts`, `late-badge.tsx`, `anchors.tsx`, and `web/src/app/features/orders/card-radius.css`.

I applied the same rules: my only repo write is this report, and every probe ran in a scratch tree.

### Commands (each tool's own exit code)
| Command | Exit | Result |
|---|---|---|
| `check-design-system.py --selftest` | 0 | 53/57 fixtures, 59 findings |
| gate on `flutter-ds` · `ng-daisy` · `ng-spartan` · `ng-hybrid` · `react-app` | 0 · 0 · 0 · 0 · 0 | 13 / 29 / 29 / 29 / 38 files; 0 errors, 0 warnings: no false positives from the new detector on real apps |
| §6 probe set re-run (`<scratchpad>/audit_reprobe.py`) | — | **F2a `statusColor="#E53935"`, F2b `[color]="late ? '#E53935' : '#2E7D32'"`, F2c `.ts` status map, F2d `const LATE='#E53935'` + `color={LATE}` → all `DS-COLOR`, exit 1**. Anchor and tone-enum negatives stay clean. Unchanged residuals: F1-FP ×2 (F20), F3a (F21), F4d/F4f (F18) |
| extra probes (8) | — | Caught: an Angular `.ts` status map, a TSX ternary on `tone`, a template-literal hex, a status array with `id` plus a `color:` key. Misses: `late: { id: 1, hex: '#E53935' }` (F2r). False positives: `querySelector('#feed')`, `{'#123'}` (F22). Clean as expected: `routerLink` with `fragment="#add"` |
| mutation: hex-string detector removed (`<scratchpad>/mut2`) | 2 | `status-colors.ts` and `late-badge.tsx` expected `DS-COLOR`, got clean |
| mutation: web `border-radius:` branch removed | 2 | `card-radius.css` expected `DS-SHAPE`, got clean (was exit 0 in §6) |
| mutation: anchor-line skip removed | 2 | `anchors.tsx` expected clean, got `DS-COLOR` (the negative control works) |

### Outcome
- **F2: FIXED.** Every form of raw hex for a business status that I found in either round is now flagged on the web. Removing the detector fails the selftest, and there are no false positives on the 5 apps.
- **F19: FIXED.** The web `border-radius:` branch now has its own selftest file.
- New residuals: F2r (P2, the whole-line `id` skip) and F22 (P3, hex-like selectors and strings).

### Verdict: READY
- **Open P0:** none.
- **Open P1:** none.
- **Status counts (22 rows):** PASS 15 · PARTIAL 6 · FAIL 0 · BLOCKED 1 · NOT APPLICABLE 0 · NOT RUN 0.
- **Conditions:**
  1. Flutter 3.50 end to end is BLOCKED by the local SDK (3.44.2). Under the toolkit's review policy, a merge verdict stays NEEDS_REVIEW until the scaffold runs on 3.50.
  2. The six PARTIAL rows rest on P2 follow-ups to track:
     - icon governance (F5);
     - Spartan/hybrid async states (F12);
     - refresh with no gate (F8);
     - animation dependency check (F9);
     - mobile UX principles (F13);
     - hook/gate drift (F11).
  3. Further P2 follow-ups: F1r, F2r, F3r, F6, F7. Plus the P3s.

---

## 8. P2 close-gaps round (2026-11-26)

Implementer notes (independent review follows). Durable matrix: [`design-system-requirements-matrix.md`](design-system-requirements-matrix.md). No commit/push this round. Property Harbor untouched. Always-loaded budget unchanged at 60,342 / 62,000.

### Commands
| Command | Exit | Result |
|---|---|---|
| `check-design-system.py --selftest` | 0 | 66/70 fixtures, 66 findings |
| `hookify/tests/test_rules.py` | 0 | 11 rules; presentational 10 positive / 8 negative (adds `useContext(CartContext)` / `ThemeContext`) |
| `check-context-budget.sh --strict` | 0 | 60342 ≤ 62000, 22/22 canaries |
| `lint-skills.sh` | 0 | 167 passed |
| `check-doc-refs.sh` | 0 | 0 violations |
| mutation: quoted-hex / Icons.* / useContext / DS-REFRESH / DS-ANIM path / DS-ANIM-DECISION / anchor skip | 2 each | selftest fails when the detector is removed |
| Flutter 3.50 scaffold | — | local SDK 3.44.2 | BLOCKED |
| Maestro | — | 2.11.0 installed; 0 booted simulators | BLOCKED |
| Spartan/hybrid Playwright | — | prior disposable apps gone; not re-scaffolded this round | NOT RUN |

### P2 outcomes
| ID | Outcome | Evidence |
|---|---|---|
| F12 Spartan/hybrid skeletons | **FIXED in templates** | `scaffold-angular-app.md` step 8; `angular-templates.md`; `ui-mode-selection.md` hlmSkeleton; `smart-dumb-components.md`; `angular-ui-tables.md`. Runtime re-scaffold NOT RUN |
| F8 refresh record | **FIXED** | `DS-REFRESH`; fixtures `feed_screen.dart` / `ptr.tsx` fail, `news_screen.dart` / `static_screen.dart` / `ptr-ok.tsx` clean |
| F9 animation decision | **FIXED** | `DS-ANIM-DECISION`; `celebration_animation.dart` now `DS-ANIM`; lottie named in DESIGN.md is clean |
| F5 Flutter `Icons.*` | **FIXED** | `delete_screen.dart` → `DS-ICON-ISOLATION`; `date_chrome.dart` ignore-design clean; `AppIcons` snippet in `flutter-templates.md` |
| F6 React `useContext` | **FIXED** (targeted) | `cart-icon.tsx` `useContext(CartContext)` → `DS-PRESENTATIONAL`; `mode-toggle.tsx` `ThemeContext` clean. Residual: custom data hooks, Flutter repo outside `features/` |
| F2r hex `id` skip | **FIXED** | `id-hex.ts` `{ id: 1, hex: '#E53935' }` → `DS-COLOR`; `href="#add"` / `id="feed"` clean |
| F13 55 UX principles | **FIXED** | `mobile-ux-principles.md`; 13 missing stated; SKILL pre-flight item 10 |
| Angular scaffold #3/#4 | **partial fix** | `sign-in-page` generate path aligned to `features/auth/login` matching `web-security.md` `/login`. `users` vs `dashboard` sample routes documented as two examples. `components.json` non-interactive wording fixed in `spartan/cli.md`. Hybrid ownership table left as the contract |

### Independent audit (this round)
A fresh `design-system-reviewer` re-read the files and re-ran selftest, hookify tests, the context budget, `flutter --version`, and `xcrun simctl list devices booted`. After unused `ANIM_WRAPPER_NAME` was removed, selftest stayed PASS (66/70 fixtures, 66 findings). Mutations of the six new/changed detectors each made `--selftest` exit 2. Auditor statuses: F2r, F5, F6 (targeted), F8, F9, F12 templates, F13 **PASS**; Angular login vs `*-page` **PARTIAL** (documented as matching `web-security.md` `/login`); Flutter 3.50 **BLOCKED** (3.44.2); Maestro **BLOCKED** (0 booted simulators). No P0/P1 opened. Matrix DS-R1/DS-R16 source cells were rewritten so this round’s docs do not introduce product names.

### Verdict
- **Toolkit:** READY for the P2 items that the in-repo gate and templates can enforce. P0/P1 remain closed.
- **Merge:** NEEDS_REVIEW. Flutter 3.50 BLOCKED, Maestro BLOCKED, Spartan/hybrid device/runtime re-proof NOT RUN.
