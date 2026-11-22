# Flutter Network Resilience Patterns

Patterns for building resilient network layers in Flutter apps: circuit breakers, retry with exponential backoff, timeout budgets, and structured error reporting.

Use these patterns any time a service makes outbound HTTP or Firebase calls.

---

## Circuit Breaker

Stops hammering a failing backend by tracking consecutive failures and opening the circuit (rejecting calls) until a recovery window passes.

### States

```
CLOSED  →  (failure threshold reached)  →  OPEN
OPEN    →  (recovery timeout elapsed)   →  HALF_OPEN
HALF_OPEN  →  (next call succeeds)      →  CLOSED
HALF_OPEN  →  (next call fails)         →  OPEN
```

### Implementation

```dart
enum CircuitState { closed, open, halfOpen }

class CircuitBreaker {
  CircuitBreaker({
    this.failureThreshold = 5,
    this.recoveryTimeout = const Duration(seconds: 30),
  });

  final int failureThreshold;
  final Duration recoveryTimeout;

  CircuitState _state = CircuitState.closed;
  int _failureCount = 0;
  DateTime? _openedAt;

  bool get isOpen {
    if (_state == CircuitState.open) {
      if (DateTime.now().difference(_openedAt!) >= recoveryTimeout) {
        _state = CircuitState.halfOpen;
        return false;
      }
      return true;
    }
    return false;
  }

  void recordSuccess() {
    _failureCount = 0;
    _state = CircuitState.closed;
  }

  void recordFailure() {
    _failureCount++;
    if (_failureCount >= failureThreshold) {
      _state = CircuitState.open;
      _openedAt = DateTime.now();
    }
  }
}
```

---

## Resilient Network Service

Wraps any async operation with: circuit breaker check → timeout → retry with exponential backoff → Crashlytics error recording.

### Timeout budgets by operation type

| Operation | Timeout |
|-----------|---------|
| Quick reads (cache hits, auth checks) | 10s |
| Standard reads (Firestore queries) | 15s |
| Writes (create/update/delete) | 20s |
| File uploads | 60s |

### Implementation

```dart
import 'package:firebase_crashlytics/firebase_crashlytics.dart';

typedef NetworkOperation<T> = Future<T> Function();

class ResilientNetworkService {
  ResilientNetworkService({CircuitBreaker? circuitBreaker})
      : _circuitBreaker = circuitBreaker ?? CircuitBreaker();

  final CircuitBreaker _circuitBreaker;

  static const _timeouts = {
    OperationType.quickRead: Duration(seconds: 10),
    OperationType.read: Duration(seconds: 15),
    OperationType.write: Duration(seconds: 20),
    OperationType.upload: Duration(seconds: 60),
  };

  /// Execute [operation] with circuit breaker, timeout, and retry.
  ///
  /// [maxRetries] defaults to 3. Pass 0 for fire-and-forget writes where
  /// retrying could cause duplicates.
  Future<T> execute<T>(
    NetworkOperation<T> operation, {
    OperationType type = OperationType.read,
    int maxRetries = 3,
    String? operationName,
  }) async {
    if (_circuitBreaker.isOpen) {
      throw CircuitOpenException(
        'Circuit open — backend unreachable. Try again later.',
      );
    }

    final timeout = _timeouts[type]!;
    Exception? lastError;

    for (int attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        final result = await operation().timeout(timeout);
        _circuitBreaker.recordSuccess();
        return result;
      } on TimeoutException catch (e, stack) {
        lastError = e;
        _circuitBreaker.recordFailure();
        await _recordToAnalytics(
          operationName ?? 'unknown',
          'TimeoutException (attempt ${attempt + 1})',
          e,
          stack,
        );
      } catch (e, stack) {
        lastError = e is Exception ? e : Exception(e.toString());
        _circuitBreaker.recordFailure();
        await _recordToAnalytics(
          operationName ?? 'unknown',
          'Attempt ${attempt + 1} failed',
          e,
          stack,
        );
        // Don't retry non-transient errors
        if (e is! TimeoutException && !_isTransient(e)) rethrow;
      }

      if (attempt < maxRetries) {
        await Future.delayed(_backoff(attempt));
      }
    }

    throw lastError!;
  }

  /// Exponential backoff: 1s, 2s, 4s, capped at 30s
  Duration _backoff(int attempt) =>
      Duration(seconds: (1 << attempt).clamp(1, 30));

  bool _isTransient(Object e) =>
      e is TimeoutException ||
      e.toString().contains('network') ||
      e.toString().contains('unavailable');

  Future<void> _recordToAnalytics(
    String operation,
    String context,
    Object error,
    StackTrace stack,
  ) async {
    FirebaseCrashlytics.instance.log('[$operation] $context: $error');
    await FirebaseCrashlytics.instance.recordError(
      error,
      stack,
      reason: '[$operation] $context',
      printDetails: false,
    );
  }
}

enum OperationType { quickRead, read, write, upload }

class CircuitOpenException implements Exception {
  CircuitOpenException(this.message);
  final String message;
  @override
  String toString() => 'CircuitOpenException: $message';
}
```

---

## Riverpod Integration

Register as a singleton provider and inject into repositories.

```dart
// core/providers/network_providers.dart
@Riverpod(keepAlive: true)
ResilientNetworkService resilientNetwork(Ref ref) {
  return ResilientNetworkService();
}

// In a repository
@riverpod
class OrderRepository extends _$OrderRepository {
  late final ResilientNetworkService _network;

  @override
  Future<List<Order>> build() async {
    _network = ref.read(resilientNetworkProvider);
    return _fetchOrders();
  }

  Future<List<Order>> _fetchOrders() =>
      _network.execute(
        () => FirebaseFirestore.instance
            .collection('orders')
            .get()
            .then((s) => s.docs.map(Order.fromFirestore).toList()),
        type: OperationType.read,
        operationName: 'OrderRepository.fetchOrders',
      );
}
```

---

## `pubspec.yaml` Dependencies

```yaml
dependencies:
  firebase_crashlytics: ^4.1.0
```

No additional packages needed — circuit breaker is pure Dart.

---

## Rules

- **Always pass `operationName`** — makes Crashlytics logs searchable by feature
- **Use `maxRetries: 0`** for writes where idempotency is not guaranteed (e.g., Firestore `add()`)
- **Do not catch `CircuitOpenException` silently** — surface it to the user as a "service temporarily unavailable" message
- **One `ResilientNetworkService` instance** — keep it a `keepAlive` Riverpod provider, not recreated per request
- **Adjust `failureThreshold`** for your SLA: 5 failures before opening is appropriate for consumer apps; tighten to 3 for payment flows

---

## Connectivity Is Not Reachability

A connectivity plugin reports that an interface is up, not that your backend answers (captive portals, flaky links, a server restart all look "online").

- Treat connectivity as a **hint to attempt** a request or drain; the **request outcome** is the truth.
- Assume "online" until the plugin's first emission arrives; expose one connectivity provider app-wide.
- Classify failures: no server answer (timeout, socket drop, DNS) is a **transport** failure — retry without spending retry budget; a 5xx/429 is a server-answered failure; a 4xx is permanent. A timeout is `timeout`, not "offline".
- Do not retry non-idempotent writes automatically unless the request carries an idempotency key (see [flutter-offline-reliability.md](flutter-offline-reliability.md) §3).
- Never map a network failure onto a domain error (offline → "invalid input").
