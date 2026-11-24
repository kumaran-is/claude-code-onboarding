"""Reference PromptOps runtime: registry protocol, safe rendering, outage tiers, eval-gated promotion.

Stdlib only. Copy into your package next to `prompts/` and adapt the marked ADAPT points. Normative rules:
`prompt-engineering-patterns/reference/promptops-lifecycle.md` (sections 1, 3, 5, 6) and
`reference/prompt-templates.md` section 2 (safe rendering).

Deterministic controls live in this code, not in prompt wording: label pinning, model binding, typed variables,
delimiter escaping, secret refusal, input budget, emergency-pack integrity and the eval gate on label moves.
Prompt text only lowers how often these checks fire; it never authorizes anything. Tool authorization, tenant
isolation and output validation stay in the caller (`agentic-ai-dev/reference/tool-execution-safety.md`).

Backends: `FileRegistry` (Git prompt tree; tests and local dev) and `LangfuseRegistry` (optional; Langfuse is
imported lazily and never required). The Langfuse adapter uses only calls documented in
`eval-guide/reference/langfuse-prompts.md` and has NOT been executed against a live Langfuse server.
"""

import ast
import hashlib
import json
import logging
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger("promptops")

DEPLOYMENT_LABELS = frozenset({"development", "staging", "production"})   # never an auto-moving alias
SLOT = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
ANY_SLOT = re.compile(r"\{\{.*?\}\}", re.DOTALL)
TAG_OPEN = re.compile(r"<([a-z_][a-z0-9_]*)(?:\s[^<>]*)?>")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PLACEHOLDER = re.compile(r"<[^<>]+>")
TRUNCATED = " [TRUNCATED]"
CHARS_PER_TOKEN = 4          # ADAPT: same approximation as validate_prompts.py; use the pinned model's tokenizer
# toolkit location of the validator; ADAPT when copied (vendor validate_prompts.py, or pass validator_path)
DEFAULT_VALIDATOR = Path(__file__).resolve().parents[3] / "scripts" / "validate_prompts.py"


# --- typed errors: every failure is raised, none returns an empty or default prompt ---------------------------
class PromptOpsError(RuntimeError):
    """Base class. Messages never contain variable values or prompt text."""


class PromptConfigError(PromptOpsError):
    """Misconfiguration: bad label, unreadable card, unpinned model, missing validator definitions."""


class PromptNotFoundError(PromptOpsError):
    """The registry is healthy and has no version of this prompt at this label: fail closed, no fallback."""


class RegistryUnavailableError(PromptOpsError):
    """The backend could not be reached; the runtime may serve last-known-good or the emergency pack."""


class PromptUnavailableError(PromptOpsError):
    """Registry, last-known-good cache and emergency pack all failed for this prompt (fail closed)."""


class PromptIntegrityError(PromptOpsError):
    """Emergency pack or version content failed its SHA-256 check, or an immutable version was re-published."""


class ModelBindingError(PromptOpsError):
    """The caller's resolved model is not the model the prompt version is pinned and evaluated for."""


class PromptRenderError(PromptOpsError):
    """Rendering refused before any model call (variables, types, delimiters, secrets, budget, language)."""


class PromotionBlocked(PromptOpsError):
    """A label move was refused: no passing eval for (version, model), missing approval, or no rollback target."""


# --- single-sourced definitions from validate_prompts.py -------------------------------------------------------
def load_validator_definitions(validator_path: Path = DEFAULT_VALIDATOR) -> tuple[list[re.Pattern[str]], Callable[[dict], str]]:
    """Return (SECRETS, content_hash) as defined in validate_prompts.py, without its third-party imports.

    Importing validate_prompts.py needs pyyaml and jsonschema; this runtime is stdlib only. So the two top-level
    definitions are compiled from that file's own source (stdlib names only: re, json, hashlib). One definition,
    no copy: a pattern added to the validator is enforced here too, and the trace hash equals the hash that
    `validate_prompts.py hash` and `prompt_drift.py` compare.
    """
    try:
        tree = ast.parse(validator_path.read_text(encoding="utf-8"), filename=str(validator_path))
    except (OSError, SyntaxError) as exc:
        raise PromptConfigError(f"cannot read validator definitions ({type(exc).__name__})") from exc
    wanted = [node for node in tree.body
              if (isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "SECRETS" for t in node.targets))
              or (isinstance(node, ast.FunctionDef) and node.name == "content_hash")]
    namespace: dict[str, Any] = {"re": re, "json": json, "hashlib": hashlib}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), str(validator_path), "exec"), namespace)  # noqa: S102 - own source, two named definitions
    secrets, hasher = namespace.get("SECRETS"), namespace.get("content_hash")
    if not secrets or not callable(hasher):
        raise PromptConfigError("validator does not define SECRETS and content_hash; refusing to run without them")
    return list(secrets), hasher


# --- data ----------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ModelBinding:
    provider: str
    model: str
    version: str

    @property
    def model_id(self) -> str:
        return f"{self.provider}/{self.model}@{self.version}"

    @classmethod
    def from_card(cls, card: Mapping[str, Any]) -> "ModelBinding":
        pinned = card["model"]
        binding = cls(str(pinned["provider"]), str(pinned["model"]), str(pinned["version"]))
        if any(PLACEHOLDER.search(part) for part in (binding.provider, binding.model, binding.version)):
            raise PromptConfigError(f"prompt {card['name']!r} has a placeholder model binding; pin it first")
        return binding


@dataclass(frozen=True)
class PromptVersion:
    name: str
    version: int
    card: Mapping[str, Any]          # full prompt card, template included
    content_hash: str


@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    name: str
    version: int
    label: str
    content_hash: str
    tier: str
    model: ModelBinding
    output_schema: str
    token_estimate: int

    def span_attributes(self) -> dict[str, str | int]:
        """Attribution for the model-call span. No prompt text and no variable values (trace privacy)."""
        return {"app.prompt.name": self.name, "app.prompt.version": self.version, "app.prompt.label": self.label,
                "app.prompt.sha256": self.content_hash, "app.prompt.tier": self.tier,
                "app.prompt.output_schema": self.output_schema, "gen_ai.provider.name": self.model.provider,
                "gen_ai.request.model": self.model.model, "app.model.version": self.model.version}


class PromptRegistry(Protocol):
    def fetch(self, name: str, label: str) -> PromptVersion: ...
    def publish(self, card: Mapping[str, Any]) -> PromptVersion: ...
    def move_label(self, name: str, version: int, label: str) -> None: ...


def check_label(label: str) -> str:
    if label not in DEPLOYMENT_LABELS:
        raise PromptConfigError(f"label {label!r} is not a deployment label {sorted(DEPLOYMENT_LABELS)}")
    return label


def card_version(card: Mapping[str, Any]) -> int:
    return max(int(entry["version"]) for entry in card["changelog"])


# --- file backend (Git prompt tree) ----------------------------------------------------------------------------
def read_card(path: Path) -> dict[str, Any]:
    """JSON cards with the stdlib; YAML cards need PyYAML (optional, imported only when a YAML card is read)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    try:
        import yaml  # optional dependency, same pin as validate_prompts.py
    except ImportError as exc:
        raise PromptConfigError(f"{path.name}: reading YAML prompt cards needs PyYAML") from exc
    return yaml.safe_load(text)


class FileRegistry:
    """Versions read from a Git prompt tree, held immutable in memory; labels are in-memory (tests, local dev)."""

    def __init__(self, root: Path, *, initial_label: str = "development",
                 content_hash: Callable[[dict], str] | None = None) -> None:
        self._hash = content_hash or load_validator_definitions()[1]
        self._versions: dict[tuple[str, int], PromptVersion] = {}
        self._labels: dict[tuple[str, str], int] = {}
        files = sorted(p for p in root.rglob("*") if p.suffix in (".yaml", ".yml", ".json")
                       and p.name != "domains.yaml" and not any(s.startswith("_") for s in p.relative_to(root).parts))
        if not files:
            raise PromptConfigError("no prompt files under the prompt root; the registry saw no input")
        for path in files:
            published = self.publish(read_card(path))
            self.move_label(published.name, published.version, check_label(initial_label))

    def publish(self, card: Mapping[str, Any]) -> PromptVersion:
        version = PromptVersion(str(card["name"]), card_version(card), dict(card), self._hash(dict(card)))
        existing = self._versions.get((version.name, version.version))
        if existing is not None and existing.content_hash != version.content_hash:
            raise PromptIntegrityError(f"{version.name} v{version.version} exists with other content; bump the version")
        self._versions[(version.name, version.version)] = existing or version
        return existing or version

    def move_label(self, name: str, version: int, label: str) -> None:
        if (name, version) not in self._versions:
            raise PromptNotFoundError(f"{name} v{version} was never published")
        self._labels[(name, check_label(label))] = version

    def fetch(self, name: str, label: str) -> PromptVersion:
        version = self._labels.get((name, check_label(label)))
        if version is None:
            raise PromptNotFoundError(f"{name} has no version at label {label!r}")
        return self._versions[(name, version)]


# --- Langfuse backend (optional) ------------------------------------------------------------------------------
class LangfuseRegistry:
    """Langfuse 5.2.0 adapter. UNTESTED against a live Langfuse server: only the SDK calls documented in
    eval-guide/reference/langfuse-prompts.md are used. The prompt card is stored as the version `config`,
    with `content_hash` written by the sync job (promptops-lifecycle.md section 2)."""

    def __init__(self, client: Any | None = None, *, content_hash: Callable[[dict], str] | None = None) -> None:
        if client is None:
            from langfuse import get_client  # optional dependency; reads LANGFUSE_* settings
            client = get_client()
        self._lf, self._hash = client, content_hash

    def fetch(self, name: str, label: str) -> PromptVersion:
        label = check_label(label)
        try:
            prompt = self._lf.get_prompt(name, label=label, cache_ttl_seconds=0, fetch_timeout_seconds=5)
        except Exception as exc:  # noqa: BLE001 - classified below: not-found fails closed, anything else is an outage
            if type(exc).__name__ == "NotFoundError":   # langfuse.api.NotFoundError (5.2.0)
                raise PromptNotFoundError(f"{name} has no version at label {label!r}") from exc
            logger.warning("prompt_fetch_failed", extra={"prompt": name, "label": label, "error_type": type(exc).__name__})
            raise RegistryUnavailableError(f"{name}: registry fetch failed ({type(exc).__name__})") from exc
        config = dict(prompt.config or {})
        if "content_hash" not in config:
            raise PromptIntegrityError(f"{name} v{prompt.version}: no content_hash in config; re-sync from Git")
        card = {**config, "template": prompt.prompt}
        hasher = self._hash or load_validator_definitions()[1]
        if hasher(card) != str(config["content_hash"]):    # a UI edit that kept the old config is caught here
            raise PromptIntegrityError(f"{name} v{prompt.version}: served text does not match its content_hash; re-sync from Git")
        return PromptVersion(name, int(prompt.version), card, str(config["content_hash"]))

    def publish(self, card: Mapping[str, Any]) -> PromptVersion:
        # Langfuse versions are immutable and numbered by the server; Git card versions travel in config.
        config = {k: v for k, v in card.items() if k != "template"}
        if "content_hash" not in config:
            raise PromptIntegrityError("publish needs content_hash in the card config (validate_prompts.py hash)")
        created = self._lf.create_prompt(name=card["name"], prompt=card["template"], type="text", labels=[],
                                         config=config, commit_message=card["changelog"][-1]["change"])
        return PromptVersion(str(card["name"]), int(created.version), dict(card), str(config["content_hash"]))

    def move_label(self, name: str, version: int, label: str) -> None:
        label = check_label(label)                 # refused before any SDK call
        self._lf.update_prompt(name=name, version=version, new_labels=[label])


# --- emergency pack --------------------------------------------------------------------------------------------
def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def build_emergency_pack(registry: PromptRegistry, label: str, names: Iterable[str]) -> dict[str, Any]:
    """Build-time pack from the versions currently at `label` (never branch content). Each entry carries a SHA-256
    checksum: it detects corruption and accidental edits, not a deliberate attacker who can rewrite the pack
    (ADAPT: sign the pack, or ship it inside the signed build artifact)."""
    entries = {}
    for name in names:
        current = registry.fetch(name, check_label(label))
        body = {"version": current.version, "content_hash": current.content_hash, "card": current.card}
        entries[name] = {**body, "sha256": hashlib.sha256(_canonical(body)).hexdigest()}
    return {"label": label, "prompts": entries}


def _verified_pack_entry(pack: Mapping[str, Any], name: str, label: str) -> PromptVersion | None:
    if pack.get("label") != label:
        raise PromptIntegrityError(f"emergency pack was built for label {pack.get('label')!r}, not {label!r}")
    entry = pack.get("prompts", {}).get(name)
    if entry is None:
        return None
    body = {k: entry.get(k) for k in ("version", "content_hash", "card")}
    if not isinstance(body["card"], Mapping) or body["card"].get("name") != name:
        raise PromptIntegrityError(f"emergency pack entry {name!r} carries another prompt's card")
    if hashlib.sha256(_canonical(body)).hexdigest() != entry.get("sha256"):
        raise PromptIntegrityError(f"emergency pack entry {name!r} failed its SHA-256 check")
    return PromptVersion(name, int(body["version"]), body["card"], str(body["content_hash"]))


# --- runtime: fetch with outage tiers + safe render -----------------------------------------------------------
class PromptRuntime:
    """Fetch by the configured label, serve last-known-good or the verified emergency pack on outage, else raise.

    `ttl_seconds` is the rollback latency: a label move reaches this instance within it (0 = fetch on every call).
    Own the cache here or in the backend SDK, never both (the Langfuse adapter disables the SDK cache).
    `allow_degraded=False` is stricter than the outage tiers: once the TTL has expired, a failed fetch raises
    instead of serving last-known-good or the pack (a version fetched within the TTL is still served; use
    ttl_seconds=0 for prompts that must never be served past a rollback). The caller turns
    PromptUnavailableError into its structured safe state."""

    def __init__(self, registry: PromptRegistry, *, label: str, emergency_pack: Mapping[str, Any] | None = None,
                 secret_patterns: list[re.Pattern[str]] | None = None,
                 on_degraded: Callable[[str, str], None] = lambda name, tier: None,
                 ttl_seconds: float = 0.0, allow_degraded: bool = True,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if ttl_seconds < 0:
            raise PromptConfigError("ttl_seconds must be >= 0")
        self._ttl, self._allow_degraded, self._clock = ttl_seconds, allow_degraded, clock
        self._fetched_at: dict[str, float] = {}
        self._registry, self._label, self._pack = registry, check_label(label), emergency_pack
        self._secrets = secret_patterns if secret_patterns is not None else load_validator_definitions()[0]
        if not self._secrets:
            raise PromptConfigError("no secret patterns loaded; refusing to render without the secret scan")
        self._on_degraded = on_degraded
        self._last_known_good: dict[str, PromptVersion] = {}

    @property
    def label(self) -> str:
        return self._label

    def get(self, name: str) -> tuple[PromptVersion, str]:
        cached_at = self._fetched_at.get(name)
        if cached_at is not None and self._clock() - cached_at < self._ttl:
            return self._last_known_good[name], "live"          # within TTL: the version fetched live
        try:
            current = self._registry.fetch(name, self._label)
        except RegistryUnavailableError as outage:
            return self._degraded(name, outage)
        self._last_known_good[name] = current
        self._fetched_at[name] = self._clock()
        return current, "live"

    def _degraded(self, name: str, outage: RegistryUnavailableError) -> tuple[PromptVersion, str]:
        if not self._allow_degraded:
            logger.error("prompt_unavailable_strict", extra={"prompt": name, "label": self._label})
            raise PromptUnavailableError(f"{name}: registry down and degraded tiers are disabled") from outage
        cached = self._last_known_good.get(name)
        if cached is not None:
            self._on_degraded(name, "last_known_good")
            logger.warning("prompt_degraded", extra={"prompt": name, "tier": "last_known_good"})
            return cached, "last_known_good"
        if self._pack is not None:
            entry = _verified_pack_entry(self._pack, name, self._label)   # tampered pack raises, never serves
            if entry is not None:
                self._on_degraded(name, "emergency")
                logger.error("prompt_emergency", extra={"prompt": name, "tier": "emergency"})
                return entry, "emergency"
        logger.error("prompt_unavailable", extra={"prompt": name, "label": self._label})
        raise PromptUnavailableError(f"{name}: registry down, no last-known-good, not in emergency pack") from outage

    def render(self, name: str, variables: Mapping[str, object], *, model: ModelBinding, language: str) -> RenderedPrompt:
        current, tier = self.get(name)
        card = current.card
        pinned = ModelBinding.from_card(card)
        if model != pinned:
            raise ModelBindingError(f"{name} v{current.version} is bound to {pinned.model_id}, not {model.model_id}")
        if language not in card["languages"]:
            raise PromptRenderError(f"{name}: language {language!r} is not declared and evaluated for this prompt")
        text = render_template(card, variables, self._secrets)
        tokens = len(text) // CHARS_PER_TOKEN
        if tokens > int(card["token_budget"]["input_max"]):
            raise PromptRenderError(f"{name}: rendered input ~{tokens} tokens exceeds token_budget.input_max")
        return RenderedPrompt(text, name, current.version, self._label, current.content_hash, tier, pinned,
                              str(card["output_schema"]), tokens)


def _enclosing_tag(template: str, pos: int) -> str | None:
    for match in reversed(list(TAG_OPEN.finditer(template, 0, pos))):
        tag = match.group(1)
        if f"</{tag}>" not in template[match.end():pos] and f"</{tag}>" in template[pos:]:
            return tag
    return None


def _as_text(name: str, kind: str, value: object) -> str:
    expected = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "string_list": list}[kind]
    if not isinstance(value, expected) or (kind in ("integer", "number") and isinstance(value, bool)):
        raise PromptRenderError(f"variable '{name}' is not of type {kind}")
    if kind == "string_list":
        if not all(isinstance(item, str) for item in value):  # type: ignore[union-attr]
            raise PromptRenderError(f"variable '{name}' must be a list of strings")
        return "\n".join(value)  # type: ignore[arg-type]
    return json.dumps(value) if isinstance(value, bool) else str(value)


def render_template(card: Mapping[str, Any], values: Mapping[str, object], secrets: list[re.Pattern[str]]) -> str:
    """Logic-less, fail-closed rendering (prompt-templates.md section 2). Deterministic for equal inputs."""
    template, specs = str(card["template"]), {v["name"]: v for v in card["variables"]}
    used = SLOT.findall(template)
    if len(used) != len(ANY_SLOT.findall(template)):
        raise PromptRenderError("template contains a non-variable slot (logic, attribute access or filter)")
    for problem, names in (("undeclared variables in template", set(used) - set(specs)),
                           ("missing variables", set(specs) - set(values)),
                           ("undeclared variables passed", set(values) - set(specs))):
        if names:
            raise PromptRenderError(f"{problem}: {sorted(names)}")
    delimiters = {tag for tag in (_enclosing_tag(template, m.start()) for m in SLOT.finditer(template)) if tag}
    for match in SLOT.finditer(template):
        spec = specs[match.group(1)]
        if spec["trust"] == "untrusted" and _enclosing_tag(template, match.start()) is None:
            raise PromptRenderError(f"untrusted variable '{spec['name']}' is not inside a named delimiter")
    rendered: dict[str, str] = {}
    for name, spec in specs.items():
        text = CONTROL.sub("", _as_text(name, spec.get("type", "string"), values[name]))
        if any(pattern.search(text) for pattern in secrets):
            raise PromptRenderError(f"variable '{name}' matches a secret pattern")   # value never in the message
        if spec["trust"] == "untrusted" and delimiters:
            tags = "|".join(re.escape(t) for t in sorted(delimiters))
            text = re.sub(rf"(?i)<(\s*/?\s*(?:{tags})\b)", r"&lt;\1", text)   # cannot open or close any slot
        limit = spec.get("max_chars")
        if limit is not None and len(text) > limit:
            if spec.get("on_overflow", "reject") == "reject":
                raise PromptRenderError(f"variable '{name}' exceeds {limit} chars")
            text = text[: limit - len(TRUNCATED)] + TRUNCATED
        rendered[name] = text
    return SLOT.sub(lambda m: rendered[m.group(1)], template)


# --- eval-gated promotion and rollback ------------------------------------------------------------------------
@dataclass(frozen=True)
class EvalRecord:
    name: str
    version: int
    model_id: str
    passed: bool
    eval_run_id: str


@dataclass
class EvalLedger:
    """Eval results and label-move history. ADAPT: persist it (eval_result rows, registry audit log)."""
    evals: list[EvalRecord] = field(default_factory=list)
    promotions: list[tuple[str, str, int, str]] = field(default_factory=list)   # (name, label, version, model_id)
    withdrawn: set[tuple[str, str, int]] = field(default_factory=set)            # rolled back from: (name, label, version)

    def passed(self, name: str, version: int, model_id: str) -> bool:
        runs = [r for r in self.evals if (r.name, r.version, r.model_id) == (name, version, model_id)]
        return bool(runs) and runs[-1].passed           # the latest run for this exact pair decides


def promote(registry: PromptRegistry, ledger: EvalLedger, name: str, version: int, label: str, *,
            model: ModelBinding, approved_by: str | None = None, registry_healthy: bool = True) -> None:
    """Move `label` onto an existing version only with a passing eval for this exact (version, model)."""
    check_label(label)
    if not registry_healthy:
        raise PromotionBlocked("promotion freeze: registry degraded or an instance serves a degraded tier")
    if not ledger.passed(name, version, model.model_id):
        raise PromotionBlocked(f"{name} v{version}: no passing eval for model {model.model_id}")
    if label == "production" and not approved_by:
        raise PromotionBlocked("production needs a recorded human approval")
    registry.move_label(name, version, label)
    ledger.promotions.append((name, label, version, model.model_id))
    ledger.withdrawn.discard((name, label, version))       # an explicit, eval-gated re-promotion re-approves it
    logger.info("prompt_label_moved", extra={"prompt": name, "version": version, "label": label})


def rollback(registry: PromptRegistry, ledger: EvalLedger, name: str, label: str, *, model: ModelBinding) -> int:
    """Move `label` back to the most recent previously approved version: promoted to this label before, with a
    passing eval for this model, not the version served now and not one already rolled back from."""
    history = [v for (n, lbl, v, m) in ledger.promotions if n == name and lbl == check_label(label) and m == model.model_id]
    if not history:
        raise PromotionBlocked(f"{name}: no promotion history at {label!r}; nothing to roll back to")
    current = history[-1]
    for candidate in reversed(history[:-1]):
        if (candidate != current and (name, label, candidate) not in ledger.withdrawn
                and ledger.passed(name, candidate, model.model_id)):
            registry.move_label(name, candidate, label)
            ledger.withdrawn.add((name, label, current))
            ledger.promotions.append((name, label, candidate, model.model_id))
            logger.info("prompt_rolled_back", extra={"prompt": name, "version": candidate, "label": label})
            return candidate
    raise PromotionBlocked(f"{name}: no previously approved version other than v{current} at {label!r}")
