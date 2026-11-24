---
name: ai-playbook
description: "Decision framework and lifecycle router for AI features, workflows and agents: whether to use AI, model routing, RAG, tools, evals, prompt-injection defence, guardrails, observability. Use when designing, building, reviewing or debugging anything that calls an LLM, embeds, retrieves or runs an agent. Not for non-AI code, Claude Code tooling questions or conceptual AI questions with no applied design."
allowed-tools: Read
last-reviewed: 2026-11-22
metadata:
  triggers: AI feature design, should I use AI, build an agent, RAG design, LLM call, prompt injection, AI lifecycle, AI guardrails, AI observability
  related-skills: ai-playbook, ai-decision-record, ai-launch-check, ai-incident-response, ai-audit, ai-governance
---

# AI Application Playbook

## Iron Law

**Start one tier below where you think you need to be. Most "agent" problems are workflows; most "workflow" problems are a single model call. Use the smallest pattern that works.**

This skill encodes a production-grade framework for deciding when to use AI and how to ship it safely. The full playbook is in `playbook.md` (10k+ words across four layers); load it only when needed using the routing below.

## Prime Directive

> **Use AI for translation between the messy world and your clean system — never as the clean system itself.**

> **Everything the model reads is untrusted input. Everything the model writes is an untrusted proposal until validated.**

## Fast triage (use this first)

Before any AI design work, ask in order:

1. **Is the input messy / unstructured / ambiguous?** If no → deterministic code, stop.
2. **Can a downstream verifier (human or code) catch errors?** If no → don't use AI for the decision.
3. **Is this on the critical latency path with no fallback?** If yes → don't use AI here.
4. **Pick the smallest pattern that works**: single model call in a workflow → ReAct loop in a state machine → planning agent → autonomous agent. Start at #1.

If the answer to all three is "AI is appropriate," route to the relevant layer below.

## Lifecycle router (canonical home per stage)

This skill is the entry point for production AI work. Each stage has ONE canonical home; other files link there instead of restating it. Paths are under `.claude/`; skills load with the Skill tool, agents are dispatched with the Agent tool (read-only reviewers report NOT RUN for anything they did not execute). Always-on invariants for AI code: `rules/ai-engineering.md` (path-scoped).

| Stage | Canonical skill / reference | Review / gate | Command |
|---|---|---|---|
| 1. Design: AI or not, pattern, risk tier, autonomy | `skills/ai-playbook/playbook.md` Layers 1–2; `skills/ai-decision-record/` | `architect` agent for system-level design | `/ai-decision-record` |
| 2. Inference: provider abstraction, structured output, timeouts, retries/429, fallback, caching, token budgets | `skills/agentic-ai-dev/reference/llm-inference-and-model-routing.md`; Gemini specifics `skills/gemini-api-dev/`; prompts `skills/prompt-engineering-patterns/` | `agentic-ai-reviewer` | — |
| 3. Context and memory | `skills/agentic-ai-dev/reference/agentic-memory-systems.md` (principles: playbook §2.6 "Agent memory") | `agentic-ai-reviewer`, `ai-security-reviewer` (memory privacy) | — |
| 4. Agents and tool execution | `skills/agentic-ai-dev/` (LangChain/LangGraph), `skills/google-adk/` (ADK); tool safety `skills/agentic-ai-dev/reference/tool-execution-safety.md`; topologies `skills/multi-agent-patterns/`, durable workflows `skills/workflow-orchestration-patterns/` | `agentic-ai-reviewer`, `adk-reviewer` | `/scaffold-agentic-ai`, `/scaffold-google-adk` |
| 5. RAG: retrieval, permissions, vector stores | `skills/rag-architect/`, `skills/vector-database/`, `skills/weaviate/`; debugging `skills/rag-debugger/`; security `skills/rag-security-reviewer/` | `rag-implementation-reviewer`, `pgvector-schema-reviewer`, `weaviate-schema-reviewer` | `/rag-design`, `/scaffold-rag-pipeline`, `/rag-debug`, `/rag-review` |
| 6. Evals and testing (fake models, golden sets, judges, CI tiers) | `skills/eval-guide/`, `skills/llm-evaluation/`, `skills/rag-evaluator/`, `skills/adk-eval-guide/` | `ai-eval-designer` (design), `eval-reviewer` (code), `rag-eval-runner` (execution) | `/rag-eval-init` |
| 7. Review (full AI checklist) | `agents/ai-security-reviewer.md` checklist; audit orchestration `skills/ai-audit/` | `ai-security-reviewer` + the stack reviewer above | `/ai-audit` |
| 8. Guardrails G1–G24 (deterministic vs probabilistic, fail closed, egress, approvals, idempotency, kill switch) | `skills/ai-playbook/reference/engineering-guardrails.md` (canonical: G1–G24 and ten-laws requirement text, T-tier and action-tier tables, and per guardrail the impl, reviewer, gate, test); playbook §2.4–§2.6, §2.13; code: `skills/agentic-ai-dev/reference/agentic-guardrails-security.md`; §9 contract tests `skills/ai-launch-check/assets/` | `ai-security-reviewer` + stack reviewer | `/ai-decision-record`, `/ai-launch-check` |
| 8b. Enterprise governance (risk class, A0–A4 autonomy, approvals, AI BOM, control evidence); multi-tenant starter | `skills/ai-governance/`; tenant isolation checklist `skills/ai-playbook/reference/multi-tenant-ai-starter.md` | — | `/ai-audit` |
| 9. Observability (GenAI semconv traces, token/cost/TTFT metrics, redaction, prompt provenance, alerts) | `skills/deployment-ci-cd/reference/ai-observability.md` (extends `python-observability.md`); ADK specifics `skills/adk-observability-guide/` | — | — |
| 10. LLMOps (prompt/model versioning, eval-gated promotion, canary/rollback, provider migration, quota) | `skills/deployment-ci-cd/reference/llmops-release-and-rollout.md`; prompt registry `skills/eval-guide/reference/langfuse-prompts.md`; ADK deploy `skills/adk-deploy-guide/` | launch gate `skills/ai-launch-check/`; incidents `skills/ai-incident-response/` | `/ai-launch-check`, `/ai-incident-response` |
| 11. Streaming, multimodal, voice (optional) | `skills/streaming-protocols/`, `skills/ai-chat/`, `skills/voice-ai-development/` | — | — |

**Three tier vocabularies, never mixed:** engineering risk tier **T0–T3** (`reference/engineering-guardrails.md` §3: which of G1–G24 are mandatory), autonomy level **A0–A4** (governance standard §6), and this playbook's blast-radius tier **0–5** (playbook §2.2: review intensity). A fourth, per action: the principles action tier A0–A4 / Emergency (`engineering-guardrails.md`, written "principles A2"). Always name the vocabulary when writing a tier.

Claude Code session guardrails for AI work (hooks in `.claude/hooks/`): `pre-prompt-injection.sh` blocks terminal-escape and NUL shapes and advises on injection phrases; `output-llm-quota-guard.sh` separates billing/quota exhaustion (stop, BLOCKED) from transient rate limits (bounded retry); `prompt-secret-scan.sh` blocks provider keys in prompts; `post-edit-python-log-pii-advisory.sh` flags exception text in log calls.

## When to load the full playbook

Read `playbook.md` and apply the matching layer based on what the user is doing:

| User is doing... | Load these layers from playbook.md |
|------------------|-------------------------------------|
| Deciding whether to add AI to a feature | Layer 1 (Principles) |
| Architecting an AI feature | Layer 1 + Layer 2 (Operating Controls) |
| Writing code: schema validation, output contract, retries, fallback | Layer 2 §2.4, §2.5; Layer 3 §3.1, §3.5 |
| Writing prompts or designing prompts for security | Layer 2 §2.5; Layer 3 §3.2 (adversarial test catalog) |
| Building or reviewing an agent | Layer 2 §2.5, §2.6; Layer 3 §3.2 |
| Designing or evaluating RAG | Layer 2 §2.7; Layer 3 §3.2 retrieval-poisoning row |
| Picking a model / deciding to fine-tune | Layer 2 §2.9 |
| Sizing cost and latency | Layer 2 §2.10, §2.11; Layer 3 §3.4 |
| Designing eval set / regression tests | Layer 2 §2.14; Layer 3 §3.2 |
| Preparing for launch | Layer 4 §4.1 (unified launch checklist) |
| Setting up rollout or canary | Layer 4 §4.2 |
| Handling an incident | Layer 4 §4.3 |
| Testing kill switch | Layer 4 §4.4 |
| Onboarding to AI workflow (first 30 days) | Layer 4 §4.5 |
| Avoiding overbuilding | Layer 4 §4.6 |

For the unified Decision Record template, run the `/ai-decision-record` skill.
For the launch checklist, run `/ai-launch-check`.
For incident response, run `/ai-incident-response`.

## Default stance

When advising on AI design work:

- **Default to the Implementation Minimum** (six items in Layer 2 §2.3). Don't over-engineer on day one.
- **Push back when AI is the wrong tool.** The Red Flag Matrix (Layer 1 §1.6) lists where deterministic code wins.
- **Insist on the Output Contract** (Layer 2 §2.4) before any AI output mutates state.
- **Treat all model inputs as untrusted** — including retrieved documents, tool outputs, file uploads, and prior conversation turns from external sources.
- **Cite thumb rules sparingly.** Don't recite the playbook at the user; apply it.

## When NOT to load the full playbook

- Pure non-AI coding tasks (writing a SQL query, fixing a CSS bug, refactoring deterministic logic).
- Conversations about Claude Code or AI tooling itself, unless the user is *building* an AI feature using those tools.
- Questions about AI as a topic ("what is RAG?") without an applied design context.

When in doubt: skim the Fast Triage section, decide if AI is even the right answer, and only load `playbook.md` if it is.

## Fast triage example

```
User: "Should I use an LLM to classify support requests into 5 buckets?"

Fast triage:
1. Is input messy/unstructured? YES — free-text requests.
2. Can a downstream verifier catch errors? YES — human review queue + SLA.
3. On critical latency path with no fallback? NO — async classification.

→ AI is appropriate. Pattern: workflow (single model call + output contract).
   NOT an agent. Routing: Layer 2 §2.9 (model selection) + §2.14 (eval set: 100–300, precision/recall per class).

User: "I want to auto-approve expense reports under $100 using an LLM."

Fast triage:
1. Is input messy/unstructured? PARTIAL — structured form but free-text justification.
2. Can a downstream verifier catch errors? NO — auto-approval with no human check = direct financial action.

→ AI is NOT appropriate for auto-approval. Red Flag Matrix hit: Tier-4 action with no verifier.
   Recommend: AI as a draft/suggest assistant only, human approves.
```

## Verify (before routing to a lifecycle skill)

```
✅ Fast triage completed — AI is appropriate for this use case
✅ Correct playbook layer(s) identified from the routing table
✅ If user is starting a new feature → directed to /ai-decision-record
✅ If user is preparing to launch → directed to /ai-launch-check
✅ If there is a production incident → directed to /ai-incident-response
✅ Only loaded playbook.md sections relevant to the current task (not the full 10k words)
```

## If this skill cannot proceed

```
Situation: fast triage returns all NO (deterministic code is sufficient)
→ Do not load playbook.md. Output: "Based on the fast triage, this looks like a
  deterministic code problem. AI would add cost and complexity without benefit."

Situation: user insists on AI after triage says no
→ Apply the Red Flag Matrix (Layer 1 §1.6). Name the specific flags.
→ Output: "The Red Flag Matrix flags this as [reason]. I recommend against AI here.
  If you want to proceed anyway, run /ai-decision-record to document the justification."
```

## References

- Full playbook (4 layers): `.claude/skills/ai-playbook/playbook.md`
- Layer 1 §1.6 Red Flag Matrix: when NOT to use AI
- Layer 2 §2.3 Implementation Minimum: 6 required items before shipping any AI feature
- Layer 2 §2.4 Output Contract: schema → types → business rules → permissions → confidence → audit → route
- Layer 3 §3.2 Adversarial test catalog: prompt injection, tool misuse, retrieval poisoning
- Guardrails G1–G24, ten laws L1–L10, tiers and adoption checklist: `.claude/skills/ai-playbook/reference/engineering-guardrails.md`
- Multi-tenant AI starter (governance §14.1 golden path; checklist of the §8.1 isolation controls, each linked to its canonical file): `.claude/skills/ai-playbook/reference/multi-tenant-ai-starter.md`
- Lifecycle skills: `/ai-decision-record` → `/ai-launch-check` → `/ai-incident-response` → `/ai-audit` (full stage map: "Lifecycle router" above)
- OWASP Top 10 for LLM Applications (2025) and Agentic Applications (2026): https://genai.owasp.org/llm-top-10/ — per-class IDs and MITRE ATLAS mapping: `.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md` §3.1
- Data governance and privacy (egress, retention, erasure propagation, purpose limits): `.claude/skills/ai-playbook/reference/data-governance-privacy.md`
