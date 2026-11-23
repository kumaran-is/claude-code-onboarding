# GenUI Contract CI (A2UI 1.0 target, v0.9.x compatibility) — GitHub Actions example

Reusable example for a project that ships generative UI on one framework-neutral A2UI catalog (1.0 target, v0.9.x compatibility path) with Angular, React and/or Flutter renderers. **Documentation only**: this repo has no live workflow for it; copy it to `.github/workflows/genui-contract.yml` in the consuming project and adjust the paths. GitHub Actions only.

Rules it encodes (`.claude/rules/genui-a2ui.md`, `.claude/rules/hook-and-gate-authoring.md`):

- **Path-filtered**: each platform job runs only when its files, the contract, or the workflow change. A platform job is skipped when its directory is absent, **unless the contract declares the platform** (`x-genui.platforms`): then a missing app fails the `declared-platforms` job.
- **Every gate reads its tool's own exit code**: no `| tail` after a gate, no `|| true` on a gate.
- **Zero inputs is a failure**: the validator must report `scanned N items: PASS` with N > 1; a test run that executed zero tests fails.
- **Tool routing** (`.claude/rules/testing-tool-selection.md`): web UI and a11y use Playwright + `@axe-core/playwright`; Flutter here runs `flutter analyze` / `flutter test` only. Flutter Android/iOS device E2E is Maestro only and needs an emulator or simulator: run it in a separate job you own (not shown); without one it is BLOCKED, never replaced by a browser run.

Action pins (resolved 2026-11-23 with `gh api repos/<owner>/<repo>/commits/<tag>`; re-resolve before copying): `actions/checkout` v7.0.1, `actions/setup-node` v7.1.0, `dorny/paths-filter` v4.0.3, `astral-sh/setup-uv` v10.4.0, `subosito/flutter-action` v2.23.0.

## Layout assumed

```
contract/                  catalog/ (canonical-catalog-v1_0.json and/or canonical-catalog.json + catalog-schema.json, vendor/a2ui-v1_0 + vendor/a2ui-v0_9) and fixtures/ (valid*, invalid*, actions*, streams*)
tools/genui/validate_a2ui_contract.py   vendored from .claude/skills/genui-contract/scripts/ (PEP 723, pinned deps)
tools/genui/audit-parity.sh             the script block from .claude/commands/audit-a2ui-parity.md
web-angular/  web-react/  mobile/       renderer apps (any subset)
services/agent/                         backend adapter (Python, uv)
```

## Workflow

```yaml
name: genui-contract

on:
  pull_request:
    paths:
      - "contract/**"
      - "tools/genui/**"
      - "web-angular/**"
      - "web-react/**"
      - "mobile/**"
      - "services/agent/**"
      - ".claude/hooks/**"
      - "**/*.md"
      - ".github/workflows/genui-contract.yml"

permissions:
  contents: read

concurrency:
  group: genui-${{ github.ref }}
  cancel-in-progress: true

jobs:
  changes:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
    outputs:
      contract: ${{ steps.f.outputs.contract }}
      angular: ${{ steps.f.outputs.angular }}
      react: ${{ steps.f.outputs.react }}
      flutter: ${{ steps.f.outputs.flutter }}
      backend: ${{ steps.f.outputs.backend }}
      hooks: ${{ steps.f.outputs.hooks }}
      docs: ${{ steps.f.outputs.docs }}
      has_angular: ${{ steps.present.outputs.angular }}
      has_react: ${{ steps.present.outputs.react }}
      has_flutter: ${{ steps.present.outputs.flutter }}
      has_backend: ${{ steps.present.outputs.backend }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - id: present
        name: Which platform apps exist (hashFiles is not allowed in a job-level if)
        run: |
          has() { if [ -f "$1" ]; then echo true; else echo false; fi; }
          {
            echo "angular=$(has web-angular/angular.json)"
            echo "react=$(has web-react/package.json)"
            echo "flutter=$(has mobile/pubspec.yaml)"
            echo "backend=$(has services/agent/pyproject.toml)"
          } >> "$GITHUB_OUTPUT"
      - id: f
        uses: dorny/paths-filter@ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d # v4.0.3
        with:
          filters: |
            contract: ['contract/**', 'tools/genui/**', '.github/workflows/genui-contract.yml']
            angular: ['web-angular/**', 'contract/**', '.github/workflows/genui-contract.yml']
            react: ['web-react/**', 'contract/**', '.github/workflows/genui-contract.yml']
            flutter: ['mobile/**', 'contract/**', '.github/workflows/genui-contract.yml']
            backend: ['services/agent/**', 'contract/**', '.github/workflows/genui-contract.yml']
            hooks: ['.claude/hooks/**']
            docs: ['**/*.md']

  contract:
    needs: changes
    if: needs.changes.outputs.contract == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@1db35dd8eee11c5894872e0b383ae6c406cf738d # v10.4.0
      - name: Catalog schema, fixtures, golden actions, stream replay
        run: |
          uv run --python 3.14 tools/genui/validate_a2ui_contract.py --root contract > validate.log 2>&1
          rc=$?
          cat validate.log
          [ "$rc" -eq 0 ] || exit "$rc"
          grep -Eq '^scanned ([2-9]|[1-9][0-9]+) items: PASS$' validate.log || { echo "validator saw no inputs"; exit 1; }
      - name: Validator negative control (planted violations must be caught)
        run: uv run --python 3.14 tools/genui/validate_a2ui_contract.py --selftest
      - name: One declared protocol version per fixture, each accepted by a catalog
        run: |
          python3 - <<'PY'
          import json, pathlib, sys
          accepted, bad = set(), []
          for cat in pathlib.Path("contract/catalog").glob("*catalog*.json"):
              doc = json.loads(cat.read_text())
              policy = doc.get("x-genui") or doc.get("metadata", {}).get("extensions", {}).get("genui_contract")
              if policy:  # v0.9.x: x-genui; 1.0: metadata.extensions.genui_contract
                  accepted |= set(policy.get("acceptedWireVersions", []))
          if not accepted:
              sys.exit("no catalog policy with acceptedWireVersions found")
          for f in pathlib.Path("contract/fixtures").glob("valid*/*.json"):
              versions = {m.get("version") for m in json.loads(f.read_text()).get("messages", []) if isinstance(m, dict)}
              if len(versions) != 1 or not versions <= accepted:
                  bad.append(f"{f}: {sorted(map(str, versions))}")
          print("protocol drift:", bad) if bad else print(f"protocol {sorted(accepted)}: PASS")
          sys.exit(1 if bad else 0)
          PY
      - name: Action payload compatibility with the base branch
        env:
          BASE_REF: ${{ github.base_ref }}
        run: |
          # Golden action payloads from the base branch must still validate against this branch's contract.
          git fetch --no-tags --depth=1 origin "$BASE_REF"
          if ! git cat-file -e "origin/$BASE_REF:contract/fixtures/actions" 2>/dev/null; then echo "no base action fixtures: NOT RUN"; exit 0; fi
          rm -rf /tmp/base && mkdir -p /tmp/base
          git archive "origin/$BASE_REF" contract/fixtures | tar -x -C /tmp/base
          cp -R contract/catalog /tmp/base/contract/catalog
          uv run --python 3.14 tools/genui/validate_a2ui_contract.py --root /tmp/base/contract

  declared-platforms:
    needs: changes
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - name: Every declared platform has an app
        run: |
          python3 - <<'PY'
          import json, pathlib, sys
          roots = {"angular": "web-angular/angular.json", "react": "web-react/package.json", "flutter": "mobile/pubspec.yaml"}
          cat = next(p for p in pathlib.Path("contract/catalog").glob("*catalog*.json") if "x-genui" in json.loads(p.read_text()))
          declared = json.loads(cat.read_text())["x-genui"].get("platforms", [])
          missing = [p for p in declared if not pathlib.Path(roots[p]).exists()]
          print("declared:", declared or "none (absent platforms are skipped)")
          sys.exit(f"declared platform without an app: {missing}" if missing else 0)
          PY
      - name: Parity (declared platforms fail, undeclared are NOT RUN)
        run: bash tools/genui/audit-parity.sh

  security-negative-controls:
    needs: changes
    if: needs.changes.outputs.angular == 'true' || needs.changes.outputs.react == 'true' || needs.changes.outputs.flutter == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - name: No raw HTML / code execution sinks in GenUI renderer code
        run: |
          files=$(git ls-files | grep -Ei '(/a2ui/|/genui/)' | grep -E '\.(ts|tsx|html|dart)$' | grep -Ev '(\.spec\.|\.test\.|_test\.dart)' || true)
          [ -n "$files" ] || { echo "no GenUI renderer files found"; exit 1; }
          echo "$files" | wc -l | xargs echo "scanned files:"
          hits=$(echo "$files" | xargs grep -nE 'innerHTML|dangerouslySetInnerHTML|bypassSecurityTrust|(^|[^.A-Za-z_])eval\(|new Function\(|WebViewWidget|loadHtmlString' || true)
          if [ -n "$hits" ]; then echo "$hits"; exit 1; fi
      - name: No protocol drift (v0.8 entry points, discontinued genui package, files mixing /v1_0 and /v0_9)
        run: |
          files=$(git ls-files | grep -Ei '(a2ui|genui)' | grep -E '\.(ts|tsx|dart)$' || true)
          hits=$(echo "$files" | xargs grep -nE "@a2ui/[a-z_]+/v0_8|package:genui/" || true)
          mixed=$(for f in $files; do grep -qE '@a2ui/[a-z_]+/v1_0' "$f" && grep -qE '@a2ui/[a-z_]+/v0_9' "$f" && echo "$f: mixes /v1_0 and /v0_9"; done || true)
          if [ -n "$hits$mixed" ]; then printf '%s\n%s\n' "$hits" "$mixed"; exit 1; fi

  angular:
    needs: changes
    if: needs.changes.outputs.angular == 'true' && needs.changes.outputs.has_angular == 'true'
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web-angular
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version-file: web-angular/.nvmrc
          cache: npm
          cache-dependency-path: web-angular/package-lock.json
      - run: npm ci
      - name: Type-check (app and spec configs; the root tsconfig checks nothing)
        run: npx tsc -p tsconfig.app.json --noEmit && npx tsc -p tsconfig.spec.json --noEmit
      - name: Unit tests (renderer, unknown component, action allowlist, streaming)
        run: npx ng test --watch=false
      - run: npx playwright install --with-deps chromium
      - name: E2E + axe on the GenUI page (web target), including @genui-stream cancel cases
        run: npx playwright test --grep "@genui"

  react:
    needs: changes
    if: needs.changes.outputs.react == 'true' && needs.changes.outputs.has_react == 'true'
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web-react
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version-file: web-react/.nvmrc
          cache: npm
          cache-dependency-path: web-react/package-lock.json
      - run: npm ci
      - run: npx tsc -b
      - name: Unit tests (Vitest + Testing Library)
        run: npx vitest run
      - run: npx playwright install --with-deps chromium
      - name: E2E + axe on the GenUI page (web target), including @genui-stream cancel cases
        run: npx playwright test --grep "@genui"

  flutter:
    needs: changes
    if: needs.changes.outputs.flutter == 'true' && needs.changes.outputs.has_flutter == 'true'
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2 # v2.23.0
        with:
          flutter-version-file: mobile/pubspec.yaml   # reads environment.flutter, e.g. 3.50.1
          cache: true
      - run: flutter pub get --enforce-lockfile
      - run: dart format --output=none --set-exit-if-changed .
      # Exits 1 on any info too, e.g. a flutter/material.dart import outside the
      # A2UI bridge file (a2ui_flutter 0.5.0 still builds on it; the app uses material_ui).
      - run: flutter analyze
      - name: Widget, security and a11y-guideline tests (device E2E is Maestro, separate job)
        run: flutter test

  backend:
    needs: changes
    if: needs.changes.outputs.backend == 'true' && needs.changes.outputs.has_backend == 'true'
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: services/agent
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@1db35dd8eee11c5894872e0b383ae6c406cf738d # v10.4.0
      - run: uv sync --locked
      - run: uv run ruff check .
      - name: Action authz (401/403), idempotency, approval, emitted messages validate, stream cancel
        run: uv run pytest

  hook-selftests:
    needs: changes
    if: needs.changes.outputs.hooks == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - name: GenUI advisory hook selftest
        run: bash .claude/hooks/post-edit-genui-advisory.sh --selftest

  broken-references:
    needs: changes
    if: needs.changes.outputs.docs == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - name: Relative markdown links resolve
        run: |
          python3 - <<'PY'
          import pathlib, re, subprocess, sys
          files = [pathlib.Path(f) for f in subprocess.run(["git", "ls-files", "*.md"], capture_output=True, text=True, check=True).stdout.split()]
          if not files: sys.exit("no markdown files found")
          bad = []
          for f in files:
              for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", f.read_text(errors="ignore")):
                  if "://" in target or target.startswith("mailto:"): continue
                  if not (f.parent / target).exists(): bad.append(f"{f}: {target}")
          print(f"checked {len(files)} files")
          print("\n".join(bad)); sys.exit(1 if bad else 0)
          PY
```

## Notes

- **Required test names** the platform jobs rely on are listed in `/validate-genui-feature` (unknown component, malformed payload, action allowlist, payload schema, streaming + cancel, a11y). Tag the Playwright specs `@genui` and the stream cases `@genui-stream` so `--grep` selects them; a `--grep` that matches nothing makes Playwright exit non-zero ("No tests found"), which is the wanted failure.
- **Backend tests** must post an unauthenticated action (401), an action for another principal (403 or 404), a repeated idempotency key (one side effect), and a `requiresHumanApproval` action without confirmation (rejected).
- **Flutter device E2E**: add a macOS or emulator job that runs `maestro test .maestro/` on a booted simulator or Android emulator. Without a device, report it BLOCKED; a browser run is not evidence about the mobile app.
- **Validated 2026-11-23**: the YAML above parses with PyYAML 6.0.3 and passes `actionlint` 1.7.12 (exit 0; a misspelled `needs:` planted as a negative control exits 1). actionlint's shellcheck pass was NOT RUN (shellcheck not installed). The workflow has not run on GitHub-hosted runners (no consuming project in this repo).
