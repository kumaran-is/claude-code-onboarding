"""MOCKED PROVIDER tests for msr_router (stdlib unittest; no network, no SDK)."""

import asyncio
import json
import unittest
from dataclasses import asdict, replace

from datetime import date

from msr_router import (
    Budget, EgressBlock, EgressDeclaration, EgressPolicy, EgressTags, ModelConfig, Overrides, PolicySignals,
    ProviderApproval, ProviderUnavailable, Reason, Registry, RegistryError, RouteFeatures, RouteRequest,
    classify_tier, route_and_execute,
)

CAP = "invoice_extraction"


def cfg(config_id, provider, tier, *, caps=(CAP,), data="confidential", state="deployed", version="2026-10-01",
        mods=("text",), safety="redteam-run-17"):
    return ModelConfig(config_id, provider, f"{provider}-model-{tier.lower()}", version, tier, frozenset(caps), data,
                       frozenset({"eu"}), frozenset(mods), state, safety)


BASE = [
    cfg("fast-a", "prov_a", "FAST"),
    cfg("std-a", "prov_a", "STANDARD", mods=("text", "image")),
    cfg("std-b", "prov_b", "STANDARD", mods=("text", "image")),
    cfg("strong-a", "prov_a", "STRONG", mods=("text", "image")),
]


def req(**kw):
    base = dict(request_id="r1", capability=CAP, data_class="confidential", region="eu",
                modalities=frozenset({"text"}), context_tokens=2_000)
    base.update(kw)
    return RouteRequest(**base)


class DraftStore:
    """Side-effect target: create-if-absent keyed by operation id (idempotent escalation, agentic-llm-routing.md §12)."""

    def __init__(self):
        self.drafts = {}
        self.create_calls = 0

    def create(self, operation_id, body):
        self.create_calls += 1
        return self.drafts.setdefault(operation_id, body)


def providers(store, down=()):
    def make(name):
        def call(c, operation_id):
            if name in down:
                raise ProviderUnavailable(name)
            store.create(operation_id, f"draft by {c.config_id}")
            return f"out:{c.config_id}", {"FAST": 0.1, "STANDARD": 1.0, "STRONG": 5.0}[c.tier]
        return call
    return {"prov_a": make("prov_a"), "prov_b": make("prov_b"), "prov_c": make("prov_c")}


def run(registry=None, *, request=None, verifier=lambda o: "PASS", budget=None, static_tier="FAST",
        ov=None, down=(), high_impact=frozenset(), egress=None):
    store = DraftStore()
    out, d = route_and_execute(
        request or req(), registry or Registry(BASE), providers(store, down), verifier,
        budget or Budget(max_attempts=6, max_cost=50.0), operation_id="op-1", static_tier=static_tier,
        overrides=ov or Overrides(), high_impact=high_impact,
        egress=egress if egress is not None else routing_test_egress())
    return out, d, store


class RegistryRules(unittest.TestCase):
    def test_alias_versions_rejected(self):
        for bad in ("latest", "default", "2026-10-01-preview", "exp-1"):
            with self.subTest(bad=bad), self.assertRaises(RegistryError):
                Registry([cfg("x", "prov_a", "FAST", version=bad)])

    def test_deployed_without_safety_eval_rejected(self):
        with self.assertRaises(RegistryError):
            Registry([cfg("x", "prov_a", "FAST", safety="")])

    def test_duplicate_config_id_rejected(self):
        with self.assertRaises(RegistryError):
            Registry([cfg("x", "prov_a", "FAST"), cfg("x", "prov_b", "FAST")])


class PolicyAndResolution(unittest.TestCase):
    def test_static_fast_route(self):
        out, d, _ = run()
        self.assertEqual((out, d.selected_tier, d.reason_codes), ("out:fast-a", "FAST", [Reason.STATIC_ROUTE]))

    def test_disallowed_models_never_selected(self):
        # data class too high, wrong region capability, non-deployed state: only std-ok is valid
        reg = Registry([
            cfg("fast-public-only", "prov_a", "FAST", data="internal"),
            cfg("fast-approved-state", "prov_a", "FAST", state="approved"),
            cfg("fast-other-cap", "prov_a", "FAST", caps=("chat",)),
            cfg("std-ok", "prov_b", "STANDARD"),
        ])
        out, d, _ = run(reg)
        self.assertEqual(d.resolved_config_id, "std-ok")
        self.assertIn(Reason.NO_APPROVED_EQUIVALENT, d.reason_codes)

    def test_multimodal_floor(self):
        out, d, _ = run(request=req(modalities=frozenset({"text", "image"})))
        self.assertEqual((d.minimum_tier, d.resolved_config_id), ("STANDARD", "std-a"))
        self.assertIn(Reason.MULTIMODAL_MINIMUM, d.reason_codes)

    def test_long_context_floor(self):
        _, d, _ = run(request=req(context_tokens=150_000))
        self.assertEqual(d.minimum_tier, "STANDARD")
        self.assertIn(Reason.LONG_CONTEXT_MINIMUM, d.reason_codes)

    def test_safety_floor_starts_strong_and_disables_cascade(self):
        _, d, _ = run(request=req(signals=PolicySignals(safety_risk="high")))
        self.assertEqual((d.selected_tier, d.allow_cascade), ("STRONG", False))
        self.assertIn(Reason.SAFETY_OVERRIDE, d.reason_codes)

    def test_force_tier_override_never_lowers_floor(self):
        _, d, _ = run(request=req(signals=PolicySignals(irreversibility="high")), ov=Overrides(force_tier="FAST"))
        self.assertEqual(d.selected_tier, "STRONG")


class EscalationAndFailover(unittest.TestCase):
    def test_escalation_reuses_operation_no_duplicate_side_effect(self):
        verdicts = iter(["ESCALATE", "PASS"])
        out, d, store = run(verifier=lambda o: next(verdicts))
        self.assertEqual((out, d.selected_tier), ("out:std-a", "STANDARD"))
        self.assertEqual(len(store.drafts), 1)                       # one draft, created by the first tier
        self.assertEqual(store.drafts["op-1"], "draft by fast-a")
        self.assertEqual(store.create_calls, 2)

    def test_no_cascade_on_high_impact_goes_to_human_review(self):
        _, d, _ = run(verifier=lambda o: "ESCALATE", high_impact=frozenset({CAP}))
        self.assertEqual((d.outcome, len(d.attempts)), ("HUMAN_REVIEW", 1))

    def test_cascade_disabled_flag_stops_escalation(self):
        _, d, _ = run(verifier=lambda o: "ESCALATE", ov=Overrides(cascade_enabled=False))
        self.assertEqual((d.outcome, [a["tier"] for a in d.attempts]), ("HUMAN_REVIEW", ["FAST"]))

    def test_verifier_timeout_is_never_pass(self):
        def boom(_):
            raise TimeoutError
        _, d, _ = run(verifier=boom, request=req(signals=PolicySignals(safety_risk="high")))
        self.assertEqual(d.attempts[0]["verification"], "INSUFFICIENT")
        self.assertEqual(d.outcome, "HUMAN_REVIEW")
        self.assertIn(Reason.VERIFIER_TIMEOUT, d.reason_codes)

    def test_outage_fails_over_same_tier_only(self):
        _, d, _ = run(static_tier="STANDARD", down=("prov_a",))
        self.assertEqual((d.resolved_config_id, d.selected_tier), ("std-b", "STANDARD"))
        self.assertIn(Reason.PROVIDER_UNAVAILABLE, d.reason_codes)

    def test_outage_never_uses_unverified_equivalent(self):
        reg = Registry(BASE + [cfg("std-c-unevaluated", "prov_c", "STANDARD", state="evaluating", safety="")])
        _, d, _ = run(reg, static_tier="STANDARD", down=("prov_a", "prov_b"))
        used = [a["config_id"] for a in d.attempts]
        self.assertNotIn("std-c-unevaluated", used)
        self.assertEqual(d.outcome, "NON_AI_FALLBACK")               # STRONG is also prov_a: down

    def test_outage_conservative_fallback_is_higher_tier_not_lower(self):
        _, d, _ = run(static_tier="STANDARD", down=("prov_b",),
                      ov=Overrides(suspended_configs={"std-a"}))
        self.assertEqual((d.resolved_config_id, d.selected_tier), ("strong-a", "STRONG"))
        self.assertNotIn("fast-a", [a["config_id"] for a in d.attempts])

    def test_outage_never_fails_over_to_provider_unapproved_for_data_class_or_region(self):
        extra = [cfg("std-c-internal-only", "prov_c", "STANDARD", data="internal"),
                 replace(cfg("std-c-us-only", "prov_c", "STANDARD"), regions=frozenset({"us"}))]
        reg = Registry(BASE + extra)
        _, d, _ = run(reg, static_tier="STANDARD", down=("prov_a", "prov_b"))
        self.assertEqual([a["config_id"] for a in d.attempts], ["std-a", "std-b", "strong-a"])
        self.assertEqual(d.outcome, "NON_AI_FALLBACK")
        # positive control: the same config is reachable when the request's data class allows it
        _, d_ok, _ = run(reg, request=req(data_class="internal"), static_tier="STANDARD", down=("prov_a", "prov_b"))
        self.assertEqual(d_ok.resolved_config_id, "std-c-internal-only")

    def test_high_risk_outage_never_downgrades_tier(self):
        _, d, _ = run(request=req(signals=PolicySignals(safety_risk="high")), down=("prov_a",))
        self.assertEqual(d.outcome, "NON_AI_FALLBACK")                # std-b (prov_b) is up but below the floor
        self.assertEqual({a["tier"] for a in d.attempts}, {"STRONG"})

    def test_suspended_provider_kill_switch(self):
        _, d, _ = run(static_tier="STANDARD", ov=Overrides(suspended_providers={"prov_a"}))
        self.assertEqual(d.resolved_config_id, "std-b")


class BudgetsRollbackTrace(unittest.TestCase):
    def test_budget_exhaustion_stops_and_never_downgrades(self):
        out, d, _ = run(static_tier="STRONG", verifier=lambda o: "ESCALATE",
                        budget=Budget(max_attempts=10, max_cost=4.0))
        self.assertIsNone(out)
        self.assertEqual(d.outcome, "HUMAN_REVIEW")                  # final tier failed; no cheaper retry
        _, d2, _ = run(verifier=lambda o: "ESCALATE", budget=Budget(max_attempts=1, max_cost=50.0))
        self.assertEqual((d2.outcome, d2.reason_codes[-1]), ("DEGRADED_BUDGET", Reason.BUDGET_EXHAUSTED))
        self.assertEqual([a["tier"] for a in d2.attempts], ["FAST"])

    def test_version_rollback_by_registry_config_only(self):
        v2 = [replace(BASE[0], config_id="fast-a-v2", pinned_version="2026-11-15")] + BASE[1:]
        _, d_new, _ = run(Registry(v2))
        rolled_back = [replace(v2[0], state="suspended")] + BASE        # suspend v2, incumbent kept warm
        _, d_old, _ = run(Registry(rolled_back))
        self.assertEqual((d_new.resolved_config_id, d_old.resolved_config_id), ("fast-a-v2", "fast-a"))

    def test_decision_trace_record_is_complete_and_serialisable(self):
        _, d, _ = run(request=req(modalities=frozenset({"text", "image"})))
        rec = json.loads(json.dumps(asdict(d), default=str))
        for key in ("request_id", "capability", "policy_signals", "minimum_tier", "selected_tier",
                    "resolved_config_id", "allow_cascade", "reason_codes", "routing_policy_version", "attempts"):
            self.assertIn(key, rec)
        self.assertNotIn("prompt", json.dumps(rec))                  # minimized: no raw content
        self.assertTrue(all(r in Reason.__members__ for r in rec["reason_codes"]))


TODAY = date(2026, 11, 24)
DECL = EgressDeclaration(CAP, purposes=frozenset({"service_delivery"}),
                         allowed_data_classes=frozenset({"public", "internal", "confidential"}),
                         prohibited_data_classes=frozenset({"restricted", "regulated"}),
                         approved_providers=frozenset({"prov_a", "prov_b"}), allowed_regions=frozenset({"eu"}))


def approval(provider, ptype="approved_cloud", classes=("public", "internal", "confidential"), regions=("eu",),
             training="none", review_due=date(2027, 6, 30)):
    return ProviderApproval(provider, ptype, frozenset(classes), frozenset(regions), training, review_due)


APPROVALS = {"prov_a": approval("prov_a"), "prov_b": approval("prov_b")}


def routing_test_egress():
    """Permissive policy for routing-only tests: every fixture provider approved in every fixture region."""
    regions = ("eu", "us")
    decl = replace(DECL, approved_providers=frozenset({"prov_a", "prov_b", "prov_c"}), allowed_regions=frozenset(regions))
    approvals = {p: approval(p, regions=regions) for p in ("prov_a", "prov_b", "prov_c")}
    return EgressPolicy(decl, EgressTags(frozenset({"confidential"}), frozenset({"service_delivery"}), 0, True),
                        approvals, TODAY)


def egress(classes=("confidential",), purposes=("service_delivery",), secrets=0, redaction_ok=True,
           decl=DECL, approvals=None):
    tags = EgressTags(frozenset(classes), frozenset(purposes), secrets, redaction_ok)
    return EgressPolicy(decl, tags, APPROVALS if approvals is None else approvals, TODAY)


class EgressAuthorization(unittest.TestCase):
    def test_missing_egress_policy_fails_closed_before_any_provider_call(self):
        store = DraftStore()
        for bad in (None, object()):
            with self.assertRaises(TypeError):
                route_and_execute(req(), Registry(BASE), providers(store), lambda o: "PASS",
                                  Budget(max_attempts=6, max_cost=50.0), operation_id="op-1", static_tier="FAST",
                                  overrides=Overrides(), egress=bad)
        with self.assertRaises(TypeError):              # omitting the argument is not an implicit allow
            route_and_execute(req(), Registry(BASE), providers(store), lambda o: "PASS",
                              Budget(max_attempts=6, max_cost=50.0), operation_id="op-1", static_tier="FAST",
                              overrides=Overrides())
        self.assertEqual(store.create_calls, 0)

    def test_candidate_listing_requires_egress_policy(self):
        for bad in (None, object()):                     # no unfiltered failover list without a policy
            with self.assertRaises(TypeError):
                Registry(BASE).candidates("FAST", req(), Overrides(), bad)
        self.assertTrue(Registry(BASE).candidates("FAST", req(), Overrides(), routing_test_egress()))

    """DGP §4 + §6: read permission is not send permission. Blocked = zero provider calls."""

    def assert_blocked(self, d, store, block):
        self.assertEqual((d.outcome, d.attempts, store.create_calls), ("EGRESS_BLOCKED", [], 0))
        self.assertIn(block, d.egress_blocks)
        self.assertIn(Reason.EGRESS_POLICY_BLOCK, d.reason_codes)

    def test_positive_declared_class_purpose_region_and_provider(self):
        out, d, store = run(egress=egress())
        self.assertEqual((out, d.outcome, d.egress_blocks, store.create_calls), ("out:fast-a", "PASS", [], 1))

    def test_request_level_blocks(self):
        cases = [
            ("secret detected", egress(secrets=1), EgressBlock.SECRET_DETECTED),
            ("prohibited class", egress(classes=("confidential", "restricted")), EgressBlock.PROHIBITED_CLASS),
            ("regulated never implied", egress(classes=("regulated",)), EgressBlock.CLASS_NOT_DECLARED),
            ("undeclared purpose", egress(purposes=("product_improvement",)), EgressBlock.PURPOSE_NOT_DECLARED),
            ("no purpose tag", egress(purposes=()), EgressBlock.PURPOSE_NOT_DECLARED),
            ("redaction down for confidential", egress(redaction_ok=False), EgressBlock.REDACTION_UNAVAILABLE),
        ]
        for label, policy, block in cases:
            with self.subTest(label):
                _, d, store = run(egress=policy)
                self.assert_blocked(d, store, block)

    def test_region_outside_declaration_is_blocked(self):
        reg = Registry([replace(c, regions=frozenset({"eu", "us"})) for c in BASE])
        _, d, store = run(reg, request=req(region="us"), egress=egress())
        self.assert_blocked(d, store, EgressBlock.REGION_NOT_ALLOWED)

    def test_redaction_outage_fails_closed_unless_public_internal_declared_optional(self):
        lenient = replace(DECL, redaction_optional=True)
        _, d, store = run(egress=egress(classes=("confidential",), redaction_ok=False, decl=lenient))
        self.assert_blocked(d, store, EgressBlock.REDACTION_UNAVAILABLE)
        out, d_ok, _ = run(egress=egress(classes=("internal",), redaction_ok=False, decl=lenient))
        self.assertEqual((out, d_ok.outcome), ("out:fast-a", "PASS"))

    def test_unknown_or_missing_classification_is_confidential(self):
        third_party_only = {"prov_a": approval("prov_a", "third_party", classes=("public", "internal")),
                            "prov_b": approval("prov_b", "third_party", classes=("public", "internal"))}
        for classes in (("unlabelled",), ()):
            with self.subTest(classes=classes):
                out, d, store = run(egress=egress(classes=classes, approvals=third_party_only))
                self.assertEqual((out, d.outcome, store.create_calls), (None, "NON_AI_FALLBACK", 0))
        out, d_ok, _ = run(egress=egress(classes=("internal",), approvals=third_party_only))
        self.assertEqual(out, "out:fast-a")                           # positive control: internal is allowed

    def test_third_party_api_never_receives_confidential_even_if_approval_lists_it(self):
        over_approved = {"prov_a": approval("prov_a", "third_party"), "prov_b": approval("prov_b", "third_party")}
        out, d, store = run(egress=egress(approvals=over_approved))
        self.assertEqual((out, d.outcome, store.create_calls), (None, "NON_AI_FALLBACK", 0))

    def test_provider_that_may_train_receives_public_only(self):
        trains = {"prov_a": approval("prov_a", training="allowed"), "prov_b": approval("prov_b", training="allowed")}
        _, d, store = run(egress=egress(classes=("internal",), approvals=trains))
        self.assertEqual((d.outcome, store.create_calls), ("NON_AI_FALLBACK", 0))
        out, _, _ = run(egress=egress(classes=("public",), approvals=trains))
        self.assertEqual(out, "out:fast-a")

    def test_expired_missing_or_undeclared_provider_approval_excludes_provider(self):
        cases = [
            ("approval past re-review date", {**APPROVALS, "prov_a": approval("prov_a", review_due=date(2026, 1, 1))}, DECL),
            ("no approval line", {"prov_b": APPROVALS["prov_b"]}, DECL),
            ("approval not for this region", {**APPROVALS, "prov_a": approval("prov_a", regions=("us",))}, DECL),
            ("not in capability declaration", APPROVALS, replace(DECL, approved_providers=frozenset({"prov_b"}))),
        ]
        for label, approvals, decl in cases:
            with self.subTest(label):
                _, d, _ = run(static_tier="STANDARD", egress=egress(approvals=approvals, decl=decl))
                self.assertEqual(d.resolved_config_id, "std-b")       # prov_a configs filtered out
                self.assertNotIn("std-a", [a["config_id"] for a in d.attempts])

    def test_regulated_needs_its_own_approval_line(self):
        decl = replace(DECL, allowed_data_classes=DECL.allowed_data_classes | {"regulated"},
                       prohibited_data_classes=frozenset({"restricted"}))
        _, d, store = run(egress=egress(classes=("regulated",), decl=decl))
        self.assertEqual((d.outcome, store.create_calls), ("NON_AI_FALLBACK", 0))
        approved = {**APPROVALS, "prov_a": approval("prov_a", classes=("public", "internal", "confidential", "regulated"))}
        out, _, _ = run(egress=egress(classes=("regulated",), decl=decl, approvals=approved))
        self.assertEqual(out, "out:fast-a")

    def test_regulated_request_needs_a_registry_config_declared_for_regulated(self):
        decl = replace(DECL, allowed_data_classes=DECL.allowed_data_classes | {"regulated"},
                       prohibited_data_classes=frozenset({"restricted"}))
        approved = {**APPROVALS, "prov_a": approval("prov_a", classes=("public", "internal", "confidential", "regulated"))}
        regulated = req(data_class="regulated")
        # negative: egress approved, but no registry config declares regulated -> no provider call
        _, d, store = run(request=regulated, egress=egress(classes=("regulated",), decl=decl, approvals=approved))
        self.assertEqual((d.outcome, store.create_calls), ("NON_AI_FALLBACK", 0))
        # positive: a config declared for regulated serves it
        reg = Registry(BASE + [cfg("fast-reg", "prov_a", "FAST", data="regulated")])
        out, d_ok, _ = run(reg, request=regulated, egress=egress(classes=("regulated",), decl=decl, approvals=approved))
        self.assertEqual((out, d_ok.resolved_config_id), ("out:fast-reg", "fast-reg"))

    def test_failover_only_to_providers_approved_for_the_same_classes(self):
        public_only_b = {**APPROVALS, "prov_b": approval("prov_b", classes=("public",))}
        out, d, _ = run(static_tier="STANDARD", down=("prov_a",), egress=egress(approvals=public_only_b))
        self.assertEqual((out, d.outcome), (None, "NON_AI_FALLBACK"))
        self.assertNotIn("std-b", [a["config_id"] for a in d.attempts])
        out_ok, _, _ = run(static_tier="STANDARD", down=("prov_a",), egress=egress())   # positive control
        self.assertEqual(out_ok, "out:std-b")

    def test_block_record_carries_codes_not_payload(self):
        _, d, _ = run(egress=egress(secrets=2))
        rec = json.loads(json.dumps(asdict(d), default=str))
        self.assertEqual(rec["egress_blocks"], ["SECRET_DETECTED"])
        self.assertTrue(all(r in Reason.__members__ for r in rec["reason_codes"]))


class FakeClassifier:
    def __init__(self, result=None, exc=None, delay=0.0):
        self.result, self.exc, self.delay, self.prompts = result, exc, delay, []

    async def ainvoke(self, prompt):
        self.prompts.append(prompt)
        await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return self.result


class TierClassifier(unittest.IsolatedAsyncioTestCase):
    F = RouteFeatures("faq", has_images=False, size_bucket="s")

    async def test_valid_label_respects_floor(self):
        self.assertEqual(await classify_tier(self.F, FakeClassifier({"tier": "FAST"}), 1, "FAST", (ConnectionError,)),
                         ("FAST", Reason.ROUTER_MODEL))
        self.assertEqual(await classify_tier(self.F, FakeClassifier({"tier": "FAST"}), 1, "STRONG", (ConnectionError,)),
                         ("STRONG", Reason.ROUTER_MODEL))

    async def test_timeout_invalid_unavailable_over_route(self):
        cases = [(FakeClassifier({"tier": "FAST"}, delay=0.2), Reason.ROUTER_TIMEOUT),
                 (FakeClassifier({"tier": "TURBO"}), Reason.ROUTER_INVALID),
                 (FakeClassifier(exc=ConnectionError()), Reason.ROUTER_UNAVAILABLE)]
        for clf, reason in cases:
            with self.subTest(reason=reason):
                self.assertEqual(await classify_tier(self.F, clf, 0.05, "FAST", (ConnectionError,)),
                                 ("STANDARD", reason))

    async def test_non_transient_error_is_loud(self):
        with self.assertRaises(PermissionError):
            await classify_tier(self.F, FakeClassifier(exc=PermissionError()), 1, "FAST", (ConnectionError,))

    async def test_prompt_is_features_only(self):
        clf = FakeClassifier({"tier": "FAST"})
        await classify_tier(self.F, clf, 1, "FAST", (ConnectionError,))
        self.assertEqual(clf.prompts, ["capability=faq size=s images=False"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
