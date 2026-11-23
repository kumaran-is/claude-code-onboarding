# Angular E2E — legacy Cypress pointer

E2E for Angular web apps in this workspace uses **Playwright** (`@playwright/test` for committed
suites, `playwright-cli` for interactive QA) — see the `browser-testing` skill. Tool choice per
target is defined in `.claude/rules/testing-tool-selection.md`.

Existing Cypress suites may stay until migrated; do not add new Cypress specs. Unit/component tests
use Vitest via `ng test` ([testing-vitest.md](testing-vitest.md)).
