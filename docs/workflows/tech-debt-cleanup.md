# Tech Debt Cleanup

> **When to use**: Reducing duplication, removing dead code, consolidating diverged patterns, or cleaning up after rapid feature development
> **Time estimate**: 2–4 hours for a focused module; 1–2 days for a full service audit
> **Prerequisites**: Tests exist for the code being cleaned up; no feature work in progress in the same area

## Overview

Tech debt identification and removal using the `dedup-code-agent` agent, `code-simplifier` agent, and systematic cleanup protocol. Covers duplicate code detection, dead code identification, dependency bloat, and the Rule of Three abstraction threshold. Always starts with test coverage verification.

---

## Iron Law

> **NO CLEANUP WITHOUT TESTS FIRST**
> Refactoring without tests means you cannot verify behavior is preserved. Write tests, then clean.

---

## Phases

### Phase 1 — Identify Debt (Agents)

**Dispatch `dedup-code-agent`** (tech debt detection):
```
Scan [service/module/directory] for:
- Duplicate code blocks (>5 lines identical or near-identical)
- Unused exports, dead functions, unreachable code
- Dependency bloat (packages imported but unused)
- Diverged implementations of the same pattern
```

**Dispatch `code-simplifier`** (complexity reduction):
```
Review [files] for:
- Unnecessary nesting (>3 levels deep)
- Redundant abstractions (wrapper around wrapper)
- Over-engineered for current use (1-2 implementations of abstraction)
- Cognitive load without benefit
```

**Output**: Prioritized debt inventory with file:line evidence.

---

### Phase 2 — Prioritize by Risk and Value

**Triage matrix**:

| Debt Type | Risk of Cleanup | Value | Priority |
|-----------|----------------|-------|---------|
| Duplicate logic diverged (different bugs) | Medium | HIGH | P1 |
| Dead code (never called) | Low | Medium | P1 |
| Unused dependencies | Low | High | P1 |
| Duplicate logic (identical) | Low | Medium | P2 |
| Complex but working code | High | Low | P3 |
| Premature abstractions | Medium | Medium | P2 |

**P1** = Do now (reduces bug surface, saves CI time)
**P2** = Do this sprint
**P3** = Log as backlog item, do only with dedicated refactor time

---

### Phase 3 — Verify Test Coverage Before Touching

Before cleaning up any file:

```bash
# Run existing tests — establish baseline
./mvnw test                    # Java
npx vitest run                 # NestJS
uv run pytest                  # Python
flutter test                   # Flutter
ng test --watch=false          # Angular
```

**If tests are insufficient**: Write characterization tests first (tests that document current behavior without asserting it's correct).

```python
# Characterization test — captures current behavior
def test_process_order_current_behavior():
    result = process_order({"id": "1", "items": []})
    # This is what it does now, not necessarily what it should do
    assert result == {"status": "empty", "total": 0}
```

**Gate**: All existing tests pass before starting any cleanup.

---

### Phase 4 — Remove Dead Code

**Dead code types** (safest to remove):

| Type | How to Confirm | How to Remove |
|------|---------------|--------------|
| Unused function | No callers in codebase | Delete function + imports |
| Unused import | IDE warning / linter | Remove import line |
| Unreachable code path | After unconditional `return` | Delete dead branch |
| Unused dependency | `npm ls --depth=0`, `pip list`, `mvn dependency:analyze` | Remove from manifest |
| Commented-out code | Git blame shows it's been commented >30 days | Delete (use git history to recover if needed) |

**Never delete** without confirming:
- No dynamic invocation (reflection, late binding)
- No external caller outside the repo
- No conditional compilation that might activate it

---

### Phase 5 — Consolidate Duplicates

**When to consolidate** (Rule of Three from `code-standards.md`):
- 3+ identical or near-identical code blocks → extract to shared utility
- 2 uses → accept the duplication (abstracting at 2 is premature)
- 1 use → no abstraction

**Consolidation pattern**:
```typescript
// ❌ BEFORE — same validation in 3 places
// in order.controller.ts
if (!request.itemId || request.itemId.length === 0) throw new BadRequestException();

// in quote.controller.ts
if (!request.itemId || request.itemId.length === 0) throw new BadRequestException();

// in cart.controller.ts
if (!request.itemId || request.itemId.length === 0) throw new BadRequestException();

// ✅ AFTER — shared validator (3 uses justifies extraction)
// src/common/validators/item-id.validator.ts
export function validateItemId(itemId: unknown): void {
  if (!itemId || typeof itemId !== 'string' || itemId.length === 0) {
    throw new BadRequestException('itemId is required');
  }
}
```

**After consolidation**:
- All callers updated
- Old duplicates deleted
- Tests for the shared utility
- No orphaned files

---

### Phase 6 — Dependency Audit

```bash
# Node.js — find unused packages
npx depcheck

# Python — unused imports, redefinitions, unused variables (check only, no --fix)
uv run --no-sync ruff check --select F401,F811,F841 src/

# Java — find unused dependencies
./mvnw dependency:analyze | grep "Unused declared"

# Flutter — find unused packages
flutter pub outdated
dart pub deps --no-dev
```

**For each unused package**:
1. Confirm it's truly unused (not dynamically loaded)
2. Remove from manifest
3. Verify build still passes

**For outdated packages with CVEs**:
→ Treat as security work (see `security-audit.md`)

---

### Phase 7 — Verify No Regressions

After all cleanup:

```bash
# Run full test suite
./mvnw test             # Java
npx vitest run          # NestJS
uv run pytest           # Python
flutter test            # Flutter
ng test --watch=false   # Angular

# Build must succeed
./mvnw package          # Java
npm run build           # NestJS/Angular
flutter build apk       # Flutter
```

**Change description** (required before PR):
```
CHANGES MADE:
- [file]: Removed dead function calculateLegacyTax (unused since v1.2, no callers)
- [file]: Extracted validateItemId to src/common/validators/ (used in 3 places)
- package.json: Removed unused packages: lodash, moment (replaced by native)

THINGS I DIDN'T TOUCH:
- Legacy payment adapter: Complex but has no test coverage — flagged for next sprint

POTENTIAL CONCERNS:
- None: all existing tests pass, no behavior changes
```

---

## Quick Reference

| Phase | Action | Agent | Gate |
|-------|--------|-------|------|
| 1 — Identify | Scan for duplicates, dead code, bloat | `dedup-code-agent`, `code-simplifier` | Prioritized inventory |
| 2 — Prioritize | Triage by risk and value | Manual | P1/P2/P3 list |
| 3 — Test coverage | Run baseline + write characterization tests | Manual | All tests pass |
| 4 — Dead code | Remove unused functions, imports, deps | Manual | No callers confirmed |
| 5 — Consolidate | Extract shared utilities (3+ uses) | Manual | All callers updated |
| 6 — Dependencies | Remove unused packages | Manual | Build passes |
| 7 — Verify | Full test suite + build | Manual | All green |

---

## Common Pitfalls

- **Cleaning without tests** — refactoring without tests = behavior-breaking regressions that aren't caught
- **Premature abstraction** — creating a shared utility for 2 uses (not 3); the interface won't be right
- **Deleting "dead" code with dynamic invocation** — reflection, late binding, plugin systems can call code with no static references
- **Big bang cleanup** — cleaning everything at once; do it in small PRs that are individually reviewable
- **Not updating all callers** — leaving one caller of the old function causes a subtle bug

## Related Workflows

- [`code-review.md`](code-review.md) — tech debt findings surface during code review
- [`test-driven-development.md`](test-driven-development.md) — write tests before refactoring
- [`pr-shipping.md`](pr-shipping.md) — cleanup PRs go through same gate as feature PRs
