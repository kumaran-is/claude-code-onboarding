# Runtime Policy, Isolation, Transactions and Provider Exit (governance §4, §5, §8, §11, §12)

These are governance requirements on runtime behaviour. The toolkit supplies patterns, reviewers and tests for application code (boundary A/B); the shared enforcement infrastructure (LLM gateway, policy decision point, tool/MCP gateway, egress controls) is enterprise infrastructure (boundary C). A design document describing a gateway is not a gateway.

Boundary principle (§2.6): **the model proposes; deterministic enterprise services authorize and execute.** Prompts, model-generated JSON and probabilistic classifiers are never authorization boundaries.

## 1. Architectural invariants (§4.1)

| # | Invariant | Where the toolkit covers it | Boundary |
|---|---|---|---|
| 1 | Every model invocation passes through the approved model-access boundary | `ai-playbook` model routing; `agentic-ai-dev/reference/llm-inference-and-model-routing.md` (single client, allow-listed models) | B in app / C for the enterprise gateway |
| 2 | Every state-changing tool call is independently authorized | `agentic-ai-dev/reference/tool-execution-safety.md` (server-injected scope, allowlists); `mcp-builder` security references | A |
| 3 | Model output is not an authorization decision | `ai-security-reviewer` agent checklist; `tool-execution-safety.md` | A |
| 4 | Retrieval enforces source and tenant permissions | `rag-security-reviewer` (permission-aware, tenant-scoped retrieval) | A |
| 5 | Agents cannot expand their own privileges | `tool-execution-safety.md` (scope injected by server, never from model arguments) | A |
| 6 | Human approvals are tied to specific proposed actions | `approval_record.action_digest` (this skill) | A |
| 7 | State-changing workflows maintain durable operation records | `tool-execution-safety.md` §9 compensation, idempotency ledger | A |
| 8 | Gateway policies are versioned and auditable | Policy-as-code repository with review [C]; record policy version in `incident_record.policy_decision` | C |
| 9 | Sensitive data cannot reach unapproved providers or regions | `ai_bom` records provider + region per model [A/B]; egress enforcement [C] | B / C |
| 10 | Critical controls fail safely when dependencies are unavailable | Fail-closed tests per control (`control_evidence`, method `failure_injection`) | A / C |

## 2. Hard stops vs soft alerts (§5.1)

Hard stops must be deterministic at a trusted enforcement boundary. Probabilistic detection may inform, never independently authorize, a consequential action.

| Condition | Enforcement | Deterministic test to record as `control_evidence` |
|---|---|---|
| Unauthorized model provider | Hard block | Call with a non-allow-listed model id → rejected before any network call |
| Missing workload identity | Hard block | Request without workload credential → 401/403, no model call |
| Disallowed data residency | Hard block | Route restricted-class data to a non-approved region → rejected |
| Unauthorized tool invocation | Hard block | Principal without the tool grant → denied, no side effect (seeded scenario `unauthorized_tool_access`) |
| Cross-tenant access | Hard block | Tenant A principal requests tenant B resource → denied (`cross_tenant_retrieval`) |
| Missing required transaction approval | Hard block | Mutation without a valid `approval_record` → refused |
| Invalid mutation schema | Hard block | Tool args failing the strict schema → rejected before execution |
| Missing idempotency key | Hard block | State-changing call without key → rejected |
| Prohibited sensitive-data transfer | Hard block | DLP-classified payload to external tool/provider → blocked (`prohibited_sensitive_data_transfer`) |
| Uncertain untrusted input affecting consequential action | Deny action / human review | Injected retrieved content proposing a write → routed to review, not executed |
| Latency degradation | Alert, then circuit breaker at policy threshold | Breaker opens at the configured threshold |
| Rising token consumption | Alert, then quota enforcement | Budget exceeded → request refused with a typed error |
| Evaluation degradation | Alert or release block by threshold | CI gate (`eval-guide/reference/ci-tiers.md`) |
| Provider cost anomalies | Alert / budget policy | `gcp-finops`, `agentic-ai-dev/reference/agentic-cost-optimization.md` |
| Model drift | Monitor / reevaluate / rollback | `deployment-ci-cd/reference/llmops-release-and-rollout.md` |

Application-level tests for the hard stops: `agentic-ai-dev/reference/tool-execution-safety.md`, `mcp-builder` contract tests, `rag-security-reviewer`. Gateway-level enforcement (provider allow-list, workload identity, residency, DLP) is boundary C.

## 3. Policy decision architecture (§5.2) and latency (§5.3)

Centralised policy decision, distributed enforcement points. Policy inputs: principal and workload identity, tenant id, data classification, tool and action, resource ownership, transaction amount, region, model/provider, agent autonomy level, approval status, current resource state, request risk classification. Pass these as structured attributes from verified context (token, server state), never from model output.

Requirements (§5.3): deterministic evaluation; bounded execution time; horizontal scaling; policy versioning; safe decision caching; cache invalidation on permission changes; policy decision latency metrics; error budgets and availability SLOs; **fail-closed for sensitive mutations**; emergency revocation propagation. Never reuse stale authorization decisions for high-impact actions.

Illustrative targets (ADAPT, not universal): p95 local evaluation < 10 ms, p99 < 25 ms. Measure the complete end-to-end authorization path, including remote attribute lookups. Record the KPI as `kpi_definition` domain "Policy Engine". The toolkit does not ship a policy engine [C]; it can test that application code fails closed when the decision call times out [A].

## 4. Multi-tenant isolation (§8.1)

For systems above Medium risk, validate explicitly: tenant identity propagation; tenant-aware retrieval authorization; per-tenant vector access; agent memory isolation; cross-product access boundaries; tool authorization by tenant; shared orchestration isolation; cache isolation; trace and audit isolation; data-retention boundaries; cross-tenant deletion propagation.

The validator requires `tenant_isolation_validation_ref` on High/Critical multi-tenant risk assessments. Test patterns: `rag-security-reviewer` (retrieval), `agentic-ai-dev/reference/agentic-memory-systems.md` (memory namespaces), `vector-database` (per-tenant filters). Cache isolation is a frequent miss (see the fictional `incident_record` example).

## 5. Cross-agent trust (§8.2)

Agent output is untrusted input. Require: authenticated agent identity; delegation scopes; message schema validation; source provenance; explicit tool authority; restricted context sharing; maximum delegation depth; independent downstream authorization. **An agent cannot delegate permissions it does not possess**: the effective scope of a delegated call is the intersection of the caller's scope and the delegate's grant, computed by the server.

Tool-level implementation (authentication, scopes, schema validation on MCP/tool boundaries): `mcp-builder` security references, `security-reviewer/reference/mcp-security.md`, `tool-execution-safety.md`. Agent-to-agent identity infrastructure (workload identity for agents, delegation tokens) is boundary C.

## 6. Memory security (§8.3) and deletion verification (§8.4)

Threat models must include: persistent memory poisoning, cross-session contamination, cross-tenant memory leakage, prompt laundering between agents, embedding inversion, membership inference, unauthorized memory writes, stale memory, unauthorized retrieval. Use the AI section of `threat-modeling`.

Verify deletion, when applicable, across: primary records, document stores, vector indexes, embedding records, derived memory, application caches, search indexes, backups under defined retention controls. Maintain a source-to-derived mapping and deletion-propagation evidence. Records: `ai_bom.lineage.source_to_derived_map_ref` and `ai_bom.deletion_propagation_tests` (required by the validator for durable memory); each deletion test result is a `control_evidence` record (control AI-MEM-001). Backups usually cannot be selectively purged: document the retention window instead of claiming deletion [C/D].

Deletion is verified only by a plant → erase → probe test that asserts no item, snippet, count, embedding or cached answer still reflects the erased content (`.claude/skills/agentic-ai-dev/reference/agent-memory-lifecycle.md` (MEM §9) "Proof") [A: test template; C: store and backup policy]. A managed memory store's delete call is not proof. Example from google-adk 2.15.0 source: `BaseMemoryService.delete_memory` raises `NotImplementedError` unless a service overrides it, and `InMemoryMemoryService.delete_memory(memory_id=None)` returns without deleting anything; the Memory Bank revisions documentation (https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/revisions) keeps a deleted memory's child revisions accessible, and restorable, for up to 48 h. Record the store's residual window (revisions, backups, caches) in the erasure SLA evidence.

## 7. Agent transaction safety (§11)

State-changing agents need: durable workflow state, operation id, idempotency keys, deterministic authorization, explicit state transitions, bounded retries, outcome reconciliation, compensation where appropriate, human remediation path, complete audit records.

Flow (§11.2): authenticate → authorize → create operation id → persist workflow state → execute and persist each action → complete. On failure: reconcile external state → safe retry? yes: retry; no: compensate / quarantine / human review.

Classify each action as reversible, compensatable or irreversible (`approval_record.proposed_action.reversibility`). Never assume a financial settlement, external notification or irreversible customer action can be undone. Reconcile against authoritative state before any retry. Implementation patterns and tests: `agentic-ai-dev/reference/tool-execution-safety.md` (idempotency ledger, payload-mismatch rejection, compensation), `python-dev` outbox/idempotency reference. Seeded scenario `duplicate_financial_mutation` proves the ledger (§10.5).

## 8. Provider resilience and exit (§12)

Operational failover (§12.1): circuit breakers, timeouts, retry budgets, bulkheads, load shedding, approved model fallback, health monitoring, error budgets, graceful degradation. **Never fail over to an unapproved provider or region**: the fallback model must be in `ai_bom` with its region and pass the same eval gate. Patterns: `agentic-ai-dev/reference/llm-inference-and-model-routing.md`, `agentic-templates-resilience.md`.

Migration playbook (§12.2), assessed by test, not by document: prompt compatibility, tool-calling schema differences, structured output behaviour, safety behaviour, tokenization, context limits, embedding dimensionality, vector-index compatibility, evaluation changes, residency, latency/throughput, cost, fine-tuned adapter portability. Run the same golden + canary suites against the alternate provider (`eval-guide`); re-embedding: `/migrate-embedding-model`.

Exit readiness evidence (§12.3): alternate provider identified; contractual export rights [D]; data export procedures; model compatibility tests; tool integration tests; RAG reindexing plan; cost and performance benchmarks; migration rollback; business continuity plan. Embeddings, model caches and fine-tuned adapters are not portable between providers. Record the provider failover simulation as `control_evidence` for AI-OPS-002.

## 9. Reference architecture (§4)

Request path, each hop a trusted boundary: enterprise applications → API / workflow layer → **identity + policy boundary** → agent orchestrator, which fans out to three governed paths:

| Path | Boundary it must cross | Behind the boundary | Invariants (§1) |
|---|---|---|---|
| Model calls | Enterprise LLM gateway | Primary model and an approved fallback only (§8) | 1, 9, 10 |
| Retrieval | Retrieval authorisation boundary | RAG / vector data stores, filtered by source and tenant permissions | 4 |
| Tool actions | MCP / tool gateway | Deterministic business APIs → operation ledger → idempotency / SAGA → recovery and reconciliation (§7) | 2, 3, 5, 6, 7 |

Cross-cutting control plane: registry, risk, IAM, policy, AI BOM, evaluations, observability, human oversight, FinOps, audit, security, compliance, incident response. In an application without the enterprise gateways (boundary C), the same hops exist in-process: one model client module, one retrieval function that takes the tenant from verified context, one tool executor that authorises, checks the approval digest and writes the ledger. A review that finds a model, store or tool reachable around its hop reports a bypass, not a design choice.
