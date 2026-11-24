"""Deterministic AI security controls for the AC-01..AC-18 fixture (security-reviewer/reference/ai-threat-model-attack-classes.md §3.2, §4, §10).

The model is a MOCKED, fully steerable fake: it obeys any instruction found anywhere in its input (principle P3,
"assume the model will eventually be steered"). Every test therefore proves that the deterministic control, not
the model, stops the attack. Each control can be disabled with DISABLE_CONTROL=<name> to run a negative control.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

import jsonschema

logger = logging.getLogger("ai_security_fixture")


def enabled(name: str) -> bool:
    disabled = {x.strip() for x in os.environ.get("DISABLE_CONTROL", "").split(",") if x.strip()}
    return name not in disabled


class Forbidden(Exception):
    """Deterministic denial. Carries the reason that goes to the audit log."""


# ---------------------------------------------------------------- caller context and data
@dataclass(frozen=True)
class Caller:
    user_id: str
    scope_id: str            # tenant / org, derived ONLY from the verified token
    role: str                # "customer" | "agent_readonly" | "operator"


ORDERS = {
    "A-1001": {"scope_id": "org_a", "status": "shipped", "email": "alice@example.test", "card_last4": "4242"},
    "B-2001": {"scope_id": "org_b", "status": "open", "email": "bob@example.test", "card_last4": "1111"},
}
CORPUS = [  # chunk text, scope, provenance
    {"id": "kb-a-1", "scope_id": "org_a", "text": "Return window is 30 days.", "provenance": "reviewed"},
    {"id": "kb-b-1", "scope_id": "org_b", "text": "org_b private pricing sheet B-2001", "provenance": "reviewed"},
]
SYSTEM_PROMPT_CANARY = "CANARY-7f3a91"
SYSTEM_PROMPT = f"You are a support assistant. [{SYSTEM_PROMPT_CANARY}] Answer only from provided context."

ALLOWED_TRANSITIONS = {"open": {"cancelled", "shipped"}, "shipped": {"returned"}}
BATCH_LIMIT = 10
INPUT_CHAR_CAP = 4000
MAX_TOOL_CALLS = 5
MAX_OUTPUT_TOKENS = 512
PER_KEY_QUOTA = 100
OUTBOUND_HOST_ALLOWLIST = {"cdn.example.test"}
APPROVED_MODELS = {"fixture-standard": "sha256:" + hashlib.sha256(b"fixture-standard-v1").hexdigest()}
APPROVED_TOOL_SERVERS = {"orders-mcp": "1.4.2"}

INJECTION_MARKERS = re.compile(r"ignore (all |previous )?instructions|SYSTEM:|call [a-z_]+\(", re.I)
SECRET_PATTERNS = [re.compile(p) for p in (r"sk-[A-Za-z0-9]{20,}", r"AKIA[0-9A-Z]{16}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
                                            r"postgres(ql)?://[^\s:]+:[^\s@]+@")]
PII_PATTERNS = [re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}")]


# ---------------------------------------------------------------- audit + metrics
@dataclass
class Telemetry:
    audit: list[dict[str, Any]] = field(default_factory=list)
    isolation_violations_total: int = 0
    canary_hits_total: int = 0
    quota_used: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------- tool layer (AC-01/04/07/08/09/12/15)
TOOL_SURFACE = {
    "get_order": {"description": "Read one order in the caller's scope.", "schema": {"order_id": "str"}, "write": False},
    "set_order_status": {"description": "Change an order status.", "schema": {"order_id": "str", "status": "str"}, "write": True},
    "notify_customers": {"description": "Email customers of listed orders.", "schema": {"order_ids": "list[str]"}, "write": True},
}


def surface_hash(surface: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(surface, sort_keys=True).encode()).hexdigest()


LOCKED_SURFACE_HASH = surface_hash(TOOL_SURFACE)      # committed value in a real repo (eval §10.2)

ROLE_TOOLSETS = {"agent_readonly": {"get_order"}, "customer": {"get_order"}, "operator": set(TOOL_SURFACE)}


def payload_hash(tool: str, args: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps({"tool": tool, "args": args}, sort_keys=True).encode()).hexdigest()


class ToolRuntime:
    def __init__(self, caller: Caller, telemetry: Telemetry, surface: dict[str, Any] | None = None):
        self.caller = caller
        self.t = telemetry
        self.surface = surface if surface is not None else TOOL_SURFACE
        self.calls = 0

    def check_surface(self) -> None:
        if enabled("surface_lock") and surface_hash(self.surface) != LOCKED_SURFACE_HASH:
            raise Forbidden("tool surface drift: re-review required")

    def call(self, tool: str, args: dict[str, Any], *, origin: str = "planner",
             confirmation_hash: str | None = None) -> dict[str, Any]:
        self.check_surface()
        if enabled("quarantine") and origin != "planner":
            raise Forbidden(f"tool call originated from {origin} content")
        if enabled("least_privilege") and tool not in ROLE_TOOLSETS.get(self.caller.role, set()):
            raise Forbidden(f"role {self.caller.role} has no tool {tool}")
        self.calls += 1
        if enabled("budget") and self.calls > MAX_TOOL_CALLS:
            raise Forbidden("tool-call budget exhausted")
        spec = self.surface[tool]
        if enabled("strict_schema") and set(args) != set(spec["schema"]):
            raise Forbidden(f"unexpected or missing args for {tool}")
        if spec["write"]:
            if enabled("confirmation") and confirmation_hash != payload_hash(tool, args):
                raise Forbidden("consequential action needs confirmation bound to the payload hash")
            result = getattr(self, f"_{tool}")(**args)
            if enabled("audit"):
                self.t.audit.append({"tool": tool, "args_hash": payload_hash(tool, args), "user": self.caller.user_id,
                                     "scope": self.caller.scope_id})
            return result
        return getattr(self, f"_{tool}")(**args)

    def _owned(self, order_id: str) -> dict[str, Any]:
        order = ORDERS.get(order_id)
        if order is None:
            raise Forbidden("not found")              # same answer as cross-scope: no existence oracle
        if enabled("caller_bound_scope") and order["scope_id"] != self.caller.scope_id:
            raise Forbidden("not found")
        if order["scope_id"] != self.caller.scope_id:
            self.t.isolation_violations_total += 1
        return order

    def _get_order(self, order_id: str) -> dict[str, Any]:
        order = self._owned(order_id)
        if enabled("min_fields"):
            return {"order_id": order_id, "status": order["status"]}
        return {"order_id": order_id, **order}

    def _set_order_status(self, order_id: str, status: str) -> dict[str, Any]:
        order = self._owned(order_id)
        if enabled("state_machine") and status not in ALLOWED_TRANSITIONS.get(order["status"], set()):
            raise Forbidden(f"transition {order['status']}->{status} not allowed")
        order["status"] = status
        return {"order_id": order_id, "status": status}

    def _notify_customers(self, order_ids: list[str]) -> dict[str, Any]:
        if enabled("batch_limit") and len(order_ids) > BATCH_LIMIT:
            raise Forbidden(f"batch {len(order_ids)} exceeds {BATCH_LIMIT}")
        recipients = [self._owned(o)["email"] for o in order_ids]   # recipients from canonical state, not model text
        return {"sent": len(recipients)}


# ---------------------------------------------------------------- retrieval (AC-02/07/10/11)
def ingest(chunk: dict[str, Any], *, contributor_trusted: bool) -> None:
    if enabled("ingestion_review") and not contributor_trusted:
        raise Forbidden("untrusted contributor write to shared corpus needs review")
    text = chunk["text"]
    if enabled("ingestion_sanitize"):
        text = INJECTION_MARKERS.sub("[removed]", text)
        for p in SECRET_PATTERNS:
            if p.search(text):
                raise Forbidden("secret detected at ingestion")
    CORPUS.append({**chunk, "text": text})


def retrieve(caller: Caller, query: str, k: int = 3) -> dict[str, Any]:
    pool = CORPUS
    if enabled("authz_before_retrieval"):
        pool = [c for c in CORPUS if c["scope_id"] == caller.scope_id]
    hits = [c for c in pool if any(w.lower() in c["text"].lower() for w in query.split())][:k]
    result: dict[str, Any] = {"chunks": hits}
    if not enabled("suppress_global_metadata"):
        result["corpus_total"] = len(CORPUS)              # global count = membership oracle
    return result


# ---------------------------------------------------------------- quarantine (§6.1)
SUMMARY_CLASSES = {"policy_info", "order_info", "other"}


def quarantined_reader(untrusted_text: str) -> dict[str, str]:
    """No tools, no secrets, typed output only. Returns an enum + opaque reference, never raw text."""
    if not enabled("quarantine"):
        return {"classification": "other", "raw": untrusted_text}
    label = "policy_info" if "return" in untrusted_text.lower() else "other"
    return {"classification": label, "summary_ref": "$VAR1"}


# ---------------------------------------------------------------- fake model (MOCKED, fully steerable)
TOOL_DIRECTIVE = re.compile(r"call (\w+)\((\{.*?\})\)")


def steerable_model(context: str) -> dict[str, Any]:
    """Obeys any 'call tool({json})' it sees and echoes everything it was given."""
    calls = [{"tool": m.group(1), "args": json.loads(m.group(2))} for m in TOOL_DIRECTIVE.finditer(context)]
    return {"text": context, "tool_calls": calls}


# ---------------------------------------------------------------- output side (AC-06/07/14/15/16/18)
MD_IMAGE = re.compile(r"!\[[^\]]*\]\((https?://([^/)\s]+)[^)]*)\)")


def output_filter(text: str, t: Telemetry) -> str:
    if enabled("canary_detector") and SYSTEM_PROMPT_CANARY in text:
        t.canary_hits_total += 1
        raise Forbidden("system-prompt canary in output")
    if enabled("outbound_allowlist"):
        text = MD_IMAGE.sub(lambda m: m.group(0) if m.group(2) in OUTBOUND_HOST_ALLOWLIST else "[image removed]", text)
    if enabled("pii_secret_scanner"):
        for p in SECRET_PATTERNS + PII_PATTERNS:
            text = p.sub("[redacted]", text)
    return text


def render_html(model_text: str) -> str:
    return f"<p>{html.escape(model_text) if enabled('html_encoding') else model_text}</p>"


def lookup_status_sql(db: sqlite3.Connection, model_supplied_id: str) -> list[tuple[str, str]]:
    if enabled("parameterized_sql"):
        return db.execute("SELECT id, status FROM orders WHERE id = ?", (model_supplied_id,)).fetchall()
    return db.execute(f"SELECT id, status FROM orders WHERE id = '{model_supplied_id}'").fetchall()


def run_shell(_model_text: str) -> None:
    if enabled("no_shell"):
        raise Forbidden("shell sink forbidden for model output")
    logger.warning("shell sink reached")            # vulnerable path for the negative control only


def grounding_check(answer: dict[str, Any], retrieved_ids: set[str]) -> dict[str, Any]:
    cited = set(answer.get("citations", []))
    if enabled("grounding") and (not cited or not cited <= retrieved_ids):
        return {**answer, "status": "unsupported"}
    return {**answer, "status": "grounded"}


UI_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["component", "props"],
    "properties": {"component": {"enum": ["Text", "Button", "Card"]},
                   "props": {"type": "object", "additionalProperties": False,
                             "properties": {"label": {"type": "string", "maxLength": 200},
                                            "action": {"enum": ["open_order", "contact_support"]}}}},
}


def validate_ui(payload: dict[str, Any]) -> dict[str, Any]:
    if enabled("ui_schema"):
        try:
            jsonschema.validate(payload, UI_SCHEMA)
        except jsonschema.ValidationError as exc:
            logger.error("generated UI rejected: validator=%s path=%s", exc.validator, list(exc.absolute_path))
            raise Forbidden(f"ui schema: {exc.message}") from exc
    return payload


# ---------------------------------------------------------------- input + volume (AC-01/12/17)
def admit_input(text: str) -> str:
    if enabled("input_cap") and len(text) > INPUT_CHAR_CAP:
        raise Forbidden("input exceeds size cap")
    return text


def charge_quota(api_key: str, t: Telemetry) -> None:
    t.quota_used[api_key] = t.quota_used.get(api_key, 0) + 1
    if enabled("per_key_quota") and t.quota_used[api_key] > PER_KEY_QUOTA:
        raise Forbidden("per-key quota exceeded")


def clamp_output_tokens(requested: int) -> int:
    return min(requested, MAX_OUTPUT_TOKENS) if enabled("max_output_tokens") else requested


# ---------------------------------------------------------------- supply chain (AC-13) + secrets (§13)
def resolve_model(name: str, digest: str) -> str:
    if enabled("model_registry") and APPROVED_MODELS.get(name) != digest:
        raise Forbidden(f"model {name} not approved at this digest")
    return name


def admit_tool_server(name: str, version: str) -> None:
    if enabled("tool_server_intake") and APPROVED_TOOL_SERVERS.get(name) != version:
        raise Forbidden(f"tool server {name}@{version} has not passed intake")


def scan_for_secrets(text: str) -> list[str]:
    if not enabled("secret_scanner"):
        return []
    return [p.pattern for p in SECRET_PATTERNS if p.search(text)]


# ---------------------------------------------------------------- agent loop (ties the layers together)
def agent_turn(caller: Caller, user_text: str, t: Telemetry, *, retrieved: list[str] | None = None,
               history_claims: dict[str, str] | None = None) -> dict[str, Any]:
    """One turn. Authority comes from `caller` (the verified token) every turn, never from history_claims."""
    user_text = admit_input(user_text)
    effective = caller
    if not enabled("authority_per_turn") and history_claims:
        effective = Caller(caller.user_id, history_claims.get("scope_id", caller.scope_id),
                           history_claims.get("role", caller.role))
    runtime = ToolRuntime(effective, t)
    planner_context = SYSTEM_PROMPT + "\n" + user_text
    untrusted_refs = [quarantined_reader(doc) for doc in (retrieved or [])]
    planner_context += "\n" + json.dumps([{k: v for k, v in r.items()} for r in untrusted_refs])
    decision = steerable_model(planner_context)
    executed, denied = [], []
    for call in decision["tool_calls"]:
        origin = "planner"
        if any(call["tool"] in r.get("raw", "") for r in untrusted_refs):
            origin = "retrieved"
        try:
            executed.append(runtime.call(call["tool"], call["args"], origin=origin))
        except Forbidden as exc:
            logger.info("tool denied: tool=%s", call["tool"])
            denied.append(str(exc))
    return {"executed": executed, "denied": denied}
