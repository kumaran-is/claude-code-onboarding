---
description: "Test-driven development mode: dispatches tdd-guide to enforce Red-Green-Refactor on the current task."
argument-hint: '"[class or feature]"'
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent
---

# /tdd — Test-Driven Development Mode

Invokes the `tdd-guide` agent to enforce Red-Green-Refactor methodology on the current task.

## When to Use

- Implementing a new feature: write tests first
- Adding a bug fix: write a reproducing test first, then fix
- Reviewing test quality: check coverage + edge case completeness

## Behavior

When `/tdd` is invoked, the `tdd-guide` agent:

1. **Identifies the feature/behavior** to be tested
2. **Writes the failing test (RED)** — the test must fail before any implementation
3. **Writes minimum implementation (GREEN)** — just enough to pass
4. **Refactors (REFACTOR)** — clean up without changing behavior
5. **Verifies coverage** — runs coverage report, flags gaps

## DO / DON'T

| DO | DON'T |
|----|-------|
| Write test before implementation | Write implementation then retrofit tests |
| Test behavior, not implementation | Test private methods or internal state |
| Use real stack test runner (JUnit5/pytest/Vitest/flutter_test) | Mock everything including the thing being tested |
| Cover all 8 edge case categories | Only test the happy path |
| Run tests 3x to confirm no flakiness | Ship after a single green run |

## Coverage Requirements

- **Minimum:** 80% line coverage
- **Critical code** (auth, crypto, payments, data migrations): 100%
- Files below threshold are listed and must be addressed before marking feature done

## Error Cases

| Situation | Response |
|-----------|----------|
| Test runner binary not found (`mvnw`, `flutter`, `pytest`, `npm`) | Report "BUILD TOOL NOT FOUND — install [tool] or run from project root" |
| Test passes immediately without implementation (RED phase fails) | "⚠️ Test did not fail first — diagnose before proceeding. The behavior may already exist or the test assertion is wrong." |
| Refactor-only task (no new behavior) | Skip RED phase — run existing tests before and after. No new tests required. |
| Config/rename change | Run existing tests only — no new tests required per first-principles.md |

## Stack Detection

`/tdd` auto-detects the stack from the current working directory:

| Detected | Runner |
|----------|--------|
| `pom.xml` with spring-boot | `./mvnw test` + JaCoCo |
| `pyproject.toml` with fastapi | `pytest --cov=src` |
| `package.json` with @nestjs/core | `npm run test:cov` |
| `pubspec.yaml` with flutter | `flutter test --coverage` |

## Usage Examples

```
/tdd                    # Start TDD cycle for current task
/tdd UserService        # Focus TDD cycle on UserService specifically
/tdd coverage           # Run coverage report only (no new tests)
/tdd audit              # Audit existing tests for edge case completeness
```

## Related

- Agent: `.claude/agents/tdd-guide.md`
- Command: `/test-coverage` — run after TDD cycle to verify overall coverage
- Skill: `.claude/skills/test-driven-development/SKILL.md`

Use instead when: `/test-coverage` — measure coverage gaps without writing tests; `/verify` — run the existing gate.
