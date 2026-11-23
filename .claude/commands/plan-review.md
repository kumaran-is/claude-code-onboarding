---
description: Structured plan review with Phase 0 self-review, 5-phase technical review, approval triage, and production readiness gate
argument-hint: "[describe the change, paste the plan, or point to a PR/branch]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
disable-model-invocation: true
---

# Plan Mode Review

Review and validate a plan before implementation using a structured multi-phase process.

**Input:** $ARGUMENTS

## Steps

1. Load the `plan-mode-review` skill and read its reference files
2. Ask the user to select a mode:
   - **Big Change** — Phase 0 + all 5 review sections (up to 4 issues each)
   - **Small Change** — Phase 0 + top issue per section only
   - **Review Only** — Skip Phase 0, go straight to 5 review sections
3. Execute the selected workflow per the skill's process
   - For **Big Change** mode: after Phase 0 gate passes, run Phase 0.5 Confidence Gate (4-dimension scoring, threshold ≥ 80%; ≥ 95% for irreversible changes) before proceeding to Phase 1
4. Maintain a Decision Log throughout — update after each section
5. Present findings using the Structured Question Format from `review-interaction-protocol.md`
6. Verify the Production Readiness Gate before final approval
7. Summarize all decisions and next steps

Use instead when: `/brainstorm` — no plan yet, generate ≥3 options; `/exploration` — adversarially stress-test ONE proposed solution; `/aidlc` — run the full adaptive inception → construction → operations lifecycle with an audit log; `/design-architecture` — the plan needs an ADR and contracts first.
