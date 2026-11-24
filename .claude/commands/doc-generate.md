---
description: Generate comprehensive documentation from existing code — API specs,
  architecture diagrams, README, docstrings, and CI/CD doc pipeline. Orchestrates
  existing skills and agents.
argument-hint: "[path or service name, e.g. 'src/' or 'nestjs-api']"
allowed-tools: Bash, Read, Glob, Grep, Write, Edit
disable-model-invocation: true
---

# Documentation Generation

Generate or refresh all documentation for the target project or path.

Target: `$ARGUMENTS` (default: current directory).

## Step 1: Detect project type

```bash
TARGET="$ARGUMENTS"; [ -n "$TARGET" ] || TARGET="."   # `${ARGUMENTS:-.}` is never substituted by Claude Code
HAS_JAVA=false; HAS_NODE=false; HAS_PYTHON=false; HAS_FLUTTER=false

[ -f "$TARGET/pom.xml" ] && HAS_JAVA=true && echo "Java/Spring detected"
[ -f "$TARGET/package.json" ] && HAS_NODE=true && echo "NestJS/Angular detected"
[ -f "$TARGET/pyproject.toml" ] || [ -f "$TARGET/requirements.txt" ] && HAS_PYTHON=true && echo "Python detected"
[ -f "$TARGET/pubspec.yaml" ] && HAS_FLUTTER=true && echo "Flutter detected"
```

## Step 2: API documentation

Load the `openapi-spec-generation` skill, then:

- **Java/Spring Boot**: Scan controllers for `@RestController`, `@GetMapping`, `@PostMapping`, etc. Extract route paths, request/response types, and generate or update `docs/api/openapi.yaml`.
- **NestJS**: Scan `*.controller.ts` for `@Controller`, `@Get`, `@Post` decorators. Extract DTOs and generate or update `docs/api/openapi.yaml`.
- **Python FastAPI**: Confirm `/openapi.json` is served at runtime (built-in). Export the spec with:
  ```bash
  curl -s http://localhost:8000/openapi.json > docs/api/openapi.json 2>/dev/null || echo "[NOTE] Start the service first to export live spec"
  ```
- **Flutter**: Skip API generation (client-side).

## Step 3: Architecture diagram

Dispatch `mermaid-expert` agent to create a system diagram from the project structure:

- Scan top-level directories and entry points
- Identify key services, controllers, models, and external dependencies
- Produce a `graph TB` diagram showing components and data flows

Output to `docs/diagrams/[detected-service-name]-architecture.md`.

Keep existing diagrams current: a diagram's file name starts with the folder it describes (`src/auth/` → `docs/diagrams/auth-flow.md`). When a change touches files under a folder that already has a diagram, update that diagram in the same change, not in a follow-up. A new service, flow or integration with no diagram gets `docs/diagrams/<feature>-flow.md` (Mermaid).

## Step 4: README

Check if `README.md` exists:

```bash
ls $TARGET/README.md 2>/dev/null && echo "README exists" || echo "README missing"
```

- **If missing**: Generate from the stack-specific template in `skills/documentation-generation/references/readme-templates.md`.
- **If exists**: Check for stale sections:
  - Missing environment variables (grep `process.env` / `os.environ` / `@Value` against README)
  - Outdated build commands (compare against `package.json scripts` / `pom.xml` / `pyproject.toml`)
  - Report stale sections without overwriting (present diff to user for review)

## Step 5: Docstring coverage

Scan for public functions/methods lacking docstrings:

```bash
# Java: public methods without Javadoc
grep -rn "public " $TARGET --include="*.java" | grep -v "^\s*//" | head -20

# TypeScript: exported functions without JSDoc
grep -n "^export " $TARGET --include="*.ts" -r | head -20

# Python: def without following docstring
grep -n "def " $TARGET --include="*.py" -r | head -20

# Dart: public methods without ///
grep -n "^\s*[A-Z].*(" $TARGET --include="*.dart" -r | grep -v "///" | head -20
```

Load `skills/documentation-generation/references/docstring-patterns.md` for the correct docstring format per stack. Report gaps — do NOT auto-generate docstrings without user approval (context required).

## Step 6: Summary

Print final report:

```
DOCUMENTATION GENERATION COMPLETE
===================================
Project type: [detected]

Generated/Updated:
  [ ] docs/api/openapi.yaml     — [status]
  [ ] docs/diagrams/[name].md   — [status]
  [ ] README.md                 — [status: created/updated/stale sections flagged]

Docstring gaps:
  [N] public functions/methods missing docstrings
  Run with approval to generate: load skills/documentation-generation/references/docstring-patterns.md

CI/CD pipeline:
  Reference: .claude/skills/documentation-generation/references/cicd-doc-pipeline.md
  Add to your pipeline to auto-generate docs on every push to main.
```

$ARGUMENTS
