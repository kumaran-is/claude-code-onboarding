# Production Folder Structure (3 layers)

The production layout extends the minimal layout in [node-mcp-setup.md](node-mcp-setup.md) (one `createServer` factory, thin entry files). It adds only what the production pages need. Create a folder when the first file for it exists, not before.

```
orders-mcp-server/
├── src/
│   ├── instrumentation.ts     # OTel bootstrap, loaded with `node --import` (node-ci-and-observability.md §1)
│   ├── register-hooks.ts      # ESM loader hook; first import of instrumentation.ts
│   ├── main.ts                # HTTP entry: listen, server timeouts, signal handling (production-runtime-shutdown-health.md §4)
│   ├── stdio.ts               # stdio entry (if the server also runs locally under a host)
│   │
│   ├── transport/             # Layer 1: HTTP and process concerns, no business logic
│   │   ├── http-server.ts     # /mcp + /health/live + /health/ready, Host/Origin guards, auth
│   │   └── lifecycle.ts       # readiness flag, in-flight tracking, graceful shutdown
│   │
│   ├── protocol/              # Layer 2: MCP surface
│   │   ├── server.ts          # createServer(): McpServer; registers tools/resources/prompts
│   │   ├── tools/             # one file per domain: register<Domain>Tools(server, deps)
│   │   └── telemetry.ts       # withToolTelemetry (observability-tracing.md §3)
│   │
│   ├── business/              # Layer 3: domain logic, no MCP types
│   │   ├── services/          # what a tool does, as plain async functions
│   │   └── clients/           # one module per upstream: pool + policy + guards (resilience-production.md §2)
│   │
│   ├── config.ts              # zod-validated env, read once at startup; fail fast
│   └── logger.ts              # pino; stdout for HTTP, stderr for stdio; redact paths
│
├── test/                      # vitest: in-process Client tests + process-level e2e with a fake OTLP collector
├── scripts/
│   ├── check-test-count.mjs   # executed-test-count gate (node-ci-and-observability.md §4)
│   └── load.mjs               # autocannon smoke with a p99 budget (resilience-production.md §4)
├── .github/workflows/ci.yml   # GitHub Actions only
├── Dockerfile                 # node-ci-and-observability.md §5
├── compose.yaml               # local stack, secrets from files (production-deployment-docker.md §1)
├── k8s/deployment.yaml        # probes, grace period, hardening (production-deployment-docker.md §2)
├── .nvmrc                     # Node version used by CI and the image
├── package.json / package-lock.json
└── tsconfig.json
```

## Layer rules

| Layer | Owns | Must not |
|-------|------|----------|
| Transport | HTTP server, probes, auth and Host/Origin checks, lifecycle, signal handling | contain tool logic or call upstreams except in readiness checks |
| Protocol | tool/resource/prompt registration, input/output schemas, mapping results and errors to MCP tool results, tool spans | hold connection pools or business rules |
| Business | domain rules, upstream clients with timeouts, breakers, bulkheads, caches | import MCP SDK types; it should be callable from a test or a CLI without MCP |

- Dependencies point down only: transport → protocol → business. Pools, policies and caches are created once at startup in `business/clients/*` and passed into `createServer(deps)`; the factory runs per request in the stateless transport and must stay cheap.
- Cross-cutting pieces stay small and live where they are used. Multi-tenant context, quotas and audit: [production-runtime-multi-tenant.md](production-runtime-multi-tenant.md). Security middleware: [security-core.md](security-core.md).
- The previous version of this page listed ~70 placeholder files (separate registries, transformers, encryption, HPA, docs). Generate only what a requirement needs; an empty `security/encryption.ts` is not security.
