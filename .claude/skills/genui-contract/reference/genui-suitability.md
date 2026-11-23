# GenUI suitability review: should this workflow use generated UI at all?

Run this **before** the contract-first workflow in `SKILL.md`. The contract says how to generate UI safely. This review decides whether the workflow should generate UI at all, and which parts must stay deterministic. It produces a report and never writes product code.

GenUI is not the default for new work. "Keep deterministic" and "reject" are first-class verdicts, and often the right ones. GenUI may change *presentation and interaction*. It must never become a second authority system.

**Governing question:** does adapting the UI at runtime reduce user friction, improve decision support or simplify exception handling enough to pay for its extra complexity, latency, risk and operating cost?

## When to run what

```
User-facing workflow change?
  NO  -> nothing to record.
  YES -> Is runtime adaptation a plausible option? (context varies, clarification branches,
         a long tail of exceptions, decision support in many shapes)
           NO  -> short form (below). Done.
           YES -> full review, for consequential workflows only.
```

Short form (settings, profile, fixed forms, refactors, small bugs):

```
GENUI: NOT APPLICABLE / KEEP DETERMINISTIC
Reason: <one evidence-based sentence with file:line or a screen ID>
```

## What counts as GenUI

| Counts (runtime UI adaptation) | Does not count |
|---|---|
| The agent picks an approved component from the catalog | AI-generated text inside a fixed card |
| The agent picks the next question in a bounded flow | A classifier result shown in a fixed UI |
| Bounded reordering or emphasis of approved sections | Server-driven data in a fixed layout |
| Cards, checklists or forms assembled from allowlisted parts | Deterministic conditionals, feature flags, fixed branching |

If the proposal is in the right-hand column, it is not GenUI. Review it with the normal stack skills.

## Patterns: analyse each subflow, never a whole screen

| Pattern | Definition | Stance |
|---|---|---|
| **CONTROLLED** | The agent picks from a closed set of approved components or questions. The client renders native catalog widgets with schema-validated props | Preferred when GenUI is justified |
| **DECLARATIVE** | The agent emits a structured surface (an A2UI tree) built from the allowlisted catalog | Only when it adds measurable value over CONTROLLED **and** a bundled deterministic fallback surface exists |
| **OPEN-ENDED** | Arbitrary runtime UI or code, unbounded components or actions | Reject by default for core workflows (gate G8) |

A single flow usually mixes patterns. For example, a clarification step may be CONTROLLED, emergency or legal copy deterministic, the scope selector (which account or record) deterministic, and the final submit an authoritative deterministic mutation.

## Authority model

```
Agent PROPOSES    -> which approved component, question or action INTENT comes next
Policy DECIDES    -> deterministic: is it permitted for this actor, scope, state and connectivity?
Workflow EXECUTES -> accepted intents through the existing authoritative command/service path
```

| The agent may | The agent must never own |
|---|---|
| Choose approved components | Authentication, authorisation, actor scope, eligibility |
| Sequence bounded questions | Safety stops and emergency downgrades |
| Choose contextual presentation | Payments, write admission, database mutation |
| Fill non-authoritative, user-editable defaults | Irreversible state transitions, dispatching work to other parties |
| Produce explanatory content | Idempotency, duplicate suppression, compliance |
| Propose action intents | Registering components, adding tools or actions |

Rendering an action does not authorise it. A user confirmation does not replace authorisation. A prompt instruction is not an enforcement boundary. Server-side handling: [action-security.md](action-security.md).

## Decision process (in order)

1. **Inspect** what exists today: AI features, GenUI, fallbacks, the write path, offline behaviour. Cite `file:line`, and label every claim VERIFIED or PROPOSED.
2. **Hard gates** (below). If any gate is TRUE, the verdict is **REJECT PROPOSED GENUI DESIGN**. A large benefit never overrides a failed gate.
3. **Simplest deterministic alternative.** Describe it concretely: a fixed screen, fixed branching or server-driven data. If it meets the need, the verdict is **KEEP DETERMINISTIC**.
4. **Benefit and cost**, only when every gate passes. Rate each dimension 1 / 3 / 5 / Unknown, with a rationale for each score.
5. **Verdict:** ADOPT / PILOT / KEEP DETERMINISTIC / REJECT PROPOSED GENUI DESIGN / INSUFFICIENT EVIDENCE.
6. **Pattern**, recorded separately for each subflow: NONE / CONTROLLED / DECLARATIVE.

**INSUFFICIENT EVIDENCE** is mandatory when the repository does not show the authoritative write path, the offline behaviour, whether the catalog fits or the fallback. Never invent a registry, renderer, policy service, offline guarantee, flag, metric or test to fill the gap. Name what is missing.

## The 8 hard gates (REJECT if any is TRUE)

| # | Gate | How to answer it from evidence |
|---|---|---|
| G1 | Model output can bypass authorisation or write admission | Trace every action intent to its executor. Any path where model JSON becomes a request body, URL or query without the existing validation makes this TRUE |
| G2 | A core workflow depends on a live model and has no deterministic continuation | Find the fallback **in code**, not in prose: a bundled surface, a static question bank or a native form |
| G3 | Untrusted content can add components, tools, actions or permissions | The component set is a closed allowlist checked on the client **and** the server. Tools are fixed when the agent is constructed. Text from documents, messages, uploads or OCR cannot add entries |
| G4 | Safety, legal or compliance information can be omitted, rewritten, downgraded or hidden | That copy is deterministic and sits in a native region the surface cannot hide or reorder. Model-authored safety text makes this TRUE |
| G5 | Action intents can bypass idempotency | Every write intent carries the existing idempotency key. A double tap, a replay or a switch to the fallback all resolve to one side effect |
| G6 | The UI or its actions cannot be schema-validated and tested within bounds | The surface is validated against the schema of the ONE A2UI version the stream declares (1.0 target, v0.9.x only for a renderer not proven on 1.0), and the reachable component × prop space can be enumerated for tests. Free-form layout, free-form action names, or a target renderer with no proven wire version make this TRUE |
| G7 | Actor, tenant, record or financial scope can escape its boundary | Scope comes from the authenticated caller and the route, never from model output. A model-chosen record ID, amount or recipient makes this TRUE |
| G8 | A core workflow needs arbitrary runtime UI or code without security approval | An OPEN-ENDED proposal on a core workflow without an approved ADR and `security-reviewer` sign-off makes this TRUE |

## Failure handling: every failure degrades to a NARROWER UI

| Failure | Required behaviour |
|---|---|
| Invalid JSON or schema mismatch | Discard the surface, render the deterministic continuation, log only the error type (never the raw payload) |
| Unknown component | Render the catalog's inert fallback. Never fetch or build the unknown widget |
| Unknown action | Drop it. Never map it to the "closest" action |
| Malformed props | Reject that component. The continuation keeps the answers already collected |
| Timeout or provider down | Use a bounded timeout from config, then the same continuation |
| Duplicate action | Collapsed by idempotency (G5) |
| Stale surface or replay | The surface carries a version or session binding, and is revalidated on reconnect before any write |

A fallback that offers more actions than the GenUI path did is itself a G3 failure.

## Offline continuity

State what happens when connectivity drops mid-flow. Answers already given must be preserved. Name the deterministic continuation. Switching between GenUI and the fallback must keep progress and intent semantics. A stale surface is invalidated and revalidated before any write. Say which writes are queued offline (each with an idempotency key) and which are online-only.

## Scoring (when every gate passes)

Score each benefit against the deterministic alternative, not against having nothing.

| Benefit | 1 | 5 |
|---|---|---|
| Friction reduction | The same steps either way | Most users skip many irrelevant fields or screens |
| Context variability | Every user needs the same inputs | The questions needed vary sharply with context |
| Clarification value | One fixed question set is enough | The next question really depends on earlier answers |
| Exception handling | Exceptions are rare or fit a fixed branch | A long tail of exception shapes that fixed branching cannot cover |
| Decision support | The user needs data, not guidance | The user must weigh several options with context-specific trade-offs |

| Cost | 1 (low) | 5 (high) |
|---|---|---|
| Safety or authority risk | Read-only presentation | The surface sits next to money, safety or irreversible state |
| Offline impact | A bundled fallback continues without the network | The flow stops without the model |
| Latency | Off the critical path | Every step waits for a model round-trip |
| Implementation and operations | Existing catalog, metrics and flags | New components, schema, fallback, dashboards, kill switch and eval set |
| Test burden | A bounded, enumerable space | Combinatorial surfaces that need golden, adversarial and device E2E tests |
| Accessibility and design risk | Catalog widgets only | New widgets or a dynamic layout that changes focus or reading order |

Do not add the scores into one number: a total hides a single 5 on safety behind several 5s on friction. Explain the deciding factors in prose. An Unknown on safety, authority or offline cost blocks ADOPT, so the verdict is at most PILOT or INSUFFICIENT EVIDENCE.

```
Any hard gate TRUE                                       -> REJECT PROPOSED GENUI DESIGN
Write path, offline behaviour, fallback or catalog fit
  missing from the evidence                              -> INSUFFICIENT EVIDENCE
Not GenUI, or the deterministic alternative meets the need -> KEEP DETERMINISTIC
Benefits clearly exceed costs, Unknowns only on value,
  bounded rollout possible                               -> PILOT (behind a flag, measured, reversible)
Benefits clearly exceed costs, value already shown,
  operations and rollback in place                       -> ADOPT
```

## ADOPT and PILOT also require

- **A value hypothesis**, and the deterministic baseline it is measured against.
- **Success measures** with a source for each baseline. Never invent thresholds. A target set before data exists is labelled `PROVISIONAL: needs product approval`. Candidates: completion rate, time to complete, abandonment at step N, rework rate, clarification turns, fallback frequency, schema-failure rate, p95 latency, model cost per completed flow.
- **An operating budget:** p95 latency against the existing timeout, model cost per flow, a ceiling on fallback frequency, and the metric that measures each (`deployment-ci-cd/reference/ai-observability.md`).
- **Rollback:** a kill switch, the fallback that remains, proof that in-flight progress survives, and a bounded rollout (`deployment-ci-cd/reference/llmops-release-and-rollout.md`).

Accessibility belongs to the catalog, not the model: semantics, target size, contrast, text scaling and screen-reader behaviour (`accessibility-audit`). A proposal that needs a widget outside the catalog is a catalog change first ([catalog-contract.md](catalog-contract.md) §Versioning), never a model capability.

## Red flags: stop and re-check

- "AI is available, so make it adaptive", with no user problem stated.
- A gate is "probably fine" with no `file:line`.
- The fallback is described in prose but not located in code.
- An action intent maps to a write with no named idempotency key.
- Safety or legal copy is written by the model.
- A threshold appears with no source and no PROVISIONAL label.
- The proposal adds a registry, renderer or framework next to the existing ones.

## Report outline (consequential workflows)

1 Verdict and confidence · 2 Scope reviewed · 3 Evidence (VERIFIED/PROPOSED, missing evidence) · 4 Existing AI/GenUI behaviour · 5 User problem · 6 Deterministic alternative · 7 Hard gates (each PASS/FAIL/UNKNOWN with evidence) · 8 Benefit/cost table · 9 Pattern per subflow · 10 Deterministic boundaries · 11 Offline continuity · 12 Failure handling · 13 Security and privacy · 14 Accessibility · 15 Tests · 16 Value hypothesis, success measures, budget and rollback (N/A unless ADOPT/PILOT) · 17 Smallest safe next step · 18 Open questions
