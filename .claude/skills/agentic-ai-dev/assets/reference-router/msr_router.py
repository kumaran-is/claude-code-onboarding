"""Reference model router for agentic-ai-dev/reference/agentic-llm-routing.md (provider-neutral; stdlib + pydantic).

Pipeline: egress authorization -> policy gate -> tier -> approved-config resolution -> execution -> verification ->
quality escalation (higher tier) | provider failover (same-tier approved equivalent).
Egress authorization implements .claude/skills/ai-playbook/reference/data-governance-privacy.md (DGP section 4) and §6 step 4: permission to read
data is not permission to send it to a provider.
Providers are injected callables; tests use fakes (MOCKED PROVIDER).
Run from this directory: uv run --locked pytest -q   (pins in pyproject.toml + uv.lock)
"""

import asyncio
import enum
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

TIERS = ("FAST", "STANDARD", "STRONG")
DATA_CLASSES = ("public", "internal", "confidential", "restricted", "regulated")  # registry ceiling; regulated also needs its egress approval line
LIVE_STATES = frozenset({"deployed"})
ALIAS = re.compile(r"(^|[-_.@:])(latest|default|preview|exp|experimental)($|[-_.@:])", re.IGNORECASE)


class Reason(enum.StrEnum):
    """Closed, versioned reason-code enum (agentic-llm-routing.md §17)."""

    STATIC_ROUTE = "STATIC_ROUTE"
    SAFETY_OVERRIDE = "SAFETY_OVERRIDE"
    MULTIMODAL_MINIMUM = "MULTIMODAL_MINIMUM"
    LONG_CONTEXT_MINIMUM = "LONG_CONTEXT_MINIMUM"
    FORCED_TIER = "FORCED_TIER"
    ROUTER_TIMEOUT = "ROUTER_TIMEOUT"
    ROUTER_INVALID = "ROUTER_INVALID"
    ROUTER_UNAVAILABLE = "ROUTER_UNAVAILABLE"
    ROUTER_MODEL = "ROUTER_MODEL"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    VERIFIER_TIMEOUT = "VERIFIER_TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    NO_APPROVED_EQUIVALENT = "NO_APPROVED_EQUIVALENT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    FINAL_TIER_FAILED = "FINAL_TIER_FAILED"
    EGRESS_POLICY_BLOCK = "EGRESS_POLICY_BLOCK"


ROUTING_POLICY_VERSION = "2026-11-24.1"


class RegistryError(ValueError):
    """A registry entry violates a hard rule; the registry refuses to load."""


class ProviderUnavailable(Exception):
    """Availability error only (timeout, 5xx, short-retry 429). Triggers failover, never escalation."""


@dataclass(frozen=True)
class ModelConfig:
    config_id: str
    provider: str
    model_id: str
    pinned_version: str
    tier: str
    capabilities_approved: frozenset[str]
    allowed_data_class: str
    regions: frozenset[str]
    modalities: frozenset[str]
    state: str
    safety_eval_run_id: str


@dataclass(frozen=True)
class PolicySignals:
    safety_risk: str = "low"
    privacy_risk: str = "low"
    legal_risk: str = "low"
    financial_authority_required: bool = False
    irreversibility: str = "low"
    requires_human_approval: bool = False


@dataclass(frozen=True)
class RouteRequest:
    request_id: str
    capability: str
    data_class: str
    region: str
    modalities: frozenset[str]
    context_tokens: int
    signals: PolicySignals = PolicySignals()


@dataclass
class Overrides:
    """Runtime flags (agentic-llm-routing.md §9): take effect without a deploy."""

    suspended_configs: set[str] = field(default_factory=set)
    suspended_providers: set[str] = field(default_factory=set)
    force_tier: str | None = None
    cascade_enabled: bool = True
    failover_enabled: bool = True


@dataclass
class Budget:
    """One budget for the whole request tree: attempts and cost (agentic-llm-routing.md §12, §16)."""

    max_attempts: int
    max_cost: float
    attempts: int = 0
    cost: float = 0.0

    def charge(self, cost: float) -> None:
        self.attempts += 1
        self.cost += cost

    def exhausted(self) -> bool:
        return self.attempts >= self.max_attempts or self.cost >= self.max_cost


# ---------------------------------------------------------------- egress authorization (DGP §3, §4, §6)

EGRESS_CLASSES = frozenset({"public", "internal", "confidential", "restricted", "regulated"})
# §4 matrix: the most a provider type can ever be approved for. Restricted and regulated also need their own
# approval line (security sign-off; Legal/Privacy approval), recorded as a class in ProviderApproval.approved_classes.
PROVIDER_TYPE_CEILING = {
    "self_hosted": EGRESS_CLASSES,
    "approved_cloud": EGRESS_CLASSES,
    "third_party": frozenset({"public", "internal"}),
}
REDACTION_OPTIONAL_CLASSES = frozenset({"public", "internal"})


class EgressBlock(enum.StrEnum):
    """Why an egress was blocked. Blocked means no provider call, never logged-and-allowed (DGP §4, §6.2)."""

    SECRET_DETECTED = "SECRET_DETECTED"
    PROHIBITED_CLASS = "PROHIBITED_CLASS"
    CLASS_NOT_DECLARED = "CLASS_NOT_DECLARED"
    PURPOSE_NOT_DECLARED = "PURPOSE_NOT_DECLARED"
    REGION_NOT_ALLOWED = "REGION_NOT_ALLOWED"
    REDACTION_UNAVAILABLE = "REDACTION_UNAVAILABLE"
    PROVIDER_NOT_DECLARED = "PROVIDER_NOT_DECLARED"
    PROVIDER_NOT_APPROVED = "PROVIDER_NOT_APPROVED"
    PROVIDER_CLASS = "PROVIDER_CLASS"
    PROVIDER_REGION = "PROVIDER_REGION"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"


@dataclass(frozen=True)
class EgressDeclaration:
    """Capability egress declaration, version-controlled config (DGP §6.1)."""

    capability: str
    purposes: frozenset[str]
    allowed_data_classes: frozenset[str]
    prohibited_data_classes: frozenset[str]
    approved_providers: frozenset[str]
    allowed_regions: frozenset[str]
    redaction_optional: bool = False   # §6.2: Public/Internal may proceed without redaction only when declared


@dataclass(frozen=True)
class EgressTags:
    """Result of classify -> minimize -> redact for one request (DGP §6 steps 1-3). Tags only, no payload."""

    data_classes: frozenset[str]       # per field/chunk; empty or unknown tags count as confidential (§3, §6.2)
    purposes: frozenset[str]
    secrets_found: int
    redaction_ok: bool


@dataclass(frozen=True)
class ProviderApproval:
    """One provider approval line (DGP §5): provider and service tier, classes, regions, terms, re-review date."""

    provider: str
    provider_type: Literal["self_hosted", "approved_cloud", "third_party"]
    approved_classes: frozenset[str]
    regions: frozenset[str]
    training_use: Literal["none", "opt_out_contracted", "allowed"]
    review_due: date


@dataclass(frozen=True)
class EgressPolicy:
    declaration: EgressDeclaration
    tags: EgressTags
    approvals: Mapping[str, ProviderApproval]   # keyed by ModelConfig.provider
    today: date


def effective_classes(tags: EgressTags) -> frozenset[str]:
    known = tags.data_classes & EGRESS_CLASSES
    if not tags.data_classes or known != tags.data_classes:
        return known | {"confidential"}            # unclassified or unknown -> Confidential
    return known


def request_egress_blocks(policy: EgressPolicy, region: str) -> list[EgressBlock]:
    """DGP §6 step 4, request side: classes, purposes, region, secrets, redaction. Deterministic, no model call."""
    decl, tags = policy.declaration, policy.tags
    classes = effective_classes(tags)
    blocks = []
    if tags.secrets_found:
        blocks.append(EgressBlock.SECRET_DETECTED)
    if classes & decl.prohibited_data_classes:
        blocks.append(EgressBlock.PROHIBITED_CLASS)
    if not classes <= decl.allowed_data_classes:
        blocks.append(EgressBlock.CLASS_NOT_DECLARED)
    if not tags.purposes or not tags.purposes <= decl.purposes:
        blocks.append(EgressBlock.PURPOSE_NOT_DECLARED)
    if region not in decl.allowed_regions:
        blocks.append(EgressBlock.REGION_NOT_ALLOWED)
    if not tags.redaction_ok and not (decl.redaction_optional and classes <= REDACTION_OPTIONAL_CLASSES):
        blocks.append(EgressBlock.REDACTION_UNAVAILABLE)
    return blocks


def provider_egress_blocks(policy: EgressPolicy, cfg: ModelConfig, region: str) -> list[EgressBlock]:
    """DGP §4 + §5, provider side: classes ⊆ provider approval within its type's ceiling, region, re-review date."""
    if cfg.provider not in policy.declaration.approved_providers:
        return [EgressBlock.PROVIDER_NOT_DECLARED]
    approval = policy.approvals.get(cfg.provider)
    if approval is None:
        return [EgressBlock.PROVIDER_NOT_APPROVED]
    blocks = []
    if policy.today > approval.review_due:
        blocks.append(EgressBlock.APPROVAL_EXPIRED)
    allowed = approval.approved_classes & PROVIDER_TYPE_CEILING[approval.provider_type]
    if approval.training_use == "allowed":
        allowed &= {"public"}                      # §5: provider may train -> public data only
    if not effective_classes(policy.tags) <= allowed:
        blocks.append(EgressBlock.PROVIDER_CLASS)
    if region not in approval.regions:
        blocks.append(EgressBlock.PROVIDER_REGION)
    return blocks


class Registry:
    """Approved-model registry; routing chooses only among `deployed` entries (G20)."""

    def __init__(self, entries: list[ModelConfig]) -> None:
        for e in entries:
            if ALIAS.search(e.pinned_version) or ALIAS.search(e.model_id):
                raise RegistryError(f"{e.config_id}: alias or floating version '{e.model_id}@{e.pinned_version}'")
            if e.tier not in TIERS or e.allowed_data_class not in DATA_CLASSES:
                raise RegistryError(f"{e.config_id}: unknown tier or data class")
            if e.state in LIVE_STATES and not (e.capabilities_approved and e.safety_eval_run_id):
                raise RegistryError(f"{e.config_id}: deployed without capability approval or safety eval")
        ids = [e.config_id for e in entries]
        if len(ids) != len(set(ids)):
            raise RegistryError("duplicate config_id")
        self._entries = tuple(entries)

    def candidates(self, tier: str, req: RouteRequest, ov: Overrides,
                   egress: EgressPolicy) -> list[ModelConfig]:
        """Policy-valid configs for this tier. Every filter is a hard constraint, never a weight.
        Failover and escalation stay within providers approved for the request's classes and region
        (DGP §4: otherwise the fallback is the non-AI path). No egress policy, no candidates (fail closed)."""
        if not isinstance(egress, EgressPolicy):
            raise TypeError("candidates requires an EgressPolicy; refusing to list providers without one")
        return [
            e for e in self._entries
            if e.tier == tier
            and e.state in LIVE_STATES
            and req.capability in e.capabilities_approved
            and DATA_CLASSES.index(req.data_class) <= DATA_CLASSES.index(e.allowed_data_class)
            and req.region in e.regions
            and req.modalities <= e.modalities
            and e.config_id not in ov.suspended_configs
            and e.provider not in ov.suspended_providers
            and not provider_egress_blocks(egress, e, req.region)
        ]


@dataclass(frozen=True)
class GateResult:
    minimum_tier: str
    allow_cascade: bool
    reasons: tuple[Reason, ...]


def policy_gate(req: RouteRequest, *, long_context_threshold: int, high_impact: frozenset[str]) -> GateResult:
    """Deterministic floors from separate policy signals (agentic-llm-routing.md §3, §12). No model call."""
    tier, reasons, cascade = "FAST", [], True
    s = req.signals
    if s.safety_risk == "high" or s.irreversibility == "high" or s.financial_authority_required \
            or req.capability in high_impact:
        tier, cascade = "STRONG", False
        reasons.append(Reason.SAFETY_OVERRIDE)
    if req.modalities & {"image", "video"} and TIERS.index(tier) < 1:
        tier = "STANDARD"
        reasons.append(Reason.MULTIMODAL_MINIMUM)
    if req.context_tokens >= long_context_threshold and TIERS.index(tier) < 1:
        tier = "STANDARD"
        reasons.append(Reason.LONG_CONTEXT_MINIMUM)
    return GateResult(tier, cascade, tuple(reasons) or (Reason.STATIC_ROUTE,))


@dataclass
class Decision:
    """Router decision record (agentic-llm-routing.md §17) plus attempt trail (§17). Never shown to end users."""

    request_id: str
    capability: str
    policy_signals: PolicySignals
    minimum_tier: str
    selected_tier: str
    allow_cascade: bool
    resolved_config_id: str | None = None
    reason_codes: list[Reason] = field(default_factory=list)
    attempts: list[dict[str, object]] = field(default_factory=list)
    outcome: str = "PENDING"
    egress_blocks: list[EgressBlock] = field(default_factory=list)
    routing_policy_version: str = ROUTING_POLICY_VERSION


# A provider call receives the config and the operation id it must reuse for any side effect.
Provider = Callable[[ModelConfig, str], tuple[str, float]]
# A verifier returns PASS | ESCALATE | HUMAN_REVIEW | FAIL | INSUFFICIENT; raising TimeoutError = unavailable.
Verifier = Callable[[str], str]


def route_and_execute(
    req: RouteRequest,
    registry: Registry,
    providers: Mapping[str, Provider],
    verifier: Verifier,
    budget: Budget,
    *,
    operation_id: str,
    static_tier: str,
    overrides: Overrides,
    long_context_threshold: int = 100_000,
    high_impact: frozenset[str] = frozenset(),
    egress: EgressPolicy,
) -> tuple[str | None, Decision]:
    # Read permission is not send permission: no egress policy means no provider call (fail closed, DGP §6.2).
    if not isinstance(egress, EgressPolicy):
        raise TypeError("route_and_execute requires an EgressPolicy; refusing to call a provider without one")
    gate = policy_gate(req, long_context_threshold=long_context_threshold, high_impact=high_impact)
    tier = max(static_tier, gate.minimum_tier, key=TIERS.index)       # never below the policy floor
    reasons = list(gate.reasons)
    if overrides.force_tier is not None:
        tier = max(overrides.force_tier, gate.minimum_tier, key=TIERS.index)
        reasons.append(Reason.FORCED_TIER)
    cascade = gate.allow_cascade and overrides.cascade_enabled
    d = Decision(req.request_id, req.capability, req.signals, gate.minimum_tier, tier, cascade, reason_codes=reasons)
    d.egress_blocks = request_egress_blocks(egress, req.region)
    if d.egress_blocks:                                # blocked before any provider is considered (DGP §6.2)
        d.reason_codes.append(Reason.EGRESS_POLICY_BLOCK)
        d.outcome = "EGRESS_BLOCKED"
        return None, d

    while True:
        output = None
        for cfg in registry.candidates(tier, req, overrides, egress):
            if budget.exhausted():
                d.reason_codes.append(Reason.BUDGET_EXHAUSTED)
                d.outcome = "DEGRADED_BUDGET"            # visible degraded outcome; never a cheaper model
                return None, d
            started = time.monotonic()
            try:
                output, cost = providers[cfg.provider](cfg, operation_id)
            except ProviderUnavailable:
                budget.charge(0.0)
                d.attempts.append({"config_id": cfg.config_id, "tier": tier, "result": "UNAVAILABLE"})
                d.reason_codes.append(Reason.PROVIDER_UNAVAILABLE)
                if not overrides.failover_enabled:
                    break
                continue                                   # failover: next approved SAME-tier equivalent
            budget.charge(cost)
            d.resolved_config_id = cfg.config_id
            d.attempts.append({"config_id": cfg.config_id, "tier": tier, "cost": cost,
                               "latency_ms": round((time.monotonic() - started) * 1000, 3)})
            break
        if output is None:
            # No approved same-tier config answered: documented conservative fallback = a HIGHER
            # approved tier, else the non-AI path. Never a lower or unapproved config (agentic-llm-routing.md §12).
            d.reason_codes.append(Reason.NO_APPROVED_EQUIVALENT)
            nxt = _next_tier(tier)
            if nxt is None or not overrides.failover_enabled:
                d.outcome = "NON_AI_FALLBACK"
                return None, d
            tier = d.selected_tier = nxt
            continue
        try:
            verdict = verifier(output)
        except TimeoutError:
            verdict = "INSUFFICIENT"                       # an unavailable verifier is never PASS
            d.reason_codes.append(Reason.VERIFIER_TIMEOUT)
        d.attempts[-1]["verification"] = verdict
        if verdict == "PASS":
            d.outcome = "PASS"
            return output, d
        if verdict in ("HUMAN_REVIEW", "FAIL"):
            d.outcome = verdict
            return None, d
        d.reason_codes.append(Reason.SCHEMA_VALIDATION_FAILED if verdict == "ESCALATE"
                              else Reason.INSUFFICIENT_EVIDENCE)
        nxt = _next_tier(tier)
        if nxt is None or not cascade:
            d.reason_codes.append(Reason.FINAL_TIER_FAILED)
            d.outcome = "HUMAN_REVIEW"
            return None, d
        tier = d.selected_tier = nxt                       # quality escalation; same operation_id reused


def _next_tier(tier: str) -> str | None:
    i = TIERS.index(tier)
    return TIERS[i + 1] if i + 1 < len(TIERS) else None


# ---------------------------------------------------------------- optional LLM tier classifier (agentic-llm-routing.md §7)


class RouteLabel(BaseModel):
    tier: Literal["FAST", "STANDARD", "STRONG"]


@dataclass(frozen=True)
class RouteFeatures:
    """Sanitized features only; never the raw user message (agentic-llm-routing.md §17)."""

    capability: str
    has_images: bool
    size_bucket: Literal["s", "m", "l"]


def max_tier(a: str, b: str) -> str:
    return max(a, b, key=TIERS.index)


async def classify_tier(f: RouteFeatures, classifier: Any, timeout_s: float, floor: str,
                        transient: tuple[type[Exception], ...]) -> tuple[str, Reason]:
    try:
        async with asyncio.timeout(timeout_s):
            raw = await classifier.ainvoke(f"capability={f.capability} size={f.size_bucket} images={f.has_images}")
        label = RouteLabel.model_validate(raw)
    except TimeoutError:
        return max_tier("STANDARD", floor), Reason.ROUTER_TIMEOUT
    except ValidationError:
        return max_tier("STANDARD", floor), Reason.ROUTER_INVALID
    except transient:
        return max_tier("STANDARD", floor), Reason.ROUTER_UNAVAILABLE
    return max_tier(label.tier, floor), Reason.ROUTER_MODEL
