# Inbound Rate Limiting — FastAPI

Rate limits are a cost and abuse bound, not an authorization control. The three ways they silently
fail in practice: a bucket that never fills (keyed on the concrete URL), a key the caller controls
(per-IP behind a proxy), and storage that is per-process (N instances × the limit).

> Executed on Python 3.14.10, FastAPI 0.165.0, `limits` 5.8.0 (async Redis via `coredis` 5.7.0),
> Redis 8.2 in a container. Examples use `limits` directly as a FastAPI dependency.

## Library choice

| Option | Status (checked 2026-11) | Decision |
|--------|--------------------------|----------|
| `limits` 5.8 `limits.aio` strategies | Maintained; async storage for Redis, Memcached, MongoDB, memory | **Use** |
| SlowAPI 0.1.10 | Calls the **synchronous** storage from async handlers (`self.limiter.hit` in `extension.py`), so every Redis round trip blocks the event loop; emits a `DeprecationWarning` on Python 3.14 (`asyncio.iscoroutinefunction`, removed in 3.16); default `key_style="url"` never fires on path parameters; `Retry-After` only with `headers_enabled=True`, which then requires a `response: Response` parameter on every limited route (otherwise an exception) | Do not add to new services; migrate existing ones when touched |

Executed SlowAPI 0.1.10 probe, `@limiter.limit("2/hour")` on `/inv/{code}`, four distinct codes:
`key_style="url"` → 200, 200, 200, 200; `key_style="endpoint"` → 200, 200, 429, 429 with no
`Retry-After`.

---

## 1. Setup

```bash
uv add "limits[async-redis]"          # pulls coredis; pin what your lockfile resolves (5.8.0 executed)
```

```python
# src/my_service/core/rate_limit.py
import ipaddress
import math
import time
from collections.abc import Awaitable, Callable
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, status
from limits import RateLimitItem, parse
from limits.aio.strategies import MovingWindowRateLimiter
from limits.storage import storage_from_string

from my_service.api.deps import CurrentUser   # the verified-token dependency (fastapi-auth-security.md)

log = structlog.get_logger(__name__)


def build_limiter(storage_uri: str) -> MovingWindowRateLimiter:
    # "async+redis://host:6379/0" in deployments; "async+memory://" only for single-process tests
    return MovingWindowRateLimiter(storage_from_string(storage_uri))


async def user_key(user: CurrentUser) -> str:
    # a dependency OF the auth dependency: FastAPI resolves (and caches) the user first
    return f"user:{user.id}"


def client_ip_key(request: Request) -> str:
    if request.client is None:   # a shared "unknown" bucket would throttle every such caller together
        raise RuntimeError("server did not report the client address")
    host = request.client.host
    if request.app.state.settings.environment in {"staging", "production"} and not _is_global(host):
        # the proxy's address, not the caller's: every caller would share one bucket (§3)
        log.error("client_address_not_public")
        raise RuntimeError("client address is the proxy: set FORWARDED_ALLOW_IPS for this deployment")
    return f"ip:{host}"


def _is_global(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:                 # "evil-1" from a trusted "*" X-Forwarded-For is not an address
        return False


async def _over_limit(request: Request, item: RateLimitItem, scope: str, ids: tuple[str, ...], *,
                      consume: bool, fail_open: bool) -> int | None:
    """Retry-After seconds when over the limit, else None."""
    limiter: MovingWindowRateLimiter = request.app.state.rate_limiter
    try:
        if await (limiter.hit if consume else limiter.test)(item, scope, *ids):
            return None
        stats = await limiter.get_window_stats(item, scope, *ids)
    except limiter.storage.base_exceptions as exc:
        log.error("rate_limit_storage_unavailable", scope=scope, error_type=type(exc).__name__)
        if fail_open:
            return None
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service unavailable") from exc
    return max(1, math.ceil(stats.reset_time - time.time()))


def too_many(retry_after: int, scope: str) -> HTTPException:
    log.info("rate_limited", scope=scope)
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests",
                         headers={"Retry-After": str(retry_after)})


def rate_limit(spec: str, *, scope: str, key: Callable[..., str | Awaitable[str]],
               fail_open: bool = False) -> Callable[..., Awaitable[None]]:
    """key is itself a dependency (user_key, client_ip_key); scope is one constant per abuse surface."""
    item = parse(spec)

    async def _dep(request: Request, identity: Annotated[str, Depends(key)]) -> None:
        retry_after = await _over_limit(request, item, scope, (identity,), consume=True, fail_open=fail_open)
        if retry_after is not None:
            raise too_many(retry_after, scope)

    return _dep
```

```python
# lifespan: app.state.rate_limiter = build_limiter(settings.rate_limit_storage_uri)
ACCEPT_SCOPE = "invite-accept"

@router.post("/invitations/{code}/accept",
             dependencies=[Depends(rate_limit("10/hour", scope=ACCEPT_SCOPE, key=user_key))])
async def accept(code: str, user: CurrentUser) -> AcceptResponse: ...
```

`limits.aio` strategies assert an async storage: `memory://` raises, use `async+memory://`.

**Key on the user through the auth dependency.** Route `dependencies=[...]` resolve before the
endpoint's own parameters, so a key function that reads `request.state.user_id` (set "later" by the
auth dependency) always falls back to the IP. Executed with that pattern: user `u1` used three of
`3/minute`, then a different user `u2` on the same IP got **429** — every user behind one proxy shares
one bucket. With `user_key` above: two users on one IP get separate buckets, one user on two IPs
shares one; keying `user_key` on a constant or swapping in `client_ip_key` turned those tests red.

---

## 2. One bucket per abuse surface, not per URL

A limiter keyed on the concrete path gives `/inv/{code}` one bucket **per code**, so enumeration is
never limited. The `scope` argument above is a constant: executed `3/minute` with five random codes
→ 200, 200, 200, 429, 429. With the scope replaced by `request.url.path` the same test went green to
red (every request 200). Routes on one abuse surface share one scope.

---

## 3. Choose the key deliberately

Per-IP keys are not a security bound behind a proxy. With uvicorn `forwarded_allow_ips="*"` the
**leftmost** `X-Forwarded-For` entry is taken, which the caller supplies and which is not checked to
be an IP (executed on uvicorn 0.54.0: `X-Forwarded-For: evil-1, 203.0.113.7` → client host `evil-1`; trusting only the
real proxy address → `203.0.113.7`).

Keep uvicorn's default: it trusts `X-Forwarded-For` only from `FORWARDED_ALLOW_IPS`, which defaults
to `127.0.0.1,::1`, so a non-loopback front end's header is ignored and the peer is the client
(executed: peer `10.1.2.3` → client host `10.1.2.3`). There is no universal proxy range: set
`FORWARDED_ALLOW_IPS` per deployment only to a range your platform documents or you have verified,
fail boot when it contains `*`, and test in the deployed setup that `request.client.host` is the
caller, not the proxy.

Behind a load balancer that is not on loopback, the default leaves `client.host` as the balancer's
address: (email, IP) failure counting then acts as a per-email lockout, and the per-IP limit as one
global bucket. `client_ip_key` therefore refuses a non-global address (private, link-local, CGNAT,
loopback, or not an IP) in staging and production. **Deployed smoke check:** after each deploy, send
one wrong-password login; it must answer 401, and a 500 with `client_address_not_public` in the log
means `FORWARDED_ALLOW_IPS` is missing for that platform. Executed: `10.20.0.5`, `169.254.1.1`,
`100.64.0.9`, `127.0.0.1`, `fd00::1` and `evil-1` raised in staging and production; `8.8.4.4` and any
address in `local` passed (environment read from `request.app.state.settings`, never a module-level
settings object); disabling the check, or testing `is_private` instead of `is_global` (which lets
CGNAT through), turned tests red.

`client_ip_key` raises when the server reports no client address rather than pooling those callers.

| Purpose | Key |
|---------|-----|
| Enumeration of codes/ids, spend on a metered API | `user_key` (not a bearer-token hash: refreshing the token mints a new bucket) |
| Login | **Failed** attempts per (email, client IP) — below — plus a per-IP limit on all attempts |
| Register / password reset | Per IP, and per target email for the mail it sends (bounds mail to the victim, never blocks sign-in) |
| Outer flood protection | `client_ip_key` (behind a proxy, only once `FORWARDED_ALLOW_IPS` names it; never `*`) |

**Login: count failures, not attempts, and never lock an account by email alone.** A per-email limit
on every attempt lets anyone lock a victim out by sending five bad passwords. Check the budget before
verifying, record a hit only when verification fails, and key on the (email, client) pair; pair it
with the per-IP limit, and add friction (step-up, alert) rather than lockout for spraying across IPs.

```python
LOGIN_FAILURES = parse("5/15 minutes")

def _login_ids(request: Request, email: str) -> tuple[str, str]:
    return email.strip().lower(), client_ip_key(request)   # Python lower(), matching SQL lower(email)

async def check_login_failures(request: Request, email: str) -> None:      # before verify_password
    retry_after = await _over_limit(request, LOGIN_FAILURES, "login-fail", _login_ids(request, email),
                                    consume=False, fail_open=False)
    if retry_after is not None:
        raise too_many(retry_after, "login-fail")

async def record_login_failure(request: Request, email: str) -> None:      # only when it fails
    await _over_limit(request, LOGIN_FAILURES, "login-fail", _login_ids(request, email),
                      consume=True, fail_open=False)
```

`check` then `record` is not atomic: 50 concurrent wrong guesses from one IP all reached password
verification despite the 5-failure budget. The per-IP limit on **all** attempts (consumed up front,
`fastapi-auth-security.md` §5) bounds it: with `20/minute`, at most 20 reached verification.

Normalise email once: look it up with the unique index's expression (`func.lower(User.email) ==
func.lower(email)`) and key failures on `email.strip().lower()`. Not `casefold()`: it maps ß to ss,
so `Straße@…` and `STRASSE@…` would share a bucket while the index keeps two accounts. Executed on
PostgreSQL 18.7 (en_US.utf8): the key matched the index for ß spellings; the one gap is dotted İ
(SQL `lower` → `i`, Python → `i̇`), which only splits the bucket — the account match stays in SQL.

Executed: an attacker IP sent six wrong passwords for the victim → 401 × 5, then 429; the victim
from another IP then logged in (200); eight successful logins in a row all 200; unknown and known
accounts kept one identical 401. Keying on the email alone, or counting successes, each turned a
test red; so did dropping the missing-client check.

---

## 4. Storage must be shared and wired

Per-process memory makes the effective limit instances × limit and resets on every cold start.
Executed with two app instances: sharing `async+redis://` → 200, 200, 200, 429 across alternating
instances; `async+memory://` → four 200s. Wire the URI in **deployment** config (a field that exists
only in an env file is not wired) and test the value:

```python
def test_limiter_uses_shared_storage(settings):
    assert settings.rate_limit_storage_uri.startswith("async+redis")
```

Decide the failure mode when the store is down and write it down. Executed with Redis unreachable:
fail-closed returned 503, `fail_open=True` returned 200 (log at error level and alert either way).
Fail closed on abuse-critical routes (login, code redemption, spend); fail open is a deliberate
choice for read traffic.

---

## 5. Limits and responses

- Return `429` with `Retry-After` (seconds); keep the body inside the standard error envelope
  (`fastapi-error-handling.md`). Executed: fourth call 429, `Retry-After` between 1 and 60 for a
  per-minute limit; removing the header turned the test red.
- Starting points: login 5 failures / 15 minutes per (email, client) plus 20/minute per IP, register
  3/hour per IP, password reset 3/hour per email, general reads 100–200/minute per user. Tune from
  measured traffic; these are not security guarantees.
- Responses may carry the rate-limit headers described in `rest-design-principles.md`.

## 6. Edge limiting (optional, platform-specific)

If your platform offers an edge/WAF policy (a cloud load balancer rule, a CDN), set a coarse
per-client baseline and tighter limits on auth paths there as an **additional** layer. The
application limiter above remains the control that knows the user id.

---

## Checklist

```
□ One constant scope per abuse surface; never keyed on the concrete URL of a route with path parameters
□ Enumeration and spend limits use a key that depends on the auth dependency (never request.state set "later")
□ Login counts failures per (email, client), never a per-email lockout; per-IP only as an outer layer
□ FORWARDED_ALLOW_IPS unset (loopback default) or a verified proxy range, boot fails on "*"; client_ip_key refuses non-global addresses in staging/production and the post-deploy wrong-password smoke login answers 401
□ async+redis:// (or another shared async store) wired in deployment, and a test asserts it
□ No synchronous limiter storage calls inside async handlers (SlowAPI does this)
□ 429 carries Retry-After; store-down behaviour (503 or fail-open + alert) decided per route
```
