# Production Deployment: Container, Compose, Kubernetes

Packaging and running a Node MCP server. The Dockerfile and the CI gates that build it are canonical in [node-ci-and-observability.md](../../deployment-ci-cd/reference/node-ci-and-observability.md) §4–5 (multi-stage, `npm ci --omit=dev`, base image pinned by digest, non-root, liveness `HEALTHCHECK`, exec-form `CMD` with `--import` for OpenTelemetry). This page covers what runs around it. Probe semantics and the shutdown sequence: [production-runtime-shutdown-health.md](production-runtime-shutdown-health.md).

Validation 2026-11-23 (Node 26.13.1, Docker Engine 29.8.0): the §0 image was built and run with `--read-only --cap-drop ALL --security-opt no-new-privileges --memory 512m`; it turned healthy, and a real SDK v2 `Client` on the host negotiated `2026-07-28` (`auto`) and `2025-11-25` (default `legacy`), listed tools and got `isError: true` for an invalid id (exit 0). Controls: a foreign `Host` → 403; no allowlist on a `0.0.0.0` bind → exit 1; `MCP_ALLOWED_HOSTS=127.0.0.1:3300` (with port) → every request 403 and the `HEALTHCHECK` unhealthy. `docker stop` returned in 1 s with exit 0 (node is PID 1). `docker compose config -q` exit 0 on §1 (an invalid `depends_on` condition exited 1); `kubeconform` 0.8.0 `-strict` exit 0 on §2 (a misspelt `httpHeader` exited 1); the `actionlint` 1.7.12 run on the CI job exited 0 (a control with `${{ github.event.pull_request.title }}` inside `run:` exited 1). Image digests were read from the registry with `docker buildx imagetools inspect` on that date.

## 0. Node 26 image and runtime deltas

Base images (multi-arch index digests, verified 2026-11-23; Renovate/Dependabot bump them, never type a digest by hand):

| Image | Digest | Use |
|---|---|---|
| `node:26.13.1-trixie-slim` | `sha256:e6bedef217677b276c591795e169840edd9096dbf13f29df8ef8d1856b8820bc` | default build + runtime (glibc; 418 MB with the sample) |
| `node:26.13.1-alpine3.23` | `sha256:39d8c143e60e99ae98f014bebea1e72fc96d3c9bdf9504bc3a27af5c05bfa39f` | musl; only when every native dependency ships musl builds |
| `gcr.io/distroless/nodejs26-debian13:nonroot` | `sha256:ffa8a7545403036c94ec76674b5dbac2d425af2d679147cdf3e30180071487b7` | runtime only: no shell, uid 65532, 296 MB with the sample |

On top of the canonical Dockerfile (ESM output from `tsc`, `"type": "module"` in the copied `package.json`):

```dockerfile
# Heap below the container limit. With a 512 MiB limit, old space 384 MiB let RSS reach ~520 MiB under load; 320 kept it ~433 MiB.
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000 NODE_OPTIONS=--max-old-space-size=320
# OpenTelemetry bootstrap preloaded before the app (exec form: node stays PID 1 and receives SIGTERM).
CMD ["node", "--import", "./dist/instrumentation.js", "dist/http.js"]
```

Distroless runtime stage (the image's entrypoint is already `node`, so `CMD` lists only node arguments, and the `HEALTHCHECK` must call the binary by path):

```dockerfile
FROM ${NODE_IMAGE} AS build
# ... npm ci, npm run build ...
RUN npm prune --omit=dev
FROM gcr.io/distroless/nodejs26-debian13:nonroot@sha256:ffa8a7545403036c94ec76674b5dbac2d425af2d679147cdf3e30180071487b7
WORKDIR /app
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY package.json ./
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["/nodejs/bin/node", "-e", "fetch('http://127.0.0.1:3000/health/live').then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
CMD ["--import", "./dist/instrumentation.js", "dist/http.js"]
```

- **Host allowlist in containers.** A `0.0.0.0` bind arms no DNS-rebinding check unless `allowedHosts` and `allowedOrigins` are passed (`createMcpFastifyApp`, `@modelcontextprotocol/fastify` 2.0.1). The allowlist holds **hostnames without ports**, and the Fastify-wide hook also guards `/health/*`: include `127.0.0.1` (the `HEALTHCHECK` target), the Compose/Kubernetes service name, and the public hostname. A probe whose `Host` is the pod IP gets 403 (verified), so set the probe `Host` header (§2).
- **Heap.** Measured inside the 512 MiB container: `heap_size_limit` 332 MiB with `--max-old-space-size=320`, 268 MiB with no flag. Keep old space near 60–65% of the limit, not 75%.
- `npm ci --only=production` still works on npm 11.20.0 but warns `Use --omit=dev`; write `--omit=dev`.
- Smoke-test the running image from outside with the SDK, never just `curl /health`:

```javascript
// smoke.mjs: node smoke.mjs http://127.0.0.1:3300/mcp (exit 1 on any failure)
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';

const client = new Client({ name: 'smoke', version: '1.0.0' }, { versionNegotiation: { mode: 'auto' } });
await client.connect(new StreamableHTTPClientTransport(new URL(process.argv[2])));
const { tools } = await client.listTools();
if (tools.length === 0 || client.getNegotiatedProtocolVersion() !== '2026-07-28') process.exitCode = 1;
await client.close();
```

### CI job for an MCP server (GitHub Actions)

Extends the Node gates in [node-ci-and-observability.md](../../deployment-ci-cd/reference/node-ci-and-observability.md) §4 with the image build and an out-of-container client call. Action SHAs resolved with `git ls-remote` on 2026-11-23.

```yaml
  mcp-image:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version: 26.13.1
          cache: npm
      - run: npm ci
      - run: npm run typecheck
      - run: npm run lint
      - run: npm run test:ci
      - run: npm audit --audit-level=high
      - run: docker build -t mcp:ci .
      - name: Run hardened and call it with a real client
        run: |
          docker run -d --name mcp --read-only --cap-drop ALL --security-opt no-new-privileges --memory 512m \
            -p 127.0.0.1:3300:3000 -e MCP_ALLOWED_HOSTS=127.0.0.1,localhost -e MCP_ALLOWED_ORIGINS=http://localhost:3300 mcp:ci
          for _ in $(seq 1 30); do [ "$(docker inspect -f '{{.State.Health.Status}}' mcp)" = healthy ] && break; sleep 1; done
          node scripts/smoke.mjs http://127.0.0.1:3300/mcp
      - if: always()
        run: docker logs mcp; docker rm -f mcp
```

| Check (sample server, Node 26.13.1) | Observed |
|---|---|
| `tsc --noEmit` / planted `const n: number = "x"` | exit 0 / exit 2 |
| `vitest run` (real `Client` over Streamable HTTP) / one planted failing test | exit 0 (5 passed) / exit 1 |
| `eslint --max-warnings=0` / planted `console.log`, floating promise | exit 0 / exit 1 |
| `prettier --check` / unformatted file | exit 0 / exit 1 |
| `vitest run --coverage` with thresholds / functions below 80% | exit 0 / exit 1 |
| `npm audit --audit-level=high` | exit 0 |
| `/verify full` MCP block (stdio) | PASS, negotiated `2026-07-28` |
| MCP Inspector 2.16.0 `--cli ... --method tools/call` invalid argument | exit 5 (`isError: true`), so it can gate CI |

## 1. Compose (local and integration)

```yaml
# Local/integration stack. Secrets come from files outside git (./secrets/*.txt is gitignored), never inline values.
services:
  mcp-server:
    build: .
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      NODE_ENV: production
      PORT: "3000"
      HOST: 0.0.0.0
      # Hostnames only (no port): HEALTHCHECK target, host port mapping, and the service name other containers use.
      MCP_ALLOWED_HOSTS: 127.0.0.1,localhost,mcp-server
      MCP_ALLOWED_ORIGINS: http://localhost:3000
      OTEL_SERVICE_NAME: orders-mcp
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4318
      DATABASE_HOST: postgres
      DATABASE_NAME: orders
      DATABASE_USER: orders_app
      DATABASE_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    depends_on:
      postgres:
        condition: service_healthy
    stop_grace_period: 30s
    restart: unless-stopped

  postgres:
    image: postgres:17-alpine@sha256:f9cf3e1f0066f0eb0c48707d864f0ac5941e9ff454a072077d97a4d278d07d73
    environment:
      POSTGRES_DB: orders
      POSTGRES_USER: orders_app
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U orders_app -d orders"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes:
      - postgres-data:/var/lib/postgresql/data

  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.165.0@sha256:e40d61f10c9a617cca1ffd1be4d7e2b3a4b0f0001798ff07e58cabe82e618cea
    command: ["--config=/etc/otelcol/config.yaml"]
    volumes:
      - ./otel-collector.yaml:/etc/otelcol/config.yaml:ro

secrets:
  db_password:
    file: ./secrets/db_password.txt

volumes:
  postgres-data:
```

- No credential appears in the file: Postgres reads `POSTGRES_PASSWORD_FILE`, the app reads `DATABASE_PASSWORD_FILE` from a Compose secret backed by a gitignored file. The previous version of this page put a full database URL with an inline password in `environment:`; that pattern ends up in git, in `docker inspect`, and in crash dumps.
- The app must support the `_FILE` convention (read the file at startup), or receive the value from a secret manager. Never log the resolved value.
- `depends_on: condition: service_healthy` waits for `pg_isready`; it does not replace the app's own readiness check or its retry on first connect.
- The top-level `version:` key is obsolete in Compose v2 and is omitted.
- Ports bound to `127.0.0.1` keep the dev stack off the LAN. `stop_grace_period: 30s` (default 10 s) gives the drain time to finish before SIGKILL.
- Every image is pinned by digest; let Renovate/Dependabot bump them.

## 2. Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-mcp
  labels: { app: orders-mcp }
spec:
  replicas: 3
  selector:
    matchLabels: { app: orders-mcp }
  strategy:
    rollingUpdate: { maxUnavailable: 0, maxSurge: 1 }
  template:
    metadata:
      labels: { app: orders-mcp }
    spec:
      # readiness drain 5 s + drain timeout 20 s + closers ~2 s must fit inside this
      terminationGracePeriodSeconds: 30
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        seccompProfile: { type: RuntimeDefault }
      containers:
        - name: orders-mcp
          # Deploy by digest, not tag: the image that passed CI is the one that runs.
          image: registry.example.com/orders-mcp@sha256:0000000000000000000000000000000000000000000000000000000000000000
          ports:
            - { name: http, containerPort: 3000 }
          env:
            - { name: OTEL_SERVICE_NAME, value: orders-mcp }
            - { name: OTEL_EXPORTER_OTLP_ENDPOINT, value: "http://otel-collector:4318" }
            - { name: READINESS_DRAIN_MS, value: "5000" }
            - { name: DRAIN_TIMEOUT_MS, value: "20000" }
            - { name: NODE_OPTIONS, value: "--max-old-space-size=320" } # ~62% of the limit (§0)
            - { name: MCP_ALLOWED_HOSTS, value: "localhost,orders-mcp,orders-mcp.default.svc.cluster.local" }
            - { name: MCP_ALLOWED_ORIGINS, value: "https://app.example.com" }
            - name: DATABASE_PASSWORD
              valueFrom:
                secretKeyRef: { name: orders-mcp-db, key: password }
          resources:
            requests: { cpu: 250m, memory: 512Mi }
            limits: { memory: 512Mi }
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
          # The host allowlist guards /health/* too; kubelet sends Host: <pod IP>:<port> unless told otherwise.
          startupProbe:
            httpGet: { path: /health/ready, port: http, httpHeaders: [{ name: Host, value: localhost }] }
            periodSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet: { path: /health/ready, port: http, httpHeaders: [{ name: Host, value: localhost }] }
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
          livenessProbe:
            httpGet: { path: /health/live, port: http, httpHeaders: [{ name: Host, value: localhost }] }
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
```

- **Probes**: readiness and startup call `/health/ready` (dependencies); liveness calls `/health/live` (process only). Readiness `failureThreshold: 2 × 5 s` removes a replica within ~10 s of a dependency failure; liveness tolerates 30 s of unresponsiveness before a restart.
- **Grace period vs drain**: `readinessDrainMs + drainTimeoutMs + closers` (5 + 20 + ~2 s) must stay below `terminationGracePeriodSeconds` (30). The app flips readiness itself, so no `preStop` sleep is needed; if you add one, subtract it from `READINESS_DRAIN_MS`.
- `maxUnavailable: 0` keeps full capacity during a rollout; with readiness gating, a bad image never receives traffic and the rollout stalls instead of failing users.
- **Memory**: set `--max-old-space-size` to about 60–65% of the container limit (320 of 512 MiB, measured in §0) so V8 collects garbage before the kernel OOM-kills the pod; 75% (384) let RSS pass the limit under load. No CPU limit (throttling inflates p99); keep a CPU request for scheduling.
- **Hardening**: non-root, no privilege escalation, all capabilities dropped, read-only root filesystem (mount an `emptyDir` at `/tmp` if a library writes temp files), no service-account token unless the pod calls the Kubernetes API.
- **Image by digest**: the placeholder `sha256:000…` is replaced by the digest CI produced; a tag can be re-pointed after review.
- Add a `PodDisruptionBudget` (`minAvailable: 2`) and spread replicas across zones with `topologySpreadConstraints` for anything user-facing.
- Session affinity is not needed for the stateless 2026-07-28 transport (`createMcpHandler`). Legacy sessionful transports need sticky routing or a shared event store ([node-mcp-advanced.md](node-mcp-advanced.md)).

## 3. Cloud Run

Cloud Run ignores the Dockerfile `HEALTHCHECK`. Configure a startup probe on `/health/ready` and a liveness probe on `/health/live` with the flags in [health-endpoints.md](../../deployment-ci-cd/reference/health-endpoints.md). Cloud Run gives 10 s between SIGTERM and SIGKILL, so shorten `READINESS_DRAIN_MS` (≈1 s) and `DRAIN_TIMEOUT_MS` (≤ 8 s) there. Put the service's `run.app` hostname (and any custom domain) in `MCP_ALLOWED_HOSTS`; the `Host` header Cloud Run's own probes send was NOT verified here, so check the probe result after the first deploy (a 403 means the allowlist rejects it). Deployment pipeline: `deployment-ci-cd` and `gcp-cloud-run` skills.
