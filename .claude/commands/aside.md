---
description: "Answer a side question without losing task state: freeze the current task, answer, then resume exactly where you left off."
argument-hint: '"[question]"'
allowed-tools: Read, Glob, Grep
---

# /aside — Answer a Side Question Without Losing Task State

Freeze current task state, answer the side question, then resume exactly where you left off.

## Behavior

When `/aside` is invoked (or the user says "aside:" or "quick question:"):

1. **FREEZE** — note the current task and last completed step
2. **READ-ONLY mode** — do not write code, create files, or run destructive commands during the aside
3. **ANSWER** — respond to the side question fully
4. **RESUME** — end the response with the footer below

## Resume Footer (mandatory)

Every aside response MUST end with:

```
---
**— Back to task:** [task name] — next step: [specific next action]
```

## Example

User is in the middle of implementing a NestJS auth guard when they ask:

> aside: what's the difference between JWT and session auth?

Response structure:
```
[Full answer to the JWT vs session question]

---
**— Back to task:** NestJS JWT auth guard — next step: implement `canActivate()` method in `auth.guard.ts`
```

## Edge Cases

### No question provided
```
/aside
```
Response: "What's the side question? (Currently working on: [task])"

### Question reveals a problem with current task
If the side question reveals that the current approach is wrong:
```
[Answer the question]

⚠️ This affects the current task: [explain impact]
Options:
A) Continue current approach with this caveat in mind
B) Stop and revise the approach before continuing
→ Which do you prefer?

---
**— Back to task:** [task name] — awaiting direction on approach
```

### Question is actually a task redirect
If the "aside" is really a new task (e.g., "aside: actually, implement X instead"):

```
This sounds like a task change, not a side question.
Current task: [task name] (last completed: [step])

Options:
A) Abandon current task and start [new task]
B) Finish current task first, then do [new task]
C) Keep this as a genuine aside — just explain [concept], don't implement

→ Which do you prefer?
```

## Constraints

- Do NOT write files, run builds, or modify state during an aside
- Do NOT lose track of the current task — always end with the resume footer
- The aside answer must be complete — do not defer it to "after the task"
- If the aside answer would take more than ~5 tool calls, flag it: "This aside is large — should we pause the task formally?"
