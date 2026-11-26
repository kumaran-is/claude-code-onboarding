# RED-GREEN-REFACTOR evidence

Loaded by `test-driven-development` and `/tdd`. Does not replace stack runners.
Does not make TDD mandatory for config, rename, generated artifacts, or
documentation (`first-principles.md` Layer 2). Do not delete a working diff
and restart because a test was written after the code — fix the test instead.

Classifier:

```bash
python3 .claude/skills/test-driven-development/scripts/check-tdd-evidence.py \
  --classify /tmp/tdd-red.log
```

Prints one of: `behavioral` | `compile` | `configuration` | `environment` | `unknown`.

## RED

1. Write the failing test for the intended behavior.
2. Run the **stack** command from the task contract (not a generic `npm test`).
3. Capture stdout/stderr and the exit code.
4. Classify the log. RED is satisfied only when the class is `behavioral` and
   the failure matches the assertion you wrote (file:line of the expect).
5. If the class is `compile`, `configuration`, or `environment`, **stop**. That
   is not a failing test. Fix the toolchain, then re-run RED.

| Class | Examples | Action |
|-------|----------|--------|
| behavioral | AssertionError, Expected/Actual, flutter `Expected:`, JUnit `expected:` | RED ok |
| compile | cannot find symbol, error TS, SyntaxError, Compilation failed | not RED |
| configuration | No tests found, unknown option, plugin not found | not RED |
| environment | command not found, SDK missing, connection refused | BLOCKED |

Do not proceed to implementation on a non-behavioral failure.

## GREEN

1. Implement the minimum change that makes **that** assertion pass.
2. Re-run the same command.
3. Exit 0 on the intended test is required. Record the command and a pass count.
4. Do not treat a skipped suite (0 executed) as GREEN.

## REFACTOR

1. Improve structure without changing approved behavior.
2. Re-run the task tests **and** the relevant regression set (`/verify` for the
   stacks touched; `/test-partner` when the change is user-visible).
3. Record actual command output. A ledger row or a checklist tick is not evidence.

## Stack commands (do not substitute)

| Stack | Unit / component | UI / E2E |
|-------|------------------|----------|
| Flutter Android/iOS | `flutter test` | Maestro CLI/MCP only — never Playwright |
| Flutter web build | `flutter test` | Playwright (web build only) |
| Angular | `ng test` (Vitest) | Playwright CLI / `@playwright/test` |
| React | Vitest + Testing Library | Playwright CLI / `@playwright/test` |
| Java / Spring Boot | `./mvnw test` (JUnit; Testcontainers when the test needs a real collaborator) | — |
| Python / FastAPI | `pytest` | — |
| NestJS | Vitest unit + e2e as the skill specifies | — |
| Agentic AI / RAG | golden dataset + deterministic tests + eval suite | — |

Routing owner: `.claude/rules/testing-tool-selection.md`. Chrome DevTools MCP is
diagnostics, not E2E.

## Exceptions (TDD does not apply)

Config, rename, formatting, generated artifacts, documentation-only, and
refactor-only changes: run existing tests before and after. No new RED test
is required (`first-principles.md` Layer 2).
