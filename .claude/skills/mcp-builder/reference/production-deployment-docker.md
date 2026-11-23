# Production Deployment: Container, Compose, Kubernetes

Packaging and running a Node MCP server. The Dockerfile and the CI gates that build it are canonical in [node-ci-and-observability.md](../../deployment-ci-cd/reference/node-ci-and-observability.md) §4–5 (multi-stage, `npm ci --omit=dev`, base image pinned by digest, non-root, liveness `HEALTHCHECK`, exec-form `CMD` with `--import` for OpenTelemetry). This page covers what runs around it. Probe semantics and the shutdown sequence: [production-runtime-shutdown-health.md](production-runtime-shutdown-health.md).

Validation 2026-11-23: `docker compose config -q` exit 0 on the compose file (a control with an invalid `depends_on` condition exited 1); `kubeconform` 0.8.0 `-strict` exit 0 on the manifest (controls: a string grace period and a misspelt probe field each exited 1). `docker build` and running the stack were **BLOCKED** (no Docker daemon); the runtime stage was reproduced on the host instead (node-ci-and-observability.md §5). Image digests were read from the registry on that date.

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
            - { name: NODE_OPTIONS, value: "--max-old-space-size=384" } # ~75% of the memory limit
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
          startupProbe:
            httpGet: { path: /health/ready, port: http }
            periodSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet: { path: /health/ready, port: http }
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
          livenessProbe:
            httpGet: { path: /health/live, port: http }
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
```

- **Probes**: readiness and startup call `/health/ready` (dependencies); liveness calls `/health/live` (process only). Readiness `failureThreshold: 2 × 5 s` removes a replica within ~10 s of a dependency failure; liveness tolerates 30 s of unresponsiveness before a restart.
- **Grace period vs drain**: `readinessDrainMs + drainTimeoutMs + closers` (5 + 20 + ~2 s) must stay below `terminationGracePeriodSeconds` (30). The app flips readiness itself, so no `preStop` sleep is needed; if you add one, subtract it from `READINESS_DRAIN_MS`.
- `maxUnavailable: 0` keeps full capacity during a rollout; with readiness gating, a bad image never receives traffic and the rollout stalls instead of failing users.
- **Memory**: set `--max-old-space-size` to about 75% of the container limit so V8 collects garbage before the kernel OOM-kills the pod. No CPU limit (throttling inflates p99); keep a CPU request for scheduling.
- **Hardening**: non-root, no privilege escalation, all capabilities dropped, read-only root filesystem (mount an `emptyDir` at `/tmp` if a library writes temp files), no service-account token unless the pod calls the Kubernetes API.
- **Image by digest**: the placeholder `sha256:000…` is replaced by the digest CI produced; a tag can be re-pointed after review.
- Add a `PodDisruptionBudget` (`minAvailable: 2`) and spread replicas across zones with `topologySpreadConstraints` for anything user-facing.
- Session affinity is not needed for the stateless 2026-07-28 transport (`createMcpHandler`). Legacy sessionful transports need sticky routing or a shared event store ([node-mcp-advanced.md](node-mcp-advanced.md)).

## 3. Cloud Run

Cloud Run ignores the Dockerfile `HEALTHCHECK`. Configure a startup probe on `/health/ready` and a liveness probe on `/health/live` with the flags in [health-endpoints.md](../../deployment-ci-cd/reference/health-endpoints.md). Cloud Run gives 10 s between SIGTERM and SIGKILL, so shorten `READINESS_DRAIN_MS` (≈1 s) and `DRAIN_TIMEOUT_MS` (≤ 8 s) there. Deployment pipeline: `deployment-ci-cd` and `gcp-cloud-run` skills.
