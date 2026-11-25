# Cloud Run Functions — Event-Driven Patterns

## Overview

Cloud Run Functions are containerized handlers invoked by:
- **Pub/Sub push** — GCP pushes a base64-encoded message to your HTTP endpoint
- **Cloud Storage notification** — Eventarc routes object events to your endpoint
- **HTTP webhook** — Direct HTTP invocation (authenticated via IAM or API Gateway)

All patterns share the same container model: build a Docker image, deploy to Cloud Run.

---

## Python FastAPI (python:3.14.10-slim-trixie)

Validated 2026-11-23 on CPython 3.14.10 with fastapi 0.165.0, pydantic 2.14.4, structlog 26.1.0: 5 pytest cases pass (valid message acked 204; invalid JSON payload and invalid base64 answered 400; processor exception answered 500; storage `finalized` handled, other event types ignored, missing `ce-*` headers 422), `mypy --strict` and ruff clean. Control: making the invalid-payload branch return 204 failed 2 tests.

### Pub/Sub Push Handler

Pub/Sub treats 102, 200, 201, 202 and 204 as an acknowledgement and any other status as a negative acknowledgement, then redelivers (Pub/Sub push docs). Every failure therefore returns non-2xx, and the subscription needs a dead-letter topic with `max_delivery_attempts` so a poison message stops retrying.

```python
# src/push_handler/main.py
"""Pub/Sub push endpoint: 2xx acks the message, any other status makes Pub/Sub redeliver it."""

import base64
import binascii
from collections.abc import Awaitable, Callable
from datetime import datetime

import structlog
from fastapi import FastAPI, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = structlog.get_logger(__name__)


class PushMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    data: str = ""  # base64; absent when the message has only attributes
    attributes: dict[str, str] = Field(default_factory=dict)
    message_id: str = Field(alias="messageId")
    publish_time: datetime = Field(alias="publishTime")


class PushEnvelope(BaseModel):
    message: PushMessage
    subscription: str
    delivery_attempt: int | None = Field(default=None, alias="deliveryAttempt")


class OrderEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    amount_cents: int = Field(ge=0)


Processor = Callable[[OrderEvent, str], Awaitable[None]]


def create_app(process: Processor) -> FastAPI:
    app = FastAPI(title="push-handler")

    @app.post("/pubsub/orders", status_code=status.HTTP_204_NO_CONTENT)
    async def receive(envelope: PushEnvelope) -> Response:
        msg = envelope.message
        log = logger.bind(message_id=msg.message_id, delivery_attempt=envelope.delivery_attempt)
        try:
            event = OrderEvent.model_validate_json(base64.b64decode(msg.data, validate=True))
        except (binascii.Error, ValidationError) as exc:
            # Non-2xx: Pub/Sub redelivers until the dead-letter policy moves it aside.
            log.warning("pubsub_payload_invalid", error_type=type(exc).__name__)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid payload") from exc
        # The processor must be idempotent on message_id: push delivery is at-least-once.
        await process(event, msg.message_id)
        log.info("pubsub_message_processed", order_id=event.order_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

Delivery is at-least-once: the injected `process` must be idempotent on `message_id` (`python-dev/reference/reliability-idempotency-retries-outbox.md`). Push requests authenticate with an OIDC token from the subscription's service account: deploy with `--no-allow-unauthenticated` and grant that account `roles/run.invoker`.

### Cloud Storage Trigger Handler (Eventarc)

```python
# src/push_handler/storage.py
"""Eventarc Cloud Storage trigger: binary-mode CloudEvent (ce-* headers, object metadata body)."""

from collections.abc import Awaitable, Callable
from typing import Annotated

import structlog
from fastapi import APIRouter, Header, Response, status
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class StorageObject(BaseModel):
    bucket: str
    name: str
    generation: str


ObjectHandler = Callable[[StorageObject], Awaitable[None]]


def storage_router(handle: ObjectHandler) -> APIRouter:
    router = APIRouter()

    @router.post("/events/storage", status_code=status.HTTP_204_NO_CONTENT)
    async def on_object(
        obj: StorageObject,
        ce_type: Annotated[str, Header()],
        ce_id: Annotated[str, Header()],
    ) -> Response:
        if ce_type != "google.cloud.storage.object.v1.finalized":
            logger.info("storage_event_ignored", ce_type=ce_type, ce_id=ce_id)
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        # (bucket, name, generation) identifies one object version: use it as the idempotency key.
        await handle(obj)
        logger.info("storage_event_processed", ce_id=ce_id, bucket=obj.bucket)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
```

### Dockerfile Reference

Use the Python multi-stage template in the `docker` skill `reference/dockerfiles.md` (uv 0.13.9, `python:3.14.10-slim-trixie@sha256:...`, built and run hardened). Start the factory with exec-form `CMD ["uvicorn", "push_handler.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--timeout-graceful-shutdown", "8"]`; when the factory takes arguments (as `create_app(process)` does here), expose a zero-argument wrapper that wires the real processor. Cloud Run sends SIGTERM 10 seconds before SIGKILL (container contract), so the graceful timeout stays below 10.

---

## NestJS / Fastify (Node 26)

### Pub/Sub Push Handler

```typescript
// src/pubsub/pubsub.controller.ts
import { Body, Controller, HttpCode, Logger, Post } from '@nestjs/common';
import { z } from 'zod';
import { PubSubMessageService } from './pubsub-message.service.js';

// Push envelope, validated at the boundary by the global StandardSchemaValidationPipe (malformed -> 400).
const pubSubEnvelopeSchema = z.object({
  message: z.object({
    data: z.base64(),
    messageId: z.string().min(1),
    publishTime: z.string().min(1),
    attributes: z.record(z.string(), z.string()).optional(),
  }),
  subscription: z.string().min(1),
});
type PubSubEnvelope = z.infer<typeof pubSubEnvelopeSchema>;

@Controller('pubsub')
export class PubSubController {
  private readonly logger = new Logger(PubSubController.name);

  constructor(private readonly messages: PubSubMessageService) {}

  // Any 2xx acknowledges the message. A thrown error becomes a 5xx and Pub/Sub redelivers it (configure a
  // dead-letter topic so a poison message cannot retry forever), so handle() must be idempotent per messageId.
  @Post()
  @HttpCode(204)
  async handlePush(@Body({ schema: pubSubEnvelopeSchema }) envelope: PubSubEnvelope): Promise<void> {
    const { messageId, data } = envelope.message;
    this.logger.log('pubsub message received', { messageId, subscription: envelope.subscription }); // never the payload
    await this.messages.handle(messageId, Buffer.from(data, 'base64').toString('utf8'));
  }
}
```

`PubSubMessageService.handle(messageId, json)` parses its payload with its own Zod schema, does the work idempotently and
throws on failure (logged once by the global exception filter). Authenticate the push: deploy with `--no-allow-unauthenticated` and create
the subscription with `--push-auth-service-account` set to an identity that holds `roles/run.invoker`, so Cloud Run rejects
every caller except Pub/Sub. Health checks follow the `nestjs-api` production baseline (§7).

### Bootstrap for Cloud Run

```typescript
// src/main.ts: Cloud Run sets PORT; it is validated by the env schema like every other setting.
import 'reflect-metadata';
import { ConfigService } from '@nestjs/config';
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, type NestFastifyApplication } from '@nestjs/platform-fastify';
import { AppModule } from './app.module.js';
import type { Env } from './config/env.js';

const app = await NestFactory.create<NestFastifyApplication>(AppModule, new FastifyAdapter());
app.enableShutdownHooks(); // SIGTERM from Cloud Run runs onModuleDestroy/onApplicationShutdown, then exits
await app.listen(app.get<ConfigService<Env, true>>(ConfigService).get('PORT', { infer: true }), '0.0.0.0');
```

The full bootstrap (structured logger, body limit, failure exit code) is `nestjs-api` › `nestjs-production-baseline.md` §4.

### Dockerfile Reference

Use the digest-pinned `node:26.13.1-alpine3.23@sha256:<index digest>` base — see `docker` skill `reference/dockerfiles.md` for the full NestJS multi-stage template.

---

## Spring Boot 4.2 WebFlux (eclipse-temurin:25-jre)

### Pub/Sub Push Handler

```java
// PubSubController.java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;
import java.util.Base64;
import tools.jackson.databind.json.JsonMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@RestController
public class PubSubController {

    private static final Logger log = LoggerFactory.getLogger(PubSubController.class);
    private final JsonMapper objectMapper;

    public PubSubController(JsonMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    record PubSubMessage(String data, String messageId, String publishTime) {}
    record PubSubEnvelope(PubSubMessage message, String subscription) {}

    @PostMapping("/")
    public Mono<ResponseEntity<Void>> handlePubSub(@RequestBody PubSubEnvelope envelope) {
        return Mono.fromCallable(() -> {
            byte[] decoded = Base64.getDecoder().decode(envelope.message().data());
            var payload = objectMapper.readTree(decoded);
            log.info("Received message messageId={} payload={}", envelope.message().messageId(), payload);
            // TODO: delegate to service
            return ResponseEntity.<Void>ok().build();
        })
        .onErrorResume(e -> {
            log.error("Failed to process Pub/Sub message messageId={}", envelope.message().messageId(), e);
            // Return 500 so Pub/Sub retries
            return Mono.just(ResponseEntity.<Void>internalServerError().build());
        });
    }

    @GetMapping("/health")
    public Mono<ResponseEntity<String>> health() {
        return Mono.just(ResponseEntity.ok("{\"status\":\"ok\"}"));
    }
}
```

> **Rule:** Never block in a WebFlux pipeline. Use `Mono.fromCallable` for CPU-bound work, delegate I/O to reactive clients.

### Dockerfile Reference

Use `eclipse-temurin:25-jre` runtime stage — see `docker` skill `reference/dockerfiles.md` for the full Java multi-stage template.

---

## TypeScript / Fastify (Node 26)

### Pub/Sub Push Handler

```typescript
// src/index.ts
import Fastify from 'fastify';
import { z } from 'zod';

const PubSubMessageSchema = z.object({
  data: z.string(),           // base64-encoded
  messageId: z.string(),
  publishTime: z.string(),
});

const PubSubEnvelopeSchema = z.object({
  message: PubSubMessageSchema,
  subscription: z.string(),
});

const app = Fastify({ logger: true });

app.post('/', async (request, reply) => {
  const result = PubSubEnvelopeSchema.safeParse(request.body);
  if (!result.success) {
    request.log.error({ errors: result.error.issues }, 'Invalid Pub/Sub envelope');
    return reply.code(400).send({ error: 'Invalid envelope' });
  }
  try {
    const payload = JSON.parse(Buffer.from(result.data.message.data, 'base64').toString('utf-8'));
    request.log.info({ messageId: result.data.message.messageId, payload });
    // TODO: process payload
    return reply.code(200).send({ status: 'ok' });
  } catch (err) {
    request.log.error(err, 'Failed to process Pub/Sub message');
    return reply.code(500).send({ error: 'Processing failed' });
  }
});

app.get('/health', async (_request, reply) => {
  return reply.code(200).send({ status: 'ok' });
});

const port = parseInt(process.env.PORT ?? '8080', 10);
app.listen({ port, host: '0.0.0.0' }).catch((err) => {
  app.log.error(err);
  process.exit(1);
});
```

### Dockerfile Reference

Use the digest-pinned `node:26.13.1-alpine3.23@sha256:<index digest>` base — see `docker` skill `reference/dockerfiles.md` for the Node/TypeScript multi-stage template.

---

## Pub/Sub Return Code Contract

| Scenario | HTTP Status | Effect |
|----------|------------|--------|
| Success | 200–299 | Message acknowledged, not retried |
| Transient error | 500 | Message retried by Pub/Sub (up to retry policy limit) |
| Poison pill / bad payload | 200 | Acknowledge to prevent infinite retry loop |
| Invalid schema | 400 | GCP does NOT retry 4xx — message is dropped |

> Return 500 for processing errors you want retried. Return 200 for messages you explicitly want to discard.

---

## gcloud CLI Alternative (Quick Prototyping)

```bash
# Deploy from source (builds and pushes automatically — dev/prototyping only)
gcloud run deploy my-function \
  --source . \
  --region us-central1 \
  --platform managed \
  --no-allow-unauthenticated \
  --set-env-vars PROJECT_ID=$PROJECT_ID

# Set up Pub/Sub push subscription to the deployed function
FUNCTION_URL=$(gcloud run services describe my-function --region us-central1 --format 'value(status.url)')
gcloud pubsub subscriptions create my-sub \
  --topic my-topic \
  --push-endpoint "$FUNCTION_URL/" \
  --push-auth-service-account my-sa@$PROJECT_ID.iam.gserviceaccount.com
```

> For production, use the GitHub Actions workflow in `SKILL.md` — not `gcloud run deploy --source`.
