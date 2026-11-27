---
description: Deterministic parity audit of a GenUI A2UI catalog (1.0 target or v0.9.x compatibility) against its Angular, React and Flutter renderers — PASS / FAIL / BLOCKED / NOT RUN per check, failing a missing platform only when the contract declares it
argument-hint: "[path to catalog JSON, default: first **/*catalog*.json with x-genui]"
allowed-tools: Bash, Read, Glob, Grep
---

# /audit-a2ui-parity — catalog vs renderer parity

Read-only. Checks that every component ID and action name in the framework-neutral catalog is mapped by each renderer the contract **declares**, that protocol versions agree, and that the contract validates. Every line of output is `PASS`, `FAIL`, `BLOCKED` (could not run: say what is missing) or `NOT RUN` (skipped by choice: say why), from the command's own exit code. Deep review (props, states, a11y, authz) is the `genui-contract-reviewer` agent's job; this command is the fast, repeatable gate.

**Catalog:** $ARGUMENTS (default: the first `*catalog*.json` that has an `x-genui` block)

## Rules

- **Declared platforms only.** The contract declares platforms in `x-genui.platforms` (array of `angular`, `react`, `flutter`). A declared platform with no renderer root, or with an unmapped ID, is `FAIL`. An undeclared platform is `NOT RUN (not declared)`, never `FAIL`. No `x-genui.platforms` → each platform found on disk is audited and absent ones are `NOT RUN (platforms not declared in the contract)`.
- **Mapping = the ID appears as a quoted string literal** (`'ActionCard'` / `"ActionCard"`) in that platform's GenUI source (`*/a2ui/*`, `*/genui/*`, `*a2ui*`, `*genui*`, `*catalog*` files; tests excluded). This is deterministic, not proof of correct props: say so in the report.
- **Never edit files** and never install packages from this command.

## Step 1 — validate the contract

The contract validator belongs to the `genui-contract` skill. It is a PEP 723 script (pinned `jsonschema` + `referencing`, run with `uv`): it checks the catalog against its schema, accepts every `fixtures/valid/*`, rejects every `fixtures/invalid/*` with its expected error code, reproduces `fixtures/actions/*` and replays `fixtures/streams/*.jsonl`. `--root` is the directory holding `catalog/` and `fixtures/` (default: the skill's own layout). Record its own exit code:

```bash
V=.claude/skills/genui-contract/scripts/validate_a2ui_contract.py   # or the project's vendored copy
if [ -f "$V" ]; then
  uv run --python 3.14 "$V" --root "${CONTRACT_ROOT:-.}" > /tmp/genui-validate.log 2>&1; rc=$?; echo "CONTRACT SCHEMA EXIT:$rc"; tail -3 /tmp/genui-validate.log
  uv run --python 3.14 "$V" --selftest > /tmp/genui-validate-self.log 2>&1; echo "VALIDATOR SELFTEST EXIT:$?"   # proves it can fail
else echo "CONTRACT SCHEMA: BLOCKED (validator not found at $V)"; fi
```

A run whose last line does not say `scanned N items: PASS` with N > 1 is not a PASS (it saw nothing). A validator that accepts an invalid fixture is `FAIL`.

## Step 2 — parity and version checks

```bash
# A2UI parity audit. CATALOG=<path> (optional). Bash 3.2 compatible; read-only. Runs in a child bash so exit is safe.
bash <<'PARITY'
FAILED=0
CATALOG="${CATALOG:-}"
if [ -z "$CATALOG" ]; then
  for f in $(find . -name '*catalog*.json' -not -path '*/node_modules/*' -not -path '*/.dart_tool/*' -not -path '*/build/*' -not -path '*/dist/*' 2>/dev/null); do
    if grep -qE '"(x-genui|genui_contract)"' "$f"; then CATALOG="$f"; break; fi  # v0.9: x-genui; 1.0: metadata.extensions.genui_contract
  done
fi
if [ -z "$CATALOG" ] || [ ! -f "$CATALOG" ]; then echo "PARITY: BLOCKED (no catalog JSON with x-genui / genui_contract found)"; exit 1; fi
echo "Catalog: $CATALOG"
read_json() { python3 -I -c 'import json,sys
d=json.load(open(sys.argv[1])); x=d.get("x-genui") or d.get("metadata",{}).get("extensions",{}).get("genui_contract",{})
k=sys.argv[2]
if k=="components": print("\n".join(d.get("components",{}).keys()))
elif k=="actions": print("\n".join(x.get("actions",{}).keys()))
elif k=="platforms": print("\n".join(x.get("platforms",[])))
elif k=="protocol": print(x.get("protocolVersion",""))' "$CATALOG" "$1"; }
IDS=$(read_json components) || { echo "PARITY: FAIL (catalog is not valid JSON)"; exit 1; }
ACTIONS=$(read_json actions); DECLARED=$(read_json platforms); PROTO=$(read_json protocol)
[ -n "$IDS" ] || { echo "PARITY: FAIL (catalog has no components)"; exit 1; }
case "$PROTO" in 1.0|v0.9) echo "PROTOCOL catalog: PASS ($PROTO)" ;; *) echo "PROTOCOL catalog: FAIL (policy protocolVersion='$PROTO', expected 1.0 or v0.9)"; FAILED=1 ;; esac
genui_files() { # $1 root, $2 extension regex -> GenUI source files, tests excluded
  find "$1" \( -name node_modules -o -name dist -o -name build -o -name .dart_tool -o -name .angular \) -prune -o -type f -print 2>/dev/null \
    | grep -E "$2" | grep -Ei '(/a2ui/|/genui/|a2ui|genui|catalog)' | grep -Ev '(\.spec\.|\.test\.|_test\.dart|/e2e/|/test/|/__tests__/)'
}
platform_root() { # $1 platform -> first root dir
  case "$1" in
    angular) find . -maxdepth 4 -name angular.json -not -path '*/node_modules/*' 2>/dev/null | head -1 | xargs -I{} dirname {} ;;
    react) for p in $(find . -maxdepth 4 -name package.json -not -path '*/node_modules/*' 2>/dev/null); do
             if grep -qE '"react"[[:space:]]*:' "$p" && ! grep -qE '"(react-native|@angular/core)"[[:space:]]*:' "$p"; then dirname "$p"; break; fi; done ;;
    flutter) for p in $(find . -maxdepth 4 -name pubspec.yaml -not -path '*/.dart_tool/*' 2>/dev/null); do
               if grep -qE '^[[:space:]]+flutter:' "$p" || grep -qE '^flutter:' "$p"; then dirname "$p"; break; fi; done ;;
  esac
}
for plat in angular react flutter; do
  declared=0; printf '%s\n' "$DECLARED" | grep -qx "$plat" && declared=1
  root=$(platform_root "$plat")
  if [ -z "$root" ]; then
    if [ "$declared" -eq 1 ]; then echo "PARITY $plat: FAIL (declared in x-genui.platforms but no $plat app root found)"; FAILED=1
    elif [ -n "$DECLARED" ]; then echo "PARITY $plat: NOT RUN (not declared)"
    else echo "PARITY $plat: NOT RUN (platforms not declared in the contract; no $plat app found)"; fi
    continue
  fi
  if [ -n "$DECLARED" ] && [ "$declared" -eq 0 ]; then echo "PARITY $plat: NOT RUN (not declared; app found at $root)"; continue; fi
  case "$plat" in angular) ext='\.ts$' ;; react) ext='\.(ts|tsx)$' ;; flutter) ext='\.dart$' ;; esac
  files=$(genui_files "$root" "$ext")
  if [ -z "$files" ]; then echo "PARITY $plat: FAIL (no GenUI source files under $root)"; FAILED=1; continue; fi
  missing=""; n=0
  for id in $IDS $ACTIONS; do
    n=$((n + 1))
    hit=$(printf '%s\n' "$files" | while IFS= read -r f; do grep -lE "['\"]${id}['\"]" "$f" 2>/dev/null; done | head -1)
    [ -n "$hit" ] || missing="$missing $id"
  done
  if [ -z "$missing" ]; then echo "PARITY $plat: PASS ($n IDs/actions mapped under $root)"
  else echo "PARITY $plat: FAIL (unmapped:$missing)"; FAILED=1; fi
  # protocol drift in the same files
  # deprecated entry points anywhere, and files that import both the 1.0 and the v0.9 entry points (mixed versions)
  drift=$(printf '%s\n' "$files" | while IFS= read -r f; do
    grep -nE "@a2ui/[a-z_]+/v0_8|package:genui/" "$f" /dev/null 2>/dev/null
    if grep -qE "@a2ui/[a-z_]+/v1_0" "$f" && grep -qE "@a2ui/[a-z_]+/v0_9" "$f"; then echo "$f: imports both /v1_0 and /v0_9"; fi
  done)
  if [ -z "$drift" ]; then echo "PROTOCOL $plat: PASS (no v0.8 entry points, no mixed 1.0/v0.9 files)"; else echo "PROTOCOL $plat: FAIL"; printf '%s\n' "$drift" | head -10; FAILED=1; fi
done
echo "PARITY VERDICT: $([ "$FAILED" -eq 0 ] && echo PASS || echo FAIL)"; exit "$FAILED"
PARITY
echo "PARITY EXIT:$?"
```

## Step 3 — report

```
## A2UI parity audit — <catalog> — <date>
| Check | Status | Evidence |
|---|---|---|
| Contract schema (validator) | PASS/FAIL/BLOCKED | <command> → exit <n>; invalid fixtures rejected: N/N |
| Protocol catalog | ... | |
| Parity angular / react / flutter | ... | unmapped IDs or NOT RUN reason |
| Protocol per platform | ... | |
Limits: mapping is a string-literal match, not a props/state comparison — run genui-contract-reviewer for depth.
```

Overall verdict is `PASS` only when every check is `PASS` or `NOT RUN` for an undeclared platform. Any `BLOCKED` on a declared platform makes the verdict `BLOCKED`, not `PASS`.

## Related

- `.claude/rules/genui-a2ui.md` · `genui-contract-reviewer` agent · `/validate-genui-feature` (tests, a11y, streaming) · `/scaffold-genui-feature`

$ARGUMENTS
