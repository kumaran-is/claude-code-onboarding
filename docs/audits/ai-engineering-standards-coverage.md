# AI engineering standards coverage register

This register maps every requirement extracted from the eleven AI engineering standards (domain map: [`docs/standards/README.md`](../standards/README.md); section homes: [`standards-section-map.tsv`](standards-section-map.tsv)) to the toolkit file that implements it, and records how that was verified.

**Source of truth:** [`ai-engineering-standards-coverage.tsv`](ai-engineering-standards-coverage.tsv) holds one row per requirement (3,201 rows). This page only summarizes it. If the two disagree, the TSV wins.

| Column | Meaning |
|---|---|
| `ID` | Stable requirement ID: `<PREFIX>-<section>-<nn>`. GR uses `G<n>`/`§<n>`; `PRE` is the preamble; GOV-19 uses checklist-group codes |
| `status` | Coverage status (below) |
| `boundary` | Governance rows only: A = toolkit enforces, B = toolkit templates/guides, C = platform or organisation runs it, D = legal/regulatory. `-` on informative rows |
| `toolkit_refs` | Repo-relative `path[:line]`, `;`-separated |
| `gap` / `evidence` | What is still missing / the command or review that supports the status |
| `shared_group` | `OV-nn` when the requirement appears in more than one standard (see [Shared requirements](#shared-requirements)) |
| `notes` | Audit adjustments (downgrades, re-anchored lines, reporter disagreement) |

Statuses:

- `IMPLEMENTED_AND_TESTED`: repo code or a byte-identical copy of it was executed, or a repo validator ran over repo content (STATIC VALIDATION). The test label (UNIT, INTEGRATION, MOCKED PROVIDER, STATIC VALIDATION) is in `evidence`.
- `IMPLEMENTED_NOT_TESTED`: the repo carries the control, but nothing in the repo was executed to prove it.
- `PARTIALLY_COVERED`: part of the requirement is covered; `gap` names the rest.
- `DOCUMENTED_ONLY`: guidance exists, with no enforcing code, schema or check.
- `MISSING`: nothing in the toolkit addresses it.
- `NOT_APPLICABLE`: informative text (purpose, adoption notes, version lines).
- `REQUIRES_ENTERPRISE_ADOPTION`: only an organisation can satisfy it (ownership, ratification, contracts, funding).
- `BLOCKED`: verification could not run. No row currently has this status. A check that did not run is recorded as such in `evidence` and never counted as a pass.

A template, schema or valid record is never evidence that a control works or has been adopted. ADAPT values in the standards stay ADAPT defaults until the adopting organisation ratifies them.

## Coverage by standard

| Standard | Rows | Tested | Impl. | Partial | Doc. | Missing | N/A | Enterprise | Blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| [AI evaluation strategy](../../.claude/skills/eval-guide/SKILL.md) (`EVAL`) | 315 | 55 | 71 | 72 | 76 | 0 | 9 | 32 | 0 |
| [AI engineering guardrails](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md) (`GR`) | 185 | 4 | 117 | 19 | 19 | 0 | 7 | 19 | 0 |
| [Enterprise AI governance](../../.claude/skills/ai-governance/SKILL.md) (`GOV`) | 906 | 21 | 18 | 612 | 52 | 0 | 28 | 175 | 0 |
| [AI security threat model and red-team playbook](../../.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md) (`SEC`) | 230 | 53 | 78 | 41 | 6 | 0 | 5 | 47 | 0 |
| [Model selection and routing](../../.claude/skills/agentic-ai-dev/reference/agentic-llm-routing.md) (`MSR`) | 199 | 58 | 3 | 53 | 47 | 0 | 4 | 34 | 0 |
| [Prompt engineering and PromptOps](../../.claude/skills/prompt-engineering-patterns/SKILL.md) (`PRM`) | 236 | 73 | 17 | 54 | 64 | 0 | 10 | 18 | 0 |
| [RAG reference architecture](../../.claude/skills/rag-architect/SKILL.md) (`RAG`) | 260 | 9 | 24 | 9 | 204 | 0 | 2 | 12 | 0 |
| [Agent memory and knowledge](../../.claude/skills/agentic-ai-dev/reference/agent-memory-lifecycle.md) (`MEM`) | 199 | 1 | 22 | 64 | 98 | 0 | 6 | 8 | 0 |
| [AI principles](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md) (`PRIN`) | 130 | 10 | 28 | 44 | 3 | 0 | 35 | 10 | 0 |
| [AI incident response runbook](../../.claude/skills/ai-incident-response/reference/runbook-playbooks.md) (`IR`) | 287 | 7 | 8 | 82 | 88 | 0 | 5 | 97 | 0 |
| [AI data governance and privacy](../../.claude/skills/ai-playbook/reference/data-governance-privacy.md) (`DGP`) | 254 | 19 | 4 | 102 | 48 | 0 | 9 | 72 | 0 |
| **All eleven** | **3201** | **310** | **390** | **1152** | **705** | **0** | **120** | **524** | **0** |

Counting rules:

- One row per table row, bullet, checklist item, normative paragraph and code block. Severity (MUST / SHOULD / MAY / ADAPT / INFORMATIVE) comes from the standard's own wording. ADAPT rows are thresholds and defaults the adopter must set.
- When two reviews of the same row disagreed, the status from the area that owns the standard wins, and `notes` records `reporters differ: …`.
- GOV rows marked `IMPLEMENTED_AND_TESTED` must include boundary A. A toolkit cannot prove an organisational control.

## AI evaluation strategy (`EVAL`)

Source standard `ai-evaluation-strategy.md` (source material; removed from the repository after migration, section homes in [`standards-section-map.tsv`](standards-section-map.tsv)). Canonical home: [`.claude/skills/eval-guide/SKILL.md`](../../.claude/skills/eval-guide/SKILL.md). 315 requirements.

Canonical toolkit: [`.claude/skills/eval-guide/`](../../.claude/skills/eval-guide/SKILL.md). Executable checks: `scripts/eval_gate.py`, `scripts/validate_golden.py` and the case schemas under `assets/schemas/`. The red-team tiers R1–R4 live in `reference/red-teaming.md`, which carries the union of eval §8 and security playbook §7 (OV-01).

| § | Rows | Tested | Impl. | Partial | Doc. | Missing | N/A | Enterprise | Blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PRE | 3 |  |  |  | 2 |  | 1 |  |  |
| 0 | 40 |  | 18 | 14 | 4 |  | 1 | 3 |  |
| 1 | 5 |  |  |  |  |  | 5 |  |  |
| 2 | 6 |  |  |  | 6 |  |  |  |  |
| 3 | 14 |  | 7 | 5 | 2 |  |  |  |  |
| 4 | 13 |  | 10 | 2 |  |  |  | 1 |  |
| 5 | 45 | 5 | 3 | 3 | 16 |  | 1 | 17 |  |
| 6 | 8 | 1 | 1 | 1 | 5 |  |  |  |  |
| 7 | 56 | 20 | 3 | 33 |  |  |  |  |  |
| 8 | 32 | 26 | 1 | 3 | 1 |  | 1 |  |  |
| 9 | 11 |  | 10 |  | 1 |  |  |  |  |
| 10 | 10 | 3 | 3 | 4 |  |  |  |  |  |
| 11 | 18 |  | 1 |  | 17 |  |  |  |  |
| 12 | 8 |  |  |  | 8 |  |  |  |  |
| 13 | 8 |  |  |  | 8 |  |  |  |  |
| 14 | 3 |  |  |  | 3 |  |  |  |  |
| 15 | 9 |  |  |  |  |  |  | 9 |  |
| 16 | 12 |  | 10 | 2 |  |  |  |  |  |
| 17 | 14 |  | 4 | 5 | 3 |  |  | 2 |  |

MISSING: none.

## AI engineering guardrails (`GR`)

Source standard `ai-engineering-guardrails.md` (source material; removed from the repository after migration, section homes in [`standards-section-map.tsv`](standards-section-map.tsv)). Canonical home: [`.claude/skills/ai-playbook/reference/engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md). 185 requirements.

Canonical toolkit: [`.claude/skills/ai-playbook/reference/engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md). It maps G1–G24 to code locations and gates. The contract tests `.claude/skills/ai-launch-check/assets/guardrail_contract_tests.py` and `guardrail-contract.test.ts` are repo templates. They run only inside an adopting service, so rows relying on them are `IMPLEMENTED_NOT_TESTED`; a disposable-app run is not repo evidence. GR-G9-07 is tested through the reference router's egress checks.

| § | Rows | Tested | Impl. | Partial | Doc. | Missing | N/A | Enterprise | Blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PRE | 3 |  |  |  |  |  | 3 |  |  |
| §1 | 3 |  | 1 |  |  |  | 2 |  |  |
| §2 | 3 |  | 3 |  |  |  |  |  |  |
| §3 | 6 |  | 6 |  |  |  |  |  |  |
| §4 | 24 |  | 24 |  |  |  |  |  |  |
| G1 | 3 |  | 3 |  |  |  |  |  |  |
| G2 | 4 |  | 4 |  |  |  |  |  |  |
| G3 | 11 | 1 | 9 |  |  |  |  | 1 |  |
| G4 | 8 | 2 | 6 |  |  |  |  |  |  |
| G5 | 9 |  | 6 | 1 |  |  |  | 2 |  |
| G6 | 6 |  | 4 | 1 | 1 |  |  |  |  |
| G7 | 9 |  | 4 | 5 |  |  |  |  |  |
| G8 | 5 |  | 3 | 1 |  |  |  | 1 |  |
| G9 | 10 | 1 | 6 | 3 |  |  |  |  |  |
| G10 | 3 |  | 2 |  |  |  |  | 1 |  |
| G11 | 2 |  | 2 |  |  |  |  |  |  |
| G12 | 2 |  | 1 | 1 |  |  |  |  |  |
| G13 | 5 |  | 4 |  |  |  |  | 1 |  |
| G14 | 3 |  |  | 3 |  |  |  |  |  |
| G15 | 8 |  | 5 | 2 |  |  | 1 |  |  |
| G16 | 3 |  | 3 |  |  |  |  |  |  |
| G17 | 3 |  | 2 | 1 |  |  |  |  |  |
| G18 | 7 |  | 2 |  |  |  |  | 5 |  |
| G19 | 2 |  |  |  |  |  |  | 2 |  |
| G20 | 5 |  | 1 |  |  |  |  | 4 |  |
| G21 | 2 |  |  |  | 2 |  |  |  |  |
| G22 | 1 |  | 1 |  |  |  |  |  |  |
| G23 | 5 |  | 5 |  |  |  |  |  |  |
| G24 | 2 |  | 2 |  |  |  |  |  |  |
| §5 | 2 |  | 2 |  |  |  |  |  |  |
| §6 | 17 |  |  | 1 | 16 |  |  |  |  |
| §7 | 1 |  | 1 |  |  |  |  |  |  |
| §8 | 2 |  | 2 |  |  |  |  |  |  |
| §9 | 1 |  | 1 |  |  |  |  |  |  |
| §10 | 2 |  |  |  |  |  |  | 2 |  |
| §11 | 1 |  | 1 |  |  |  |  |  |  |
| §12 | 2 |  | 1 |  |  |  | 1 |  |  |

MISSING: none.

## Enterprise AI governance (`GOV`)

Source standard `enterprise-ai-governance.md` (source material; removed from the repository after migration, section homes in [`standards-section-map.tsv`](standards-section-map.tsv)). Canonical home: [`.claude/skills/ai-governance/SKILL.md`](../../.claude/skills/ai-governance/SKILL.md). 906 requirements.

Canonical toolkit: [`.claude/skills/ai-governance/`](../../.claude/skills/ai-governance/SKILL.md): record schemas under `assets/schemas/` and `scripts/validate_governance_record.py`. Most rows are `PARTIALLY_COVERED` by design. The toolkit supplies boundary A/B (validation, templates), while ownership, registers, committees and contracts are boundary C/D and stay `REQUIRES_ENTERPRISE_ADOPTION`.

| § | Rows | Tested | Impl. | Partial | Doc. | Missing | N/A | Enterprise | Blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PRE | 10 |  |  |  |  |  | 6 | 4 |  |
| ES | 9 |  |  |  |  |  | 9 |  |  |
| GP | 16 |  |  | 14 |  |  |  | 2 |  |
| 1 | 46 | 1 |  | 14 | 20 |  |  | 11 |  |
| 2 | 200 | 1 |  | 145 |  |  |  | 54 |  |
| 3 | 39 |  |  | 20 |  |  |  | 19 |  |
| 4 | 11 | 1 |  | 7 |  |  | 1 | 2 |  |
| 5 | 45 |  |  | 17 | 15 |  |  | 13 |  |
| 6 | 41 | 2 | 10 | 29 |  |  |  |  |  |
| 7 | 41 | 10 |  | 26 | 2 |  |  | 3 |  |
| 8 | 40 |  |  | 39 |  |  |  | 1 |  |
| 9 | 31 | 2 |  | 28 |  |  |  | 1 |  |
| 10 | 56 | 2 |  | 41 |  |  |  | 13 |  |
| 11 | 16 |  |  | 15 |  |  | 1 |  |  |
| 12 | 34 |  |  | 10 | 14 |  |  | 10 |  |
| 13 | 37 |  |  | 37 |  |  |  |  |  |
| 14 | 30 | 1 | 8 | 17 | 1 |  |  | 3 |  |
| 15 | 36 |  |  | 36 |  |  |  |  |  |
| 16 | 28 |  |  | 26 |  |  |  | 2 |  |
| 17 | 31 | 1 |  | 30 |  |  |  |  |  |
| 18 | 37 |  |  |  |  |  |  | 37 |  |
| 19 | 41 |  |  | 41 |  |  |  |  |  |
| 20 | 20 |  |  | 20 |  |  |  |  |  |
| CLOSE | 11 |  |  |  |  |  | 11 |  |  |

MISSING: none.

## AI security threat model and red-team playbook (`SEC`)

Source standard `ai-security-redteam-playbook.md` (source material; removed from the repository after migration, section homes in [`standards-section-map.tsv`](standards-section-map.tsv)). Canonical home: [`.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md`](../../.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md). 230 requirements.

Canonical toolkit: [`.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md`](../../.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md) (AC-01–AC-18, sinks, intake, anti-patterns), plus `eval-guide/reference/red-teaming.md` for the case schema and tiers. Tool-surface locking (§12.2) is enforced and tested by `mcp-tool-validator` (`--surface-lock`, exit 4 on drift).

| § | Rows | Tested | Impl. | Partial | Doc. | Missing | N/A | Enterprise | Blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PRE | 4 |  |  |  |  |  | 4 |  |  |
| 1 | 3 |  | 2 |  |  |  | 1 |  |  |
| 2 | 6 | 5 | 1 |  |  |  |  |  |  |
| 3 | 16 |  | 16 |  |  |  |  |  |  |
| 4 | 21 | 2 | 1 | 18 |  |  |  |  |  |
| 5 | 20 | 1 |  | 19 |  |  |  |  |  |
| 6 | 26 | 13 | 13 |  |  |  |  |  |  |
| 7 | 26 | 12 | 6 |  |  |  |  | 8 |  |
| 8 | 13 |  | 5 | 1 | 6 |  |  | 1 |  |
| 9 | 12 |  | 3 |  |  |  |  | 9 |  |
| 10 | 11 | 6 | 1 | 3 |  |  |  | 1 |  |
| 11 | 13 |  | 8 |  |  |  |  | 5 |  |
| 12 | 18 | 4 | 11 |  |  |  |  | 3 |  |
| 13 | 10 | 2 | 3 |  |  |  |  | 5 |  |
| 14 | 15 | 7 | 8 |  |  |  |  |  |  |
| 15 | 16 | 1 |  |  |  |  |  | 15 |  |

MISSING: none.

## Model selection and routing (`MSR`)

Source standard `model-selection-routing.md` (source material; removed from the repository after migration, section homes in [`standards-section-map.tsv`](standards-section-map.tsv)). Canonical home: [`.claude/skills/agentic-ai-dev/reference/agentic-llm-routing.md`](../../.claude/skills/agentic-ai-dev/reference/agentic-llm-routing.md). 199 requirements.

Canonical toolkit: [`.claude/skills/agentic-ai-dev/reference/agentic-llm-routing.md`](../../.claude/skills/agentic-ai-dev/reference/agentic-llm-routing.md) (policy gate, cascades, verifier semantics), with the model registry in `assets/model-registry.schema.json` and `scripts/validate_model_registry.py` (selftest exit 0). The router logic itself was exercised only in a disposable app, so those rows are `IMPLEMENTED_NOT_TESTED`.

| § | Rows | Tested | Impl. | Partial | Doc. | Missing | N/A | Enterprise | Blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PRE | 3 |  |  |  |  |  | 3 |  |  |
| 1 | 4 |  |  |  | 3 |  | 1 |  |  |
| 2 | 3 | 1 |  | 2 |  |  |  |  |  |
| 3 | 5 | 1 |  | 4 |  |  |  |  |  |
| 4 | 13 | 5 |  | 4 | 4 |  |  |  |  |
| 5 | 29 | 20 |  | 9 |  |  |  |  |  |
| 6 | 14 |  | 1 | 5 | 7 |  |  | 1 |  |
| 7 | 10 |  |  |  | 10 |  |  |  |  |
| 8 | 10 | 8 |  |  | 2 |  |  |  |  |
| 9 | 11 | 7 |  | 3 | 1 |  |  |  |  |
| 10 | 4 | 3 |  | 1 |  |  |  |  |  |
| 11 | 6 |  |  | 4 | 2 |  |  |  |  |
| 12 | 9 | 2 |  | 1 | 6 |  |  |  |  |
| 13 | 7 |  |  | 7 |  |  |  |  |  |
| 14 | 6 |  |  |  | 6 |  |  |  |  |
| 15 | 4 | 2 | 2 |  |  |  |  |  |  |
| 16 | 7 |  |  | 7 |  |  |  |  |  |
| 17 | 9 |  |  | 1 |  |  |  | 8 |  |
| 18 | 2 |  |  | 1 |  |  |  | 1 |  |
| 19 | 9 |  |  |  |  |  |  | 9 |  |
| 20 | 18 | 9 |  | 3 | 6 |  |  |  |  |
| 21 | 16 |  |  | 1 |  |  |  | 15 |  |

MISSING: none.

## Prompt engineering and PromptOps (`PRM`)

Source standard `prompt-engineering-standard.md` (source material; removed from the repository after migration, section homes in [`standards-section-map.tsv`](standards-section-map.tsv)). Canonical home: [`.claude/skills/prompt-engineering-patterns/SKILL.md`](../../.claude/skills/prompt-engineering-patterns/SKILL.md). 236 requirements.

Canonical toolkit: [`.claude/skills/prompt-engineering-patterns/reference/promptops-lifecycle.md`](../../.claude/skills/prompt-engineering-patterns/reference/promptops-lifecycle.md), with `scripts/validate_prompts.py` (selftest 54/54), the stdlib PromptRegistry runtime `assets/prompts-scaffold/promptops/prompt_registry.py` (35 tests) and `scripts/prompt_drift.py` (selftest 15/15). The Langfuse backend notes and the measurement side of prompt changes are in `eval-guide/reference/langfuse-prompts.md` (OV-11, OV-12); it carries no second registry implementation.

| § | Rows | Tested | Impl. | Partial | Doc. | Missing | N/A | Enterprise | Blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PRE | 4 |  |  | 1 | 1 |  | 2 |  |  |
| 1 | 12 | 4 | 3 | 1 | 2 |  | 2 |  |  |
| 2 | 14 | 3 |  | 8 | 3 |  |  |  |  |
| 3 | 22 | 9 | 2 | 2 | 8 |  | 1 |  |  |
| 4 | 8 |  | 4 | 3 | 1 |  |  |  |  |
| 5 | 10 | 6 |  |  | 3 |  | 1 |  |  |
| 6 | 12 |  |  | 1 | 10 |  | 1 |  |  |
| 7 | 7 | 1 |  | 6 |  |  |  |  |  |
| 8 | 3 | 3 |  |  |  |  |  |  |  |
| 9 | 16 | 6 | 3 | 5 | 1 |  |  | 1 |  |
| 10 | 16 | 10 | 3 | 3 |  |  |  |  |  |
| 11 | 11 | 6 |  |  | 4 |  | 1 |  |  |
| 12 | 9 | 1 |  | 2 | 6 |  |  |  |  |
| 13 | 7 | 2 |  |  | 3 |  | 1 | 1 |  |
| 14 | 10 | 3 |  |  | 6 |  | 1 |  |  |
| 15 | 14 |  |  | 12 | 2 |  |  |  |  |
| 16 | 2 |  |  | 1 | 1 |  |  |  |  |
| 17 | 10 | 9 |  |  | 1 |  |  |  |  |
| 18 | 2 |  |  |  | 2 |  |  |  |  |
| 19 | 2 |  |  | 1 |  |  |  | 1 |  |
| 20 | 9 |  |  | 1 |  |  |  | 8 |  |
| 21 | 16 | 8 |  | 2 | 6 |  |  |  |  |
| 22 | 20 | 2 | 2 | 5 | 4 |  |  | 7 |  |

MISSING: none.

## RAG reference architecture (`RAG`)

Source standard `rag-reference-architecture.md` (source material; removed from the repository after migration, section homes in [`standards-section-map.tsv`](standards-section-map.tsv)). Canonical home: [`.claude/skills/rag-architect/SKILL.md`](../../.claude/skills/rag-architect/SKILL.md). 260 requirements.

Canonical toolkit: [`.claude/skills/rag-architect/`](../../.claude/skills/rag-architect/SKILL.md) (`references/rag-response-contract.md` and siblings), plus `rag-security-reviewer` (canonical for permission-aware retrieval) and `rag-evaluator`. The toolkit is guidance, not a library, so most rows are `DOCUMENTED_ONLY`. Only the response-contract snippet was extracted verbatim from the repo and executed.

| § | Rows | Tested | Impl. | Partial | Doc. | Missing | N/A | Enterprise | Blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PRE | 3 |  |  |  |  |  | 2 | 1 |  |
| 1 | 4 |  |  |  | 4 |  |  |  |  |
| 2 | 2 |  | 1 |  | 1 |  |  |  |  |
| 3 | 10 |  |  |  | 10 |  |  |  |  |
| 4 | 15 |  |  |  | 14 |  |  | 1 |  |
| 5 | 18 |  | 1 |  | 17 |  |  |  |  |
| 6 | 16 |  |  |  | 16 |  |  |  |  |
| 7 | 16 | 1 |  |  | 15 |  |  |  |  |
| 8 | 6 |  | 2 | 1 | 3 |  |  |  |  |
| 9 | 23 |  |  |  | 23 |  |  |  |  |
| 10 | 8 | 2 |  | 1 | 4 |  |  | 1 |  |
| 11 | 22 |  | 2 |  | 20 |  |  |  |  |
| 12 | 8 |  |  |  | 8 |  |  |  |  |
| 13 | 10 | 6 |  |  | 4 |  |  |  |  |
| 14 | 9 |  | 4 | 2 | 3 |  |  |  |  |
| 15 | 8 |  | 3 |  | 5 |  |  |  |  |
| 16 | 10 |  |  |  | 10 |  |  |  |  |
| 17 | 20 |  | 4 | 4 | 11 |  |  | 1 |  |
| 18 | 2 |  |  |  | 1 |  |  | 1 |  |
| 19 | 9 |  |  |  | 8 |  |  | 1 |  |
| 20 | 2 |  |  |  | 1 |  |  | 1 |  |
| 21 | 19 |  | 5 |  | 14 |  |  |  |  |
| 22 | 20 |  | 2 | 1 | 12 |  |  | 5 |  |

MISSING: none.

## Agent memory and knowledge (`MEM`)

Source standard `agent-memory-knowledge.md` (source material; removed from the repository after migration, section homes in [`standards-section-map.tsv`](standards-section-map.tsv)). Canonical home: [`.claude/skills/agentic-ai-dev/reference/agent-memory-lifecycle.md`](../../.claude/skills/agentic-ai-dev/reference/agent-memory-lifecycle.md). 199 requirements.

Canonical toolkit: [`.claude/skills/agentic-ai-dev/reference/agent-memory-lifecycle.md`](../../.claude/skills/agentic-ai-dev/reference/agent-memory-lifecycle.md) and `agentic-memory-systems.md`, with authority over memory in guardrails G16 (OV-06). No memory store is shipped as executable toolkit code. The Docker-backed integration suite `.claude/skills/agentic-ai-dev/scripts/test_memory_lifecycle_integration.py` (PostgreSQL 18.7 row-level security, Redis 7.4.8 cache) ran with `RUN_DB_INTEGRATION=1`: 6 passed, and disabling RLS or the cache erasure made the expected tests fail. Its tables and helpers are test code built from the guide, not a shipped store.

| § | Rows | Tested | Impl. | Partial | Doc. | Missing | N/A | Enterprise | Blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PRE | 4 |  |  |  | 1 |  | 3 |  |  |
| 1 | 3 |  |  |  | 1 |  | 2 |  |  |
| 2 | 6 |  | 3 | 1 | 1 |  | 1 |  |  |
| 3 | 10 |  |  | 6 | 4 |  |  |  |  |
| 4 | 10 |  | 2 | 7 | 1 |  |  |  |  |
| 5 | 14 |  | 5 | 1 | 7 |  |  | 1 |  |
| 6 | 12 |  |  | 3 | 9 |  |  |  |  |
| 7 | 10 |  | 3 | 3 | 3 |  |  | 1 |  |
| 8 | 12 |  |  | 4 | 8 |  |  |  |  |
| 9 | 9 |  |  | 7 |  |  |  | 2 |  |
| 10 | 11 |  | 5 | 2 | 4 |  |  |  |  |
| 11 | 10 |  | 1 | 6 | 3 |  |  |  |  |
| 12 | 8 |  |  | 1 | 7 |  |  |  |  |
| 13 | 7 |  |  | 3 | 4 |  |  |  |  |
| 14 | 6 |  |  |  | 2 |  |  | 4 |  |
| 15 | 13 |  |  | 6 | 7 |  |  |  |  |
| 16 | 12 |  |  |  | 12 |  |  |  |  |
| 17 | 10 |  |  |  | 10 |  |  |  |  |
| 18 | 15 |  | 3 | 7 | 5 |  |  |  |  |
| 19 | 17 | 1 |  | 7 | 9 |  |  |  |  |

MISSING: none.

## AI principles (`PRIN`)

Source standard `ai-principles.md` (source material; removed from the repository after migration, section homes in [`standards-section-map.tsv`](standards-section-map.tsv)). Canonical home: [`.claude/skills/ai-playbook/reference/engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md). 130 requirements.

Canonical toolkit: the ten-laws map in [`.claude/skills/ai-playbook/reference/engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md) links each law to its G1–G24 control, owner role, evidence test and failure condition. The per-law table lives in the AI decision record (`ai-decision-record` skill), and `ai-launch-check` fails a law with no evidence. Rows inherit status from the existing guardrail, governance and eval rows only where that evidence exercises the law's control.

| § | Rows | Tested | Impl. | Partial | Doc. | Missing | N/A | Enterprise | Blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PRE | 5 |  |  | 1 |  |  | 3 | 1 |  |
| 1 | 4 |  |  | 1 |  |  | 1 | 2 |  |
| 2 | 10 |  |  |  |  |  | 10 |  |  |
| 3 | 9 |  | 1 | 6 | 1 |  |  | 1 |  |
| 4 | 2 |  | 1 | 1 |  |  |  |  |  |
| 5 | 11 | 1 | 6 | 2 |  |  |  | 2 |  |
| 6 | 10 |  |  |  |  |  | 10 |  |  |
| 7 | 2 |  | 1 |  |  |  | 1 |  |  |
| 8 | 1 |  | 1 |  |  |  |  |  |  |
| L1 | 5 |  | 4 |  |  |  | 1 |  |  |
| L2 | 8 | 3 |  | 4 |  |  | 1 |  |  |
| L3 | 6 | 1 |  | 4 |  |  | 1 |  |  |
| L4 | 8 |  | 1 | 5 |  |  | 1 | 1 |  |
| L5 | 6 | 1 | 1 | 3 |  |  | 1 |  |  |
| L6 | 8 |  | 1 | 5 | 1 |  | 1 |  |  |
| L7 | 8 |  | 3 | 3 |  |  | 1 | 1 |  |
| L8 | 6 |  | 1 | 4 |  |  | 1 |  |  |
| L9 | 9 |  | 7 |  | 1 |  | 1 |  |  |
| L10 | 12 | 4 |  | 5 |  |  | 1 | 2 |  |

MISSING: none.

## AI incident response runbook (`IR`)

Source standard `ai-incident-response-runbook.md` (source material; removed from the repository after migration, section homes in [`standards-section-map.tsv`](standards-section-map.tsv)). Canonical home: [`.claude/skills/ai-incident-response/reference/runbook-playbooks.md`](../../.claude/skills/ai-incident-response/reference/runbook-playbooks.md). 287 requirements.

Canonical toolkit: [`.claude/skills/ai-incident-response/`](../../.claude/skills/ai-incident-response/SKILL.md) with `reference/runbook-playbooks.md` (I1–I11, containment ladder, kill-switch drills, recovery verification, closure). The incident record schema and `validate_governance_record.py` in `ai-governance` enforce closure rules; severity scales are reconciled in `ai-governance/reference/supply-chain-eval-and-release.md` §7.1 (stricter rule wins). On-call, drill cadence, notification decisions and named owners need organisation adoption.

| § | Rows | Tested | Impl. | Partial | Doc. | Missing | N/A | Enterprise | Blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PRE | 3 |  |  |  |  |  | 2 | 1 |  |
| 1 | 4 |  |  |  | 2 |  | 1 | 1 |  |
| 2 | 14 |  |  | 12 | 1 |  |  | 1 |  |
| 3 | 9 |  |  | 5 | 3 |  |  | 1 |  |
| 4 | 12 |  |  | 4 |  |  |  | 8 |  |
| 5 | 13 |  |  | 1 |  |  |  | 12 |  |
| 6 | 11 |  |  | 4 | 6 |  |  | 1 |  |
| 7 | 13 | 2 | 7 | 1 | 2 |  |  | 1 |  |
| 8 | 1 |  |  |  | 1 |  |  |  |  |
| 9 | 14 | 1 |  |  | 9 |  |  | 4 |  |
| 10 | 16 |  |  |  | 1 |  |  | 15 |  |
| 11 | 12 | 1 |  | 10 | 1 |  |  |  |  |
| 12 | 13 | 2 |  | 2 | 9 |  |  |  |  |
| 13 | 3 |  |  |  | 1 |  |  | 2 |  |
| 14 | 6 |  |  | 4 |  |  | 1 | 1 |  |
| 15 | 9 |  |  |  |  |  |  | 9 |  |
| 16 | 11 |  |  |  |  |  | 1 | 10 |  |
| 17 | 7 |  |  |  |  |  |  | 7 |  |
| 18 | 14 | 1 | 1 | 1 | 8 |  |  | 3 |  |
| 19 | 16 |  |  | 4 |  |  |  | 12 |  |
| I1 | 8 |  |  | 3 | 4 |  |  | 1 |  |
| I2 | 8 |  |  | 3 | 5 |  |  |  |  |
| I3 | 10 |  |  | 4 | 4 |  |  | 2 |  |
| I4 | 8 |  |  | 4 | 4 |  |  |  |  |
| I5 | 8 |  |  | 3 | 5 |  |  |  |  |
| I6 | 7 |  |  | 3 | 3 |  |  | 1 |  |
| I7 | 7 |  |  | 3 | 4 |  |  |  |  |
| I8 | 7 |  |  | 3 | 3 |  |  | 1 |  |
| I9 | 8 |  |  | 2 | 3 |  |  | 3 |  |
| I10 | 7 |  |  | 3 | 4 |  |  |  |  |
| I11 | 8 |  |  | 3 | 5 |  |  |  |  |

MISSING: none.

## AI data governance and privacy (`DGP`)

Source standard `ai-data-governance-privacy.md` (source material; removed from the repository after migration, section homes in [`standards-section-map.tsv`](standards-section-map.tsv)). Canonical home: [`.claude/skills/ai-playbook/reference/data-governance-privacy.md`](../../.claude/skills/ai-playbook/reference/data-governance-privacy.md). 254 requirements.

Canonical toolkit: the deterministic egress check in [`reference-router/msr_router.py`](../../.claude/skills/agentic-ai-dev/assets/reference-router/msr_router.py) (`request_egress_blocks`, `provider_egress_blocks`: read permission is not send permission; data class, purpose, provider approval and region are checked before any model call, with negative tests), the model registry validator, memory-item validator, golden-set PII rules (`validate_golden.py` GD013) and synthetic-data provenance in `dataset_manifest.schema.json`. The erasure inventory (store → mechanism → proof) is in `ai-playbook/reference/engineering-guardrails.md`. Contracts, legal bases, retention values and residency registers need organisation adoption.

| § | Rows | Tested | Impl. | Partial | Doc. | Missing | N/A | Enterprise | Blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PRE | 4 |  |  |  |  |  | 2 | 2 |  |
| 1 | 3 |  |  |  |  |  | 2 | 1 |  |
| 2 | 7 | 1 |  | 6 |  |  |  |  |  |
| 3 | 10 | 1 |  | 8 |  |  |  | 1 |  |
| 4 | 11 | 3 |  | 5 |  |  | 3 |  |  |
| 5 | 17 |  |  | 7 | 1 |  |  | 9 |  |
| 6 | 7 | 2 |  | 5 |  |  |  |  |  |
| 7 | 14 | 1 |  | 4 | 5 |  |  | 4 |  |
| 8 | 9 |  |  | 4 | 5 |  |  |  |  |
| 9 | 10 | 1 |  | 1 | 2 |  |  | 6 |  |
| 10 | 18 |  | 2 | 3 | 10 |  |  | 3 |  |
| 11 | 17 |  | 1 | 4 | 4 |  |  | 8 |  |
| 12 | 13 |  |  | 3 | 4 |  | 1 | 5 |  |
| 13 | 7 |  |  | 5 | 2 |  |  |  |  |
| 14 | 17 | 3 |  | 11 | 3 |  |  |  |  |
| 15 | 8 | 1 |  | 1 | 2 |  |  | 4 |  |
| 16 | 10 |  |  | 5 | 3 |  |  | 2 |  |
| 17 | 24 | 2 |  | 14 | 4 |  |  | 4 |  |
| 18 | 15 |  |  |  |  |  | 1 | 14 |  |
| 19 | 15 | 4 | 1 | 5 | 2 |  |  | 3 |  |
| 20 | 18 |  |  | 11 | 1 |  |  | 6 |  |

MISSING: none.

## Shared requirements

Some requirements appear in more than one standard. Each group has one canonical implementation; the other standards' rows point to it and carry the group ID in `shared_group`. When the standards differ, the stricter security or domain requirement wins.

| Group | Topic | Rows | Defining standard | Canonical implementation |
|---|---|---|---|---|
| OV-01 | Red-team tiers R1–R4, hard blockers, path routing, never-every-PR | EVAL-8.2..8.5; SEC-7.1..7.4; GOV-10.4 | eval §8 (defines R1–R4) | [`red-teaming.md`](../../.claude/skills/eval-guide/reference/red-teaming.md) |
| OV-02 | Threat/attack classes | EVAL-8.1; SEC-4; SEC-5 | security playbook §4 (AC-01–AC-18) | [`ai-threat-model-attack-classes.md`](../../.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md) |
| OV-03 | Risk tiers T0–T3 and per-tier gates | GR-§3; SEC-11; MSR-17; PRM-9/19 (T2/T3) | guardrails §3 | [`engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md) |
| OV-04 | Risk classification + autonomy A0–A4 | GOV-6.1..6.4; GOV-2.8 | governance §6 | [`risk-autonomy-oversight.md`](../../.claude/skills/ai-governance/reference/risk-autonomy-oversight.md) |
| OV-05 | Eval layers L1–L5 and PR gates | EVAL-5.*; GR-G7; GR-§6 | eval §5 | [`SKILL.md`](../../.claude/skills/eval-guide/SKILL.md) |
| OV-06 | Authority / current state beats memory | GR-§2; GR-G16; MEM-2; MEM-8; RAG-12 | guardrails G16 (+ §2) | [`engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md)<br>[`agent-memory-lifecycle.md`](../../.claude/skills/agentic-ai-dev/reference/agent-memory-lifecycle.md) |
| OV-07 | Authorize before retrieval / isolation / ACL propagation | GR-G9; RAG-8; RAG-10; MEM-7; GOV-8.1; EVAL-3 dim 7 | guardrails G9 | [`engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md)<br>[`SKILL.md`](../../.claude/skills/rag-security-reviewer/SKILL.md) |
| OV-08 | Retrieval is evidence, not authority; grounding & citations | GR-G14; RAG-11; RAG-13 | guardrails G14 | [`engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md) |
| OV-09 | RAG lifecycle: freshness, deletion, retention | GR-G15; RAG-14; MEM-9; GOV-8.4 | guardrails G15 (deletion verification: governance §8.4) | [`engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md)<br>[`agent-memory-lifecycle.md`](../../.claude/skills/agentic-ai-dev/reference/agent-memory-lifecycle.md) |
| OV-10 | Memory security / poisoning | GOV-8.3; MEM-10; SEC AC-03, AC-10; RAG-16 | security playbook (attack classes) + governance §8.3 (control) | [`agent-memory-lifecycle.md`](../../.claude/skills/agentic-ai-dev/reference/agent-memory-lifecycle.md)<br>[`ai-threat-model-attack-classes.md`](../../.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md) |
| OV-11 | Prompt lifecycle, registry, labels, rollback | EVAL-9; PRM-9; PRM-10; GR-G11 | prompt standard §9–§10 (eval §9 = measurement side) | [`promptops-lifecycle.md`](../../.claude/skills/prompt-engineering-patterns/reference/promptops-lifecycle.md)<br>[`langfuse-prompts.md`](../../.claude/skills/eval-guide/reference/langfuse-prompts.md) |
| OV-12 | Prompt change → required evals | PRM-15; EVAL-9; GR-G7 | prompt standard §15 | [`promptops-lifecycle.md`](../../.claude/skills/prompt-engineering-patterns/reference/promptops-lifecycle.md) |
| OV-13 | Version pinning, no latest, rollback | GR-G11; MSR-11; PRM-13; RAG-7.2 | guardrails G11 (model-specific detail: MSR §11) | [`engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md)<br>[`agentic-llm-routing.md`](../../.claude/skills/agentic-ai-dev/reference/agentic-llm-routing.md) |
| OV-14 | Approved models / provider governance | GR-G20; MSR-5; GOV-2.7; GOV-2.14; SEC-12 | model-selection-routing §5 (registry); governance §2.7 (org control) | [`model-registry.schema.json`](../../.claude/skills/agentic-ai-dev/assets/model-registry.schema.json)<br>[`validate_model_registry.py`](../../.claude/skills/agentic-ai-dev/scripts/validate_model_registry.py) |
| OV-15 | Provider failover and exit | MSR-10; MSR-12; GOV-12.*; GR-G6 | governance §12 (exit); MSR §12 (runtime resilience) | [`agentic-llm-routing.md`](../../.claude/skills/agentic-ai-dev/reference/agentic-llm-routing.md)<br>[`SKILL.md`](../../.claude/skills/ai-governance/SKILL.md) |
| OV-16 | Kill switches / flags | GR-G10; MSR-18; SEC-9 (via G10) | guardrails G10 | [`engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md) |
| OV-17 | Budgets, cost, latency | GR-G12; GR-G5; MSR-13; PRM-14; RAG-19; MEM-17; EVAL-14; GOV-2.12 | guardrails G12 | [`engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md) |
| OV-18 | Observability / attribution spans | GR-G8; EVAL-5.5; EVAL-11; MSR-16; PRM-18; RAG-18; MEM-16; GOV-2.11 | guardrails G8 (attributes: eval §5.5/§11) | [`ai-observability.md`](../../.claude/skills/deployment-ci-cd/reference/ai-observability.md) |
| OV-19 | Idempotent side effects / escalation | GR-G4; MSR-9.3; RAG-5.3; GOV-11.1; EVAL-10.3 | guardrails G4 | [`engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md)<br>[`security-middleware-attacks.md`](../../.claude/skills/mcp-builder/reference/security-middleware-attacks.md) |
| OV-20 | Tool-server intake / supply chain | SEC-12; GOV-9.*; GOV-2.14; EVAL-10 | security playbook §12 (intake); governance §9 (AI BOM/provenance) | [`ai-threat-model-attack-classes.md`](../../.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md)<br>[`ai_bom.schema.json`](../../.claude/skills/ai-governance/assets/schemas/ai_bom.schema.json) |
| OV-21 | RAG eval metrics + golden sets | RAG-17; EVAL-6; EVAL-7; EVAL-3 dim 4 | eval §6/§7 (thresholds, datasets); RAG §17 lists RAG metrics | [`per-agent-thresholds.md`](../../.claude/skills/eval-guide/reference/per-agent-thresholds.md)<br>[`SKILL.md`](../../.claude/skills/rag-evaluator/SKILL.md) |
| OV-22 | Secrets in prompts / AI systems | SEC-13; PRM-3; PRM-11; GR-G9 | security playbook §13 | [`ai-threat-model-attack-classes.md`](../../.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md)<br>[`post-edit-ai-patterns.sh`](../../.claude/hooks/post-edit-ai-patterns.sh) |
| OV-23 | Structured output / typed contracts | GR-G3; PRM-4; SEC-6.4; EVAL-3 dim 3 | guardrails G3 | [`engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md) |

## Conflicts between standards

None of the standards were edited. Where they differ, the stricter security or domain requirement wins. Where neither is stricter, the decision is recorded here.

| # | Conflict | Resolution in the toolkit |
|---|---|---|
| 1 | Security playbook §7 vs eval §8. The playbook adds hard blockers (model-supplied scope, RAG snippet/count/neighbour leaks, unencoded output to a sink, system-prompt canary), path routes (retrieval and ingestion config, output renderers, model or provider change → full R2 before merge), a daily R4 prompt-leak canary and R2 sets (multi-turn, RAG poisoning). Only eval §8 routes compliance-load-bearing prompts and judge cases | Union in `eval-guide/reference/red-teaming.md` and the case-schema blocker enum. Playbook-only items are labelled "security playbook" (OV-01). Jailbreak text with no tool, data or sink impact is tracked, not blocking |
| 2 | Attack taxonomy: eval §8.1 has 14 slugs; the playbook has AC-01–AC-18. Each has classes the other lacks | Crosswalk in `red-teaming.md` and `ai-threat-model-attack-classes.md` §3. The `attack_class` enum carries both. No new AC IDs invented |
| 3 | Incident severity: playbook §8 SEV-1–SEV-4 vs governance §13 S0–S3. Neither defines a mapping | **Open**: an organisational decision (boundary C). Both scales are kept unmapped |
| 4 | Risk vocabularies: guardrails T0–T3, governance Low–Critical risk and A0–A4 autonomy, eval critical/high/medium/low, and the playbook's 0–5 blast-radius tiers ("Tier 3+ never auto-commit" is in the 0–5 scale) | Kept separate and labelled, never renumbered. `engineering-guardrails.md` gives a blast-radius → minimum T-tier floor. The governance validator rejects a T-tier in `risk_tier` |
| 5 | Model routing §10 step 4 allows outage fallback to "a higher approved tier"; llm-inference §6 keeps provider failover within the same tier | Same-tier equivalents first. A higher tier is the documented conservative fallback with reason `NO_APPROVED_EQUIVALENT`; it never drops to a lower tier (`agentic-llm-routing.md`) |
| 6 | Guardrails G22 cites WCAG 2.1 | WCAG 2.2 AA (stricter) |
| 7 | Eval §5.5 and prompt §18 name span attributes `prompt_name`, `prompt_version`…; OpenTelemetry semantic conventions put custom attributes under an application namespace | Control objective kept (each response attributable to prompt and model) using `app.prompt.*` and `gen_ai.request.model`. The mapping is in `deployment-ci-cd/reference/ai-observability.md` |
| 8 | Eval §6 "hallucination = 0" is a rate, while ADK `hallucinations_v1` is a supported-sentence score where higher is better | Gate the ADK metric with ≥ threshold, never `= 0`. Both directions documented |
| 9 | Eval §8.3 makes "write tool without audit-log call" a merge blocker; the MCP security checklist rated missing audit MEDIUM | New CRITICAL check for write tools; the MEDIUM check is kept for denials and reads |
| 10 | Memory §7 requires `org_id` on every item; the ADK memory scope is `{app_name, user_id}` | The adapter encodes org (documented in `agent-memory-lifecycle.md`) |

## Conflicts and ambiguities within a standard

| Standard | Item | Toolkit reading |
|---|---|---|
| Guardrails | G4 key formula (GR-G4-03) embeds `payload_hash`, so "same key + different hash → `IDEMPOTENCY_PAYLOAD_MISMATCH`" (GR-G4-04) can never trigger | Look up by a payload-independent scope (org, entity, action, client request id), compare hashes, persist the standard's key for audit. Covered by `ai-launch-check/assets/guardrail_contract_tests.py` (template, run in the adopting service) and `mcp-builder/scripts/contract-test` |
| Guardrails | GR-G3-04 orders version check before schema validation; MCP SDKs validate the whole schema before the handler | Order differs; the objective (nothing executes) is kept |
| Guardrails | §9 "bounded answer for legal/medical/safety-adjacent questions" implies probabilistic topic detection | Deterministic intercept plus routing to review |
| Guardrails | Preamble names a companion file that is not in the repo | Normalised to `ai-evaluation-strategy.md` |
| Eval | §8.4 "data model / migrations → full red team" vs §8.5 "full red-team corpus never on every PR" | Path-triggered exception with its own suite name |
| Eval | §7.4 `splits` are run stages; the toolkit's old `split` meant a data partition | Toolkit field renamed to `partition` |
| Eval | §7.3 places multi-turn files under `features/`, but §7.2 has no multi-turn type | `multi_turn` added as a dataset type |
| Eval | §7.12 needs an owner per case; the §7.5 example has none | Case owner optional, falling back to the manifest owner |
| Eval | §7.9 "≤ 1 sprint" has no length in days | Checked only when `--sprint-days` is given |
| Eval | §8.3 lists 9 blockers; the toolkit's CI tiers had 10 (PII) | PII labelled a toolkit addition |
| Eval | §10.3 `session_id`: MCP revision 2026-07-28 removed protocol sessions | Host conversation id via request `_meta`, never `Mcp-Session-Id` |
| Eval | §7.10-07 needs 5 cases per tool (ADAPT); `mcp-tool-validator` gates at 3 | Kept as an ADAPT default, not a hard gate |
| Governance | §6.3 calls thresholds illustrative and to be approved by risk owners, but the table rows read as gates | Numbers not enforced; risk-owner approval of thresholds enforced on final records |
| Governance | §6.3 lists one-step transitions but does not forbid multi-step jumps | Validator enforces one step per promotion (toolkit reading) |
| Governance | §7.1 display list is "should"; §7.2 "no concealed material warnings" is unconditional | Schema requires every display field (stricter) |
| Governance | §19 checklist is "Mandatory", but some items do not apply to A0/A1 | N/A allowed with justification, except owners, risk class, approved provider, model/prompt versions and next review |
| Governance | §16.2 control IDs and §13.1 incident categories share prefixes (AI-SEC…) | `control_id` pattern accepts both |
| Governance | §15.2 regulatory dates are "as of" a past date | Dates unchanged; the standard's caution kept |
| Security | Case-field names: §10.2 `tier: [r1…]`, `atlas_tactics`, `owasp_category` vs the eval schema's `tiers: [R1…]`, `atlas_ids`, `owasp_ids` | Eval schema names kept; crosswalk documented |
| Security | OWASP Agentic ASI07/ASI08/ASI10 have no playbook class | Mapped as secondary classes only |
| Model routing | §5.2 shows `deployed (canary → general)` but makes `approved` the canary state | `approved` = shadow/canary, `deployed` = production |
| Prompt | §10.3 serves last-known-good and raises only when the prompt is absent everywhere; the toolkit's `allow_degraded=False` raises earlier | Stricter, stated explicitly |
| Prompt | §14 static-size budget does not say how to count tokens | chars/4 approximation (ADAPT; swap in the model tokenizer) |
| Prompt | §10 asks for one thin in-house registry wrapper; three existed | Two replaced by pointers to the canonical wrapper in `eval-guide/reference/langfuse-prompts.md` |
| RAG | §13.3 outcome enum (STALE, CONFLICTED, HUMAN_REVIEW, NOT_FOUND) vs the toolkit's `abstained` | The standard's enum wins; operational statuses kept as extensions |
| RAG | §15 forbids semantic answer caches for personalised, high-stakes or ACL-varying answers; the toolkit allowed a tenant-scoped one | The standard wins |
| RAG | §9.1 "start where the data lives; a new store needs review (G13)" vs the toolkit mandating Weaviate for pure text | Collocated-first step added |
| RAG | Chunk size/overlap and re-index gate defaults differ (all ADAPT) | Both kept; the owner should ratify one value. Per-slice re-index rule added |
| Memory | §9 erasure SLA vs a managed memory service keeping deleted revisions up to 48 h | Recorded as a residual window |
| Memory | Per-org cost metric vs bounded metric labels | Org kept on traces, not metric labels |
| Several | Companion standards referenced but not in the repo (data governance/privacy, gateway/tool server) | Out of scope; dependent data classes stay ADAPT |

## Requirement-list corrections

Severity tags were corrected where the extractor contradicted the source text. The requirement wording is unchanged.

| ID | Was | Now | Reason |
|---|---|---|---|
| PRM-9.2-05 | SHOULD | MUST | "No `latest`, `default` or auto-upgrade label is used in staging or production" is unconditional |
| GOV-6.3-18, GOV-6.3-19 | ADAPT | MUST | Normative cautions under "Important", not thresholds |
| GOV-5.3-12, GOV-5.3-13 | MUST | ADAPT | Listed under "Illustrative performance target" |

## Audit adjustments

Rows the audit changed or qualified relative to the area reviews. Each row's `notes` cell says which adjustment applies.

| Adjustment | EVAL | GR | GOV | SEC | MSR | PRM | RAG | MEM | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Executed only in a disposable app; downgraded to IMPLEMENTED_NOT_TESTED | 37 | 0 | 0 | 0 | 0 | 14 | 0 | 0 | 51 |
| Ref line re-anchored to the line that states the control | 32 | 1 | 191 | 32 | 25 | 43 | 1 | 28 | 353 |
| Ref is a section pointer, not line-verified | 30 | 5 | 70 | 92 | 11 | 57 | 0 | 28 | 293 |
| Unsupported ref dropped | 2 | 0 | 0 | 1 | 3 | 1 | 0 | 0 | 7 |
| Cited file does not mention the requirement (section pointer only) | 0 | 0 | 14 | 0 | 0 | 0 | 0 | 0 | 14 |
| Reviews of the row disagreed (owner's status kept) | 14 | 19 | 49 | 6 | 1 | 1 | 2 | 1 | 93 |
| Final independent audit: executed only in a disposable app (GR: the guardrail contract template ran against an app outside the repo); downgraded to IMPLEMENTED_NOT_TESTED | 0 | 66 | 0 | 1 | 2 | 0 | 0 | 14 | 83 |
| Final independent audit: other status corrections (RAG-13.3-01 → DOCUMENTED_ONLY, SEC-PRE-02 → NOT_APPLICABLE, MSR-21-03 → PARTIALLY_COVERED) | 0 | 0 | 0 | 1 | 1 | 0 | 1 | 0 | 3 |
| Final independent audit: evidence re-anchored (GOV-9.2-01, GOV-4.1-06) | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 2 |
| Remediation: upgraded to IMPLEMENTED_AND_TESTED on new repo evidence (RAG response-contract tests, pgvector and memory integration suites, unsafe-release exercise validator, incident severity rule, router egress tests) | 0 | 1 | 8 | 1 | 0 | 0 | 4 | 3 | 17 |
| Remediation: tested rows whose evidence was Markdown only, downgraded after mutation probes showed no test catches the change | 8 | 0 | 3 | 1 | 15 | 0 | 0 | 0 | 27 |
| Remediation: other status changes (partial evidence added, MISSING → DOCUMENTED_ONLY for GOV-14.1-06) | 1 | 2 | 1 | 0 | 0 | 0 | 2 | 2 | 8 |
| Remediation: status kept, evidence re-pointed at the code line and test that prove it | 7 | 0 | 205 | 0 | 42 | 0 | 5 | 0 | 259 |

The PRIN, IR and DGP rows were extracted in this pass and carry no adjustments yet.

Independent audit adjustment (2026-11-24): 175 rows moved from `IMPLEMENTED_AND_TESTED` to `PARTIALLY_COVERED` because their gap cell names behaviour no test exercises (record- or field-level checks only, runtime or organisation-owned parts, ADAPT numbers not enforced). 16 GR §6 process items moved from `IMPLEMENTED_NOT_TESTED` to `DOCUMENTED_ONLY`.

## Verification and rerun

Each `IMPLEMENTED_AND_TESTED` claim was re-checked. Shipped test artifacts were compared by SHA-256 with the bytes that ran. The cited file was read at the cited line, and executed claims were rerun where the artifact is in the repo. Claims the audit could not support were downgraded or dropped (above). Validators rerun in this audit (each command's own exit code):

| Command | Exit | Result |
|---|---:|---|
| `python .claude/skills/agentic-ai-dev/scripts/validate_model_registry.py --selftest` | 0 | selftest PASS |
| `python .claude/skills/prompt-engineering-patterns/scripts/validate_prompts.py --selftest` | 0 | 54/54 controls |
| `python .claude/skills/prompt-engineering-patterns/scripts/prompt_drift.py --selftest` | 0 | 15/15 controls |
| `uv run --locked --python 3.14 pytest -q` in `.claude/skills/agentic-ai-dev/assets/reference-router/` | 0 | 49 passed, 19 subtests (UNIT, MOCKED PROVIDER), including the egress-authorization tests (a missing policy fails closed before any provider call or candidate listing) and the regulated data class |
| `uv run --script .claude/skills/prompt-engineering-patterns/assets/prompts-scaffold/promptops/test_prompt_registry.py` | 0 | 35 run, 0 skipped (32 RUNTIME, 3 STATIC VALIDATION); stdlib `python3.14`: 30 executed, 5 skipped; 22 mutated-copy negative controls each fail their target test |
| `uv run --frozen pytest` in `.claude/skills/security-reviewer/assets/ai-attack-class-fixture/` | 0 | 38 passed |
| `run_negative_controls.sh` in the same directory | 0 | 30/30 controls fail as intended |
| `uv run --script .claude/skills/security-reviewer/scripts/check_attack_class_ids.py --selftest` | 0 | PASS |
| `python3 .claude/skills/agentic-ai-dev/scripts/validate_memory_item.py --selftest` | 0 | selftest PASS |
| `npm ci && npm run typecheck && npm test` in `.claude/skills/mcp-builder/scripts/contract-test/` | 0 | 18/18 on Node 26.13.1 (the declared engine) |
| `python3 .claude/skills/ai-governance/scripts/validate_governance_record.py --selftest` | 0 | 108 checks, Python 3.14 and 3.9 |
| `python3 .claude/skills/rag-architect/scripts/test_response_contract.py` | 0 | 13 tests (UNIT) |
| `uv run --script .claude/skills/eval-guide/scripts/validate_golden.py --selftest` and `eval_gate.py --selftest` | 0 | PASS |
| `RUN_DB_INTEGRATION=1 pytest .claude/skills/vector-database/scripts/test_pgvector_integration.py` (PostgreSQL 18.7, pgvector 0.8.7) | 0 | 12 passed (INTEGRATION); with RLS disabled: exit 1, 3 failed |
| `RUN_DB_INTEGRATION=1 pytest .claude/skills/agentic-ai-dev/scripts/test_memory_lifecycle_integration.py` (PostgreSQL 18.7, Redis 7.4.8) | 0 | 6 passed (INTEGRATION); RLS disabled: exit 1, 3 failed; cache erasure skipped: exit 1, 1 failed |
| `bash .claude/scripts/check-coverage-register.sh --selftest` | 0 | every case reports its expected check code; an empty register fails |
| `bash .claude/scripts/check-coverage-register.sh docs/audits/ai-engineering-standards-coverage.tsv` | 0 | every ref exists, line in range |

To re-audit after a toolkit change, run:

```bash
bash .claude/scripts/check-coverage-register.sh docs/audits/ai-engineering-standards-coverage.tsv
```

It checks the header, ID format and uniqueness, status and governance boundary values, and that every `IMPLEMENTED_*`/`PARTIALLY_COVERED` row has a ref that exists with its line in range. It does not judge whether the cited line still supports the requirement. After a refactor that moves lines, re-anchor the refs and review them.

## Not run

- Docker-backed tests ran for pgvector (`vector-database/scripts/test_pgvector_integration.py`, 12 passed) and memory (`agentic-ai-dev/scripts/test_memory_lifecycle_integration.py`, 6 passed) with `RUN_DB_INTEGRATION=1` on local containers bound to 127.0.0.1. Weaviate and other vector stores were not run. Both suites skip without the variable, so CI does not run them.
- The guardrail contract tests (Python and TypeScript) are templates; they were not run against a service in the repo.
- Live-provider evaluations were not run. Model-dependent checks ran against scripted or mocked providers, labelled `MOCKED PROVIDER` in `evidence`.
- The TypeScript guardrail contract test was not rerun in the final pass. Its rows rely on the Python contract test, which covers the same invariants.
