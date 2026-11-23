---
name: documentation-generation
description: "Generate READMEs, docstrings (JSDoc, JavaDoc, Python, dartdoc), OpenAPI prose and doc pipelines. Use when asked to write or automate documentation. Not for checking existing comments (comment-analyzer)."
allowed-tools: Read, Grep, Glob, Bash, Write, Edit
metadata:
  triggers: README, docstring, documentation, API docs, JSDoc, JavaDoc, doc generation, documentation pipeline
  related-skills: openapi-spec-generation, changelog-generator, architecture-decision-records
  domain: workflow
  role: specialist
  scope: design
  output-format: document
last-reviewed: "2026-03-15"
---

## Iron Law: NO DOC GENERATION WITHOUT READING THE PROJECT-SPECIFIC TEMPLATES FIRST

Read the appropriate reference before writing any documentation.

## Process

1. **Detect stack** — Check for `pom.xml` (Java), `package.json` (NestJS/Angular), `pyproject.toml` (Python), `pubspec.yaml` (Flutter)
2. **Load template** — Read the matching section in `references/readme-templates.md`
3. **Apply docstring pattern** — Read `references/docstring-patterns.md` for the correct format per language
4. **Configure CI/CD** — Read `references/cicd-doc-pipeline.md` when setting up automated doc generation

## When to Use

- Creating or refreshing a project README
- Writing docstrings for public APIs (with `/doc-generate`)
- Setting up a CI/CD pipeline that auto-generates API docs on push
- Generating OpenAPI specs from code annotations (see `openapi-spec-generation` skill)
- Creating architecture diagrams (use `mermaid-expert` agent)

## References

| File | Content | Load When |
|------|---------|-----------|
| `references/readme-templates.md` | Stack-specific README templates for Java/Spring, NestJS, Python FastAPI, Flutter | Writing README for Java, NestJS, Python, or Flutter project |
| `references/docstring-patterns.md` | Javadoc, JSDoc, Python Google-style, Dart `///` patterns with examples | Writing Javadoc, JSDoc, Python docstrings, Dart doc comments |
| `references/cicd-doc-pipeline.md` | GitHub Actions workflow for auto-doc generation + Redocly + GitHub Pages | Setting up automated doc generation, GitHub Pages, Redocly |

## Error Handling

If project type cannot be auto-detected, ask the user to specify the stack before loading templates.
If README exists and appears current, report that and do not overwrite without explicit approval.
