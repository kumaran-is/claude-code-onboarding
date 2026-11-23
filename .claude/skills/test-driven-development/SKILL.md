---
name: test-driven-development
description: "Use when implementing new features or logic that requires tests — before writing implementation code. Covers Red-Green-Refactor cycle, stack-specific test patterns, test naming conventions, and mocking. Triggers: \"write tests first\", \"TDD\", \"test-driven\", \"failing test\", \"red-green-refactor\", \"how do I test X\"."
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
metadata:
  triggers: TDD, test-driven, write tests first, failing test, red-green-refactor, test first, unit test, TDD cycle
  related-skills: systematic-debugging, verification-before-completion, code-reviewer
  domain: quality
  role: specialist
  scope: testing
  output-format: code
last-reviewed: "2026-03-14"
---

# Test-Driven Development

## Iron Law

**NO IMPLEMENTATION WITHOUT A FAILING TEST FIRST**

Write the test. Run it. See it fail (RED). Then implement until it passes (GREEN). Then refactor.

## When TDD Applies

**DO use TDD for:**
- New features and new logic
- Bug fixes (write a test that reproduces the bug first)
- Any code path that has business logic

**DO NOT use TDD for:**
- Config changes, renames, formatting
- Trivial one-line fixes with no logic
- See `leverage-patterns.md` Test-First section for the full rule

## Red-Green-Refactor Cycle

```
RED   -> Write a test that FAILS for the right reason
         Run it. Confirm it fails. If it passes without code -> test is wrong.

GREEN -> Write the MINIMUM code to make the test pass
         No extras. No "while I'm here" additions.

REFACTOR -> Clean up code without changing behavior
            Run tests again. Must still pass.
```

> For verifying regression tests are genuine (not vacuous): see `verification-before-completion` Red-Green protocol.
> For TDD during bug investigation: see `systematic-debugging` Phase 4 — Create Failing Test Case.

## Test Naming Convention

Pattern: `test_<what>_<when>_<expected>` (or `should_<expected>_when_<condition>`)

```
# Java
@Test void createUser_withDuplicateEmail_throwsConflictException()

# NestJS, Angular, React (Vitest)
it('should throw ConflictException when email already exists', ...)

# Python/pytest
def test_create_user_with_duplicate_email_raises_conflict():

# Flutter
test('createUser throws ConflictException when email is duplicate', ...)
```

## Stack Dispatch

| Stack | Reference File | Load When |
|-------|---------------|-----------|
| Java 21 / Spring Boot WebFlux | `references/tdd-patterns-java.md` | Writing tests for Spring Boot, WebFlux, reactive Java |
| NestJS 11 / TypeScript | `references/tdd-patterns-nestjs.md` | Writing tests for NestJS, TypeScript, Fastify |
| Python 3.14 / FastAPI | `references/tdd-patterns-python.md` | Writing tests for FastAPI, Pydantic, async Python |
| Flutter / Dart | `references/tdd-patterns-flutter.md` | Writing tests for Flutter widgets, Riverpod providers, Dart |
| Angular 22 | `../angular-spa/reference/testing-vitest.md` | Writing `ng test` (Vitest) component and service tests |
| React 19 | `../react-spa/reference/testing.md` | Writing Vitest + React Testing Library tests |

## Quick Checklist

Before claiming a test is real:
- [ ] Test FAILED before implementation (you saw the red output)
- [ ] Test PASSES after implementation (you saw the green output)
- [ ] Test name describes behavior, not implementation
- [ ] One assertion per logical outcome (not 10 assertions in one test)
- [ ] Mocks are used for external dependencies only (not to avoid writing logic)
