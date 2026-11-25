# API Performance Testing

Latency benchmarking for our backend APIs: NestJS 12.x (Fastify), Spring Boot 4.2 (MVC default, WebFlux when justified), FastAPI.

## When to Use

- Before/after a PR that changes a hot API endpoint
- When users report "the API feels slow"
- Establishing SLA baselines for a new service
- Comparing implementation approaches (e.g. reactive vs blocking)

## Tools

| Tool | When to use |
|------|------------|
| `playwright-cli eval` | Quick latency check from browser context |
| `curl` + bash loop | Simple sequential baseline (no extra deps) |
| `k6` | Load testing with concurrent requests and reports |

## Method 1: Quick Latency Check (curl loop)

Measures p50/p95/p99 for a single endpoint using bash:

```bash
# 100 sequential requests, collect all latencies
ENDPOINT="http://localhost:3000/api/users"
TOKEN="your-jwt-token"

for i in $(seq 1 100); do
  curl -s -o /dev/null -w "%{time_total}\n" \
    -H "Authorization: Bearer $TOKEN" \
    "$ENDPOINT"
done | sort -n | awk '
  BEGIN { count=0 }
  { times[count++] = $1 }
  END {
    p50 = times[int(count*0.50)]
    p95 = times[int(count*0.95)]
    p99 = times[int(count*0.99)]
    printf "p50: %.0fms  p95: %.0fms  p99: %.0fms\n", p50*1000, p95*1000, p99*1000
  }
'
```

Expected output:
```
p50: 12ms  p95: 45ms  p99: 120ms
```

## Method 2: Concurrent Load Test (k6)

Install: `brew install k6` or `npm install -g k6`

```javascript
// k6-api-test.js — tailored for our stack
import http from 'k6/http'
import { check, sleep } from 'k6'

export const options = {
  stages: [
    { duration: '30s', target: 10 },   // ramp up to 10 VUs
    { duration: '1m',  target: 10 },   // hold 10 concurrent
    { duration: '10s', target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // 95% of requests under 500ms
    http_req_failed:   ['rate<0.01'],  // error rate under 1%
  },
}

const BASE_URL = __ENV.BASE_URL || 'http://localhost:3000'
const TOKEN    = __ENV.API_TOKEN || ''

export default function () {
  const headers = { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' }

  // GET endpoint
  const res = http.get(`${BASE_URL}/api/users`, { headers })
  check(res, {
    'status 200': r => r.status === 200,
    'latency < 500ms': r => r.timings.duration < 500,
  })

  sleep(1)
}
```

Run:
```bash
k6 run --env BASE_URL=http://localhost:3000 --env API_TOKEN=$TOKEN k6-api-test.js
```

## Method 3: Quick Check via playwright-cli eval

For checking from the browser context (includes network overhead from client to server):

```bash
playwright-cli -s=perf goto http://localhost:4200
playwright-cli -s=perf eval "
  const t0 = performance.now();
  const r = await fetch('/api/health');
  const t1 = performance.now();
  \`Status: \${r.status}, Latency: \${Math.round(t1-t0)}ms\`
"
```

## SLA Targets — Our Stack

| API | p50 | p95 | p99 | Notes |
|-----|-----|-----|-----|-------|
| NestJS REST GET (simple) | < 20ms | < 100ms | < 300ms | Fastify + Prisma |
| NestJS REST POST (write) | < 50ms | < 200ms | < 500ms | Includes DB write |
| Spring Boot WebFlux GET | < 15ms | < 80ms | < 250ms | R2DBC reactive |
| FastAPI GET | < 25ms | < 120ms | < 350ms | Async endpoints |
| Authentication endpoint | < 100ms | < 300ms | < 800ms | BCrypt(12) is slow by design |

## Before/After Comparison

Run before and after a code change to measure regression:

```bash
# Step 1: Capture baseline
./run-curl-benchmark.sh > baseline.txt
cat baseline.txt
# p50: 12ms  p95: 45ms  p99: 120ms

# Step 2: Apply code change
# ... make changes, restart server ...

# Step 3: Compare
./run-curl-benchmark.sh > after.txt

# Step 4: Diff
paste baseline.txt after.txt | awk '{
  printf "Before: %s | After: %s\n", $0, $4
}'
```

Or use the table format:

```
| Endpoint | Before p50 | After p50 | Delta | Verdict |
|----------|-----------|-----------|-------|---------|
| GET /api/users | 12ms | 14ms | +2ms | OK |
| POST /api/orders | 45ms | 180ms | +135ms | REGRESSION |
```

## Anti-Patterns

- **Testing against localhost with no warm-up** — first request is always slow (JVM startup, connection pool init). Always discard first 5 requests or add a warm-up phase.
- **Single-request latency** — one curl call is not a benchmark. Use minimum 100 requests.
- **Not isolating the bottleneck** — if p99 is high, check: DB queries (`EXPLAIN ANALYZE`), N+1 patterns, external API calls, serialization. Don't optimize blindly.
- **Benchmarking through the Angular proxy** — adds network hop. Test backend APIs directly.
- **BCrypt timing** — authentication endpoints are intentionally slow (BCrypt strength=12 ≈ 100ms). This is correct, not a regression.
