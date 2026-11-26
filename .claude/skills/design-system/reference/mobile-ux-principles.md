# Mobile UX principles (brand-free)

Generic rules for Flutter, Angular and React. Product names, personas and brand language do not belong here. Machine enforcement is the design gate plus the async/refresh contracts; the rest is review (`ui-standards-expert`). Pre-flight: `design-system/SKILL.md`.

Status: **applied** has a statement elsewhere in the toolkit; **here** is newly stated in this file (the 13 that were missing, plus the reusable form of role-aware density).

| # | Principle | Where |
|---|---|---|
| 1 | Remove before adding (no extra chrome, no nested cards) | `SKILL.md` pre-flight |
| 2 | One quality bar; do not copy other apps | `SKILL.md` AI-slop table |
| 3 | The primary task and the next action are obvious; progressive disclosure for the rest | **here** |
| 4 | Do fewer things well; one screen, one job | **here** |
| 5 | Shared visual grammar; density and actions may vary by audience (not product-specific roles) | **here** |
| 6 | Prioritise what matters now; demote the rest | **here** |
| 7 | Minimise effort safely: frequent low-risk tasks in ≤3 taps, with a confirm when the action is irreversible | **here** |
| 8 | Safety and truth beat conversion; no false success | `interaction-contracts.md` |
| 9 | Fold complexity into simple decisions (defaults, sensible grouping, one choice at a time) | **here** |
| 10 | Never re-ask what the product already knows | `accessibility-auditor` (redundant entry) |
| 11 | Onboarding is frictionless: one first success, skippable extras, no tour that blocks the task | **here** |
| 12 | One-handed use; primary actions in the thumb zone | `mobile-design/reference/touch-psychology.md` |
| 13 | Simple navigation; no duplicate CTA for a destination already in persistent nav | `SKILL.md` |
| 14 | Glanceable status; never colour alone | `token-governance.md` |
| 15 | Reduce anxiety while waiting (stall copy, no fake progress) | `interaction-contracts.md` §6b |
| 16 | No false urgency (fake scarcity, countdown theatre, blocking nags) | **here** |
| 17 | Reuse before inventing | `design-md-governance.md` |
| 18 | Visual chunking over chrome | `SKILL.md` |
| 19 | Desirability without decoration | `SKILL.md` |
| 20 | Illustration is intentional; operational flows stay chrome-free | `token-governance.md` (Lottie decorative only) |
| 21 | Immediate feedback; optimistic UI only when reversible | `interaction-contracts.md` |
| 22 | Motion must earn its place | `token-governance.md` |
| 23 | Respect native behaviour (system back, share sheet, OS search) | `flutter-mobile/SKILL.md` |
| 24 | Protect in-progress work: drafts survive backgrounding, rotation and a killed process until the user discards them | **here** |
| 25 | Offline-first: cached content stays usable | `interaction-contracts.md` |
| 26 | Degraded networks: slow ≠ offline; timeout ≠ failure | `interaction-contracts.md` |
| 27 | Optimistic only when safe | `interaction-contracts.md` |
| 28 | Canonical state owns the lifecycle | `interaction-contracts.md` |
| 29 | Never trade truth for speed | `interaction-contracts.md` |
| 30 | Skeletons for a cold read of a known layout | `interaction-contracts.md` §6b |
| 31 | Design every state | `ui-standards-expert` |
| 32 | Purposeful empty states | `interaction-contracts.md` |
| 33 | Concise human copy; no enums or UUIDs | `interaction-contracts.md` |
| 34 | Show time and effort (duration, steps remaining, payload size) when the wait is long | **here** |
| 35 | Accessibility, 200% text | `accessibility-audit` |
| 36 | Never colour alone | `token-governance.md` |
| 37 | Dynamic text reflow | `SKILL.md` |
| 38 | Forms usable with the keyboard open | `SKILL.md` |
| 39 | One destructive-action pattern | `interaction-contracts.md` |
| 40 | Consistent bulk selection (same select-all, range and overflow pattern on every list that supports it) | **here** |
| 41 | Safe areas and system UI | `SKILL.md` |
| 42 | Light and dark are equal | `token-governance.md` |
| 43 | Responsive, not device-specific | `interaction-contracts.md` |
| 44 | Secure re-authentication | `flutter-security-hardening.md` |
| 45 | Privacy-aware surfaces | `flutter-security-client-trust.md` |
| 46 | Ask for a permission in context, at the moment of need, with a reason; never on first launch as a bundle | **here** |
| 47 | Deep links land on current truth (reload canonical state; never trust the payload) | **here** (generic remainder) |
| 48 | AI transparency without theatre | `interaction-contracts.md` |
| 49 | Action recoverability (Undo where reversible) | `interaction-contracts.md` |
| 50 | Interruptible: every long or generated task exposes Stop/Cancel and leaves partial work | **here** |
| 51 | Auditable state changes: consequential writes are attributable (who/what/when) in the product's own record, not only in logs | **here** |
| 52 | Localisation beyond translation | `i18n-rtl-intl.md` |
| 53 | Performance is UX | `code-standards.md` |
| 54 | Eliminate small annoyances (scroll reset, clear-then-refetch) | `interaction-contracts.md` |
| 55 | Micro-consistency: hierarchy, one radius scale, optical alignment | `token-governance.md` |

## Newly stated rules (review; not a gate)

**Primary task dominant.** The first screenful answers “what can I do next?”. Secondary actions sit behind progressive disclosure (overflow, “more”, a later step). Do not compete with the primary CTA.

**One job per screen.** Split a kitchen-sink surface rather than adding another panel.

**Shared grammar, varying density.** The same tokens, components and patterns everywhere; a given audience may see fewer fields or a denser table, not a different visual language.

**Prioritise now.** Default filters, sort and the first list rows reflect the current task, not an archive.

**Few taps, safe confirms.** Frequent low-risk actions complete in at most three taps. Irreversible or high-cost actions keep an explicit confirm (principle 39).

**Simple decisions.** Replace a multi-field puzzle with a default plus one optional choice.

**Frictionless first success.** The shortest path to one real outcome; optional setup is skippable and never a modal tour that blocks the task.

**No false urgency.** No fake stock counts, countdown theatre or blocking nags that are not backed by a real constraint.

**Protect in-progress work.** Local drafts (forms, messages, partially filled flows) survive app backgrounding, configuration change and process death until the user discards them.

**Show time and effort.** When a wait routinely exceeds a few seconds, name the remaining time, steps or size. Determinate only with a real measure (`interaction-contracts.md` §6b).

**Consistent bulk selection.** Lists that support multi-select share one pattern for select-all, range select, an overflow action and an exit.

**Permission in context.** Request a capability when the user invokes the feature that needs it, with one sentence of why. Never a first-launch permission bundle.

**Deep links reload truth.** A cold start from a link fetches canonical state; the link payload is an identifier, not trusted content.

**Interruptible work.** Uploads, exports, generated text and long syncs expose Stop/Cancel. Partial output stays unless the user discards it.

**Auditable writes.** Create/update/delete of money, access, identity or user-visible records stores actor, action and time in the product's own history.
