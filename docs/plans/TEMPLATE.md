# Plan Template — `docs/plans/YYYY-MM-DD-<feature>.md`

This template is the required format for all plan files in this workspace.
Created by `/plan-review`. Validated by `subagent-driven-development` Step 0-PRE.

---

## Plan: [Feature Name]

**Created:** YYYY-MM-DD
**Status:** DRAFT | APPROVED | IN PROGRESS | COMPLETE
**Tech layers:** [ ] NestJS  [ ] Angular  [ ] Flutter  [ ] Spring Boot  [ ] FastAPI  [ ] PostgreSQL  [ ] Firebase

---

## Objective

[One paragraph. What problem does this solve? For whom? What is the success condition?]

---

## Tasks

### Task 1: [Title]

**Stack:** NestJS 11.x | Angular 22.3.x | React 19.3 | Flutter 3.50 | Spring Boot 4.2 | FastAPI | PostgreSQL | Firebase

#### Context Brief

> A fresh agent must be able to execute this task reading only this section — no prior context required.

| Field | Value |
|-------|-------|
| **Affected files** | `src/path/to/file.ts`, `src/path/to/other.ts` |
| **Preconditions** | What must be true before this task starts (e.g. "Task 0 complete — users table exists") |
| **Invariants** | What must remain true throughout (e.g. "existing /api/users endpoint must continue to respond 200") |
| **Verification command** | `npm test -- --testPathPattern=auth` or `flutter test test/feature_test.dart` |

#### Rollback Strategy

| Scenario | Rollback Action |
|----------|----------------|
| NestJS/Node change | `git revert <sha>` + `npm run prisma:migrate:reset` if schema changed |
| DB migration | Run `migration_name_down.sql` — down script is mandatory per database-schema-designer Iron Law |
| Flutter change | Restore previous `pubspec.lock`: `git checkout HEAD~1 -- pubspec.lock && flutter pub get` |
| Spring Boot change | Disable feature flag in `application.yml` + `git revert <sha>` |
| Firebase config | Re-apply previous `firebase.json` + `firebase deploy --only hosting` |

#### Acceptance Criteria

- [ ] [Specific, testable criterion 1]
- [ ] [Specific, testable criterion 2]

#### Implementation Notes

[Optional: constraints, tech decisions, patterns to follow — e.g. "use Riverpod AsyncNotifier not StateProvider"]

---

### Task 2: [Title]

[Repeat Task structure above]

---

## Dependency Graph

```
Task 1 → Task 2 → Task 4
Task 1 → Task 3 → Task 4   (Task 3 parallel with Task 2 if no shared files)
```

**Parallel candidates:** Tasks that share NO files and have no output dependency on each other.
Run [reference/parallel-dispatch-checklist.md] in `subagent-driven-development` skill before dispatching in parallel.

---

## Mutations Log

Record every change to this plan after it is APPROVED. Do NOT edit tasks silently.

| Date | Type | Task Affected | Reason | Author |
|------|------|---------------|--------|--------|
| YYYY-MM-DD | split \| insert \| skip \| reorder \| abandon | Task N | [why] | human \| agent |

**Mutation types:**
- `split` — one task became two or more
- `insert` — new task added after approval
- `skip` — task deferred (must state why and when it will be addressed)
- `reorder` — dependency order changed
- `abandon` — task permanently dropped (must state what replaces it or why it's no longer needed)

> Every mutation must be recorded in this table before work continues.

---

## Known Gaps / Deferred

[Populated from implementer handoff tag `DEFERRED:` entries after all tasks complete]

---

## Implementation notes

[Append-only, one dated line per decision too small for an ADR: `- YYYY-MM-DD: chose X over Y because Z (file:line)`. Add ` [needs human review]` to a line when the choice changes behaviour the plan did not specify, weakens a check, or was a guess; the PR body lists every flagged line and the human clears it there. `/promote-lessons` routes project facts here. Once this plan is committed, `git diff --numstat -- <this file>` must show `N	0` before each commit; before its first commit there is nothing to check.]

---

## PR References

| Task | Branch | PR | Status |
|------|--------|----|--------|
| Task 1 | `feature/ticket-description` | #N | Open \| Merged |
