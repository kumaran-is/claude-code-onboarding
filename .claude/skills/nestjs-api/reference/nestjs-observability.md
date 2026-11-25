# NestJS Observability & Logging

Observability patterns for NestJS 12.x covering OpenTelemetry tracing, metrics, and structured logging.

## Structured Logging Configuration

Configuration for structured logging with cloud provider support and request logging.

### Configuration File (`src/config/logging.config.ts`)

```typescript
/**
 * Structured Logging Configuration
 *
 * Supports multiple output formats and cloud logging providers:
 * - JSON format for production (GCP, AWS compatible)
 * - Pretty format for development
 * - Configurable log levels per environment
 */

import { registerAs } from '@nestjs/config';
import { getOptionalString, getRequiredBoolean, getRequiredString } from './static-config-reader.js';

export default registerAs('logging', () => ({
  // Log level: error, warn, log, debug, verbose
  level: getRequiredString('LOG_LEVEL'),

  // Output format: json, pretty
  format: getRequiredString('LOG_FORMAT'),

  // Include timestamps in logs
  timestamps: getRequiredBoolean('LOG_TIMESTAMPS'),

  // Service context for structured logging
  serviceContext: {
    service: getRequiredString('APP_NAME'),
    version: getRequiredString('APP_VERSION'),
    environment: getRequiredString('NODE_ENV'),
  },

  // Cloud logging configuration
  cloudLogging: {
    // Enable cloud logging integration
    enabled: getRequiredBoolean('CLOUD_LOGGING_ENABLED'),

    // GCP-specific
    gcpProjectId: getOptionalString('GCP_PROJECT_ID'),

    // AWS-specific
    awsRegion: getOptionalString('AWS_REGION'),
    awsLogGroup: getOptionalString('AWS_LOG_GROUP'),
  },

  // Request logging
  requestLogging: {
    // Log all requests
    enabled: getRequiredBoolean('LOG_REQUESTS'),

    // Fields to exclude from request body logging
    excludeFields: ['password', 'token', 'secret', 'apiKey', 'authorization'],

    // Max body size to log (bytes)
    maxBodySize: 10000,

    // Log slow requests (ms)
    slowRequestThreshold: 3000,
  },
}));
```

Defaults for the factory above, in `src/config/env.ts` (one place; `@nestjs/config` applies them before the
factory runs):

```typescript
  APP_NAME: z.string().min(1),
  APP_VERSION: z.string().min(1),                       // set by CI from the image tag; no fake default
  LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'log', 'debug', 'verbose']).default('log'),   // Nest LogLevel values
  LOG_FORMAT: z.enum(['json', 'pretty']).default('json'),
  LOG_TIMESTAMPS: z.stringbool().default(true),
  CLOUD_LOGGING_ENABLED: z.stringbool().default(false),
  LOG_REQUESTS: z.stringbool().default(true),
```

## OpenTelemetry Configuration

Configuration for distributed tracing and metrics collection via OpenTelemetry.

### Configuration File (`src/config/observability.config.ts`)

```typescript
/**
 * OpenTelemetry Observability Configuration
 *
 * Configures distributed tracing and metrics collection:
 * - OTLP exporters for traces and metrics
 * - Auto-instrumentation for common libraries
 * - Sampling strategies
 */

import { registerAs } from '@nestjs/config';
import { getOptionalString, getRequiredBoolean, getRequiredNumber, getRequiredString } from './static-config-reader.js';

export default registerAs('observability', () => ({
  // Master switch for observability
  enabled: getRequiredBoolean('OTEL_ENABLED'),

  // Service identification
  // Precedence between two declared variables (OTel spec), not a literal default.
  serviceName: getOptionalString('OTEL_SERVICE_NAME') ?? getRequiredString('APP_NAME'),
  serviceVersion: getRequiredString('APP_VERSION'),
  deploymentEnvironment: getRequiredString('NODE_ENV'),

  // Tracing configuration
  tracing: {
    enabled: getRequiredBoolean('OTEL_TRACING_ENABLED'),

    // OTLP exporter endpoint
    endpoint: getOptionalString('OTEL_EXPORTER_OTLP_TRACES_ENDPOINT') ??
              `${getRequiredString('OTEL_EXPORTER_OTLP_ENDPOINT')}/v1/traces`,

    // Sampling rate (0.0 to 1.0)
    samplingRatio: getRequiredNumber('OTEL_TRACES_SAMPLER_ARG'),

    // Always sample errors
    alwaysSampleErrors: true,
  },

  // Metrics configuration
  metrics: {
    enabled: getRequiredBoolean('OTEL_METRICS_ENABLED'),

    // OTLP exporter endpoint
    endpoint: getOptionalString('OTEL_EXPORTER_OTLP_METRICS_ENDPOINT') ??
              `${getRequiredString('OTEL_EXPORTER_OTLP_ENDPOINT')}/v1/metrics`,

    // Export interval (ms)
    exportIntervalMs: getRequiredNumber('OTEL_METRIC_EXPORT_INTERVAL'),
  },

  // Instrumentation options
  instrumentation: {
    http: true,
    fastify: true,
    prisma: true,
    redis: true,
    dns: false, // Usually too noisy
    fs: false, // Usually too noisy
  },
}));
```

Its schema entries (defaults once, in `src/config/env.ts`; the OTLP variable names follow the OpenTelemetry spec):

```typescript
  OTEL_ENABLED: z.stringbool().default(false),
  OTEL_TRACING_ENABLED: z.stringbool().default(true),
  OTEL_METRICS_ENABLED: z.stringbool().default(true),
  OTEL_SERVICE_NAME: z.string().min(1).optional(),
  OTEL_EXPORTER_OTLP_ENDPOINT: z.url().default('http://localhost:4318'),
  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: z.url().optional(),
  OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: z.url().optional(),
  OTEL_TRACES_SAMPLER_ARG: z.coerce.number().min(0).max(1).default(1),
  OTEL_METRIC_EXPORT_INTERVAL: z.coerce.number().int().positive().default(60_000),
```

## OpenTelemetry Tracing Bootstrap

Start the SDK **before** any application module is loaded, from a separate entry file passed to `node --import`.
An SDK started in a Nest `onModuleInit` starts too late: `http` and Fastify are already loaded, so their
auto-instrumentation never patches them.

Verified 2026-11-24 on NestJS 12.6.0 / Fastify 5.12.8 / Node 26.13.1 with `@opentelemetry/sdk-node` 0.301.2,
`@opentelemetry/sdk-trace` 3.1.1, `@opentelemetry/instrumentation-http` 0.301.2 and `@opentelemetry/api` 1.10.0:
one server span per HTTP request in the console exporter, `/health` excluded.

### Instrumentation entry (`src/instrumentation.ts`)

```typescript
import { HttpInstrumentation } from '@opentelemetry/instrumentation-http';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { ConsoleSpanExporter, SimpleSpanProcessor } from '@opentelemetry/sdk-trace';

/**
 * Loaded with `node --import ./dist/instrumentation.js dist/main.js`, before any app module,
 * so the http module is patched before Fastify requires it. Console exporter here; swap in
 * an OTLP exporter for a real collector.
 */
const sdk = new NodeSDK({
  serviceName: 'orders-api',
  spanProcessors: [new SimpleSpanProcessor({ exporter: new ConsoleSpanExporter() })],
  instrumentations: [new HttpInstrumentation({ ignoreIncomingRequestHook: (req) => req.url === '/health' })],
});
sdk.start();

process.once('SIGTERM', () => {
  sdk.shutdown().catch((error: unknown) => {
    process.stderr.write(`otel shutdown failed: ${String(error)}\n`);
  });
});
```

`package.json`: `"start:prod": "node --import ./dist/instrumentation.js dist/main.js"`; the Dockerfile `CMD` uses the
same arguments.

### Production exporter (OTLP over HTTP)

Replace the processor with a batching one and an OTLP exporter (`@opentelemetry/exporter-trace-otlp-http` 0.301.2;
constructor and option names checked against its published types, not run against a collector):

```typescript
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace';

// Endpoint, headers and sampler come from the standard OTEL_EXPORTER_OTLP_* / OTEL_TRACES_SAMPLER* env vars.
spanProcessors: [new BatchSpanProcessor({ exporter: new OTLPTraceExporter() })],
```

Breaking changes from the 1.x/0.5x SDKs used in earlier versions of this page (each one fails `tsc`):

| Old | Now |
|---|---|
| `new Resource({ [ATTR_SERVICE_NAME]: … })` | `serviceName: '…'`, or `resource: defaultResource().merge(resourceFromAttributes({ … }))` (`Resource` is type-only) |
| `spanProcessor: new BatchSpanProcessor(exporter)` | `spanProcessors: [new BatchSpanProcessor({ exporter })]` |
| `@opentelemetry/sdk-trace-node` / `sdk-trace-base` processors | `@opentelemetry/sdk-trace` |
| `await sdk.start()` inside `TracingModule.onModuleInit` | `sdk.start()` in the `--import` entry; never swallow its errors |

Optional: `getNodeAutoInstrumentations()` from `@opentelemetry/auto-instrumentations-node` instead of
`HttpInstrumentation` (disable `instrumentation-fs` and `instrumentation-dns`, which are noisy).

### `@nestjs/observe` — DEFER

NestJS 12 ships `@nestjs/observe` (0.3.27, pre-1.0) and `nest new` enables it in a non-interactive run unless you
pass `--no-observe`. It reports to the hosted, paid Observe platform and needs its app key and secret; it adds
nothing without that service. Use OpenTelemetry above (vendor-neutral, works with any collector). Revisit if the
team adopts the Observe platform.

## Logging Interceptor

Global request/response logging interceptor with correlation ID tracking.

### Implementation (`src/common/interceptors/logging.interceptor.ts`)

```typescript
import { Injectable, NestInterceptor, ExecutionContext, CallHandler, Logger } from '@nestjs/common';
import { Observable } from 'rxjs';
import { tap, catchError } from 'rxjs/operators';

/**
 * Global Logging Interceptor
 *
 * Logs all incoming requests and responses with:
 * - Request method, URL, and correlation ID
 * - Response status and duration
 * - Errors with stack traces
 * - Automatic masking of sensitive fields
 */
@Injectable()
export class LoggingInterceptor implements NestInterceptor {
  private readonly logger = new Logger(LoggingInterceptor.name);
  private readonly sensitiveFields = ['password', 'token', 'secret', 'apiKey', 'authorization'];

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const request = context.switchToHttp().getRequest();
    const correlationId = request.headers['x-correlation-id'] ?? 'unknown';
    const { method, url } = request;

    this.logger.log(`[${correlationId}] → ${method} ${url}`);
    const start = Date.now();

    return next.handle().pipe(
      tap(() => {
        const response = context.switchToHttp().getResponse();
        const duration = Date.now() - start;
        this.logger.log(
          `[${correlationId}] ← ${method} ${url} ${response.statusCode} ${duration}ms`
        );
      }),
      catchError((error) => {
        const duration = Date.now() - start;
        this.logger.error(
          `[${correlationId}] ✗ ${method} ${url} ${error.status ?? 500} ${duration}ms`,
          error.stack
        );
        throw error;
      }),
    );
  }

  private maskSensitiveData(body: Record<string, unknown>): Record<string, unknown> {
    if (!body || typeof body !== 'object') {
      return body;
    }

    const masked = { ...body };
    for (const field of this.sensitiveFields) {
      if (field in masked) {
        masked[field] = '***REDACTED***';
      }
    }
    return masked;
  }
}
```

### Registration

```typescript
// main.ts (ESM: relative imports carry .js)
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, type NestFastifyApplication } from '@nestjs/platform-fastify';
import { AppModule } from './app.module.js';
import { LoggingInterceptor } from './common/interceptors/logging.interceptor.js';

const app = await NestFactory.create<NestFastifyApplication>(AppModule, new FastifyAdapter());
app.useGlobalInterceptors(new LoggingInterceptor());
await app.listen({ port: 3000, host: '0.0.0.0' });
```

## Environment Configuration

### Base Configuration (`.env.example`)

```bash
# Base — observability disabled
OTEL_ENABLED=false
LOG_LEVEL=info
LOG_FORMAT=json
LOG_TIMESTAMPS=true
LOG_REQUESTS=true
```

### Development Configuration (`.env.development`)

```bash
# Development — pretty logs, no tracing
LOG_FORMAT=pretty
LOG_LEVEL=debug
OTEL_ENABLED=false
```

### Production Configuration (`.env.production`)

```bash
# Production — full observability
OTEL_ENABLED=true
OTEL_TRACING_ENABLED=true
OTEL_METRICS_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_SERVICE_NAME=my-nestjs-service
OTEL_TRACES_SAMPLER_ARG=1.0

# Structured logging
LOG_LEVEL=info
LOG_FORMAT=json
LOG_TIMESTAMPS=true
LOG_REQUESTS=true

# Cloud logging (if applicable)
CLOUD_LOGGING_ENABLED=true
GCP_PROJECT_ID=my-project
```

## Dependencies

Add these packages to your project:

```bash
# Exact pins (npm view, 2026-11-24); the first four were run in the NestJS 12.6.0 reference app
npm install -E @opentelemetry/api@1.10.0 @opentelemetry/sdk-node@0.301.2 \
  @opentelemetry/sdk-trace@3.1.1 @opentelemetry/instrumentation-http@0.301.2 \
  @opentelemetry/exporter-trace-otlp-http@0.301.2
```

## Troubleshooting

| Issue | Symptom | Fix |
|-------|---------|-----|
| Tracing not working | No spans exported | Start the process with `node --import ./dist/instrumentation.js`; check `OTEL_EXPORTER_OTLP_ENDPOINT` is reachable |
| No HTTP spans although the SDK started | SDK started inside Nest (`onModuleInit`) | Move it to the `--import` entry: `http` must be patched before Fastify loads |
| Too many spans | High cardinality, storage cost | Lower `OTEL_TRACES_SAMPLER_ARG` to 0.1 or 0.01 (1% sampling) |
| Missing correlation IDs | Logs show `unknown` | Ensure upstream services send `x-correlation-id` header or generate in middleware |
| Sensitive data in logs | Passwords appearing | Add field names to `sensitiveFields` array in interceptor |
| Noisy file system traces | Too many fs/dns spans | Verify `instrumentation.fs` and `instrumentation.dns` are `false` |
| Logs not structured | Text output instead of JSON | Set `LOG_FORMAT=json` in production environment |
