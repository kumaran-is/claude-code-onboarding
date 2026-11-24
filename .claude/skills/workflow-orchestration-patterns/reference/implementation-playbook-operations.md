# Temporal Implementation Playbook — Operations

Second half of `implementation-playbook.md` (SDK setup, saga, entity, fan-out, signals). Same evidence: the Python code is executed on temporalio 1.36.1 / Python 3.14.10 (time-skipping test server); Java and NestJS snippets are illustrative.

---

## Activity Heartbeats {#heartbeat}

For activities running longer than 30 seconds.

### Python — Long-Running Activity with Heartbeat Resume

```python
import asyncio

from temporalio import activity


@activity.defn
async def process_chunks(total_chunks: int, crash_at: int = -1) -> int:
    """Long-running activity: heartbeats progress and resumes from the last heartbeat after a retry.

    Returns how many chunks THIS attempt processed. crash_at simulates a worker crash on attempt 1.
    """
    details = activity.info().heartbeat_details
    start = int(details[0]) + 1 if details else 0
    for chunk in range(start, total_chunks):
        if chunk == crash_at and activity.info().attempt == 1:
            raise RuntimeError("simulated crash")
        await asyncio.sleep(0.01)  # one unit of real work
        activity.heartbeat(chunk)  # progress is the resume point; also how cancellation is delivered
    return total_chunks - start


@workflow.defn
class ChunkedJobWorkflow:
    @workflow.run
    async def run(self, total_chunks: int, crash_at: int) -> int:
        return await workflow.execute_activity(
            process_chunks,
            args=[total_chunks, crash_at],
            start_to_close_timeout=timedelta(hours=2),
            heartbeat_timeout=timedelta(seconds=30),  # no heartbeat for 30 s = attempt failed, retried
            retry_policy=RetryPolicy(initial_interval=timedelta(milliseconds=100), maximum_attempts=3),
        )
```

Executed: a crash at chunk 6 on attempt 1 is retried and the retry processes only chunks 6–9 (4). Control: ignoring `heartbeat_details` reprocesses all 10. Heartbeats are throttled by the SDK; a cancelled activity sees `asyncio.CancelledError` at its next await: clean up and re-raise.

### Java — Long-Running Activity with Heartbeat

```java
@ActivityImpl
public class FileProcessingActivitiesImpl implements FileProcessingActivities {

    @Override
    public String processLargeFile(String filePath) {
        List<FileChunk> chunks = getFileChunks(filePath);
        for (int i = 0; i < chunks.size(); i++) {
            Activity.getExecutionContext().heartbeat("Chunk " + (i + 1) + "/" + chunks.size());
            processChunk(chunks.get(i));
        }
        return "Processed " + chunks.size() + " chunks";
    }
}
```

---

## Workflow Versioning {#versioning}

Safe changes to workflow code while old executions are still running.

### Python

```python
@workflow.defn
class OrderWorkflow:
    @workflow.run
    async def run(self, input: OrderInput) -> str:
        # Use patched() to branch behavior for new vs old executions
        if workflow.patched("add-notification-step"):
            # New code path for executions started after this deploy
            await workflow.execute_activity(send_notification, args=[input.order_id], ...)

        await workflow.execute_activity(fulfill_order, args=[input.order_id], ...)
        return "done"
```

### Java

```java
@Override
public String processOrder(OrderInput input) {
    int version = Workflow.getVersion("add-notification-step", Workflow.DEFAULT_VERSION, 1);
    if (version == 1) {
        notification.sendNotification(input.getOrderId());
    }
    // ... rest of workflow
}
```

---

## Child Workflows {#child}

Decompose large workflows for scalability and isolation.

### Python — Parent Dispatching Child Workflows

```python
import asyncio

from temporalio import workflow
from temporalio.workflow import ParentClosePolicy

@workflow.defn
class BulkNotificationWorkflow:
    @workflow.run
    async def run(self, user_ids: list[str], message: str) -> dict[str, str]:
        # Decompose into batches of 1000 to stay under history limits
        batch_size = 1000
        batches = [user_ids[i:i + batch_size] for i in range(0, len(user_ids), batch_size)]

        handles = [
            await workflow.start_child_workflow(
                NotificationBatchWorkflow,
                args=[batch, message],
                id=f"notify-batch-{idx}",
                parent_close_policy=ParentClosePolicy.TERMINATE,
            )
            for idx, batch in enumerate(batches)
        ]

        results = await asyncio.gather(*[h.result() for h in handles])
        return {"total_batches": len(batches), "results": results}
```

---

## Retry Policies {#retry}

### Non-Retryable Error Classification

**Python:**
```python
# In activity: throw non-retryable for business rule violations
from temporalio.exceptions import ApplicationError

async def charge_payment(order_id: str, amount_cents: int) -> None:
    result = await payment_gateway.charge(order_id, amount_cents)
    if result.code == "INSUFFICIENT_FUNDS":
        raise ApplicationError(
            "Payment declined — insufficient funds",
            type="InsufficientFundsError",  # keyword: a positional 2nd argument is a DETAIL, not the type
            non_retryable=True,
        )
    if result.code == "NETWORK_TIMEOUT":
        raise ApplicationError("Gateway timeout", type="NetworkTimeoutError")  # retryable (default)
```

**Java:**
```java
// Non-retryable: throw ApplicationFailure
throw ApplicationFailure.newNonRetryableFailure("Insufficient funds", "InsufficientFundsError");

// Retryable (default behavior — just throw any other exception):
throw new RuntimeException("Gateway timeout");
```

**NestJS:**
```typescript
import { ApplicationFailure } from '@temporalio/workflow';

// In activity:
throw ApplicationFailure.create({
  message: 'Payment declined',
  type: 'InsufficientFundsError',
  nonRetryable: true,
});
```

### Standard Retry Policy

```python
# Python
RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=5,
    non_retryable_error_types=["InsufficientFundsError", "ValidationError"],
)
```

```java
// Java
RetryOptions.newBuilder()
    .setInitialInterval(Duration.ofSeconds(1))
    .setBackoffCoefficient(2.0)
    .setMaximumInterval(Duration.ofSeconds(60))
    .setMaximumAttempts(5)
    .setDoNotRetry("InsufficientFundsError", "ValidationError")
    .build()
```

---

## Starting Workflows (Client Code)

### Python — FastAPI Client

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy

from orders.activities import OrderInput
from orders.workflows import OrderSagaWorkflow


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.temporal = await Client.connect(settings.TEMPORAL_ADDRESS, namespace=settings.TEMPORAL_NAMESPACE)
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/orders", status_code=202)
async def create_order(order: OrderInput, request: Request) -> dict[str, str]:
    client: Client = request.app.state.temporal
    handle = await client.start_workflow(
        OrderSagaWorkflow.run,
        order,
        id=f"order-{order.order_id}",  # business key: a client retry finds the same execution
        task_queue="order-processing",
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
    )
    return {"workflow_id": handle.id, "run_id": handle.first_execution_run_id or ""}
```

Executed (duplicate start): two `start_workflow` calls with the same id and `USE_EXISTING` return the same `first_execution_run_id`. The endpoint returns 202 and never awaits `handle.result()`: the HTTP request does not block on the workflow.

### Java — Spring Boot REST Controller

```java
@RestController
@RequestMapping("/orders")
@RequiredArgsConstructor
public class OrderController {

    private final WorkflowClient workflowClient;

    @PostMapping
    public ResponseEntity<OrderResponse> createOrder(@RequestBody @Valid OrderInput input) {
        OrderWorkflow workflow = workflowClient.newWorkflowStub(
            OrderWorkflow.class,
            WorkflowOptions.newBuilder()
                .setWorkflowId("order-" + input.getOrderId())
                .setTaskQueue("order-processing")
                .build()
        );

        WorkflowClient.start(workflow::processOrder, input);
        return ResponseEntity.accepted().body(new OrderResponse(input.getOrderId()));
    }
}
```

### NestJS — Controller + Temporal Client Service

```typescript
// temporal-client.service.ts
import { Injectable, OnModuleInit } from '@nestjs/common';
import { Client, Connection } from '@temporalio/client';
import { orderSagaWorkflow } from './workflows/order-saga.workflow';
import { OrderInput } from './types';

@Injectable()
export class TemporalClientService implements OnModuleInit {
  private client: Client;

  async onModuleInit() {
    const connection = await Connection.connect({ address: 'localhost:7233' });
    this.client = new Client({ connection });
  }

  async startOrderWorkflow(input: OrderInput): Promise<string> {
    const handle = await this.client.workflow.start(orderSagaWorkflow, {
      args: [input],
      taskQueue: 'order-processing',
      workflowId: `order-${input.orderId}`,
    });
    return handle.workflowId;
  }
}
```

---

## Common Pitfalls

| Mistake | Why It Breaks | Fix |
|---------|--------------|-----|
| `datetime.now()` in workflow | Non-deterministic — replay produces different time | Use `workflow.now()` |
| HTTP call in workflow | Non-deterministic, may fail | Move to activity |
| Non-idempotent activity | Retries cause duplicate charges/sends | Add idempotency key or upsert |
| Missing heartbeat on long activity | Temporal can't detect stalled work | Call `heartbeat()` every <30s |
| No `non_retryable_error_types` | Validation errors retried forever | Classify errors explicitly |
| Giant workflow (1M tasks in one) | History size limit hit | Use child workflows to decompose |
| `if not await workflow.wait_condition(..., timeout=...)` | Returns `None`; a timeout RAISES `TimeoutError` | `try` / `except TimeoutError` |
| `ApplicationError("msg", "SomeType")` | Second positional arg is a detail, not the type: `non_retryable_error_types` never matches | `type="SomeType"` keyword |
| Compensation registered after its step / `except: pass` in compensation | Timed-out step never undone; failed undo is invisible | Register before the step; fail the workflow listing failed compensations |
| Changing workflow code without versioning | Old executions replay incorrectly | Use `workflow.patched()` / `Workflow.getVersion()` |
