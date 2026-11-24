# Workflow Orchestration Implementation Playbook

> Referenced by `SKILL.md`. Load when implementing Temporal workflows in Java, Python, or NestJS.

## SDK Setup Per Stack

### Java 21 / Spring Boot 3.5.x

pom.xml dependencies:
```xml
<dependency>
    <groupId>io.temporal</groupId>
    <artifactId>temporal-sdk</artifactId>
    <version>1.25.0</version>
</dependency>
<dependency>
    <groupId>io.temporal</groupId>
    <artifactId>temporal-spring-boot-autoconfigure-alpha</artifactId>
    <version>0.6.0</version>
</dependency>
```

application.yml:
```yaml
spring:
  temporal:
    connection:
      target: 127.0.0.1:7233
    workers:
      - task-queue: order-processing
        workflow-classes:
          - com.example.workflows.OrderWorkflow
        activity-beans:
          - paymentActivity
          - inventoryActivity
          - notificationActivity
```

### Python 3.14 / FastAPI

Executed on temporalio 1.36.1 / Python 3.14.10 (time-skipping test server): the saga, approval, heartbeat-resume and duplicate-start code below, 8 tests; negative controls in the comments. Pin exactly with a lockfile:

```bash
uv add "temporalio==1.36.1" "fastapi[standard-no-fastapi-cloud-cli]==0.165.0"
uv add --dev "pytest==9.2.0" "pytest-asyncio==1.5.0"   # module-scoped env: asyncio_default_{fixture,test}_loop_scope = "module"
```

Worker startup (separate process from FastAPI; SIGTERM drains in-flight activities):
```python
import asyncio
import signal
from datetime import timedelta

from temporalio.client import Client
from temporalio.worker import Worker

from orders.activities import Ledger, process_chunks
from orders.workflows import ApprovalWorkflow, ChunkedJobWorkflow, OrderSagaWorkflow


async def run_worker() -> None:
    client = await Client.connect(settings.TEMPORAL_ADDRESS, namespace=settings.TEMPORAL_NAMESPACE)
    ledger = Ledger()  # real code: inject the payment / inventory clients here
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    async with Worker(
        client,
        task_queue="order-processing",
        workflows=[OrderSagaWorkflow, ApprovalWorkflow, ChunkedJobWorkflow],
        activities=[
            ledger.reserve_inventory, ledger.release_inventory, ledger.charge_payment,
            ledger.refund_payment, ledger.fulfil_order, process_chunks,
        ],
        graceful_shutdown_timeout=timedelta(seconds=8),  # under Cloud Run's 10 s SIGTERM->SIGKILL window
    ):
        await stop.wait()  # leaving the block calls Worker.shutdown(): stop polling, drain, cancel the rest


if __name__ == "__main__":
    asyncio.run(run_worker())
```

Workflow modules import activity types through `with workflow.unsafe.imports_passed_through():` so the sandbox does not re-import them on every replay.

### NestJS 11.x / TypeScript

```typescript
// worker.ts — run as separate process
import { NativeConnection, Worker } from '@temporalio/worker';
import * as activities from './activities';

async function runWorker() {
  const connection = await NativeConnection.connect({ address: 'localhost:7233' });
  const worker = await Worker.create({
    connection,
    namespace: 'default',
    taskQueue: 'order-processing',
    workflowsPath: require.resolve('./workflows'),
    activities,
  });
  await worker.run();
}

runWorker().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

---

## Saga Pattern with Compensation {#saga}

### Python — Saga Workflow

Activities are methods on one object holding the clients (`orders/activities.py`: `Ledger.reserve_inventory`, `release_inventory`, `charge_payment` raising `ApplicationError(..., type="InsufficientFundsError", non_retryable=True)` on a decline, `refund_payment`, `fulfil_order`), each keyed by `order_id` so a retry is not a second effect.

```python
from collections.abc import Awaitable, Callable
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from orders.activities import Ledger, OrderInput, process_chunks

STEP_TIMEOUT = timedelta(seconds=30)
COMPENSATE_RETRY = RetryPolicy(maximum_attempts=10, maximum_interval=timedelta(minutes=1))


@workflow.defn
class OrderSagaWorkflow:
    @workflow.run
    async def run(self, order: OrderInput) -> str:
        compensations: list[Callable[[Ledger, OrderInput], Awaitable[None]]] = []
        try:
            # register the compensation BEFORE the step: a step that timed out may still have applied
            compensations.append(Ledger.release_inventory)
            await workflow.execute_activity_method(
                Ledger.reserve_inventory,
                order,
                retry_policy=RetryPolicy(maximum_attempts=3),
                start_to_close_timeout=STEP_TIMEOUT,
            )
            compensations.append(Ledger.refund_payment)
            await workflow.execute_activity_method(
                Ledger.charge_payment,
                order,
                retry_policy=RetryPolicy(
                    maximum_attempts=3, non_retryable_error_types=["InsufficientFundsError"]
                ),
                start_to_close_timeout=STEP_TIMEOUT,
            )
            await workflow.execute_activity_method(
                Ledger.fulfil_order, order, start_to_close_timeout=STEP_TIMEOUT
            )
            return "fulfilled"
        except ActivityError as step_error:
            failed: list[str] = []
            for compensate in reversed(compensations):
                try:
                    await workflow.execute_activity_method(
                        compensate, order, retry_policy=COMPENSATE_RETRY, start_to_close_timeout=STEP_TIMEOUT
                    )
                except ActivityError as comp_error:
                    workflow.logger.error(
                        "compensation_failed", extra={"step": compensate.__name__, "error": str(comp_error)}
                    )
                    failed.append(compensate.__name__)
            if failed:  # never silent: the workflow fails with the steps a human must fix
                raise ApplicationError(
                    "compensation incomplete", failed, type="CompensationFailed", non_retryable=True
                ) from step_error
            raise ApplicationError("order failed and was compensated", type="OrderFailed") from step_error
```

Executed: happy path; a declined charge runs once (non-retryable type) and compensates `refund` then `release` (the compensation for the failing step is registered BEFORE it, because a timed-out step may still have applied); a failure after the charge refunds then releases. Control: registering the refund after the charge leaves `['charge', 'release']` and fails the test. A compensation that still fails after its retries fails the workflow with `CompensationFailed` and the step names: never `except Exception: pass`.

### Java — Saga Workflow

```java
@WorkflowInterface
public interface OrderWorkflow {
    @WorkflowMethod
    String processOrder(OrderInput input);
}

@WorkflowImpl
public class OrderWorkflowImpl implements OrderWorkflow {

    private final PaymentActivities payment = Workflow.newActivityStub(
        PaymentActivities.class,
        ActivityOptions.newBuilder()
            .setStartToCloseTimeout(Duration.ofSeconds(30))
            .setRetryOptions(RetryOptions.newBuilder()
                .setMaximumAttempts(3)
                .setDoNotRetry("InsufficientFundsError", "InvalidCardError")
                .build())
            .build()
    );

    private final InventoryActivities inventory = Workflow.newActivityStub(
        InventoryActivities.class,
        ActivityOptions.newBuilder()
            .setStartToCloseTimeout(Duration.ofSeconds(30))
            .build()
    );

    @Override
    public String processOrder(OrderInput input) {
        Saga saga = new Saga(new Saga.Options.Builder().setParallelCompensation(false).build());

        try {
            inventory.reserveInventory(input.getOrderId(), input.getProductId());
            saga.addCompensation(inventory::releaseInventory, input.getOrderId(), input.getProductId());

            payment.chargePayment(input.getOrderId(), input.getUserId(), input.getAmountCents());
            saga.addCompensation(payment::refundPayment, input.getOrderId(), input.getAmountCents());

            return "Order " + input.getOrderId() + " fulfilled";

        } catch (ActivityFailure e) {
            saga.compensate();
            throw e;
        }
    }
}
```

### NestJS — Saga Workflow

```typescript
// workflows/order-saga.workflow.ts
import { proxyActivities, ApplicationFailure } from '@temporalio/workflow';
import type * as activities from '../activities';
import { OrderInput } from '../types';

const { reserveInventory, releaseInventory, chargePayment, refundPayment, fulfillOrder } =
  proxyActivities<typeof activities>({
    startToCloseTimeout: '30 seconds',
    retry: { maximumAttempts: 3 },
  });

export async function orderSagaWorkflow(input: OrderInput): Promise<string> {
  const compensations: Array<() => Promise<void>> = [];

  try {
    await reserveInventory(input.orderId, input.productId);
    compensations.push(() => releaseInventory(input.orderId, input.productId));

    await chargePayment(input.orderId, input.userId, input.amountCents);
    compensations.push(() => refundPayment(input.orderId, input.amountCents));

    await fulfillOrder(input.orderId);
    return `Order ${input.orderId} fulfilled`;

  } catch (err) {
    // Run compensations in reverse order (LIFO)
    for (const compensate of compensations.reverse()) {
      try {
        await compensate();
      } catch {
        // best-effort compensation — log and continue
      }
    }
    throw ApplicationFailure.create({ message: `Order ${input.orderId} failed, compensated` });
  }
}
```

---

## Entity Workflow (Actor Model) {#entity}

One workflow execution = one entity. Receives signals for mutations, handles queries for reads.

### Python — Shopping Cart Entity Workflow

```python
from dataclasses import dataclass, field
from datetime import timedelta
from temporalio import workflow

@dataclass
class CartItem:
    product_id: str
    quantity: int
    price_cents: int

@workflow.defn
class ShoppingCartWorkflow:
    def __init__(self) -> None:
        self._items: list[CartItem] = []
        self._checked_out: bool = False

    @workflow.run
    async def run(self, cart_id: str) -> str:
        # Cart expires 24 hours after start; wait_condition RAISES TimeoutError on timeout
        try:
            await workflow.wait_condition(lambda: self._checked_out, timeout=timedelta(hours=24))
        except TimeoutError:
            return f"Cart {cart_id} expired"
        return f"Cart {cart_id} checked out with {len(self._items)} items"

    @workflow.signal
    def add_item(self, item: CartItem) -> None:
        self._items.append(item)

    @workflow.signal
    def remove_item(self, product_id: str) -> None:
        self._items = [i for i in self._items if i.product_id != product_id]

    @workflow.signal
    def checkout(self) -> None:
        self._checked_out = True

    @workflow.query
    def get_items(self) -> list[CartItem]:
        return self._items

    @workflow.query
    def total_cents(self) -> int:
        return sum(i.price_cents * i.quantity for i in self._items)
```

### Java — Shopping Cart Entity Workflow

```java
@WorkflowInterface
public interface ShoppingCartWorkflow {
    @WorkflowMethod
    String run(String cartId);

    @SignalMethod
    void addItem(CartItem item);

    @SignalMethod
    void removeItem(String productId);

    @SignalMethod
    void checkout();

    @QueryMethod
    List<CartItem> getItems();

    @QueryMethod
    int getTotalCents();
}

@WorkflowImpl
public class ShoppingCartWorkflowImpl implements ShoppingCartWorkflow {
    private final List<CartItem> items = new ArrayList<>();
    private boolean checkedOut = false;

    @Override
    public String run(String cartId) {
        Workflow.await(Duration.ofHours(24), () -> checkedOut);
        return checkedOut
            ? "Cart " + cartId + " checked out"
            : "Cart " + cartId + " expired";
    }

    @Override public void addItem(CartItem item) { items.add(item); }
    @Override public void removeItem(String productId) { items.removeIf(i -> i.getProductId().equals(productId)); }
    @Override public void checkout() { checkedOut = true; }
    @Override public List<CartItem> getItems() { return Collections.unmodifiableList(items); }
    @Override public int getTotalCents() { return items.stream().mapToInt(i -> i.getPriceCents() * i.getQuantity()).sum(); }
}
```

---

## Fan-Out / Fan-In {#fanout}

Execute N tasks in parallel, aggregate results.

### Python — Parallel Document Processing

```python
import asyncio
from temporalio import workflow
from temporalio.workflow import ParentClosePolicy

@workflow.defn
class DocumentBatchWorkflow:
    @workflow.run
    async def run(self, document_ids: list[str]) -> dict[str, str]:
        # Fan-out: start all child workflows in parallel
        handles = [
            await workflow.start_child_workflow(
                ProcessDocumentWorkflow,
                args=[doc_id],
                id=f"process-doc-{doc_id}",
                parent_close_policy=ParentClosePolicy.TERMINATE,
            )
            for doc_id in document_ids
        ]

        # Fan-in: wait for all and collect results
        results = await asyncio.gather(*[h.result() for h in handles])
        return dict(zip(document_ids, results))
```

**Scaling rule:** Do not put 1M tasks in one workflow. Decompose: 1M tasks = 1K child workflows x 1K tasks each.

---

## Signals and Async Callbacks {#signals}

### Python — Human Approval Workflow

```python
@workflow.defn
class ApprovalWorkflow:
    def __init__(self) -> None:
        self._decision: bool | None = None

    @workflow.run
    async def run(self, request_id: str, timeout_hours: int = 48) -> str:
        try:
            await workflow.wait_condition(
                lambda: self._decision is not None, timeout=timedelta(hours=timeout_hours)
            )
        except TimeoutError:  # wait_condition RAISES on timeout; it does not return False
            return "timed_out"
        return "approved" if self._decision else "rejected"

    @workflow.signal
    def decide(self, approved: bool) -> None:
        if self._decision is None:  # first decision wins; duplicate signals are ignored
            self._decision = approved

    @workflow.query
    def pending(self) -> bool:
        return self._decision is None
```

Executed: approve, reject (a second, contradicting signal is ignored), and timeout (the time-skipping server fires the 48 h timer at once). Control: the old pattern `approved = await workflow.wait_condition(...)`; `if not approved` fails the timeout test: `wait_condition` returns `None` and raises `TimeoutError` on timeout, so the "timed out" branch was unreachable and the workflow failed instead.

---

Heartbeats, versioning, child workflows, retry policies, client code and common pitfalls: `implementation-playbook-operations.md`.
