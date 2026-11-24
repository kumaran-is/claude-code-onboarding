"""MOCKED PROVIDER tests of litellm 1.110.2 Router fallback behaviour (mock_response deployments; no network).

Asserts the failover settings documented in agentic-llm-routing.md §8: failover only on availability errors,
same tier only, and never on 400 / content-policy / context-window errors.
Run from this directory: uv run --locked pytest -q   (litellm==1.110.2 pinned in pyproject.toml + uv.lock)
"""

import asyncio

import pytest
from litellm import Router
from litellm.types.router import RetryPolicy

GROUP, EQUIV, FAST = "cap.standard", "cap.standard-b", "cap.fast"


class Status400(Exception):
    status_code = 400
    text = "unsupported parameter"


def dep(name: str, model: str, mock: object) -> dict:
    return {"model_name": name,
            "litellm_params": {"model": model, "api_key": "sk-fake-not-a-secret", "mock_response": mock}}


def msr_router(primary_mock: object, **overrides: object) -> Router:
    """The settings agentic-llm-routing.md §8 prescribes; overrides let a test remove one control."""
    kwargs: dict = dict(
        fallbacks=[{GROUP: [EQUIV]}],                       # same-tier approved equivalent only
        content_policy_fallbacks=[{GROUP: []}],             # explicit empty: never fail over on a refusal
        context_window_fallbacks=[{GROUP: []}],             # explicit empty: context size is a routing floor
        fallback_on_unsupported_params=False,               # a provider 400 never fails over
        num_retries=0,
        retry_policy=RetryPolicy(BadRequestErrorRetries=0, AuthenticationErrorRetries=0,
                                 ContentPolicyViolationErrorRetries=0),
        enable_pre_call_checks=True,
    )
    kwargs.update(overrides)
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    return Router(model_list=[dep(GROUP, "openai/a", primary_mock), dep(EQUIV, "openai/b", "served-by-b"),
                              dep(FAST, "openai/f", "served-by-fast")], **kwargs)


def call(router: Router, **request: object) -> str:
    async def go() -> str:
        resp = await router.acompletion(model=GROUP, messages=[{"role": "user", "content": "x"}], **request)
        return resp.choices[0].message.content
    return asyncio.run(go())


def test_availability_error_fails_over_same_tier():
    assert call(msr_router("litellm.InternalServerError")) == "served-by-b"


def test_bad_request_is_not_failed_over():
    with pytest.raises(Exception) as exc:
        call(msr_router(Status400("unsupported parameter")))
    assert getattr(exc.value, "status_code", None) == 400


def test_default_flag_fails_over_on_bad_request_negative_control():
    """Documents WHY fallback_on_unsupported_params=False is required: the default fails over on a 400."""
    assert call(msr_router(Status400("unsupported parameter"), fallback_on_unsupported_params=True)) == "served-by-b"


def test_context_window_error_is_not_failed_over():
    with pytest.raises(Exception) as exc:
        call(msr_router("litellm.ContextWindowExceededError"))
    assert type(exc.value).__name__ == "ContextWindowExceededError"


def test_unset_context_window_fallbacks_use_generic_fallbacks_negative_control():
    assert call(msr_router("litellm.ContextWindowExceededError", context_window_fallbacks=None)) == "served-by-b"


def test_content_policy_error_is_not_failed_over():
    with pytest.raises(Exception) as exc:
        call(msr_router("served-by-a"), mock_testing_content_policy_fallbacks=True)
    assert type(exc.value).__name__ == "ContentPolicyViolationError"


def test_unset_content_policy_fallbacks_use_generic_fallbacks_negative_control():
    router = msr_router("served-by-a", content_policy_fallbacks=None)
    assert call(router, mock_testing_content_policy_fallbacks=True) == "served-by-b"


def test_fallback_access_check_blocks_unapproved_target():
    async def deny(*, model: str, request_kwargs: object, ctx: object) -> bool:
        return model != EQUIV                                 # EQUIV not approved for this data class

    with pytest.raises(Exception) as exc:
        call(msr_router("litellm.InternalServerError", fallback_access_check=deny))
    assert getattr(exc.value, "status_code", None) == 500


def test_default_fallbacks_cross_tiers_negative_control():
    """Documents WHY default_fallbacks is rejected: it reaches the FAST group."""
    router = msr_router("litellm.InternalServerError", fallbacks=None, default_fallbacks=[FAST])
    assert call(router) == "served-by-fast"
