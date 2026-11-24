# Cold Start Optimization

Cold starts happen when Cloud Run scales from zero or creates a new instance. The flags and patterns below reduce startup latency.

## Universal Flags (All Stacks)

| Flag | Value | Notes |
|------|-------|-------|
| `--cpu-boost` | (no value) | Allocates extra CPU during startup. Most impactful single change. Always set for functions. |
| `--min-instances` | 0 (staging) / 1 (prod) | min=1 eliminates cold starts; costs money when idle. Use 0 for cost-sensitive staging. |
| `--cpu` | 1 (light) / 2 (heavy) | Higher CPU ratio speeds startup. Spring Boot benefits from cpu=2. |
| `--memory` | 256Mi–1Gi | Spring Boot ≥512Mi; Python FastAPI ≥256Mi; Node stacks 256Mi–512Mi. |
| `--concurrency` | 80 (default) / 1 (CPU-bound) | Set to 1 if the handler does heavy CPU work per request to avoid contention. |

### Recommended defaults per environment

```bash
# Staging — zero cost when idle
gcloud run deploy my-function \
  --cpu-boost \
  --min-instances 0 \
  --max-instances 5 \
  --cpu 1 \
  --memory 256Mi

# Production — warm instance always available
gcloud run deploy my-function \
  --cpu-boost \
  --min-instances 1 \
  --max-instances 20 \
  --cpu 2 \
  --memory 512Mi
```

---

## Python FastAPI

### Lazy Imports

```python
# Heavy, rarely used dependency: import inside the function that needs it
def render_report(html: str) -> bytes:
    import weasyprint  # deferred until the first report request

    return weasyprint.HTML(string=html).write_pdf()
```

Measure before moving imports: `python -X importtime -c "import my_service.main" 2> import.log` lists cumulative import time per module. Python 3.15 adds explicit `lazy import` statements (PEP 810); the stack is on 3.14, so that is DEFER (`python-patterns` skill, runtime decision).

### One worker per instance

Cloud Run scales instances and sets per-instance `--concurrency`; one uvicorn process per container avoids several workers competing for the boosted startup CPU.

```dockerfile
CMD ["uvicorn", "my_service.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--timeout-graceful-shutdown", "8"]
```

### Base image

Stay on `python:3.14.10-slim-trixie@sha256:...` for builder and runtime. `gcr.io/distroless/python3-debian13` is REJECTED for this stack: it ships Debian's CPython 3.13 (executed: `3.13.5`), so a venv built for 3.14 cannot run on it.

---

## NestJS / TypeScript / Fastify (Node 24)

### Lazy Module Loading

```typescript
// BAD — all providers eagerly initialized at startup
@Module({ imports: [HeavyModule] })
export class AppModule {}

// GOOD — lazy load modules not needed for every request
@Module({
  imports: [LazyModuleLoader],
})
export class AppModule {}
// In handler: await this.lazyModuleLoader.load(() => import('./heavy/heavy.module'))
```

### Tree-shaking and Bundle Size

Use `esbuild` or `@nestjs/cli` bundler to produce a single-file bundle — reduces module resolution overhead at startup.

```json
// nest-cli.json
{
  "compilerOptions": {
    "builder": "esbuild",
    "deleteOutDir": true
  }
}
```

---

## Plain Node.js services and MCP servers (Node 26)

Verified 2026-11-23 against Node 26.13.1, TypeScript 6.0.3, MCP SDK 2.4.0 and esbuild 0.28.2, locally (not on Cloud Run): a stdio server started by a real `Client`, then 50 tool calls, medians of 3 or more runs.

| Build | Connect (spawn → initialized) | Peak RSS |
|---|---|---|
| `tsc` output, unbundled ESM | 163–251 ms | 93–96 MB |
| esbuild CJS bundle (`.cjs`) | 80–159 ms | 78–80 MB |
| unbundled ESM + OTel NodeSDK (`--import`; sync hook / `module.register` fallback) | 341 / 434 ms medians (runs ranged to 1030 ms) | 126 / 140 MB |
| CJS bundle + OTel (`--require`) | 187–333 ms | 102–105 MB |

- Default to unbundled ESM. Bundle to CJS only when cold start is the measured bottleneck; name the output `.cjs` so a `"type": "module"` `package.json` does not make Node load it as ESM. Details and the OTel hook trade-off: `typescript-expert` › `references/node-service-engineering.md` §2.
- OTel adds about 30–45 MB RSS and 100 ms or more at start: load only the instrumentations you use.
- Heap: `NODE_OPTIONS=--max-old-space-size=320` for `--memory 512Mi`. V8's real limit is the flag plus about 96 MB, and RSS sits above the heap; with 384 the process reached 520 MiB RSS before V8's own OOM, past a 512 MiB limit.

---

## Spring Boot WebFlux (Java 21)

### JVM Startup Flags

```dockerfile
# Dockerfile — fast startup via tiered compilation tier 1 (interpreted only)
ENV JAVA_OPTS="-XX:TieredStopAtLevel=1 -XX:+UseSerialGC -Xmx512m"
CMD ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
```

| Flag | Effect | Trade-off |
|------|--------|-----------|
| `-XX:TieredStopAtLevel=1` | Skip JIT compilation on startup | Lower peak throughput (acceptable for short-lived functions) |
| `-XX:+UseSerialGC` | Lighter GC for small heaps | Not suitable for high-throughput services |
| `-Xmx512m` | Cap heap — prevents over-allocation | Set to 75% of `--memory` flag value |

### Distroless Java

```dockerfile
FROM gcr.io/distroless/java21-debian12
COPY --from=builder /app/target/app.jar /app.jar
CMD ["/app.jar"]
```

### CRaC (Checkpoint/Restore) — Advanced

CRaC snapshots the JVM after warmup and restores from snapshot on cold start. ~10x startup improvement. Requires:
- `eclipse-temurin:21-crac` base image
- `org.crac:crac` dependency
- GCP Cloud Run alpha feature: `--execution-environment gen2`

Only use CRaC if cold start > 3s after all other optimizations are applied.

---

## Cold Start Budget Reference

Typical cold start times after applying `--cpu-boost`:

| Stack | Typical Cold Start | After Optimization |
|-------|-------------------|-------------------|
| Python FastAPI (minimal) | 1.5–2.5s | 0.8–1.2s |
| NestJS (bundled) | 1.0–1.8s | 0.5–0.9s |
| TypeScript / Fastify | 0.6–1.2s | 0.3–0.6s |
| Node 26 MCP server (measured locally, not on Cloud Run) | 0.16–0.25s unbundled ESM | 0.08–0.16s CJS bundle |
| Spring Boot WebFlux | 3.0–5.0s | 1.5–2.5s (TieredStop=1) |

> These are estimates. Always measure with `gcloud run services describe --format='value(status.latestReadyRevisionName)'` and Cloud Run metrics in GCP Console before and after.
