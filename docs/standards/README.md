# AI engineering domains: where they live in the toolkit

The eleven AI engineering standards this toolkit was built from were source material. Their applicable requirements now live in skills, skill references, agents, rules, templates and tests; the source documents are not kept in the repository.

| Domain | Requirement IDs | Canonical home | Reviewer / command |
|---|---|---|---|
| AI evaluation | 13 dimensions, L1–L5, R1–R4, golden sets (`EVAL`) | [`eval-guide`](../../.claude/skills/eval-guide/SKILL.md), [`llm-evaluation`](../../.claude/skills/llm-evaluation/SKILL.md) | `ai-eval-designer`, `eval-reviewer` |
| Engineering guardrails | G1–G24, T0–T3 (`GR`) | [`ai-playbook/reference/engineering-guardrails.md`](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md), [`ai-launch-check`](../../.claude/skills/ai-launch-check/SKILL.md) | `ai-security-reviewer`, `/ai-launch-check` |
| Ten laws of agentic AI | L1–L10, action tiers A0–A4 + Emergency (`PRIN`) | [`engineering-guardrails.md` ten laws](../../.claude/skills/ai-playbook/reference/engineering-guardrails.md), [`ai-decision-record`](../../.claude/skills/ai-decision-record/SKILL.md) | `/ai-decision-record`, `/ai-launch-check` |
| Enterprise AI governance | 15 pillars, A0–A4 autonomy, Low–Critical risk (`GOV`) | [`ai-governance`](../../.claude/skills/ai-governance/SKILL.md), [`ai-audit`](../../.claude/skills/ai-audit/SKILL.md) | `/ai-audit` |
| AI incident response | I1–I11, SEV1–SEV4, rungs 1–5, D1–D6 (`IR`) | [`ai-incident-response`](../../.claude/skills/ai-incident-response/SKILL.md) | `/ai-incident-response` |
| AI security and red teaming | AC-01–AC-18 (`SEC`) | [`security-reviewer/reference/ai-threat-model-attack-classes.md`](../../.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md), [`eval-guide/reference/red-teaming.md`](../../.claude/skills/eval-guide/reference/red-teaming.md) | `ai-security-reviewer`, `threat-modeling-expert` |
| Data governance and privacy | D1–D7, five data classes (`DGP`) | [`ai-playbook/reference/data-governance-privacy.md`](../../.claude/skills/ai-playbook/reference/data-governance-privacy.md); egress check in the reference router | `ai-security-reviewer` |
| Model selection and routing | FAST / STANDARD / STRONG (`MSR`) | [`agentic-ai-dev/reference/agentic-llm-routing.md`](../../.claude/skills/agentic-ai-dev/reference/agentic-llm-routing.md), reference router | `agentic-ai-reviewer` |
| Prompt engineering and PromptOps (`PRM`) | prompt cards, §15 change matrix | [`prompt-engineering-patterns`](../../.claude/skills/prompt-engineering-patterns/SKILL.md), [`promptops-lifecycle.md`](../../.claude/skills/prompt-engineering-patterns/reference/promptops-lifecycle.md) | `eval-reviewer`, `ai-security-reviewer` |
| RAG architecture | response contract outcomes (`RAG`) | [`rag-architect`](../../.claude/skills/rag-architect/SKILL.md), [`vector-database`](../../.claude/skills/vector-database/SKILL.md), [`rag-security-reviewer`](../../.claude/skills/rag-security-reviewer/SKILL.md) | `rag-implementation-reviewer`, `/rag-review` |
| Agent memory and knowledge | six memory types (`MEM`) | [`agentic-ai-dev/reference/agent-memory-lifecycle.md`](../../.claude/skills/agentic-ai-dev/reference/agent-memory-lifecycle.md) | `agentic-ai-reviewer`, `adk-reviewer` |

Precedence where domains overlap: a stricter security or domain requirement wins; otherwise the domain that owns the topic is canonical and the others reference it.

Section citations such as "governance §13.2", "eval strategy §7.9" or "DGP §6.2" in skills are requirement-section IDs. Each resolves to its toolkit home in [`docs/audits/standards-section-map.tsv`](../audits/standards-section-map.tsv); every requirement, with status and test evidence, is in [`docs/audits/ai-engineering-standards-coverage.tsv`](../audits/ai-engineering-standards-coverage.tsv) (summary: [`ai-engineering-standards-coverage.md`](../audits/ai-engineering-standards-coverage.md)).

Organisation-owned requirements (owners, Legal, Privacy, Compliance and executive approvals, contracts, cadences) appear as adoption checklists in the canonical skills. The toolkit does not enforce them.
