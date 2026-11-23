---
description: "Multi-stack test coverage report: run coverage for each detected stack and list files below 80%, worst first."
allowed-tools: Read, Bash, Glob, Grep
---

# /test-coverage — Multi-Stack Test Coverage Report

Detect which stacks are present and run coverage for each. Lists files below 80% threshold sorted worst-first.

**Minimum threshold: 80% coverage. 100% required for auth, crypto, payment logic.**

## Stack Detection + Coverage Commands

### Spring Boot (Java 21 / Maven)
Detected by: `pom.xml` containing `spring-boot`

```bash
./mvnw test jacoco:report -q > /tmp/cov-java.log 2>&1; echo "COVERAGE EXIT:$?"   # non-zero → FAIL; show tail of the log
# Files below threshold (display only, reads the CSV the run produced):
awk -F',' 'NR>1 {missed=$4+$6; total=missed+$5+$7; pct=(total>0)?int((total-missed)*100/total):0; if(pct<80) print pct"% "$2"/"$3}' \
  target/site/jacoco/jacoco.csv | sort -n | head -20
```
No `jacoco-maven-plugin` in `pom.xml` → BLOCKED (say so), never 0%.

### Python / FastAPI (Python 3.14)
Detected by: `pyproject.toml` or `requirements.txt` containing `fastapi`

```bash
# Capture pytest's OWN exit code: a --cov-fail-under failure is invisible behind `| grep`
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80 -q > /tmp/cov.log 2>&1; echo "COVERAGE EXIT:$?"
tail -40 /tmp/cov.log
# Files below threshold (reads the saved log; the awk output is display only):
awk '/^TOTAL/{next} /[0-9]+%/{if(int($4)<80) print $4" "$1}' /tmp/cov.log | sort -n
```

A coverage percentage is a diagnostic, not a proof of quality: measure hand-written code only (exclude generated code and migrations in `[tool.coverage.run] omit`), ratchet floors up and never down, never pad with assertion-free tests, and keep `--cov` out of pytest `addopts` (it slows every run and interferes with debuggers; run it here). Zero executed tests is FAIL (all-skipped exits 0). For the riskiest modules prefer mutation testing on the PR diff over a higher percentage.

### NestJS (Node.js / TypeScript)
Detected by: `package.json` containing `@nestjs/core`

```bash
npm run test:cov > /tmp/cov-node.log 2>&1; echo "COVERAGE EXIT:$?"   # vitest run --coverage; thresholds in vitest.config fail the run
tail -40 /tmp/cov-node.log
```
Missing `@vitest/coverage-v8` or no `test:cov` script → BLOCKED. Thresholds belong in `vitest.config.*` (`coverage.thresholds`), so the exit code is the verdict; the table is display only.

### Angular (21.x, `@angular/build:unit-test`)
Detected by: `angular.json`

```bash
npx ng test --watch=false --coverage > /tmp/cov-ng.log 2>&1; echo "COVERAGE EXIT:$?"
tail -40 /tmp/cov-ng.log
```
Source: `.claude/skills/angular-spa/reference/testing-vitest.md`.

### React (Vite + Vitest)
Detected by: `package.json` containing `react` and `vitest` (no `angular.json`, no `@nestjs/core`)

```bash
npx vitest run --coverage > /tmp/cov-react.log 2>&1; echo "COVERAGE EXIT:$?"
tail -40 /tmp/cov-react.log
```
Missing `@vitest/coverage-v8` → BLOCKED. Coverage is unit/component only; E2E (Playwright) is not counted here — see `.claude/rules/testing-tool-selection.md`.

### Flutter (Dart 3.10.9)
Detected by: `pubspec.yaml` containing `flutter:`

```bash
flutter test --coverage > /tmp/cov-flutter.log 2>&1; echo "COVERAGE EXIT:$?"   # writes coverage/lcov.info
tail -20 /tmp/cov-flutter.log
lcov --summary coverage/lcov.info   # lcov not installed → report the summary as NOT RUN, the test result still stands
```
Unit and widget coverage only. Device UI/E2E flows run with Maestro and are not part of this number.

## Output Format

```
## Test Coverage Report — {date}

### Spring Boot API
✅ Overall: 84% (threshold: 80%)

Files below 80%:
| File | Coverage | Missing Lines |
|------|----------|---------------|
| UserService.java | 67% | 45-52, 78-80 |
| AuthFilter.java  | 71% | 12-15 |

### Python API
❌ Overall: 71% (threshold: 80%) — BELOW THRESHOLD

Files below 80% (sorted worst-first):
| File | Coverage | Missing Lines |
|------|----------|---------------|
| payment_service.py | 45% | 23-67, 89-102 |
| user_repository.py | 62% | 34-45 |

### NestJS API
✅ Overall: 88% (threshold: 80%)
(No files below threshold)

### Flutter App
✅ Overall: 82% (threshold: 80%)

## Summary
- Stacks checked: 4 (one status line each: PASS / FAIL / BLOCKED / NOT RUN)
- Passing (≥80%): 3
- Failing (<80%): 1 (Python API)
- Critical files below 100%: [list any auth/crypto/payment files not at 100%]

## Suggested Next Steps
Generate missing tests for worst-coverage files:
1. payment_service.py (45%) — add tests for lines 23-67 (payment processing logic)
2. user_repository.py (62%) — add tests for lines 34-45 (error paths)
```

## Rules

- Run ALL detected stacks — do not skip
- 80% is the minimum; auth/crypto/payment code requires 100%
- Sort worst-coverage files first — highest ROI to fix
- Do NOT auto-generate tests — report only, human decides
- Status per stack is PASS / FAIL / BLOCKED / NOT RUN from each command's OWN exit code (`cmd > log 2>&1; echo $?`), never from `cmd | tail` (that reports `tail`'s status)
- Zero executed tests is FAIL, even when the runner exits 0
- If a stack build fails before coverage runs: FAIL — "STACK BUILD FAILED — fix build errors first"
- If no test runner or coverage provider is installed: BLOCKED — name what is missing

## Related

Use instead when: `/verify full` — pass/fail of build and tests without coverage; `/tdd` — write the missing tests test-first.

- `/tdd` — test-first implementation when coverage is below threshold
- Agent: `.claude/agents/tdd-guide.md` — Red-Green-Refactor enforcement
