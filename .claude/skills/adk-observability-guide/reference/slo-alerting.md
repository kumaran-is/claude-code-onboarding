# SLO-Based Alerting

> Prometheus mechanics for burn-rate alerts. The AI alert catalog (signals, owners, dedup, drift) lives in `.claude/skills/deployment-ci-cd/reference/ai-observability.md` §9. Metric names below are examples: label only with bounded values (never user or tenant ids).

> **Assumes Prometheus + Grafana stack.** Rule files are loaded via `rule_files:` in `prometheus.yml`. For alerting to fire, Alertmanager must be configured separately.

## SLO vs Threshold Alerting

**Threshold alerting** fires when a metric crosses a fixed value:

```yaml
# Threshold — fires constantly, low signal
- alert: HighErrorRate
  expr: rate(requests_total{status="error"}[5m]) / rate(requests_total[5m]) > 0.05
```

Problems: fires at 3am for a 2-minute spike; pages on noise; no sense of cumulative damage.

**SLO/burn-rate alerting** fires when you are consuming error budget faster than sustainable:

```yaml
# Burn-rate — fires only when budget is genuinely at risk
- alert: SLOAvailabilityBurnRateCritical
  expr: |
    rate(requests_total{status="error"}[1h]) / rate(requests_total[1h]) > (14.4 * 0.001)
    and
    rate(requests_total{status="error"}[5m]) / rate(requests_total[5m]) > (14.4 * 0.001)
```

The difference: burn-rate alerts tell you "at this rate, you will exhaust your monthly budget in X hours." That is always actionable. A 5% error rate for 30 seconds is not.

Reference: [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)

## SLO Targets (example values: set yours from measured baselines)

| SLO | Target | Error Budget |
|-----|--------|-------------|
| Availability | 99.9% | 0.1% = 43.8 min/month |
| Latency P95 — standard queries (`simple`, `standard` tier) | < 2s | Alert at 2x target (4s) |
| Latency P95 — complex queries (`complex`, `emergency` tier) | < 5s | Alert at 2x target (10s) |
| Correctness (sampled answers passing the frozen eval rubric) | 95% | 5% |
| Safety (critical policy guardrail, PII leak) | 100% | Zero tolerance |

## Burn Rate Windows

Three tiers of response urgency, each with its own burn-rate multiplier and window:

| Tier | Burn Rate | Window | Alert | Meaning |
|------|-----------|--------|-------|---------|
| Fast burn — page immediately | 14.4x | 1h | `SLOAvailabilityBurnRateCritical` | Budget exhausted in ~2 days |
| Slow burn — page within 1h | 6x | 6h | `SLOAvailabilityBurnRateHigh` | Budget exhausted in ~5 days |
| Budget exhaustion pace | 1x | 3d | `SLOAvailabilityBurnRateElevated` | Consuming budget at exactly SLO pace (non-paging notification) |

**How to read burn rate:** `14.4x` means errors are arriving 14.4 times faster than your SLO allows. At `14.4x` on a 99.9% SLO (0.1% error budget), the monthly budget is gone in `720h / 14.4 ≈ 50h` — roughly 2 days.

## Alert Rule Structure (example PromQL for `slo_alert_rules.yml`)

### Error Budget Record Rule

```yaml
- record: ai_agent:slo:availability:error_budget_remaining
  expr: |
    1 - (
      sum(increase(ai_agent_requests_total{status="error"}[30d]))
      /
      sum(increase(ai_agent_requests_total[30d]))
    ) / 0.001
```

This produces a gauge of remaining budget (1.0 = full, 0.0 = exhausted). Use it in Grafana dashboards for the error budget burn-down panel.

### Critical Burn Rate Alert (Dual-Window)

```yaml
- alert: SLOAvailabilityBurnRateCritical
  expr: |
    (
      sum(rate(ai_agent_requests_total{status="error"}[1h]))
      /
      sum(rate(ai_agent_requests_total[1h]))
    ) > (14.4 * 0.001)
    and
    (
      sum(rate(ai_agent_requests_total{status="error"}[5m]))
      /
      sum(rate(ai_agent_requests_total[5m]))
    ) > (14.4 * 0.001)
  for: 2m
  labels:
    severity: critical
    slo: availability
    burn_rate: "14.4x"
    window: "1h"
  annotations:
    summary: "SLO Availability - Critical burn rate (14.4x)"
    description: |
      Error rate is consuming error budget at 14.4x normal rate.
      At this rate, monthly budget will be exhausted in ~2.5 days.
      Current error rate: {{ $value | humanizePercentage }}
    runbook_url: "https://runbooks.example.com/ai-agent/slo-availability"
```

### High Burn Rate Alert (Dual-Window)

```yaml
- alert: SLOAvailabilityBurnRateHigh
  expr: |
    (
      sum(rate(ai_agent_requests_total{status="error"}[6h]))
      /
      sum(rate(ai_agent_requests_total[6h]))
    ) > (6 * 0.001)
    and
    (
      sum(rate(ai_agent_requests_total{status="error"}[30m]))
      /
      sum(rate(ai_agent_requests_total[30m]))
    ) > (6 * 0.001)
  for: 15m
  labels:
    severity: warning
    slo: availability
    burn_rate: "6x"
    window: "6h"
```

### Safety Alert (Zero-Tolerance, Immediate)

```yaml
- alert: SLOSafetyCriticalPolicyViolation
  expr: |
    increase(ai_agent_guardrail_violations_total{guardrail="critical_policy"}[5m]) > 0
  for: 0s    # Fire immediately — no grace period
  labels:
    severity: critical
    slo: safety
```

`for: 0s` means the alert fires on the first scrape that satisfies the condition. No burn rate calculation — any violation breaks the 100% SLO.

## Dual-Window Pattern

Every burn-rate alert uses TWO windows connected by `and`:

```
Long window  (1h or 6h)  AND  Short window (5m or 30m)
```

**Why both windows are required:**

- Long window alone: slow to detect sudden outages (waits for 1h of data)
- Short window alone: fires on brief spikes that self-resolve in minutes
- Both together: confirms the rate is sustained, not a transient spike

A spike that clears in 3 minutes fails the `for: 2m` check even if the short window was briefly elevated. The alert does not fire.

**How to read the PromQL:**
```
rate(errors[1h]) / rate(total[1h]) > (14.4 * 0.001)
```
- `14.4` = burn rate multiplier
- `0.001` = error budget (1 - 0.999 SLO target)
- `14.4 * 0.001 = 0.01440` = the threshold error rate that represents 14.4x burn

## Latency SLOs (from `slo_alert_rules.yml`)

Latency SLOs use histogram quantile rules, not burn rate, because latency has no "budget":

```yaml
# Record P95 for standard tier
- record: ai_agent:slo:latency:standard:p95
  expr: |
    histogram_quantile(0.95,
      sum(rate(ai_agent_request_latency_seconds_bucket{tier=~"simple|standard"}[5m])) by (le)
    )

# Alert at 2x target (4s, target is 2s)
- alert: SLOLatencyStandardCritical
  expr: |
    histogram_quantile(0.95,
      sum(rate(ai_agent_request_latency_seconds_bucket{tier=~"simple|standard"}[5m])) by (le)
    ) > 4
  for: 5m
```

Tier labels (`simple`, `standard`, `complex`, `emergency`) must be set on the metric at instrumentation time — the alert rules filter on them.

## Wiring into Prometheus

From `prometheus.yml` (lines 40–42):

```yaml
rule_files:
  - "/etc/prometheus/alert_rules.yml"        # Threshold alerts (health checks)
  - "/etc/prometheus/slo_alert_rules.yml"    # SLO burn-rate alerts
```

Both files are loaded. `alert_rules.yml` handles infrastructure health (API down, MCP failures). `slo_alert_rules.yml` handles SLO burn rates. Keep them separate — threshold alerts and SLO alerts answer different questions.

**Prometheus global config (from `prometheus.yml`):**

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s    # Rules evaluated every 15s
  scrape_timeout: 10s
  external_labels:
    environment: 'production'
    project: 'my-ai-agent'
```

`evaluation_interval: 15s` means burn-rate calculations update every 15 seconds. For `for: 2m` alerts, the condition must be true for at least 8 consecutive evaluations before firing.

## Grafana Dashboard Panel — Error Budget Burn

```promql
# Panel: Error budget remaining (0–1 gauge)
ai_agent:slo:availability:error_budget_remaining

# Panel: Current burn rate (multiplier)
(
  sum(rate(ai_agent_requests_total{status="error"}[1h]))
  /
  sum(rate(ai_agent_requests_total[1h]))
) / 0.001

# Panel: Time to budget exhaustion (hours)
1 / (
  (
    sum(rate(ai_agent_requests_total{status="error"}[1h]))
    /
    sum(rate(ai_agent_requests_total[1h]))
  ) / 0.001
) * 720
```

Set thresholds on the burn rate panel: green < 1x, yellow 1–6x, red > 6x.

## Checklist for Agentic AI SLOs

- [ ] Availability SLO defined with numeric error budget (e.g., 99.9% = 43.8 min/month)
- [ ] Latency SLO defined per query tier — `simple`/`standard` and `complex`/`emergency` have different targets
- [ ] Burn rate alerts use dual-window pattern (long AND short window) — no single-window alerts
- [ ] Fast burn fires in < 5 minutes; slow burn fires in < 30 minutes
- [ ] Safety operations (critical policy, PII) have 100% SLO with `for: 0s` (immediate fire)
- [ ] SLO metrics exposed via Prometheus histogram (latency) and counter (errors/total)
- [ ] Record rules pre-compute expensive quantile expressions (not inline in alert `expr`)
- [ ] `slo_alert_rules.yml` is separate from `alert_rules.yml` — different concerns
- [ ] Error budget record rule exists for dashboard burn-down panel
- [ ] Runbook URL in `annotations.runbook_url` for every critical alert
