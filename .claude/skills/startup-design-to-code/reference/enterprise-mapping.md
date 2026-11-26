# Enterprise standard → existing toolkit

Do not copy the 30-section enterprise document into always-loaded rules. Apply it by routing to files that already exist.

| Standard (v1.2) | Toolkit home |
|---|---|
| §1–2 north star / invariants | `design-system/SKILL.md` pre-flight; `mobile-ux-principles.md` |
| §3 DESIGN.md authority | `design-md-governance.md` |
| §4 Atomic Design | `atomic-decision-tree.md` |
| §5 Smart/dumb | `atomic-decision-tree.md`; Angular `smart-dumb-components.md` |
| §6 truthful async UI | `interaction-contracts.md` §6b |
| §7 refresh / offline | `interaction-contracts.md` §6c |
| §8 journeys | this skill G0/G2; `feature-forge` if a backlog is requested |
| §9–13 color, type, space, icons, motion | `token-governance.md`; Flutter `ui-standards-tokens` |
| §14 accessibility | `accessibility-audit` + `accessibility-auditor` |
| §15 forms / trust | `interaction-contracts.md`; `web-security.md` for `/login` |
| §16 performance | `web-performance-optimization`; Flutter polish refs |
| §17–18 framework + UI library | `/scaffold-flutter-app`, `/scaffold-angular-app`, `/scaffold-react-app` |
| §19–20 DoD / tests | `/verify`; Playwright vs Maestro per `testing-tool-selection.md` |
| §22 governance | `/lint-design-system`; `ui-standards-expert`; `design-system-reviewer` |
| §30 Google Labs DESIGN.md | this skill G4; https://github.com/google-labs-code/design.md |

Reviewers to dispatch (existing, do not create new ones): `ui-standards-expert`, `design-system-reviewer`, `accessibility-auditor`, `architect`, `code-reviewer`, `security-reviewer`, `riverpod-reviewer` (Flutter), `reality-checker` before merge of UI.
