# /// script
# requires-python = ">=3.12"
# dependencies = ["jsonschema==4.26.0", "referencing==0.37.0"]
# ///
"""Deterministic validator for the canonical A2UI GenUI contract (target 1.0, compatibility v0.9.x).

Every message is validated by the protocol family its own `version` field selects:
  "1.0"            -> A2UI 1.0 schemas (vendor/a2ui-v1_0) + the 1.0 catalog document;
  "v0.9" | "v0.9.1" -> A2UI v0.9 schemas (vendor/a2ui-v0_9) + the v0.9 catalog document.
Any other version is UNSUPPORTED_VERSION; a message whose version differs from the first message of
the same sequence or stream is MIXED_VERSIONS. Nothing is translated between versions.

Checks, in order:
  1. each present catalog against its schema (v0.9: catalog-schema.json; 1.0: the official
     catalog_definition.json plus the contract policy subschemas), the JSON Schema 2020-12 metaschema,
     its own cross-references, and 1.0/v0.9 parity (same components and actions);
  2. every valid*/*.json message sequence is accepted;
  3. every invalid*/*.json sequence is rejected with its expectedError code (renderer->agent
     `rendererMessages`, when present, are checked after the agent->renderer `messages`);
  4. every actions*/*.json golden renderer->agent action is reproduced byte-for-byte (canonical form);
  5. every streams*/*.jsonl stream gives the errors and final state in its .expect.json sidecar.

Exit 0 when everything passes, 1 otherwise. `--selftest` plants violations and exits 0 only if every
planted violation is caught.

Layouts (auto-detected from --root, default: this script's directory):
  skill:   scripts/ beside reference/{canonical-catalog.json, canonical-catalog-v1_0.json, vendor/, fixtures/}
  project: <root>/catalog/{canonical-catalog.json, canonical-catalog-v1_0.json, vendor/} and <root>/fixtures/
A project on the v0.9.x compatibility path may omit canonical-catalog-v1_0.json (and vice versa);
messages of an absent family are then UNSUPPORTED_VERSION.

Run: uv run validate_a2ui_contract.py [--root DIR] [--catalog-v0_9 F] [--catalog-v1_0 F] [--fixtures DIR ...] [--subset]
     uv run validate_a2ui_contract.py --selftest
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

TIMESTAMP_SENTINEL = "1970-01-01T00:00:00.000Z"
RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?Z$")
POINTER = re.compile(r"^(/([^~/]|~[01])*)*$")


@dataclass(frozen=True)
class Family:
    key: str                 # "v0_9" | "v1_0"
    wire_versions: tuple     # exact `version` strings this family accepts
    schema_version: str      # the const in the vendored schemas
    base: str                # $id base of the vendored schemas
    vendor_dir: str
    agent_to_renderer: str
    renderer_to_agent: str
    message_keys: tuple
    binding_key: str         # data binding key: "path" (v0.9) / "@path" (1.0)


V0_9 = Family("v0_9", ("v0.9", "v0.9.1"), "v0.9", "https://a2ui.org/specification/v0_9/", "a2ui-v0_9",
              "server_to_client.json", "client_to_server.json",
              ("createSurface", "updateComponents", "updateDataModel", "deleteSurface"), "path")
V1_0 = Family("v1_0", ("1.0",), "1.0", "https://a2ui.org/specification/v1_0/", "a2ui-v1_0",
              "agent_to_renderer.json", "renderer_to_agent.json",
              ("createSurface", "updateComponents", "updateDataModel", "deleteSurface",
               "callRendererFunction", "agentFunctionResponse"), "@path")
FAMILIES = (V1_0, V0_9)


class ContractError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class Paths:
    catalogs: dict[str, Path]       # family key -> catalog file (present ones only)
    catalog_schema: Path
    vendor: Path
    fixtures: list[Path]

    @staticmethod
    def detect(root: Path) -> Paths:
        if (root / "catalog").is_dir():  # project layout
            cat, fixtures = root / "catalog", [root / "fixtures"]
        else:  # skill layout: scripts/ beside reference/
            cat = root.parent / "reference"
            fixtures = [cat / "fixtures"]
        catalogs = {k: p for k, p in (("v0_9", cat / "canonical-catalog.json"), ("v1_0", cat / "canonical-catalog-v1_0.json")) if p.is_file()}
        return Paths(catalogs, cat / "catalog-schema.json", cat / "vendor", fixtures)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: Any) -> str:
    """Canonical action form: sorted keys, no whitespace, UTF-8, integers only."""
    def check(node: Any, where: str) -> None:
        if isinstance(node, float):
            raise ContractError("NON_INTEGER_NUMBER", f"{where}: {node!r}; send decimals as strings")
        if node is None:
            raise ContractError("NULL_VALUE", f"{where}: null is not allowed in action payloads")
        if isinstance(node, dict):
            for key, child in node.items():
                check(child, f"{where}/{key}")
        if isinstance(node, list):
            for index, child in enumerate(node):
                check(child, f"{where}/{index}")
    check(value, "")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pointer_get(doc: Any, pointer: str) -> Any:
    if not POINTER.match(pointer):
        raise ContractError("INVALID_POINTER", pointer)
    node = doc
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        else:
            raise ContractError("ACTION_CONTEXT_UNRESOLVED", f"no value at {pointer}")
    return node


def pointer_set(doc: dict, pointer: str | None, value: Any, delete: bool) -> dict:
    if pointer in (None, "", "/"):
        if delete:
            return {}
        if not isinstance(value, dict):
            raise ContractError("SCHEMA_INVALID", "root data model must be an object")
        return copy.deepcopy(value)
    if not POINTER.match(pointer):
        raise ContractError("INVALID_POINTER", pointer)
    tokens = [t.replace("~1", "/").replace("~0", "~") for t in pointer.split("/")[1:]]
    node: Any = doc
    for token in tokens[:-1]:
        if isinstance(node, dict):
            node = node.setdefault(token, {})
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        else:
            raise ContractError("INVALID_POINTER", f"cannot traverse {pointer}")
    last = tokens[-1]
    if isinstance(node, dict):
        if delete:
            node.pop(last, None)
        else:
            node[last] = copy.deepcopy(value)
    elif isinstance(node, list) and last.isdigit() and int(last) < len(node) and not delete:
        node[int(last)] = copy.deepcopy(value)
    else:
        raise ContractError("INVALID_POINTER", f"cannot write {pointer}")
    return doc


@dataclass
class Surface:
    catalog_id: str
    family: Family
    components: dict[str, dict] = field(default_factory=dict)
    data: dict = field(default_factory=dict)


@dataclass
class Session:
    """One message sequence or stream: its surfaces and the wire version fixed by its first message."""
    surfaces: dict[str, Surface] = field(default_factory=dict)
    version: str | None = None


class FamilyContract:
    """The catalog, policy and schema validators of one protocol family."""

    def __init__(self, family: Family, catalog_path: Path, paths: Paths, subset: bool) -> None:
        self.family = family
        self.catalog = load_json(catalog_path)
        self.catalog_schema = load_json(paths.catalog_schema)
        if subset:  # a non-canonical catalog (e.g. a shared runtime subset): skip the canonical component-name list
            comps = self.catalog_schema["properties"]["components"]
            comps.pop("propertyNames", None)
            comps.pop("minProperties", None)
        if family is V1_0:
            self.ext = self.catalog.get("metadata", {}).get("extensions", {}).get("genui_contract", {})
        else:
            self.ext = self.catalog.get("x-genui", {})
        self.limits = self.ext.get("limits", {})
        self.forbidden = [re.compile(p) for p in self.ext.get("forbiddenStringPatterns", [])]
        vdir = paths.vendor / family.vendor_dir
        names = [family.agent_to_renderer, family.renderer_to_agent, "common_types.json"]
        if family is V1_0:
            names.append("catalog_definition.json")
        vendor = {name: _python_regex(load_json(vdir / name)) for name in names}
        resources = [(family.base + name, Resource.from_contents(doc, default_specification=DRAFT202012)) for name, doc in vendor.items()]
        catalog_resource = Resource.from_contents(self.catalog, default_specification=DRAFT202012)
        resources += [
            (self.catalog["$id"], catalog_resource),
            (family.base + "catalog.json", catalog_resource),  # the wire schema's `catalog.json` slot
            (self.catalog_schema["$id"], Resource.from_contents(self.catalog_schema, default_specification=DRAFT202012)),
        ]
        if family is V1_0:  # 1.0 catalogs reference standard types relatively: common_types.json beside the catalog
            beside = self.catalog["$id"].rsplit("/", 1)[0] + "/common_types.json"
            resources.append((beside, Resource.from_contents(vendor["common_types.json"], default_specification=DRAFT202012)))
        self.registry: Registry = Registry().with_resources(resources)
        fmt = FormatChecker()
        self.agent_v = Draft202012Validator(vendor[family.agent_to_renderer], registry=self.registry, format_checker=fmt)
        self.renderer_v = Draft202012Validator(vendor[family.renderer_to_agent], registry=self.registry, format_checker=fmt)
        self.catalog_schema_v = Draft202012Validator(self.catalog_schema, registry=self.registry, format_checker=fmt)
        self.catalog_def_v = (Draft202012Validator(vendor["catalog_definition.json"], registry=self.registry, format_checker=fmt)
                              if family is V1_0 else None)

    def comp_policy(self, comp: dict) -> dict:
        if self.family is V1_0:
            return comp.get("metadata", {}).get("extensions", {}).get("genui_contract", {})
        return comp.get("x-genui", {})

    # ---------- catalog ----------
    def check_catalog(self) -> list[str]:
        tag = f"[{self.family.key}]"
        problems: list[str] = []
        if self.family is V1_0:
            problems += [f"{tag} catalog_definition: {e.json_path}: {e.message[:200]}" for e in self.catalog_def_v.iter_errors(self.catalog)]
            if self.catalog.get("protocolVersion") != "1.0":
                problems.append(f"{tag} protocolVersion must be '1.0'")
            policy_schema = {"$ref": self.catalog_schema["$id"] + "#/properties/x-genui"}
            comp_schema = {"$ref": self.catalog_schema["$id"] + "#/$defs/componentDefinition/properties/x-genui"}
            pv = Draft202012Validator(policy_schema, registry=self.registry, format_checker=FormatChecker())
            cv = Draft202012Validator(comp_schema, registry=self.registry, format_checker=FormatChecker())
            problems += [f"{tag} genui_contract: {e.json_path}: {e.message[:200]}" for e in pv.iter_errors(self.ext)]
            for name, comp in self.catalog["components"].items():
                problems += [f"{tag} {name} genui_contract: {e.message[:200]}" for e in cv.iter_errors(self.comp_policy(comp))]
        else:
            problems += [f"{tag} catalog-schema: {e.json_path}: {e.message[:200]}" for e in self.catalog_schema_v.iter_errors(self.catalog)]
        if not self.ext:
            return problems + [f"{tag} catalog has no contract policy"]
        expected_pv = "1.0" if self.family is V1_0 else "v0.9"
        if self.ext.get("protocolVersion") != expected_pv:
            problems.append(f"{tag} policy protocolVersion {self.ext.get('protocolVersion')!r} != {expected_pv!r}")
        stray = set(self.ext.get("acceptedWireVersions", [])) - set(self.family.wire_versions)
        if stray:
            problems.append(f"{tag} acceptedWireVersions {sorted(stray)} do not belong to this family")
        try:
            Draft202012Validator.check_schema(self.catalog)
        except Exception as exc:  # SchemaError carries the detail; reported, not swallowed
            problems.append(f"{tag} metaschema: {exc}")
        actions = self.ext.get("actions", {})
        used: set[str] = set()
        listed = {item["$ref"].rsplit("/", 1)[-1] for item in self.catalog["$defs"]["anyComponent"]["oneOf"]}
        for name, comp in self.catalog["components"].items():
            allowed = set(self.comp_policy(comp).get("allowedActions", []))
            in_schema = set(_event_enums(comp))
            if allowed != in_schema:
                problems.append(f"{tag} {name}: allowedActions {sorted(allowed)} != schema enums {sorted(in_schema)}")
            for action in allowed - set(actions):
                problems.append(f"{tag} {name}: action {action} has no actions entry")
            used |= allowed
            if name not in listed:
                problems.append(f"{tag} {name}: missing from $defs.anyComponent")
        for action, spec in actions.items():
            if action not in used:
                problems.append(f"{tag} action {action} is not allowed on any component")
            try:
                Draft202012Validator.check_schema(spec["payloadSchema"])
            except Exception as exc:
                problems.append(f"{tag} action {action}: payloadSchema invalid: {exc}")
        return problems


class Contract:
    def __init__(self, paths: Paths, subset: bool = False) -> None:
        if not paths.catalogs:
            raise SystemExit(f"no catalog found (looked for canonical-catalog.json / canonical-catalog-v1_0.json near {paths.catalog_schema.parent})")
        self.paths = paths
        self.families = {f.key: FamilyContract(f, paths.catalogs[f.key], paths, subset) for f in FAMILIES if f.key in paths.catalogs}

    def family_for(self, version: Any) -> FamilyContract:
        for fc in self.families.values():
            if version in fc.ext.get("acceptedWireVersions", []):
                return fc
        raise ContractError("UNSUPPORTED_VERSION", repr(version))

    def check_catalogs(self) -> list[str]:
        problems: list[str] = []
        for fc in self.families.values():
            problems += fc.check_catalog()
        if len(self.families) == 2:  # the 1.0 catalog is the same contract in another wire format
            old, new = self.families["v0_9"], self.families["v1_0"]
            if set(old.catalog["components"]) != set(new.catalog["components"]):
                problems.append(f"parity: components differ: v0.9 {sorted(old.catalog['components'])} vs 1.0 {sorted(new.catalog['components'])}")
            if canonical_safe(old.ext.get("actions")) != canonical_safe(new.ext.get("actions")):
                problems.append("parity: action allowlists / payload schemas differ between the v0.9 and 1.0 catalogs")
            for name in set(old.catalog["components"]) & set(new.catalog["components"]):
                if old.comp_policy(old.catalog["components"][name]).get("allowedActions") != new.comp_policy(new.catalog["components"][name]).get("allowedActions"):
                    problems.append(f"parity: {name} allowedActions differ between versions")
        return problems

    # ---------- agent -> renderer ----------
    def apply(self, session: Session, message: Any) -> None:
        """Validates and applies one message atomically; raises ContractError and leaves state unchanged."""
        if not isinstance(message, dict):
            raise ContractError("MALFORMED_MESSAGE", "message is not a JSON object")
        if "version" not in message:
            raise ContractError("MALFORMED_MESSAGE", "missing version")
        fc = self.family_for(message["version"])
        if session.version is not None and message["version"] != session.version:
            raise ContractError("MIXED_VERSIONS", f"{message['version']!r} after {session.version!r}")
        fam = fc.family
        size = len(json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode())
        if size > fc.limits["maxMessageBytes"]:
            raise ContractError("MESSAGE_TOO_LARGE", f"{size} bytes")
        bodies = [k for k in message if k != "version"]
        if len(bodies) != 1 or bodies[0] not in fam.message_keys:
            raise ContractError("MALFORMED_MESSAGE", f"expected exactly one of {fam.message_keys}, got {bodies}")
        kind = bodies[0]
        body = message[kind]
        if kind in ("updateComponents", "createSurface") and isinstance(body, dict):
            self._precheck_components(fc, body.get("components"), body.get("catalogId"))
        self._check_strings(fc, message, "")
        # v0.9.1 is wire-identical to v0.9 (one web_core adapter, schema enum ['v0.9','v0.9.1']); the vendored
        # JSON Schema pins the const 'v0.9', so the version is normalised for schema validation only.
        probe = {**message, "version": fam.schema_version}
        errors = sorted(fc.agent_v.iter_errors(probe), key=lambda e: list(e.absolute_path))
        if errors:
            raise ContractError("SCHEMA_INVALID", "; ".join(f"{list(e.absolute_path)}: {e.message[:160]}" for e in errors[:3]))
        if session.version is None:
            session.version = message["version"]
        surfaces = session.surfaces
        if kind == "agentFunctionResponse":
            raise ContractError("FUNCTION_CALL_NOT_ALLOWED", "this contract defines no agent functions, so no callAgentFunction is ever pending")
        if kind == "callRendererFunction":
            name = body["callFunction"]["@call"]
            spec = fc.catalog["functions"].get(name)
            if spec is None or spec.get("allowedCallers", "rendererOnly") == "rendererOnly":
                raise ContractError("FUNCTION_CALL_NOT_ALLOWED", f"{name!r} is not callable by the agent (spec code INVALID_FUNCTION_CALL)")
            return
        sid = body["surfaceId"]
        if kind == "createSurface":
            if sid in surfaces:
                raise ContractError("DUPLICATE_SURFACE", sid)
            cat_id = body.get("catalogId")
            if cat_id != fc.catalog["catalogId"]:
                raise ContractError("UNSUPPORTED_CATALOG", repr(cat_id))
            surface = Surface(cat_id, fam)
            if "components" in body:  # 1.0 single-message surface initialisation
                surface.components = self._merge(fc, {}, body["components"])
            if "dataModel" in body:
                surface.data = copy.deepcopy(body["dataModel"])
            surfaces[sid] = surface
            return
        if sid not in surfaces:
            raise ContractError("SURFACE_NOT_FOUND", f"{kind} for {sid} before createSurface")
        if kind == "deleteSurface":
            del surfaces[sid]
            return
        surface = surfaces[sid]
        if kind == "updateDataModel":
            delete = body.get("value") is None if fam is V1_0 else "value" not in body
            surface.data = pointer_set(copy.deepcopy(surface.data), body.get("path"), body.get("value"), delete)
            return
        surface.components = self._merge(fc, surface.components, body["components"])

    def _merge(self, fc: FamilyContract, existing: dict, components: list[dict]) -> dict:
        ids = [c["id"] for c in components]
        if len(ids) != len(set(ids)):
            raise ContractError("DUPLICATE_COMPONENT_ID", str(ids))
        merged = {**existing, **{c["id"]: c for c in components}}
        self._check_graph(fc, merged, complete=False)
        return merged

    def _precheck_components(self, fc: FamilyContract, components: Any, surface_catalog: Any) -> None:
        if not isinstance(components, list):
            return
        known = fc.catalog["components"]
        for comp in components:
            if not isinstance(comp, dict):
                continue
            if fc.family is V1_0 and "@catalogId" in comp and comp["@catalogId"] != fc.catalog["catalogId"]:
                raise ContractError("UNSUPPORTED_CATALOG", f"component {comp.get('id')!r} names catalog {comp['@catalogId']!r}; this contract does not mix catalogs")
            name = comp.get("component")
            if name not in known:
                raise ContractError("UNKNOWN_COMPONENT", f"{name!r} (id {comp.get('id')!r})")
            allowed = set(fc.comp_policy(known[name]).get("allowedActions", []))
            for node in _walk(comp):
                if isinstance(node, dict) and "functionCall" in node and set(node) == {"functionCall"}:
                    raise ContractError("FUNCTION_ACTION_FORBIDDEN", f"{comp.get('id')}: client-side functionCall actions are not allowed")
                if isinstance(node, dict) and isinstance(node.get("event"), dict):
                    action = node["event"].get("name")
                    if action not in allowed:
                        raise ContractError("ACTION_NOT_ALLOWED", f"{action!r} on {name} {comp.get('id')!r}")
                    # Static shape check at surface time: the context keys the renderer will send must fit the
                    # action's payloadSchema (values are bound later, so only keys are checked here).
                    schema = fc.ext["actions"][action]["payloadSchema"]
                    keys = set(node["event"].get("context", {}))
                    missing = set(schema.get("required", [])) - keys
                    extra = keys - set(schema.get("properties", {})) if schema.get("additionalProperties") is False else set()
                    if missing or extra:
                        raise ContractError("ACTION_PAYLOAD_INVALID", f"{action!r} on {comp.get('id')!r}: context keys missing {sorted(missing)}, not allowed {sorted(extra)}")

    def _check_strings(self, fc: FamilyContract, node: Any, where: str) -> None:
        if isinstance(node, str):
            if len(node) > fc.limits["maxStringLength"]:
                raise ContractError("STRING_TOO_LONG", where)
            for pattern in fc.forbidden:
                if pattern.search(node):
                    raise ContractError("UNSAFE_CONTENT", f"{where}: matches {pattern.pattern}")
        elif isinstance(node, dict):
            for key, child in node.items():
                self._check_strings(fc, child, f"{where}/{key}")
        elif isinstance(node, list):
            for index, child in enumerate(node):
                self._check_strings(fc, child, f"{where}/{index}")

    def _check_graph(self, fc: FamilyContract, components: dict[str, dict], complete: bool) -> None:
        if len(components) > fc.limits["maxComponentsPerSurface"]:
            raise ContractError("TOO_MANY_COMPONENTS", str(len(components)))
        if complete and "root" not in components:
            raise ContractError("MISSING_ROOT", "no component with id 'root'")
        max_depth = fc.limits["maxDepth"]

        def visit(cid: str, path: tuple[str, ...]) -> None:
            if cid in path:
                raise ContractError("CYCLE", " -> ".join((*path, cid)))
            if len(path) + 1 > max_depth:
                raise ContractError("MAX_DEPTH_EXCEEDED", f"depth {len(path) + 1} > {max_depth} at {cid}")
            comp = components.get(cid)
            if comp is None:
                if complete:
                    raise ContractError("DANGLING_REFERENCE", f"{path[-1] if path else '?'} -> {cid}")
                return  # progressive rendering: the child may arrive in a later message
            for child in _children(comp):
                visit(child, (*path, cid))

        for start in (["root"] if "root" in components else []) + sorted(components):
            visit(start, ())

    def finish(self, session: Session) -> None:
        for surface in session.surfaces.values():
            self._check_graph(self.families[surface.family.key], surface.components, complete=True)

    # ---------- renderer -> agent ----------
    def build_action(self, surface_id: str, surface: Surface, component_id: str, action_pointer: str, version: str) -> dict:
        comp = surface.components.get(component_id)
        if comp is None:
            raise ContractError("SURFACE_NOT_FOUND", f"component {component_id}")
        key = surface.family.binding_key
        event = pointer_get(comp, action_pointer)["event"]
        context = {}
        for name, value in event.get("context", {}).items():
            context[name] = pointer_get(surface.data, value[key]) if isinstance(value, dict) else value
        message = {"version": version, "action": {"name": event["name"], "surfaceId": surface_id,
                                                   "sourceComponentId": component_id, "timestamp": TIMESTAMP_SENTINEL, "context": context}}
        self.check_action(message, comp)
        return message

    def check_action(self, message: dict, source: dict | None) -> None:
        fc = self.family_for(message.get("version"))
        errors = list(fc.renderer_v.iter_errors({**message, "version": fc.family.schema_version}))
        if errors:
            raise ContractError("SCHEMA_INVALID", errors[0].message[:200])
        if "action" not in message:
            raise ContractError("ACTION_NOT_ALLOWED", f"renderer message {sorted(k for k in message if k != 'version')} is not an allowlisted action")
        act = message["action"]
        if not RFC3339_UTC.match(act["timestamp"]):
            raise ContractError("BAD_TIMESTAMP", act["timestamp"])
        datetime.fromisoformat(act["timestamp"].replace("Z", "+00:00"))
        spec = fc.ext["actions"].get(act["name"])
        if spec is None:
            raise ContractError("ACTION_NOT_ALLOWED", act["name"])
        if source is not None and act["name"] not in fc.comp_policy(fc.catalog["components"][source["component"]]).get("allowedActions", []):
            raise ContractError("ACTION_NOT_ALLOWED", f"{act['name']} from {source['component']}")
        payload_errors = list(Draft202012Validator(spec["payloadSchema"]).iter_errors(act["context"]))
        if payload_errors:
            raise ContractError("ACTION_PAYLOAD_INVALID", payload_errors[0].message[:200])
        canonical(message)


UAX31_PATTERN = "^[\\p{XID_Start}_][\\p{XID_Continue}]*$"
UAX31_PYTHON = r"^[^\W\d]\w*$"  # Python `re` has no \p{...}; Unicode-aware \w approximates XID_Start/XID_Continue


def _python_regex(node: Any) -> Any:
    """In-memory only: rewrites the v1.0 UAX #31 key pattern (Extensions) into Python `re` syntax.
    The vendored file stays byte-identical to upstream; any other \\p{...} pattern fails loudly."""
    if isinstance(node, dict):
        return {(UAX31_PYTHON if k == UAX31_PATTERN else k): _python_regex(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_python_regex(v) for v in node]
    if isinstance(node, str) and "\\p{" in node:
        raise SystemExit(f"unsupported Unicode property pattern in vendored schema: {node}")
    return node


def canonical_safe(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _walk(node: Any):
    yield node
    if isinstance(node, dict):
        for child in node.values():
            yield from _walk(child)
    elif isinstance(node, list):
        for child in node:
            yield from _walk(child)


def _children(comp: dict) -> list[str]:
    out: list[str] = []
    children = comp.get("children")
    if isinstance(children, list):
        out += [c for c in children if isinstance(c, str)]
    elif isinstance(children, dict) and isinstance(children.get("componentId"), str):
        out.append(children["componentId"])
    if isinstance(comp.get("child"), str):
        out.append(comp["child"])
    return out


def _event_enums(comp: dict) -> list[str]:
    found: list[str] = []
    for node in _walk(comp):
        if isinstance(node, dict) and isinstance(node.get("properties"), dict):
            event = node["properties"].get("event")
            if isinstance(event, dict):
                name = event.get("properties", {}).get("name", {})
                found += name.get("enum", [])
    return found


def run_sequence(contract: Contract, messages: list[Any]) -> Session:
    session = Session()
    for index, message in enumerate(messages):
        try:
            contract.apply(session, message)
        except ContractError as exc:
            raise ContractError(exc.code, f"message {index}: {exc.detail}") from exc
    contract.finish(session)
    return session


def check_renderer_messages(contract: Contract, session: Session, messages: list[dict]) -> None:
    for message in messages:
        act = message.get("action", {})
        surface = session.surfaces.get(act.get("surfaceId"))
        source = surface.components.get(act.get("sourceComponentId")) if surface else None
        if session.version is not None and message.get("version") != session.version:
            raise ContractError("MIXED_VERSIONS", f"renderer message {message.get('version')!r} on a {session.version!r} session")
        contract.check_action(message, source)


def _glob(roots: list[Path], pattern: str) -> list[Path]:
    return sorted({p for root in roots for p in root.glob(pattern)})


def check_fixtures(contract: Contract, out: list[str]) -> list[str]:
    problems: list[str] = []
    roots = contract.paths.fixtures
    for path in _glob(roots, "valid*/*.json"):
        out.append(f"valid    {path.parent.name}/{path.name}")
        try:
            run_sequence(contract, load_json(path)["messages"])
        except ContractError as exc:
            problems.append(f"{path.parent.name}/{path.name}: rejected: {exc}")
    for path in _glob(roots, "invalid*/*.json"):
        out.append(f"invalid  {path.parent.name}/{path.name}")
        doc = load_json(path)
        try:
            session = run_sequence(contract, doc["messages"])
            check_renderer_messages(contract, session, doc.get("rendererMessages", []))
            problems.append(f"{path.parent.name}/{path.name}: accepted, expected {doc['expectedError']}")
        except ContractError as exc:
            if exc.code != doc["expectedError"]:
                problems.append(f"{path.parent.name}/{path.name}: got {exc.code}, expected {doc['expectedError']} ({exc.detail})")
    for path in _glob(roots, "actions*/*.json"):
        out.append(f"action   {path.parent.name}/{path.name}")
        problems += check_golden(contract, path, load_json(path))
    for path in _glob(roots, "streams*/*.jsonl"):
        out.append(f"stream   {path.parent.name}/{path.name}")
        problems += check_stream(contract, path)
    if not out:
        problems.append(f"no fixtures found under {[str(r) for r in roots]}")
    return problems


def check_golden(contract: Contract, path: Path, doc: dict) -> list[str]:
    name = f"{path.parent.name}/{path.name}"
    try:
        session = run_sequence(contract, load_json(path.parent.parent / doc["fixture"])["messages"])
        trigger = doc["trigger"]
        surface = session.surfaces[trigger["surfaceId"]]
        for edit in doc.get("edits", []):
            surface.data = pointer_set(surface.data, edit["path"], edit["value"], delete=False)
        built = contract.build_action(trigger["surfaceId"], surface, trigger["sourceComponentId"], trigger["actionPointer"], session.version)
        expected = copy.deepcopy(doc["expected"])
        contract.check_action(expected, surface.components[trigger["sourceComponentId"]])
        expected["action"]["timestamp"] = TIMESTAMP_SENTINEL  # timestamp is normalised before comparison
    except ContractError as exc:
        return [f"{name}: {exc}"]
    problems = []
    if canonical(built) != canonical(expected):
        problems.append(f"{name}: built {canonical(built)} != expected {canonical(expected)}")
    if canonical(built) != doc["canonical"]:
        problems.append(f"{name}: canonical string differs from the recorded golden")
    return problems


def check_stream(contract: Contract, path: Path) -> list[str]:
    expect = load_json(path.with_suffix(".expect.json"))
    session = Session()
    errors: list[dict] = []
    raw = path.read_text(encoding="utf-8")
    lines = raw.split("\n")
    trailing_partial = not raw.endswith("\n")
    for number, line in enumerate(lines, start=1):
        if line.strip() == "":
            continue
        if trailing_partial and number == len(lines):
            errors.append({"line": number, "code": "INCOMPLETE_FRAME"})  # no newline yet: buffer, never parse
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            errors.append({"line": number, "code": "MALFORMED_MESSAGE"})
            continue
        try:
            contract.apply(session, message)
        except ContractError as exc:
            errors.append({"line": number, "code": exc.code})
    problems = []
    name = f"{path.parent.name}/{path.name}"
    if errors != expect["errors"]:
        problems.append(f"{name}: errors {errors} != expected {expect['errors']}")
    state = {sid: {"componentIds": sorted(s.components), "dataModel": s.data} for sid, s in session.surfaces.items()}
    if canonical(state) != canonical(expect["finalState"]):
        problems.append(f"{name}: final state {canonical(state)} != expected {canonical(expect['finalState'])}")
    return problems


def selftest(paths: Paths) -> int:
    contract = Contract(paths)
    failures: list[str] = []

    def expect(code: str, messages: list, label: str) -> None:
        try:
            run_sequence(contract, messages)
            failures.append(f"planted {label}: accepted")
        except ContractError as exc:
            if exc.code != code:
                failures.append(f"planted {label}: got {exc.code} ({exc.detail[:120]})")
            else:
                print(f"selftest caught {label} -> {code}")

    def root_of(messages: list) -> dict:
        for m in messages:
            body = m.get("updateComponents") or m.get("createSurface") or {}
            for c in body.get("components", []):
                if c["id"] == "root":
                    return c
        raise AssertionError("no root component in base fixture")

    for key, base_file, other in (("v0_9", "valid/action-card.json", "1.0"), ("v1_0", "valid-v1_0/action-card.json", "v0.9")):
        if key not in contract.families:
            continue
        base = load_json(paths.fixtures[0] / base_file)["messages"]
        if root_of(base).get("component") != "ActionCard":
            failures.append(f"selftest base fixture {base_file} changed: root is not an ActionCard")
            continue

        def planted(mutate, base=base):
            messages = copy.deepcopy(base)
            mutate(root_of(messages), messages)
            return messages

        bind = "@path" if key == "v1_0" else "path"
        stale = "path" if key == "v1_0" else "@path"
        cases = {
            "UNKNOWN_COMPONENT": planted(lambda c, m: c.update(component="HtmlBlock")),
            "UNSAFE_CONTENT": planted(lambda c, m: c.update(body="javascript:alert(1)")),
            "ACTION_NOT_ALLOWED": planted(lambda c, m: c["actions"][0]["action"]["event"].update(name="approval.approve")),
            "ACTION_PAYLOAD_INVALID": planted(lambda c, m: c["actions"][0]["action"]["event"]["context"].update(isAdmin=True)),
            "SCHEMA_INVALID": planted(lambda c, m: c.pop("title")),
            "UNSUPPORTED_VERSION": planted(lambda c, m: m[0].update(version="v0.8")),
            "MIXED_VERSIONS": planted(lambda c, m: m.append({"version": other, "deleteSurface": {"surfaceId": "card-1"}})),
        }
        if key == "v0_9":
            cases["SURFACE_NOT_FOUND"] = planted(lambda c, m: m.pop(0))
        for code, messages in cases.items():
            expect(code, messages, f"[{key}] {code}")
        expect("SCHEMA_INVALID", planted(lambda c, m: c.update(title={stale: "/card/title"})), f"[{key}] wrong-version binding key {stale!r}")
        if key == "v1_0":
            expect("SCHEMA_INVALID", planted(lambda c, m: m[0]["createSurface"].update(theme={"primaryColor": "#000000"})), "[v1_0] createSurface.theme")
            expect("SCHEMA_INVALID", planted(lambda c, m: c.update(accessibility={"label": "x"})), "[v1_0] bare accessibility envelope key")
            expect("UNSUPPORTED_CATALOG", planted(lambda c, m: c.update({"@catalogId": "https://evil.example/catalog.json"})), "[v1_0] foreign @catalogId")
            expect("FUNCTION_CALL_NOT_ALLOWED", base + [{"version": "1.0", "callRendererFunction": {
                "functionCallId": "c1", "callFunction": {"@call": "required", "catalogId": contract.families["v1_0"].catalog["catalogId"], "args": {"value": "x"}}}}],
                "[v1_0] agent calls a rendererOnly function")
        del bind
    # v1.0 renderer->agent action built from a valid fixture must validate; a payload drift must not
    if "v1_0" in contract.families:
        session = run_sequence(contract, load_json(paths.fixtures[0] / "valid-v1_0/approval-form.json")["messages"])
        surface = session.surfaces["appr-1"]
        try:
            msg = contract.build_action("appr-1", surface, "root", "/approveAction", session.version)
            print("selftest built a valid 1.0 approval.approve action")
            bad = copy.deepcopy(msg)
            bad["action"]["context"].pop("requestId")
            try:
                contract.check_action(bad, surface.components["root"])
                failures.append("planted [v1_0] action without requestId: accepted")
            except ContractError as exc:
                print(f"selftest caught [v1_0] action payload drift -> {exc.code}")
        except ContractError as exc:
            failures.append(f"[v1_0] valid action rejected: {exc}")
    if "v0_9" in contract.families:
        fc = contract.families["v0_9"]
        bad_catalog = copy.deepcopy(fc.catalog)
        del bad_catalog["components"]["ApprovalForm"]["x-genui"]
        if not list(fc.catalog_schema_v.iter_errors(bad_catalog)):
            failures.append("planted catalog without x-genui: accepted")
        else:
            print("selftest caught catalog component without x-genui")
        bad_platforms = copy.deepcopy(fc.catalog)
        bad_platforms["x-genui"]["platforms"] = ["angular", "swiftui"]
        if not list(fc.catalog_schema_v.iter_errors(bad_platforms)):
            failures.append("planted unknown platform 'swiftui': accepted")
        else:
            print("selftest caught unknown platform value")
    if "v1_0" in contract.families:
        fc = contract.families["v1_0"]
        saved = fc.catalog
        fc.catalog = copy.deepcopy(saved)
        fc.catalog["theme"] = {"primaryColor": "#000000"}
        if not fc.check_catalog():
            failures.append("planted [v1_0] catalog root 'theme': accepted")
        else:
            print("selftest caught [v1_0] catalog root key outside catalog_definition")
        fc.catalog = saved
    if len(contract.families) == 2:
        fc = contract.families["v1_0"]
        saved = fc.ext["actions"]
        fc.ext["actions"] = {k: v for k, v in saved.items() if k != "item.dismiss"}
        if not contract.check_catalogs():
            failures.append("planted 1.0/v0.9 action drift: accepted")
        else:
            print("selftest caught 1.0/v0.9 catalog parity drift")
        fc.ext["actions"] = saved
    goldens = _glob(paths.fixtures, "actions*/*.json")
    if goldens:
        golden = load_json(goldens[0])
        golden["expected"]["action"]["context"]["planted"] = "x"
        if not check_golden(contract, goldens[0], golden):
            failures.append("planted golden context drift: accepted")
        else:
            print("selftest caught golden action drift")
    try:
        canonical({"n": 2.0})
        failures.append("planted float 2.0 in action payload: accepted")
    except ContractError:
        print("selftest caught NON_INTEGER_NUMBER")
    for failure in failures:
        print(f"SELFTEST FAIL: {failure}")
    print(f"selftest: {'PASS' if not failures else 'FAIL'}")
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--root", type=Path, help="directory holding catalog/ and fixtures/ (project layout) or scripts/ (skill layout)")
    parser.add_argument("--catalog-v0_9", type=Path, help="override the v0.9.x catalog document")
    parser.add_argument("--catalog-v1_0", type=Path, help="override the 1.0 catalog document")
    parser.add_argument("--fixtures", type=Path, action="append", help="fixture root(s) holding valid*/, invalid*/, actions*/, streams*/")
    parser.add_argument("--subset", action="store_true", help="the catalogs are a non-canonical subset: skip the canonical component-name list")
    args = parser.parse_args()
    paths = Paths.detect((args.root or Path(__file__).parent).resolve())
    if args.catalog_v0_9:
        paths.catalogs["v0_9"] = args.catalog_v0_9.resolve()
    if args.catalog_v1_0:
        paths.catalogs["v1_0"] = args.catalog_v1_0.resolve()
    if args.fixtures:
        paths.fixtures = [p.resolve() for p in args.fixtures]
    if args.selftest:
        return selftest(paths)
    contract = Contract(paths, subset=args.subset)
    for fc in contract.families.values():
        print(f"catalog  [{fc.family.key}] {paths.catalogs[fc.family.key].name} ({len(fc.catalog['components'])} components, "
              f"{len(fc.ext.get('actions', {}))} actions, wire {fc.ext.get('acceptedWireVersions')})")
    problems = contract.check_catalogs()
    scanned: list[str] = []
    problems += check_fixtures(contract, scanned)
    print("\n".join(scanned))
    for problem in problems:
        print(f"FAIL {problem}")
    print(f"scanned {len(scanned) + len(contract.families)} items: {'PASS' if not problems else f'FAIL ({len(problems)})'}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
