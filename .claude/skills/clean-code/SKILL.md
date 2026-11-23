---
name: clean-code
description: "Clean Code principles (naming, small functions, comments, formatting, error handling, tests, classes, smells) for any stack. Use when writing or refactoring for readability. For a review of a diff use code-reviewer or code-simplifier."
allowed-tools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
metadata:
  triggers: clean code, readability, naming, refactor for readability, code smells, function size, comments, maintainability review
  risk: safe
  source: "ClawForge (https://github.com/jackjin1997/ClawForge)"
  date_added: "2026-02-27"
  domain: quality
  role: reference
  scope: cross-stack
last-reviewed: "2026-03-14"
---

# Clean Code Skill

## Iron Law

Before applying any principle, READ the relevant source file first.
> Do not refactor or flag issues based on memory — verify the actual code (file:line) before making any claim.

This skill embodies the principles of "Clean Code" by Robert C. Martin (Uncle Bob). Use it to transform "code that works" into "code that is clean."

## Core Philosophy
> "Code is clean if it can be read, and enhanced by a developer other than its original author." — Grady Booch

## When to Use
- **Writing new code**: Ensure high quality from the start.
- **Reviewing Pull Requests**: Provide constructive, principle-based feedback.
- **Refactoring legacy code**: Identify and remove code smells.
- **Improving team standards**: Align on industry-standard best practices.

## 1. Meaningful Names
- **Use Intention-Revealing Names**: `elapsedTimeInDays` instead of `d`.
- **Avoid Disinformation**: Don't use `accountList` if it's actually a `Map`.
- **Make Meaningful Distinctions**: Avoid `ProductData` vs `ProductInfo`.
- **Use Pronounceable/Searchable Names**: Avoid `genymdhms`.
- **Class Names**: Use nouns (`Customer`, `WikiPage`). Avoid `Manager`, `Data`.
- **Method Names**: Use verbs (`postPayment`, `deletePage`).

## 2. Functions
- **Small**: Functions should be shorter than you think.
- **Do One Thing**: A function should do only one thing, and do it well.
- **One Level of Abstraction**: Don't mix high-level business logic with low-level details (like regex).
- **Descriptive Names**: `isPasswordValid` is better than `check`.
- **Arguments**: 0 is ideal, 1-2 is okay, 3+ requires a very strong justification — introduce a parameter object.
- **No Side Effects**: Functions shouldn't secretly change global state.

## 3. Comments
- **Don't Comment Bad Code — Rewrite It**: Most comments are a sign of failure to express in code.
- **Explain Yourself in Code**:
  ```python
  # BAD: comment explains intent that code should express
  if employee.flags & HOURLY and employee.age > 65:

  # GOOD: code expresses intent directly
  if employee.isEligibleForFullBenefits():
  ```
- **Good Comments**: Legal, informative (regex intent), clarification (external library behavior), TODOs (with ticket).
- **Bad Comments**: Mumbling, redundant, misleading, mandated, noise, position markers.

## 4. Formatting
- **The Newspaper Metaphor**: High-level concepts at the top, details at the bottom.
- **Vertical Density**: Related lines should be close to each other.
- **Indentation**: Essential for structural readability.

## 5. Objects and Data Structures
- **Data Abstraction**: Hide the implementation behind interfaces.
- **The Law of Demeter**: A module should not know about the innards of objects it manipulates.
  ```java
  // BAD — violates Law of Demeter
  String city = order.getCustomer().getAddress().getCity();

  // GOOD — delegate to the object
  String city = order.getCustomerCity();
  ```
- **Data Transfer Objects (DTO)**: Classes with public variables and no functions — already enforced in NestJS/Spring patterns.

## 6. Error Handling
- **Use Exceptions instead of Return Codes**: Keeps logic clean.
- **Write Try-Catch-Finally First**: Defines the scope of the operation.
- **Don't Return Null**: Forces the caller to null-check every time — throw or return an error state instead.
- **Don't Pass Null**: Leads to `NullPointerException` / `NullError`. Validate at boundaries.

> This section reinforces `code-standards.md` error handling rules ("No Silent Failures"). These are consistent — not conflicting.

## 7. Unit Tests
- **The Three Laws of TDD**:
  1. Don't write production code until you have a failing unit test.
  2. Don't write more of a unit test than is sufficient to fail.
  3. Don't write more production code than is sufficient to pass the failing test.
- **F.I.R.S.T. Principles**: Fast, Independent, Repeatable, Self-Validating, Timely.

## 8. Classes
- **Small**: Classes should have a single responsibility (SRP).
- **The Stepdown Rule**: Code should read like a top-down narrative — callers before callees.

## 9. Smells and Heuristics
- **Rigidity**: Hard to change because every change cascades.
- **Fragility**: Breaks in many places when changed.
- **Immobility**: Hard to reuse in another context.
- **Viscosity**: Hard to do the right thing; wrong things are easier.
- **Needless Complexity/Repetition**: More code than needed.

## Anti-Patterns to Avoid

> **Don't do these** — they are the most common clean code violations in this codebase.

- **Don't** use single-letter variable names outside of loop counters (`i`, `j`) — name by intent
- **Don't** write functions longer than ~20 lines — extract until each function does one thing
- **Don't** return `null` or an empty list on error — throw or return an explicit error state
- **Don't** write a comment that restates what the code does — rewrite the code to be self-explanatory
- **Don't** pass more than 2–3 arguments to a function — introduce a parameter object instead
- **Don't** mix abstraction levels in one function (e.g., high-level business logic + raw SQL in the same method)

## Verify Step

After applying any clean code refactor, run the following to confirm nothing regressed:

```bash
# Run all tests — refactors must not change behavior
# Java
mvn test

# NestJS / Angular
npm test

# Python
uv run pytest

# Flutter / Dart
flutter test
```

Also check:
- `git diff` — confirm no behavior-changing lines snuck into a "rename only" refactor
- `grep -n "as any\|: any\b" <changed files>` — zero new `any` types in TypeScript
- `flutter analyze` — zero new warnings in Dart

## Implementation Checklist
- [ ] Is this function smaller than 20 lines?
- [ ] Does this function do exactly one thing?
- [ ] Are all names searchable and intention-revealing?
- [ ] Have I avoided comments by making the code clearer?
- [ ] Am I passing too many arguments (3+ = needs parameter object)?
- [ ] Is there a failing test for this change?
