# Inbound Rate Limiting — FastAPI

Rate limits are a cost and abuse bound, not an authorization control. The three ways they silently
fail in practice: a bucket that never fills (path parameters), a key the caller controls (per-IP behind
a proxy), and storage that is per-process (N instances × the limit). Examples use SlowAPI; the
rules apply to any limiter. Executed with slowapi 0.1.10, limits 5.8, uvicorn 0.54, FastAPI 0.165.

> SlowAPI 0.1.10 emits a `DeprecationWarning` on Python 3.14 (`asyncio.iscoroutinefunction`, slated
> for removal in 3.16). Check the maintained release before pinning.

---

## 1. Setup

```bash
uv add slowapi
```

```python
from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, storage_uri=settings.rate_limit_storage_uri)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

Every limited route must accept `request: Request`. One `Limiter` instance per route: stacking
two on one route makes the inner one skip its check.

---

## 2. `.limit()` never fires on routes with path parameters

`.limit()` buckets on the concrete request path, so `/inv/{code}` gets one bucket **per code** and
enumeration is never limited. Use `shared_limit` with a constant scope:

```python
ACCEPT_SCOPE = "invite-accept"                        # module constant, one per abuse surface

@router.post("/invitations/{code}/accept")
@limiter.shared_limit("10/hour", scope=ACCEPT_SCOPE, key_func=user_id_key)
async def accept(request: Request, code: str, user: CurrentUser) -> AcceptResponse: ...
```

Executed (`2/hour`, six distinct codes):

| Decorator | Statuses |
|-----------|----------|
| `@limiter.limit("2/hour")` on `/inv/{code}` | 200, 200, 200, 200, 200, 200 (**never fires**) |
| `@limiter.shared_limit("2/hour", scope="invite-lookup")` | 200, 200, 429, 429, 429, 429 |

Routes on one abuse surface share one scope. A route tested by calling the handler function
directly needs the lookup extracted into a plain function once a limiter decorates it.

---

## 3. Choose the key deliberately

Per-IP keys are not a security bound behind a proxy. With uvicorn trusted proxy hosts set to `*`
the **leftmost** `X-Forwarded-For` entry is taken, which the caller supplies and which is not
checked to be an IP (executed: `X-Forwarded-For: evil-1, 203.0.113.7` → client host `evil-1`;
trusting only the real proxy address → `203.0.113.7`).

```python
def user_id_key(request: Request) -> str:
    """Authenticated id from request.state (route-local dependency); IP only when anonymous."""
    uid = getattr(request.state, "user_id", None)
    return f"user:{uid}" if uid else get_remote_address(request)
```

| Purpose | Key |
|---------|-----|
| Enumeration of codes/ids, spend on a metered API | Authenticated **user id** (not a bearer-token hash: refreshing the token mints a new bucket) |
| Login / register / reset before authentication | Client IP **and** target email as separate limits |
| Outer flood protection | Per-IP, with the real proxy addresses listed as trusted (never `*`) |

Executed: `1/hour` keyed on user id → `200, 429` for the same user, `200` for a second user.

---

## 4. Storage must be shared and wired

A limiter without `storage_uri` uses per-process memory: effective limit = instances × limit, reset
on every cold start. Use a shared store (Redis is one choice) and wire it in **deployment** config
(a field that exists only in an env file is not wired). Test the storage value, not just the
decorator:

```python
def test_limiter_uses_shared_storage(settings):
    assert settings.rate_limit_storage_uri.startswith("redis")
```

Decide the failure mode when the store is down (fail open with an alert, or fail closed for
abuse-critical routes) and write it down.

---

## 5. Limits and responses

- Return `429` with `Retry-After`; keep the body inside the standard error envelope (`fastapi-error-handling.md`).
- Starting points: login 5/minute, register 3/hour, password reset 3/hour per email, general
  reads 100–200/minute per user. Tune from measured traffic; these are not security guarantees.
- Responses should carry the rate-limit headers described in `rest-design-principles.md`.

## 6. Edge limiting (optional, platform-specific)

If your platform offers an edge/WAF policy (a cloud load balancer rule, a CDN), set a coarse
per-client baseline and tighter limits on auth paths there as an **additional** layer. The
application limiter above remains the control that knows the user id.

---

## Checklist

```
□ shared_limit(scope=<constant>) on every route with a path parameter; .limit() only on parameter-free routes
□ Enumeration and spend limits keyed on user id; per-IP only as an outer layer with listed proxies
□ storage_uri points at a shared store and a test asserts it
□ One Limiter per route; request: Request present on every limited handler
□ Failure mode when the store is down is decided and documented
```
