# /// script
# requires-python = ">=3.12"
# dependencies = ["jsonschema==4.26.0", "referencing==0.37.0"]
# ///
"""Deterministic validator for the canonical A2UI v0.9 GenUI contract.

Checks, in order:
  1. the catalog against catalog-schema.json, the JSON Schema 2020-12 metaschema
     and the catalog's own cross-references (actions, anyComponent);
  2. every fixtures/valid/*.json message sequence is accepted;
  3. every fixtures/invalid/*.json sequence is rejected with its expectedError code;
  4. every fixtures/actions/*.json golden client->server action is reproduced
     byte-for-byte (canonical form) from its surface fixture plus the user edits;
  5. every fixtures/streams/*.jsonl stream gives the errors and final state in
     its .expect.json sidecar.

Exit 0 when everything passes, 1 otherwise. `--selftest` plants violations and
exits 0 only if every planted violation is caught.

Run: uv run validate.py            (layout auto-detected)
     uv run validate.py --selftest
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

A2UI_BASE = "https://a2ui.org/specification/v0_9/"
MESSAGE_KEYS = ("createSurface", "updateComponents", "updateDataModel", "deleteSurface")
TIMESTAMP_SENTINEL = "1970-01-01T00:00:00.000Z"
RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?Z$")
POINTER = re.compile(r"^(/([^~/]|~[01])*)*$")


class ContractError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class Paths:
    catalog: Path
    catalog_schema: Path
    vendor: Path
    fixtures: Path

    @staticmethod
    def detect(script_dir: Path) -> Paths:
        if (script_dir / "catalog").is_dir():  # shared layout: validate.py beside catalog/ and fixtures/
            return Paths(script_dir / "catalog/canonical-catalog.json", script_dir / "catalog/catalog-schema.json",
                         script_dir / "catalog/vendor/a2ui-v0_9", script_dir / "fixtures")
        ref = script_dir.parent / "reference"  # skill layout: scripts/ beside reference/
        return Paths(ref / "canonical-catalog.json", ref / "catalog-schema.json", ref / "vendor/a2ui-v0_9", ref / "fixtures")


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
    components: dict[str, dict] = field(default_factory=dict)
    data: dict = field(default_factory=dict)


class Contract:
    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self.catalog = load_json(paths.catalog)
        self.catalog_schema = load_json(paths.catalog_schema)
        self.ext = self.catalog["x-genui"]
        self.limits = self.ext["limits"]
        self.forbidden = [re.compile(p) for p in self.ext["forbiddenStringPatterns"]]
        vendor = {name: load_json(paths.vendor / name) for name in ("server_to_client.json", "client_to_server.json", "common_types.json")}
        resources = [
            (A2UI_BASE + name, Resource.from_contents(doc, default_specification=DRAFT202012)) for name, doc in vendor.items()
        ]
        catalog_resource = Resource.from_contents(self.catalog, default_specification=DRAFT202012)
        resources += [
            (self.catalog["$id"], catalog_resource),
            (A2UI_BASE + "catalog.json", catalog_resource),  # the wire schema's `catalog.json` slot
            (self.catalog_schema["$id"], Resource.from_contents(self.catalog_schema, default_specification=DRAFT202012)),
        ]
        self.registry: Registry = Registry().with_resources(resources)
        fmt = FormatChecker()
        self.server_v = Draft202012Validator(vendor["server_to_client.json"], registry=self.registry, format_checker=fmt)
        self.client_v = Draft202012Validator(vendor["client_to_server.json"], registry=self.registry, format_checker=fmt)
        self.catalog_v = Draft202012Validator(self.catalog_schema, registry=self.registry, format_checker=fmt)

    # ---------- catalog ----------
    def check_catalog(self) -> list[str]:
        problems = [f"catalog-schema: {e.json_path}: {e.message}" for e in self.catalog_v.iter_errors(self.catalog)]
        try:
            Draft202012Validator.check_schema(self.catalog)
        except Exception as exc:  # SchemaError carries the detail; reported, not swallowed
            problems.append(f"metaschema: {exc}")
        actions = self.ext["actions"]
        used: set[str] = set()
        listed = {item["$ref"].rsplit("/", 1)[-1] for item in self.catalog["$defs"]["anyComponent"]["oneOf"]}
        for name, comp in self.catalog["components"].items():
            allowed = set(comp["x-genui"]["allowedActions"])
            in_schema = set(_event_enums(comp))
            if allowed != in_schema:
                problems.append(f"{name}: allowedActions {sorted(allowed)} != schema enums {sorted(in_schema)}")
            for action in allowed - set(actions):
                problems.append(f"{name}: action {action} has no x-genui.actions entry")
            used |= allowed
            if name not in listed:
                problems.append(f"{name}: missing from $defs.anyComponent")
        for action, spec in actions.items():
            if action not in used:
                problems.append(f"action {action} is not allowed on any component")
            try:
                Draft202012Validator.check_schema(spec["payloadSchema"])
            except Exception as exc:
                problems.append(f"action {action}: payloadSchema invalid: {exc}")
        return problems

    # ---------- server -> client ----------
    def apply(self, surfaces: dict[str, Surface], message: Any) -> None:
        """Validates and applies one message atomically; raises ContractError and leaves state unchanged."""
        if not isinstance(message, dict):
            raise ContractError("MALFORMED_MESSAGE", "message is not a JSON object")
        size = len(json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode())
        if size > self.limits["maxMessageBytes"]:
            raise ContractError("MESSAGE_TOO_LARGE", f"{size} bytes")
        if "version" not in message:
            raise ContractError("MALFORMED_MESSAGE", "missing version")
        if message["version"] not in self.ext["acceptedWireVersions"]:
            raise ContractError("UNSUPPORTED_VERSION", repr(message["version"]))
        bodies = [k for k in message if k != "version"]
        if len(bodies) != 1 or bodies[0] not in MESSAGE_KEYS:
            raise ContractError("MALFORMED_MESSAGE", f"expected exactly one of {MESSAGE_KEYS}, got {bodies}")
        kind = bodies[0]
        body = message[kind]
        if kind == "updateComponents" and isinstance(body, dict):
            self._precheck_components(body.get("components"))
        self._check_strings(message, "")
        errors = sorted(self.server_v.iter_errors(message), key=lambda e: list(e.absolute_path))
        if errors:
            raise ContractError("SCHEMA_INVALID", "; ".join(f"{list(e.absolute_path)}: {e.message[:160]}" for e in errors[:3]))
        sid = body["surfaceId"]
        if kind == "createSurface":
            if sid in surfaces:
                raise ContractError("DUPLICATE_SURFACE", sid)
            if body["catalogId"] != self.catalog["catalogId"]:
                raise ContractError("UNSUPPORTED_CATALOG", body["catalogId"])
            surfaces[sid] = Surface(body["catalogId"])
            return
        if sid not in surfaces:
            raise ContractError("SURFACE_NOT_FOUND", f"{kind} for {sid} before createSurface")
        if kind == "deleteSurface":
            del surfaces[sid]
            return
        surface = surfaces[sid]
        if kind == "updateDataModel":
            surface.data = pointer_set(copy.deepcopy(surface.data), body.get("path"), body.get("value"), "value" not in body)
            return
        ids = [c["id"] for c in body["components"]]
        if len(ids) != len(set(ids)):
            raise ContractError("DUPLICATE_COMPONENT_ID", str(ids))
        merged = {**surface.components, **{c["id"]: c for c in body["components"]}}
        self._check_graph(merged, complete=False)
        surface.components = merged

    def _precheck_components(self, components: Any) -> None:
        if not isinstance(components, list):
            return
        known = self.catalog["components"]
        for comp in components:
            if not isinstance(comp, dict):
                continue
            name = comp.get("component")
            if name not in known:
                raise ContractError("UNKNOWN_COMPONENT", f"{name!r} (id {comp.get('id')!r})")
            allowed = set(known[name]["x-genui"]["allowedActions"])
            for node in _walk(comp):
                if isinstance(node, dict) and "functionCall" in node and set(node) == {"functionCall"}:
                    raise ContractError("FUNCTION_ACTION_FORBIDDEN", f"{comp.get('id')}: client-side functionCall actions are not allowed")
                if isinstance(node, dict) and isinstance(node.get("event"), dict):
                    action = node["event"].get("name")
                    if action not in allowed:
                        raise ContractError("ACTION_NOT_ALLOWED", f"{action!r} on {name} {comp.get('id')!r}")

    def _check_strings(self, node: Any, where: str) -> None:
        if isinstance(node, str):
            if len(node) > self.limits["maxStringLength"]:
                raise ContractError("STRING_TOO_LONG", where)
            for pattern in self.forbidden:
                if pattern.search(node):
                    raise ContractError("UNSAFE_CONTENT", f"{where}: matches {pattern.pattern}")
        elif isinstance(node, dict):
            for key, child in node.items():
                self._check_strings(child, f"{where}/{key}")
        elif isinstance(node, list):
            for index, child in enumerate(node):
                self._check_strings(child, f"{where}/{index}")

    def _check_graph(self, components: dict[str, dict], complete: bool) -> None:
        if len(components) > self.limits["maxComponentsPerSurface"]:
            raise ContractError("TOO_MANY_COMPONENTS", str(len(components)))
        if complete and "root" not in components:
            raise ContractError("MISSING_ROOT", "no component with id 'root'")
        max_depth = self.limits["maxDepth"]

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

    def finish(self, surfaces: dict[str, Surface]) -> None:
        for surface in surfaces.values():
            self._check_graph(surface.components, complete=True)

    # ---------- client -> server ----------
    def build_action(self, surface_id: str, surface: Surface, component_id: str, action_pointer: str) -> dict:
        comp = surface.components.get(component_id)
        if comp is None:
            raise ContractError("SURFACE_NOT_FOUND", f"component {component_id}")
        action = pointer_get(comp, action_pointer)
        event = action["event"]
        context = {}
        for key, value in event.get("context", {}).items():
            context[key] = pointer_get(surface.data, value["path"]) if isinstance(value, dict) else value
        message = {"version": "v0.9", "action": {"name": event["name"], "surfaceId": surface_id,
                                                  "sourceComponentId": component_id, "timestamp": TIMESTAMP_SENTINEL, "context": context}}
        self.check_action(message, comp)
        return message

    def check_action(self, message: dict, source: dict | None) -> None:
        errors = list(self.client_v.iter_errors(message))
        if errors:
            raise ContractError("SCHEMA_INVALID", errors[0].message[:200])
        act = message["action"]
        if not RFC3339_UTC.match(act["timestamp"]):
            raise ContractError("BAD_TIMESTAMP", act["timestamp"])
        datetime.fromisoformat(act["timestamp"].replace("Z", "+00:00"))
        spec = self.ext["actions"].get(act["name"])
        if spec is None:
            raise ContractError("ACTION_NOT_ALLOWED", act["name"])
        if source is not None and act["name"] not in self.catalog["components"][source["component"]]["x-genui"]["allowedActions"]:
            raise ContractError("ACTION_NOT_ALLOWED", f"{act['name']} from {source['component']}")
        payload_errors = list(Draft202012Validator(spec["payloadSchema"]).iter_errors(act["context"]))
        if payload_errors:
            raise ContractError("ACTION_PAYLOAD_INVALID", payload_errors[0].message[:200])
        canonical(message)


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


def run_sequence(contract: Contract, messages: list[Any]) -> dict[str, Surface]:
    surfaces: dict[str, Surface] = {}
    for index, message in enumerate(messages):
        try:
            contract.apply(surfaces, message)
        except ContractError as exc:
            raise ContractError(exc.code, f"message {index}: {exc.detail}") from exc
    contract.finish(surfaces)
    return surfaces


def check_fixtures(contract: Contract, out: list[str]) -> list[str]:
    problems: list[str] = []
    fx = contract.paths.fixtures
    for path in sorted((fx / "valid").glob("*.json")):
        out.append(f"valid    {path.name}")
        try:
            run_sequence(contract, load_json(path)["messages"])
        except ContractError as exc:
            problems.append(f"valid/{path.name}: rejected: {exc}")
    for path in sorted((fx / "invalid").glob("*.json")):
        out.append(f"invalid  {path.name}")
        doc = load_json(path)
        try:
            run_sequence(contract, doc["messages"])
            problems.append(f"invalid/{path.name}: accepted, expected {doc['expectedError']}")
        except ContractError as exc:
            if exc.code != doc["expectedError"]:
                problems.append(f"invalid/{path.name}: got {exc.code}, expected {doc['expectedError']} ({exc.detail})")
    for path in sorted((fx / "actions").glob("*.json")):
        out.append(f"action   {path.name}")
        problems += check_golden(contract, path, load_json(path))
    for path in sorted((fx / "streams").glob("*.jsonl")):
        out.append(f"stream   {path.name}")
        problems += check_stream(contract, path)
    if not out:
        problems.append(f"no fixtures found under {fx}")
    return problems


def check_golden(contract: Contract, path: Path, doc: dict) -> list[str]:
    name = path.name
    try:
        surfaces = run_sequence(contract, load_json(contract.paths.fixtures / doc["fixture"])["messages"])
        trigger = doc["trigger"]
        surface = surfaces[trigger["surfaceId"]]
        for edit in doc.get("edits", []):
            surface.data = pointer_set(surface.data, edit["path"], edit["value"], delete=False)
        built = contract.build_action(trigger["surfaceId"], surface, trigger["sourceComponentId"], trigger["actionPointer"])
        expected = copy.deepcopy(doc["expected"])
        contract.check_action(expected, surface.components[trigger["sourceComponentId"]])
        expected["action"]["timestamp"] = TIMESTAMP_SENTINEL  # timestamp is normalised before comparison
    except ContractError as exc:
        return [f"actions/{name}: {exc}"]
    problems = []
    if canonical(built) != canonical(expected):
        problems.append(f"actions/{name}: built {canonical(built)} != expected {canonical(expected)}")
    if canonical(built) != doc["canonical"]:
        problems.append(f"actions/{name}: canonical string differs from the recorded golden")
    return problems


def check_stream(contract: Contract, path: Path) -> list[str]:
    expect = load_json(path.with_suffix(".expect.json"))
    surfaces: dict[str, Surface] = {}
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
            contract.apply(surfaces, message)
        except ContractError as exc:
            errors.append({"line": number, "code": exc.code})
    problems = []
    if errors != expect["errors"]:
        problems.append(f"streams/{path.name}: errors {errors} != expected {expect['errors']}")
    state = {sid: {"componentIds": sorted(s.components), "dataModel": s.data} for sid, s in surfaces.items()}
    if canonical(state) != canonical(expect["finalState"]):
        problems.append(f"streams/{path.name}: final state {canonical(state)} != expected {canonical(expect['finalState'])}")
    return problems


def selftest(paths: Paths) -> int:
    contract = Contract(paths)
    base = load_json(paths.fixtures / "valid/action-card.json")["messages"]
    card = next(c for m in base if "updateComponents" in m for c in m["updateComponents"]["components"] if c["id"] == "root")

    def with_card(mutate) -> list:
        messages = copy.deepcopy(base)
        target = next(c for m in messages if "updateComponents" in m for c in m["updateComponents"]["components"] if c["id"] == "root")
        mutate(target, messages)
        return messages

    planted = {
        "UNKNOWN_COMPONENT": with_card(lambda c, m: c.update(component="HtmlBlock")),
        "UNSUPPORTED_VERSION": with_card(lambda c, m: m[1].update(version="v0.8")),
        "UNSAFE_CONTENT": with_card(lambda c, m: c.update(body="javascript:alert(1)")),
        "ACTION_NOT_ALLOWED": with_card(lambda c, m: c["actions"][0]["action"]["event"].update(name="approval.approve")),
        "SCHEMA_INVALID": with_card(lambda c, m: c.pop("title")),
        "SURFACE_NOT_FOUND": with_card(lambda c, m: m.pop(0)),
    }
    failures = []
    if card.get("component") != "ActionCard":
        failures.append("selftest base fixture changed: root is not an ActionCard")
    for code, messages in planted.items():
        try:
            run_sequence(contract, messages)
            failures.append(f"planted {code}: accepted")
        except ContractError as exc:
            if exc.code != code:
                failures.append(f"planted {code}: got {exc.code}")
            else:
                print(f"selftest caught {code}")
    bad_catalog = copy.deepcopy(contract.catalog)
    del bad_catalog["components"]["ApprovalForm"]["x-genui"]
    if not list(contract.catalog_v.iter_errors(bad_catalog)):
        failures.append("planted catalog without x-genui: accepted")
    else:
        print("selftest caught catalog component without x-genui")
    bad_platforms = copy.deepcopy(contract.catalog)
    bad_platforms["x-genui"]["platforms"] = ["angular", "swiftui"]
    if not list(contract.catalog_v.iter_errors(bad_platforms)):
        failures.append("planted unknown platform 'swiftui': accepted")
    else:
        print("selftest caught unknown platform value")
    golden_path = next(iter(sorted((paths.fixtures / "actions").glob("*.json"))))
    golden = load_json(golden_path)
    golden["expected"]["action"]["context"]["planted"] = "x"
    if not check_golden(contract, golden_path, golden):
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
    parser.add_argument("--root", type=Path, help="directory holding catalog/ and fixtures/ (shared layout) or scripts/ (skill layout)")
    args = parser.parse_args()
    paths = Paths.detect((args.root or Path(__file__).parent).resolve())
    if args.selftest:
        return selftest(paths)
    contract = Contract(paths)
    print(f"catalog  {paths.catalog.name} ({len(contract.catalog['components'])} components, {len(contract.ext['actions'])} actions)")
    problems = contract.check_catalog()
    scanned: list[str] = []
    problems += check_fixtures(contract, scanned)
    print("\n".join(scanned))
    for problem in problems:
        print(f"FAIL {problem}")
    print(f"scanned {len(scanned) + 1} items: {'PASS' if not problems else f'FAIL ({len(problems)})'}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
