---
name: threat-modeling
description: "Threat modeling skill for STRIDE analysis, attack tree construction, and security requirement extraction. Use when designing new features, reviewing architecture, conducting threat modeling sessions, creating security documentation, or training teams on security thinking. Triggers: threat model, STRIDE, attack tree, DFD, security design, threat analysis, security architecture review."
allowed-tools: Read, Grep, Glob, Bash
agent: threat-modeling-expert
metadata:
  triggers: threat model, STRIDE, attack tree, security design, threat analysis, security architecture review, DFD, AI threat model, agent threat model
  related-skills: security-reviewer, sast-configuration, architecture-design, ai-governance, ai-playbook
  domain: security
  role: architect
  scope: design
  output-format: document
last-reviewed: "2026-11-23"
---

## Iron Law: NO ARCHITECTURE REVIEW WITHOUT THREAT MODELING FIRST

Every new feature, service, or architectural change requires a threat model before implementation begins.

## When to Use

- New feature or service design → STRIDE analysis + DFD
- Architecture change → full DFD analysis of affected components
- Production security incident → post-incident threat review
- Security audit preparation → staleness check on all threat models

## Process

1. **Load methodology** — Read `references/stride-methodology.md` for STRIDE matrix, DFD element mapping, risk scoring, and output template
2. **Load control library** — Read `references/threat-mitigation-mapping.md` for control categories, the 16-control lookup table, and coverage scoring
3. **Model the system** — Identify assets, trust boundaries, DFD elements, and interactions
4. **Run STRIDE** — Apply per-element and per-interaction analysis using the methodology reference
5. **Map mitigations** — Select controls from the library; verify defense-in-depth across layers
6. **Score and report** — Calculate `risk = impact × likelihood`, document residual risks

## AI, RAG and Agent Systems

Apply when the system calls a model, retrieves for a model, gives an agent tools or stores agent memory. Source: `.claude/skills/ai-governance/SKILL.md` (GOV §2.6, §4, §8.2, §8.3) (governance); runtime invariants in `.claude/skills/ai-playbook/reference/engineering-guardrails.md`.

1. **Draw the extra trust boundaries.** Model output, retrieved documents, tool results, other agents' messages and memory reads are all **untrusted input** crossing into the orchestrator. The authorization boundary sits in deterministic services (policy, tool gateway, business API), never in the prompt or a classifier.
2. **Add these elements to the DFD:** model gateway, retrieval store (with tenant/ACL filter), tool/MCP gateway, each state-changing business API, operation ledger, memory store, approval service, every other agent.
3. **Enumerate AI threats per element** (map each to a STRIDE letter):

| Threat | STRIDE | Typical element | Deterministic mitigation to require |
|---|---|---|---|
| Direct / indirect prompt injection (incl. via retrieved content) | T, E | Orchestrator, retrieval | Action gate outside the model; tool scope injected by server |
| Unauthorized tool invocation, excessive agency | E | Tool gateway | Per-principal, per-tenant tool authorization; least agency |
| Model output used as authorization | E | Business API | Independent authorization of every state change |
| Cross-tenant retrieval or cache leakage | I | Retrieval, cache, traces | Tenant filter in the query; tenant in every cache key |
| Sensitive data / system prompt / secret disclosure | I | Model gateway, logs | DLP/redaction; secrets never in context |
| Agent-to-agent impersonation, delegation beyond own scope, unbounded delegation depth | S, E | Agent messages | Authenticated agent identity; delegation scope ⊆ caller scope; max depth; schema validation |
| Memory poisoning, cross-session contamination, unauthorized memory writes, stale memory | T, I | Memory store | Write authorization, provenance, namespacing, TTL, re-read canonical state |
| Embedding inversion, membership inference | I | Vector store | Access control on vectors; no shared indexes across tenants |
| Duplicate or replayed mutation; stale approval | T, R | Business API, approval service | Idempotency key + payload hash; approval bound to action digest and expiry |
| Model/data/tool supply-chain compromise | T | Artifacts | Pinned versions, digests, provenance (AI BOM) |
| Cost or loop exhaustion | D | Orchestrator, provider | Budgets, iteration caps, quotas |
| Unsafe fallback to an unapproved provider/region | I | Model gateway | Allow-listed fallback only |

4. **Cross-reference:** OWASP Top 10 for LLM Applications and OWASP agentic security guidance (https://genai.owasp.org/), MITRE ATLAS techniques (https://atlas.mitre.org/). Cite the category per threat; do not invent technique ids, look them up. Verified IDs per attack class (OWASP LLM 2025, OWASP Agentic 2026, MITRE ATLAS 2026.10) and the trust-boundary worksheet: `.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md` §2, §3.1; per-layer controls (input, retrieval, model, tool, output, monitoring) for each class: §3.2. Every trust-boundary arrow needs a named control; an arrow with no control is a finding.
5. **Hand-offs:** each AI threat's mitigation becomes a guardrail requirement (`ai-playbook`), an eval or red-team case (`eval-guide`), and, for governed systems, a control row and seeded test (`ai-governance`: `control_register_entry`, `control_evidence`). The `risk_assessment.threat_model_ref` points at the resulting document.

## References

| File | Content | Load When |
|------|---------|-----------|
| `references/stride-methodology.md` | STRIDE matrix, DFD mapping, risk scoring formula, output template | STRIDE analysis, DFD mapping, risk scoring |
| `references/threat-mitigation-mapping.md` | Control library (16 controls), coverage scoring, budget prioritization | Selecting security controls, budget prioritization |

## Error Handling

If architecture documents are missing, reconstruct system topology from the codebase using Grep/Glob.
If a component lacks context for threat analysis, flag it explicitly rather than guessing.
