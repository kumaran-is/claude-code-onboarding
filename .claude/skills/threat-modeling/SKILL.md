---
name: threat-modeling
description: "Threat modeling skill for STRIDE analysis, attack tree construction, and security requirement extraction. Use when designing new features, reviewing architecture, conducting threat modeling sessions, creating security documentation, or training teams on security thinking. Triggers: threat model, STRIDE, attack tree, DFD, security design, threat analysis, security architecture review."
allowed-tools: Read, Grep, Glob, Bash
agent: threat-modeling-expert
metadata:
  triggers: threat model, STRIDE, attack tree, security design, threat analysis, security architecture review, DFD
  related-skills: security-reviewer, sast-configuration, architecture-design
  domain: security
  role: architect
  scope: design
  output-format: document
last-reviewed: "2026-03-15"
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

## References

| File | Content | Load When |
|------|---------|-----------|
| `references/stride-methodology.md` | STRIDE matrix, DFD mapping, risk scoring formula, output template | STRIDE analysis, DFD mapping, risk scoring |
| `references/threat-mitigation-mapping.md` | Control library (16 controls), coverage scoring, budget prioritization | Selecting security controls, budget prioritization |

## Error Handling

If architecture documents are missing, reconstruct system topology from the codebase using Grep/Glob.
If a component lacks context for threat analysis, flag it explicitly rather than guessing.
