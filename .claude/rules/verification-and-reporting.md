# Verification and Status Reporting

## Verify Before Claiming

Actually check code before saying "missing" or "implemented". Don't guess. Don't flip when challenged.

### Before ANY claim about code state:

1. FIND the specific file(s) where it should exist
2. READ the actual code (not just file names)
3. TRACE the full implementation (UI → service → data)
4. ONLY THEN make a claim

### Required format:

```
## Feature: [Name]
### Verification:
- UI Component: [file:line] or ❌ NOT FOUND
- Service/Logic: [file:line] or ❌ NOT FOUND
- Data Connection: [file:line] or ❌ NOT FOUND
### Status: ✅ IMPLEMENTED / ❌ MISSING / ⚠️ PARTIAL (requires per-layer evidence above)
### Evidence: [Actual code snippet or function signature]
```

### Spec Conformance (when plan/spec exists for this feature):

```
- Completeness: All WHEN/THEN scenarios from spec covered? [YES/NO — list uncovered]
- Correctness: Behavior matches spec intent, not just "code exists"? [YES/NO — evidence]
- Coherence: Design decisions from plan reflected in code structure? [YES/NO — evidence]
- Constraints: All non-functional requirements met? [YES/NO — list violated]
```

> Skip this section if no spec/plan document exists for the feature being verified.

### When User Challenges Your Analysis

Don't flip. Re-verify:

```
"Let me re-verify by actually reading the code..."
[Actually read the files]
"I found [X] at [file:line]. My initial analysis was wrong because
I didn't check [specific thing]."

OR

"I re-verified and my initial analysis was correct.
Here's the evidence: [show what you searched, what's not there]"
```

**Forbidden:** "I believe it's..." / "It should be in..." — either you verified or you didn't.

---

## Honest Status Reporting

### Forbidden:

- "Feature is 95% complete" → then listing critical blocking issues
- "Mostly functional" → then describing why it doesn't work
- Vague qualifiers: "mostly", "almost", "nearly", "partially" (note: ⚠️ PARTIAL in verification template is allowed because it requires per-layer file:line evidence — the ban is on "partially" as a hand-wave without proof)
- Percentage estimates that contradict the details

### Required:

- Binary status: "Works" or "Doesn't work"
- If broken: "X works, Y is broken because Z"
- Details must match the summary

### Format:

```
What WORKS:
- [Feature A]: ✅ User can do X, Y, Z end-to-end

What's BROKEN:
- [Feature B]: ❌ Clicking does X instead of Y
```

### Self-Check Before Reporting:

1. Did I say something "works" or is "functional"?
2. Did I then list reasons why it doesn't work?
3. If yes → REWRITE with honest, non-contradictory status
4. **Principal engineer check:** Would a principal engineer approve this if they reviewed your diff? If not — what would they flag? Fix it before reporting done.

---

## Action Claims Require Evidence

Status updates about actions (not just code state) must include proof:

| Claim | Required Evidence |
|-------|------------------|
| "Started server/service" | PID, port, or startup log output |
| "Running tests" | Command + output (pass/fail count) |
| "Deployed/launched" | URL, response, or deployment log |
| "Fixed the bug" | Test that failed before, passes now |
| "Installed dependency" | Package manager output or lockfile diff |
| "Check/gate is green" | The tool's OWN exit code (`cmd; echo $?`, never a pipe's) and a positive control: the same check fails on a planted violation |
| "Zero findings" on a diff-aware or generated-output check | Proof the check saw input: it is vacuous on uncommitted work or absent generated files |
| "Passes locally" | Same pinned toolchain and lockfile as CI (env parity); say what differed if not |

**Forbidden:** "Working on it" / "Done" without corresponding tool output in the same response.

**Rule:** The claim and its evidence must appear in the same message. No forward promises. A false completion is worse than a delayed honest answer.

---

## Plan Execution Completeness

When a plan is approved, implement 100%. Not 60%. Not "most of it." ALL of it.

### Before saying "done":

```
□ Item 1 from plan → Implemented? [YES/NO]
□ Item 2 from plan → Implemented? [YES/NO]
□ Item 3 from plan → Implemented? [YES/NO]
If ANY item is NO → Do NOT say "done"
```

### If you cannot complete an item:

```
STOP and say:
"I cannot complete [item] because [reason].
Options:
1. Try a different approach
2. Skip this item (with your approval)
3. Stop here and discuss"
```

**Never** silently skip plan items. **Never** defer without explicit approval.

## Confidence Levels on Research Claims

When reporting findings from external sources (web search, MCP docs, code analysis, library
behavior), every non-trivial claim MUST carry an explicit confidence level.

### Required Format

```
[HIGH] The `useEffect` cleanup function runs before the next effect and on unmount.
       Source: React docs (MCP-verified this session, react.dev/reference/react/useEffect)

[MEDIUM] This pattern should work with NestJS 11.x — the `@Module()` API hasn't changed
         in v10→v11 based on changelog review, but I haven't run it against this specific version.

[LOW] I believe this package supports tree-shaking, but I haven't verified the bundle output.
     You should confirm with `npm run build -- --stats` before relying on it.
```

### Confidence Definitions

| Level | Meaning | When to use |
|-------|---------|-------------|
| **HIGH** | MCP/docs verified this session, or tested with tool output | API signatures, tested code, official docs fetched |
| **MEDIUM** | Reasoning from adjacent knowledge, changelog review, or strong prior | Version compatibility, inferred behavior, partially verified |
| **LOW** | Best guess, memory-based, or not verified | Unverified claims, things that "should" work, assumptions |

### Rules

- **HIGH** requires a source (file:line, MCP URL, or tool output in the same response)
- **MEDIUM** requires a reason ("based on X", "changelog shows Y")
- **LOW** requires an action item ("verify with Z before relying on this")
- Never present a LOW claim as if it were HIGH — that is confabulation
- If you cannot assign at least MEDIUM confidence, say "I don't know" and propose how to find out

---

## Review Severity Policy

One policy for every review: `/review-code`, `/verify`, `/ship`, `/create-pr`, reviewer agents and CI.

| Highest unresolved finding | Verdict | Merge |
|---|---|---|
| CRITICAL | **BLOCK** | No. Fix first. |
| HIGH | **NEEDS_REVIEW** | Only after each HIGH is fixed or has a written justification in the PR. Never reported as PASS or APPROVE. |
| MEDIUM / LOW only | **APPROVE** with advisories | Yes. List each advisory, and track MEDIUMs as follow-up tasks or issues. |

- A required check that is BLOCKED or NOT RUN caps the verdict at NEEDS_REVIEW.
- Domain gates may be stricter, never looser: security reviewers (BLOCK on CRITICAL; HIGH must be fixed before production), database migrations (`SAFE TO APPLY` only), design-system tier rules and accessibility audits keep their own thresholds.
- Other vocabularies map onto this one: `PASS` = APPROVE; `CONDITIONAL PASS` / `NEEDS WORK` = NEEDS_REVIEW; `REJECT` = BLOCK.

## Quality Gates

Before declaring any workflow type complete, the following gates must pass. These are minimum bars — do not skip them.

### Feature / PR Gate
- [ ] All existing tests pass (run them — don't assume)
- [ ] New logic has at least one test covering the happy path
- [ ] `security-reviewer` agent verdict = **no CRITICAL or HIGH findings unresolved** (running it and ignoring findings does not pass this gate)
- [ ] No new unused imports, variables, or functions introduced
- [ ] `npm audit --audit-level=high` (Node.js) or `pip audit` (Python) or `mvn dependency-check:check` (Java) — zero critical/high CVEs
- [ ] Change description written (CHANGES MADE / THINGS I DIDN'T TOUCH / POTENTIAL CONCERNS)

### Architecture Gate
- [ ] ADR (Architecture Decision Record) created for the key tech choice
- [ ] `architect` agent or `/design-architecture` command was used
- [ ] API contracts defined before implementation starts
- [ ] No circular dependencies introduced

### Database Schema Gate
- [ ] Migration is reversible (has both up and down)
- [ ] Indexes defined for expected query patterns
- [ ] `postgresql-database-reviewer` agent verdict = **SAFE TO APPLY** (running it and proceeding with open issues does not pass this gate)
- [ ] No direct table drops without explicit human approval

### UI / Design System Gate
- [ ] No hardcoded colors — all colors use theme tokens (Flutter: `colorScheme`, Angular: daisyUI semantic)
- [ ] No raw spacing values — all spacing uses semantic tokens (Flutter: `AppSpacing`, Angular: Tailwind scale)
- [ ] No inline TextStyles — all typography uses theme text styles
- [ ] Target size >= 24×24 CSS px (WCAG 2.2 AA); house standard 48dp (Flutter) / 44px (web)
- [ ] `/lint-design-system` run with zero violations
- [ ] Exception markers (`// ignore-design: [reason]`) reviewed and justified
- [ ] Angular: `shared/components/` components have zero `inject()` calls (dumb rule enforced)
- [ ] Flutter: `packages/shared_ui/` widgets extend `StatelessWidget` — no `ConsumerWidget` (dumb rule enforced)

### Release / Merge Gate
- [ ] `/review-code` verdict = **APPROVE** (NEEDS_REVIEW requires written justification in PR; BLOCK = hard block)
- [ ] `/audit-security` verdict = **APPROVED** — Lock Document exists at `docs/approvals/security-YYYY-MM-DD-<commit>.md` (no file = audit was not run or failed; `/ship` will block without it)
- [ ] CLAUDE.md tech stack versions still accurate
- [ ] No TODOs or stub implementations in changed files

**If ANY gate item is NO → do NOT declare done. State which gate items are open.**
