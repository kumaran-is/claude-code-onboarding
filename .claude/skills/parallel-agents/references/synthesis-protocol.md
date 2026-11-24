# Synthesis Protocol

Template and rules for synthesizing outputs from multiple agents into a single deliverable.

---

## When to Use

After all agents in an orchestration complete — before reporting to the user.

**Rule:** Never present raw agent outputs side by side. Always synthesize into a single, deduplicated, severity-ordered report.

---

## Synthesis Steps

1. **Collect all agent outputs** — read each agent's findings completely
2. **Deduplicate** — merge identical or overlapping findings (same bug found by two agents = one entry, note both agents flagged it)
3. **Resolve contradictions** — if two agents disagree, note the disagreement and explain which finding is authoritative
4. **Order by severity** — CRITICAL -> HIGH -> MEDIUM -> LOW
5. **Produce verdict** — one of: APPROVE / NEEDS_REVIEW / BLOCK

---

## Synthesis Output Template

```markdown
## Orchestration Synthesis

### Task Summary
[One sentence: what was reviewed and for what purpose]

### Agents Dispatched
| Agent | Scope | Finding Count |
|-------|-------|---------------|
| [agent] | [what it reviewed] | [N findings] |

### Consolidated Findings

#### CRITICAL (must fix before merge)
- **[Finding title]** — [agent that found it] — `file:line`
  [One sentence description + concrete impact]

#### HIGH (should fix before merge)
- **[Finding title]** — [agent that found it] — `file:line`
  [One sentence description]

#### MEDIUM (fix in follow-up PR)
- **[Finding title]** — [agent that found it] — `file:line`
  [One sentence description]

#### LOW (tech debt backlog)
- **[Finding title]** — [agent that found it]
  [One sentence description]

#### Contradictions Noted
- [Agent A] says [X] but [Agent B] says [Y] — authoritative: [which is correct and why]

### Verdict
**[APPROVE | NEEDS_REVIEW | BLOCK]**

Verdict criteria (repo Review Severity Policy, `.claude/rules/verification-and-reporting.md`; domain reviewers may be stricter, never looser):
- APPROVE: zero CRITICAL, zero HIGH — MEDIUM/LOW listed as advisories, MEDIUMs tracked as follow-up tasks
- NEEDS_REVIEW: any HIGH (and no CRITICAL) — merge only after each HIGH is fixed or justified in writing in the PR; never reported as PASS. A required check that is BLOCKED or NOT RUN also caps the verdict here
- BLOCK: any CRITICAL — fix before merge

### Action Items
- [ ] [Critical fix 1] — assign to: [team/person]
- [ ] [High fix 1] — assign to: [team/person]
- [ ] [Medium fix 1] — schedule for follow-up PR
```

---

## Contradiction Resolution Rules

When two agents report conflicting findings:

| Situation | Resolution |
|-----------|-----------|
| Agent A flags issue, Agent B does not | Trust the agent whose domain is more relevant (e.g., nestjs-reviewer over code-reviewer for NestJS patterns) |
| Two reviewers flag the same issue differently | Use the higher severity rating |
| One agent claims implementation is correct, another claims it is wrong | Verify against the code manually; do NOT flip-flop based on confidence |
| Agent output seems hallucinated (file:line doesn't exist) | Discard finding, note it in synthesis as unverified |

---

## Anti-Patterns to Avoid

- **Raw dump:** Pasting all agent outputs without synthesis — unhelpful noise
- **Cherry-picking:** Only including findings from one agent — incomplete picture
- **False consensus:** Marking a finding as resolved because one agent didn't flag it
- **Severity inflation:** Calling everything CRITICAL — desensitizes the team
- **Missing verdict:** Presenting findings without a clear APPROVE/NEEDS_REVIEW/BLOCK
