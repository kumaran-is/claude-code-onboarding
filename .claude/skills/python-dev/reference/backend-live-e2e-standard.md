# Backend Live E2E Integration Testing Standard

## Why Unit Tests Are Not Enough

Per-service unit tests use `ASGITransport(app=app)`, which bypasses the real HTTP stack, does not run
ASGI lifespan, mocks external client initialisation, and often uses `AsyncMock()` for DB sessions.
They never hit a real container.

Unit tests CANNOT catch:
- Wrong HTTP method (PUT vs PATCH vs POST)
- Missing route prefixes (`/api/v1/`)
- Auth gate ordering (auth checked before validation)
- Container startup failures or port mismatches
- Real auth token rejection
- Cross-service integration issues
- A stale container that does not contain your change

Database behaviour (constraints, JSONB, savepoints) is covered by the real-PostgreSQL integration tests in
`.claude/skills/python-testing-patterns/reference/postgres-integration-testing.md`; live E2E covers the deployed shape.

## The Live E2E Test Standard

**Location:** one canonical live E2E module (for example `tests/e2e/test_backend_live_e2e.py`) covering every backend service.
It uses `httpx.AsyncClient(base_url=...)` with NO transport override, hitting actual running containers.

**Configuration (environment, never hard-coded):**

| Setting | Rule |
|---------|------|
| Base URLs | `<SVC>_BASE_URL` env var; default `http://localhost:<port>` for local, override to run against a deployed environment |
| Timeout | per-test timeout via env (`E2E_TIMEOUT_S`, passed to both httpx and `pytest-timeout`); a hung container must fail, not stall CI |
| Tokens | for deployed runs, pre-minted real identity tokens in env; locally, a test credential |
| Scheduler/internal-only endpoints | mark them (`@pytest.mark.internal_only`) and skip them against a deployed environment ONLY with an explicit reason |

**Run command:** your project's E2E target (`make backend-e2e-live` or `uv run pytest tests/e2e/test_backend_live_e2e.py`).

**When to run:** before any PR touching backend services, after the freshness check below proves the containers run your code.

## Pre-run: prove the container runs YOUR code

Neither an uptime reset nor "the image is newer than the source" is proof. Do all four:

1. Build the changed service(s).
2. `docker compose up -d --force-recreate <service>` (recreate, not restart).
3. Poll until every affected container is `healthy` (a condition with a deadline, never a fixed `sleep`).
4. Probe the running container (commands in this section are not executed in the validation environment; adapt paths to your image): `docker compose exec <service> grep -c "<pre-existing symbol>" <file>` must be greater than 0 (positive control: the probe can find code), then `grep -c "<new symbol>" <file>` must be greater than 0.

If step 4's control returns 0 the probe is wrong (wrong path, wrong working directory); fix the probe before trusting a 0 for the new symbol.

## Per-Service Test Pattern

Every backend service MUST have these test cases in the live E2E module:

```python
# 1. Health check (liveness)
async def test_<svc>_health(<svc>_client):
    r = await <svc>_client.get("/health/live")
    assert r.status_code == 200

# 2. Auth gate — no credentials → 401/403
async def test_<svc>_list_requires_auth(<svc>_client):
    r = await <svc>_client.get("/api/v1/<resources>")
    assert r.status_code in (401, 403)

# 3. Fake JWT rejection → 401
async def test_<svc>_create_with_fake_jwt_returns_401(<svc>_client):
    r = await <svc>_client.post(
        "/api/v1/<resources>",
        json={...},
        headers={"Authorization": _FAKE_JWT},
    )
    assert r.status_code == 401

# 4. Internal endpoint requires secret (for services with /internal/* routes)
async def test_<svc>_internal_requires_secret(<svc>_client):
    r = await <svc>_client.post(f"/api/v1/internal/<resources>/{uuid.uuid4()}/action")
    assert r.status_code in (401, 403)

# 5. Input validation — 422 on missing required fields
#    Only testable with a credential that PASSES the auth dependency. With a JWT dependency,
#    an empty JSON object gets 401 first, not 422 (see Auth Ordering).
async def test_<svc>_create_missing_fields(<svc>_client):
    if not _INTERNAL_SECRET:
        pytest.skip("INTERNAL_API_SECRET not available: export it or add it to .env")
    r = await <svc>_client.post(
        "/api/v1/<resources>",
        json={},
        headers={_INTERNAL_SECRET_KEY: _INTERNAL_SECRET},
    )
    assert r.status_code == 422
```

### Skip vs fail in deployed runs

A skip is acceptable LOCALLY with an actionable message. In a deployed/CI run (`E2E_REQUIRE=1`):
- a missing credential, token or base URL FAILS the run;
- an "expected 401" persona (the case that proves the gate rejects) must FAIL, never skip, when its token is absent: skipping it silently removes the security assertion;
- assert collected-and-executed count > 0 (an all-skipped run exits 0): `scripts/check_executed.py` in `postgres-integration-testing.md` section 9.

## Adding Tests for a New Backend Service

1. Add the service client fixture:
```python
@pytest_asyncio.fixture
async def <svc>_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(base_url=<SVC>_BASE_URL, timeout=E2E_TIMEOUT_S) as client:
        yield client
```

2. Add the base-URL constant at the top of the file:
```python
<SVC>_BASE_URL = os.getenv("<SERVICE_NAME>_BASE_URL", "http://localhost:<default_port>")
```

3. Add the 5 standard test cases (pattern above).

4. Add the service to the `_ALL_SERVICES` mapping used by the cross-service reachability test:
```python
_ALL_SERVICES = {
    ...,
    "<service-name>": <SVC>_BASE_URL,
}
```

5. Add the `<svc>_client` fixture to the `test_all_services_are_reachable` params.

## Critical Implementation Notes

### Auth Ordering
Executed on FastAPI 0.165 (re-run on your version): with an auth dependency that raises `HTTPException(401)` and a body model with a required field,
- empty JSON object `{}` and no credentials → **401** (not 422);
- no body at all and no credentials → **401**;
- **malformed JSON** and no credentials → **422** (the body is parsed before the dependency runs);
- empty JSON object with valid credentials → **422**.

Always check the actual auth mechanism from the service's OpenAPI spec before writing input-validation tests.

### HTTP Methods
ALWAYS verify from `curl -s http://localhost:<port>/openapi.json` before writing tests.
Do NOT assume method from endpoint name:
- Status updates are typically PATCH, not PUT
- Internal scoring endpoints are POST, not PUT

### Route Prefix
Backend services commonly use an `/api/v1/` prefix. Internal routes often use
`/api/v1/internal/`. Always verify from the OpenAPI spec — admin or identity routes may differ.

### Lifespan and state
Live E2E exercises the real lifespan (startup checks, pools, health checker). In-process tests must wrap the app with
`asgi_lifespan.LifespanManager` or `TestClient` to get the same.

## Pre-commit Gate

```bash
# After the freshness check, before PR creation
uv run pytest tests/e2e/test_backend_live_e2e.py -v --tb=short --junitxml=e2e.xml > e2e.log 2>&1; echo "E2E EXIT:$?"; tail -30 e2e.log
uv run python scripts/check_executed.py e2e.xml; echo "EXECUTED EXIT:$?"
```

All tests must pass and the executed count must be greater than 0. Any failure = fix before PR creation. Feedback loop:
1. Read the failure — check the actual OpenAPI spec at `http://localhost:<port>/openapi.json`
2. Fix the test OR fix the service code (if behaviour is genuinely wrong)
3. Re-run the freshness check if service code changed, then the E2E command
4. Repeat until GREEN (status `PASS` only when pytest's own exit code is 0 AND executed > 0; unreachable containers are `BLOCKED`)
