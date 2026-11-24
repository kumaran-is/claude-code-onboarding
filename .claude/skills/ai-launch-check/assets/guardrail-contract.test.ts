// Guardrail contract tests (TypeScript + Zod 4 + Vitest): guardrails G3 tool boundary, G4 idempotency (ai-playbook/reference/engineering-guardrails.md).
// Run: `vitest run`; type-check: `tsc --noEmit`. Replace `toolBoundary` and `IdempotencyGate` with the service's
// real boundary and idempotency store (or call them over HTTP); keep the assertions. GR_BREAK=<name> disables one
// control so you can watch the matching test fail (negative control) before trusting a green run.
import { createHash } from "node:crypto";
import { describe, expect, test } from "vitest";
import { z } from "zod";

const broken = (name: string): boolean => (process.env.GR_BREAK ?? "").split(",").includes(name);

// Example write-tool contract; substitute your own tool name, version and schema.
const WriteArgs = z.strictObject({
  entity_id: z.string().regex(/^ent_[a-z0-9]+$/),
  amount_minor: z.int().positive().max(50_000),
  reason: z.enum(["a", "b", "other"]),
});
type WriteArgs = z.infer<typeof WriteArgs>;

const REGISTRY = { write_action: { version: "2.1", schema: WriteArgs } } as const;
type ToolName = keyof typeof REGISTRY;

type Outcome =
  | { ok: true; args: WriteArgs }
  | { ok: false; code: "TOOL_NOT_FOUND" | "SCHEMA_VERSION_MISMATCH" | "SCHEMA_VALIDATION_FAILED" };

function supported(requested: string, pinned: string): boolean {
  const [rMaj, rMin] = requested.split(".").map(Number);
  const [pMaj, pMin] = pinned.split(".").map(Number);
  return rMaj === pMaj && rMin <= pMin;
}

// tool exists -> schema version supported -> payload conforms to the pinned schema (authorization follows)
function toolBoundary(tool: string, version: string, payload: unknown): Outcome {
  if (!(tool in REGISTRY)) return { ok: false, code: "TOOL_NOT_FOUND" };
  const spec = REGISTRY[tool as ToolName];
  if (!supported(version, spec.version) && !broken("schema_version")) return { ok: false, code: "SCHEMA_VERSION_MISMATCH" };
  const parsed = spec.schema.safeParse(payload);
  if (!parsed.success && !broken("schema")) return { ok: false, code: "SCHEMA_VALIDATION_FAILED" };
  return { ok: true, args: (parsed.success ? parsed.data : payload) as WriteArgs };
}

const canonicalJson = (value: object): string => JSON.stringify(value, Object.keys(value).sort());
const sha256 = (s: string): string => createHash("sha256").update(s).digest("hex");

class IdempotencyGate {
  private readonly seen = new Map<string, { payloadHash: string; result: string }>();
  effects = 0;

  execute(org: string, entity: string, action: string, requestId: string, args: WriteArgs): { code: string; result?: string } {
    const payloadHash = sha256(canonicalJson(args));
    // Look up by the payload-independent scope; the standard's key (with payload hash) is persisted for audit.
    const scope = [org, entity, action, requestId].join("|");
    const prior = this.seen.get(scope);
    if (prior && !broken("idempotency")) {
      if (prior.payloadHash !== payloadHash && !broken("idempotency_hash")) return { code: "IDEMPOTENCY_PAYLOAD_MISMATCH" };
      return { code: "OK", result: prior.result };
    }
    this.effects += 1;
    const result = sha256([org, entity, action, payloadHash].join("|"));
    this.seen.set(scope, { payloadHash, result });
    return { code: "OK", result };
  }
}

const VALID = { entity_id: "ent_1", amount_minor: 1200, reason: "a" };

describe("G3 tool boundary", () => {
  test("invalid payload is rejected before execution", () => {
    expect(toolBoundary("write_action", "2.1", { ...VALID, amount_minor: "lots" }))
      .toEqual({ ok: false, code: "SCHEMA_VALIDATION_FAILED" });
  });

  test("unknown field is rejected, not stripped", () => {
    expect(toolBoundary("write_action", "2.1", { ...VALID, override_limit: true }))
      .toEqual({ ok: false, code: "SCHEMA_VALIDATION_FAILED" });
  });

  test("unsupported schema version is an explicit rejection", () => {
    expect(toolBoundary("write_action", "3.0", VALID)).toEqual({ ok: false, code: "SCHEMA_VERSION_MISMATCH" });
  });
});

describe("G4 idempotency", () => {
  test("duplicate call has one side effect; same key with a changed payload is rejected", () => {
    const gate = new IdempotencyGate();
    const first = toolBoundary("write_action", "2.1", VALID);
    if (!first.ok) throw new Error(`fixture rejected: ${first.code}`);
    const a = gate.execute("A", "ent_1", "write_action", "req-1", first.args);
    const b = gate.execute("A", "ent_1", "write_action", "req-1", first.args);
    expect(b.result).toBe(a.result);
    expect(gate.effects).toBe(1);
    const changed = toolBoundary("write_action", "2.1", { ...VALID, amount_minor: 9900 });
    if (!changed.ok) throw new Error(`fixture rejected: ${changed.code}`);
    expect(gate.execute("A", "ent_1", "write_action", "req-1", changed.args).code).toBe("IDEMPOTENCY_PAYLOAD_MISMATCH");
    expect(gate.effects).toBe(1);
  });
});
