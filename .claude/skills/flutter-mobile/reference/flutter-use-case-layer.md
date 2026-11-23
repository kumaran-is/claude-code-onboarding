# Flutter Use-Case Layer

Use cases are optional domain-layer classes that encapsulate a single business operation.

## When to Add a Use Case

Add a use case when ANY of these are true:

1. The same business operation is called from **2+ ViewModels** — extract to avoid duplication
2. The operation **orchestrates 2+ repositories** — keeps ViewModel thin
3. The operation has **non-trivial business rules** that belong in the domain layer, not the UI or data layer

## When NOT to Add a Use Case

Single repository call with no business logic → call the repository directly from the ViewModel.
Do not add use cases for simple CRUD operations. Unnecessary indirection is worse than the
problem it was meant to solve.

```
// ❌ Unnecessary use case — just wraps one repo call with no logic
class GetOrderUseCase {
  Future<Order> execute(String id) => _repo.getOrder(id);
}

// ✅ Just call the repository from the ViewModel directly
final order = await ref.read(orderRepositoryProvider).getOrder(id);
```

## File Location

```
lib/features/<feature>/domain/use_cases/<name>_use_case.dart
```

## Example — Orchestrating Two Repositories

`PlaceOrderUseCase` creates the order AND reserves stock in one domain operation. Neither the
ViewModel nor a single repository owns this logic. The optional second step must not turn a
successful order into a failure, but it must not vanish silently either — log it.

```dart
// lib/features/orders/domain/use_cases/place_order_use_case.dart

class PlaceOrderUseCase {
  // Dart 3.14: a private field can be a named initializing formal; callers still
  // pass `orderRepo:`. The older `: _orderRepo = orderRepo` initializer list now
  // triggers `prefer_initializing_formals`.
  const PlaceOrderUseCase({
    required this._orderRepo,
    required this._inventoryRepo,
    required this._logger,
  });

  final OrderRepository _orderRepo;
  final InventoryRepository _inventoryRepo;
  final AppLogger _logger;

  Future<Result<Order>> execute(PlaceOrderParams params) async {
    // Step 1 — the operation that defines success
    final Order order;
    switch (await _orderRepo.create(params)) {
      case Failure(:final error):
        return Failure(error);
      case Success(:final value):
        order = value; // exhaustive switch: no `as Success<Order>` cast
    }

    // Step 2 — best-effort follow-up: failure is logged and surfaced to the caller
    // through a retry path, never swallowed
    try {
      await _inventoryRepo.reserve(order.id, order.lines);
    } on Object catch (e, st) {
      _logger.error('reserve stock failed for order ${order.id}', error: e, stackTrace: st);
    }
    return Success(order);
  }
}
```

If the follow-up is mandatory for correctness, do not use best-effort: return a `Failure` (or
make the operation transactional on the backend) instead of logging and moving on.

Register in DI via a Riverpod provider:

```dart
@riverpod
PlaceOrderUseCase placeOrder(Ref ref) => PlaceOrderUseCase(
      orderRepo: ref.watch(orderRepositoryProvider),
      inventoryRepo: ref.watch(inventoryRepositoryProvider),
      logger: ref.watch(appLoggerProvider),
    );
```

ViewModel calls the use case, not the repositories directly:

```dart
Future<void> submit(PlaceOrderParams params) async {
  state = const AsyncLoading();
  final next = await AsyncValue.guard(() async {
    final result = await ref.read(placeOrderProvider).execute(params);
    return switch (result) {
      Success(:final value) => value,
      Failure(:final error) => throw error,
    };
  });
  if (!ref.mounted) return; // screen closed while placing the order
  state = next;
}
```

## Testing

Use cases get **unit tests with fake repositories** — no mocks needed, no widget tree required.

```dart
// test/features/orders/domain/use_cases/place_order_use_case_test.dart

void main() {
  test('creates the order and reserves stock', () async {
    final orderRepo = FakeOrderRepository();
    final inventoryRepo = FakeInventoryRepository();
    final useCase = PlaceOrderUseCase(
      orderRepo: orderRepo,
      inventoryRepo: inventoryRepo,
      logger: FakeLogger(),
    );

    final result = await useCase.execute(const PlaceOrderParams(
      customerId: 'c1',
      lines: [OrderLine(sku: 'sku-1', quantity: 2)],
    ));

    expect(result, isA<Success<Order>>());
    expect(inventoryRepo.reserved, isTrue);
  });

  test('a failed reservation is logged and does not fail the order', () async {
    final logger = FakeLogger();
    final useCase = PlaceOrderUseCase(
      orderRepo: FakeOrderRepository(),
      inventoryRepo: FakeInventoryRepository(throwOnReserve: true),
      logger: logger,
    );

    final result = await useCase.execute(const PlaceOrderParams(
      customerId: 'c1',
      lines: [OrderLine(sku: 'sku-1', quantity: 2)],
    ));

    expect(result, isA<Success<Order>>());
    expect(logger.errors, hasLength(1));
  });

  test('a failed order is returned as Failure and nothing is reserved', () async {
    final inventoryRepo = FakeInventoryRepository();
    final useCase = PlaceOrderUseCase(
      orderRepo: FakeOrderRepository(fail: true),
      inventoryRepo: inventoryRepo,
      logger: FakeLogger(),
    );

    final result = await useCase.execute(const PlaceOrderParams(
      customerId: 'c1',
      lines: [OrderLine(sku: 'sku-1', quantity: 2)],
    ));

    expect(result, isA<Failure<Order>>());
    expect(inventoryRepo.reserved, isFalse);
  });
}
```

Fake repositories implement the repository interface and store calls in-memory —
no `mocktail` or `mockito` required for use-case tests.
