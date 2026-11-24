---
name: python-testing-patterns
description: Comprehensive pytest patterns for Python 3.14 / FastAPI — fixtures, parametrize, mocking, async testing, database fixtures, test markers, coverage config, and CI integration. Use when writing or structuring Python test suites beyond the basic TDD cycle.
allowed-tools: Read, Write, Edit, Bash
metadata:
  triggers: pytest, pytest fixtures, parametrize, pytest mocking, async tests, test database, coverage config, pytest markers, Python test suite, conftest.py, GitHub Actions tests, property-based testing, Hypothesis pytest
  related-skills: test-driven-development, python-dev, agentic-ai-dev
  domain: quality
  role: specialist
  scope: testing
  output-format: code
last-reviewed: "2026-11-23"
---

## Iron Law

**NO TEST INFRASTRUCTURE WITHOUT READING THE PLAYBOOK FIRST — fixtures, markers, and coverage config have workspace-specific patterns that prevent test debt**

# Python Testing Patterns

Deep reference for pytest test infrastructure, fixtures, async patterns, and CI integration for Python 3.14 / FastAPI services.

## When to Use

Load this skill when:
- Setting up a new test suite from scratch (conftest.py, pyproject.toml config)
- Writing parametrized tests for multiple input scenarios
- Mocking async dependencies (AsyncMock patterns)
- Testing database operations with session fixtures
- Configuring test markers (`slow`, `integration`) for selective execution
- Setting up coverage reporting gates
- Wiring GitHub Actions CI for Python tests

Load `test-driven-development` skill first for the Red-Green-Refactor process. This skill handles the *infrastructure* — not the TDD process.

## Quick Reference

| Need | Pattern |
|------|---------|
| Multiple inputs | `@pytest.mark.parametrize` |
| Async test | `asyncio_mode = "auto"` (or `@pytest.mark.asyncio` in strict mode) + `AsyncMock` |
| HTTP endpoint test | `httpx2.AsyncClient` + `httpx2.ASGITransport` inside `app.router.lifespan_context(app)` (ASGITransport does not run lifespan) + clear `dependency_overrides`; Starlette 1.10 deprecates `httpx` for its `TestClient`; outbound service clients stay on `httpx` 0.28.1 |
| DB session in test | real PostgreSQL, outer transaction + `join_transaction_mode="create_savepoint"` ([reference](reference/postgres-integration-testing.md)) |
| Commit boundary / race | two real connections + `asyncio.Barrier` + remove-the-guard control (not the savepoint fixture) |
| Missing infra | skip locally, FAIL in CI (`REQUIRE_DB_TESTS=1`); assert executed count > 0 |
| Slow/integration gate | `@pytest.mark.slow` + `-m "not slow"` in CI |
| Coverage gate | `pytest --cov=src --cov-fail-under=80` |
| Parallel / hangs | `pytest -n auto` (pytest-xdist 3.8; per-worker DB names) + `timeout = "30"` (pytest-timeout, string value) |
| Config | pytest 9 `[tool.pytest]` + `strict = true`; never both `[tool.pytest]` and `[tool.pytest.ini_options]` |
| Property-based | `@given(st.text())` from Hypothesis |

## Reference File

Load `resources/implementation-playbook.md` for:
- 5 fundamental patterns (basic tests, fixtures, parametrize, mocking, exceptions)
- Test organization and naming, best-practices summary

Load `reference/pytest-advanced-and-config.md` for:
- 5 advanced patterns (async, monkeypatch, tmp_path, conftest fixtures, Hypothesis)
- Test markers, coverage, the real-PostgreSQL session fixture, CI pointers
- `pyproject.toml` configuration: pytest 9 native `[tool.pytest]`, coverage, ruff, mypy, vulture (and the stub-package trap)

Load `reference/postgres-integration-testing.md` for any test that touches the database: async pytest config and loop scopes, skip-vs-fail fixture, SAVEPOINT session, ASGI client with lifespan, race tests, singleton restore, deterministic clocks/ids, the executed-count gate, flaky-test policy. Load `reference/mock-patterns.md` for autospec, async mocks and fidelity traps. CI gates, pins and dependency audit: `../deployment-ci-cd/reference/python-ci-supply-chain.md`.

## Relationship to Other Skills

- `test-driven-development` — process (Red-Green-Refactor, when to write tests, naming)
- `python-testing-patterns` — infrastructure (how to structure, configure, and run tests)
- `agentic-ai-dev/reference/agentic-testing.md` — LangGraph agent-specific testing patterns

## Post-Test Checklist

- [ ] `pytest -q > log 2>&1; echo "EXIT:$?"` — read pytest's OWN exit code (never through `| tail`) and show the summary counts
- [ ] Executed count > 0: an all-skipped run exits 0 (`reference/postgres-integration-testing.md` §9)
- [ ] `pytest --cov=src --cov-report=term-missing` — coverage visible; floor is a diagnostic: measure hand-written code only, ratchet up only, never pad assertion-free tests; keep `--cov` out of `addopts`
- [ ] No `print()` in test files — use `capfd` fixture or logging
- [ ] One asyncio mode (`auto` or strict); both `asyncio_default_fixture_loop_scope` and `asyncio_default_test_loop_scope` set explicitly; no `event_loop` fixture (removed in pytest-asyncio 1.0: `fixture 'event_loop' not found`), use `asyncio.get_running_loop()` inside the test
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` each read by their own exit code; no `types-*` stub shadowing a package that ships `py.typed`
- [ ] ORM/SQL behaviour tested on real PostgreSQL; SQLite only for pure-logic tests
- [ ] Infra-dependent tests probe the ACTUAL dependency and skip with an actionable message; CI sets `REQUIRE_<X>=1` so absence FAILS
- [ ] External services mocked/blocked — no real network in unit tests; no `sleep`, no wall clock, no unseeded ids, explicit `ORDER BY`
- [ ] Module globals restored via `monkeypatch`; `app.dependency_overrides` cleared in teardown
- [ ] Assert outcomes (one side effect, same status on replay), not that a mechanism was called
- [ ] Every new "zero findings" gate has a known-bad positive control
- [ ] A flaky test is re-run ONCE with the artifact captured, then fixed or quarantined with owner + exit criterion; never re-run until green
