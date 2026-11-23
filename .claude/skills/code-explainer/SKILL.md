---
name: code-explainer
description: "Explain a piece of code for handoff or onboarding: user-facing and modifier-facing views, the fragile part and the key assumption. Use for \"explain this code\", \"what does this do\", code walkthroughs. Not for whole-repo onboarding (codebase-onboarding)."
allowed-tools: Read, Grep, Glob, Bash
metadata:
  triggers: explain code, what does this do, code explanation, onboard, handoff, understand this code, document this function, code walkthrough
  related-skills: systematic-debugging, code-reviewer, codebase-onboarding
  domain: quality
  role: specialist
  scope: analysis
  output-format: report
last-reviewed: "2026-05-26"
---

# Code Explainer

## Iron Law

**TWO LEVELS EVERY TIME — NEVER COLLAPSE THEM INTO ONE**

Level 1 is for someone who uses the code. Level 2 is for someone who changes it. They need different information. Mixing them makes both audiences worse off.

## When to Use

- Inheriting code you did not write
- Onboarding a new developer to an existing module
- Preparing to modify something you haven't touched in months
- Handing off ownership to another team
- Writing documentation from code

## The Four Outputs (All Mandatory)

### Level 1 — For the User (what it does)

Explain what this code accomplishes in plain language. No jargon. A non-technical stakeholder should be able to read this and understand:
- What problem the code solves
- What inputs it needs
- What it produces or causes to happen

Write this as if you're explaining to a product manager, not a developer.

### Level 2 — For the Modifier (why it is built this way)

Explain the architectural decisions. A senior engineer about to touch this code needs to know:
- Why is it structured this way? (not just what it does)
- What would break if you changed X?
- What are the dependencies — internal and external?
- Where are the edge cases? What inputs cause unexpected behavior?
- What assumptions are baked in that aren't obvious from reading?
- What would a senior engineer want to verify before touching this?

Do not dumb this down. Level 2 readers are technical.

### The Fragile Part (1 sentence, mandatory)

The section of this code most likely to break under unexpected conditions — unusual inputs, concurrent access, external failures, edge-case data. Name the specific location (function, line, block), not a general area.

### The Assumption (1 sentence, mandatory)

The key assumption baked into this code that, if wrong, causes it to fail. This is not an edge case — it's a design premise. Examples: "assumes the caller always passes a non-null user object", "assumes the upstream API returns items in chronological order", "assumes this runs in a single-threaded context".

## Process

1. **Read the code** — do not explain from filenames or function names alone. Read the actual implementation.
2. **Trace execution** — follow the real data flow, not the intended data flow. Note where they differ.
3. **Find the structural decisions** — look for unusual choices: why a loop instead of a map, why a flag instead of a type, why synchronous instead of async.
4. **Identify the fragile section** — look for: unchecked array access, external calls without retry/timeout, regex on unvalidated input, shared mutable state, implicit ordering.
5. **Name the assumption** — ask: "What must be true for this to work correctly that the code doesn't verify?"
6. **Write Level 1 first** — forces you to understand what it actually does before explaining why.
7. **Write Level 2** — now add the structural reasoning. If you can't explain why, say so explicitly.

## Output Format

```
## [Function / Module / File Name]

### Level 1 — What It Does
[Plain language, no jargon. 2-5 sentences. Non-technical reader can follow this.]

### Level 2 — Why It Is Built This Way
[Architectural reasoning. Dependencies. What breaks if you change X. Edge cases. Implicit contracts.]

### The Fragile Part
[One sentence. Specific location. Why it breaks under unexpected conditions.]

### The Assumption
[One sentence. The design premise that, if wrong, causes failure.]
```

## Rules

- Level 1 must be readable by someone who does not code. Test this by re-reading and asking: "would a PM understand this?"
- Level 2 must be useful to a developer who knows the language. Do not over-simplify.
- The fragile part and the assumption are **never optional**. Every piece of code has both. If you cannot find them, you have not read the code carefully enough.
- If you genuinely cannot determine the assumption, say: "I haven't verified this — would need to trace the callers."
- Do not explain what the code says — explain what it means and why it is that way.

## Common Mistakes to Avoid

| Mistake | What to do instead |
|---------|-------------------|
| Restating the code in prose ("it loops through the list and…") | Explain the intent and the contract |
| Vague fragile part ("error handling could be improved") | Name the specific line or block and the specific failure mode |
| Generic assumption ("assumes valid input") | Name the specific invariant the code relies on |
| Collapsing Level 1 and Level 2 | Keep them separate — different readers, different needs |
| Explaining a function in isolation | Check what it calls and what calls it before writing Level 2 |

## Related

> For debugging broken code: use `systematic-debugging` skill.
> For reviewing code for quality issues: use `code-reviewer` skill.
> For onboarding to an entire codebase: use `codebase-onboarding` skill.
