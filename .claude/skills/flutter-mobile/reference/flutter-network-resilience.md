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

Compiled and tested on Flutter 3.50.1 / Dart 3.14.0 (`resilient_call_test.dart`: retries a transient 503 then succeeds; a 400 is reported and rethrown without retry; an error whose text says "network" is NOT transient; timeouts count toward the breaker and an open circuit rejects without calling). Planting a message-text check in `isTransient` fails the suite.

```dart
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:firebase_core/firebase_core.dart';

import 'api_failure.dart'; // classifyDioException: flutter-api-contract-parity.md §5

enum CircuitState { closed, open, halfOpen }

class CircuitBreaker {
  CircuitBreaker({
    this.failureThreshold = 5,
    this.recoveryTimeout = const Duration(seconds: 30),
    DateTime Function()? now, // injectable clock for tests
  }) : _now = now ?? DateTime.now;

  final int failureThreshold;
  final Duration recoveryTimeout;
  final DateTime Function() _now;

  CircuitState _state = CircuitState.closed;
  int _failures = 0;
  DateTime? _openedAt;

  CircuitState get state => _state;

  /// True when calls must be rejected without touching the network.
  bool get isOpen {
    final openedAt = _openedAt;
    if (_state == CircuitState.open && openedAt != null) {
      if (_now().difference(openedAt) >= recoveryTimeout) {
        _state = CircuitState.halfOpen; // allow one probe
        return false;
      }
      return true;
    }
    return false;
  }

  void recordSuccess() {
    _failures = 0;
    _state = CircuitState.closed;
  }

  void recordFailure() {
    _failures++;
    if (_state == CircuitState.halfOpen || _failures >= failureThreshold) {
      _state = CircuitState.open;
      _openedAt = _now();
    }
  }
}

class CircuitOpenException implements Exception {
  const CircuitOpenException();
}

/// Reports a failure (Crashlytics in production, a fake in tests).
typedef FailureReporter =
    Future<void> Function(Object error, StackTrace stack, String operation);

/// Transient = the server did not answer, or answered "try later".
/// Decided from types and status codes, never from message text.
bool isTransient(Object e) => switch (e) {
  TimeoutException() => true,
  DioException() => switch (classifyDioException(e)) {
    TimeoutFailure() || NetworkFailure() => true,
    ServerFailure(:final retryable) => retryable,
    _ => false,
  },
  FirebaseException(:final code) =>
    code == 'unavailable' || code == 'deadline-exceeded',
  _ => false,
};

class ResilientCall {
  ResilientCall({
    required this._report, // Dart 3.12+ private named parameter
    CircuitBreaker? breaker,
    Future<void> Function(Duration)? sleep,
  }) : _breaker = breaker ?? CircuitBreaker(),
       _sleep = sleep ?? Future<void>.delayed;

  final FailureReporter _report;
  final CircuitBreaker _breaker;
  final Future<void> Function(Duration) _sleep;

  /// [maxRetries] 0 for non-idempotent writes without an idempotency key.
  Future<T> run<T>(
    Future<T> Function() operation, {
    required String operationName,
    Duration timeout = const Duration(seconds: 15),
    int maxRetries = 3,
  }) async {
    if (_breaker.isOpen) throw const CircuitOpenException();
    for (var attempt = 0; ; attempt++) {
      try {
        final result = await operation().timeout(timeout);
        _breaker.recordSuccess();
        return result;
      } catch (e, st) {
        final transient = isTransient(e);
        if (transient) _breaker.recordFailure();
        await _report(e, st, operationName);
        if (!transient || attempt >= maxRetries || _breaker.isOpen) rethrow;
        await _sleep(Duration(seconds: 1 << attempt.clamp(0, 4))); // 1,2,4,8,16s
      }
    }
  }
}
```

Only transient failures open the breaker: a burst of 400s is a client bug, not an outage. Pass the timeout from the budget table above.

The production reporter (breadcrumb first, then the error, both awaited, no PII):

```dart
import 'package:firebase_crashlytics/firebase_crashlytics.dart';

Future<void> reportFailure(Object error, StackTrace stack, String operation) async {
  final crashlytics = FirebaseCrashlytics.instance;
  await crashlytics.log('[$operation] ${error.runtimeType}');
  await crashlytics.recordError(error, stack, reason: operation, printDetails: false);
}
```

---

## Riverpod Integration

One instance app-wide, because the breaker state must be shared (riverpod 3.5.0 / riverpod_generator 4.0.10):

```dart
@Riverpod(keepAlive: true)
ResilientCall resilientCall(Ref ref) => ResilientCall(report: reportFailure);

// In a repository
Future<List<Order>> fetchOrders() => _call.run(
  () => _firestore
      .collection('orders')
      .get()
      .then((s) => s.docs.map(Order.fromFirestore).toList()),
  operationName: 'OrderRepository.fetchOrders',
);
```

Pick one retry layer: Riverpod 3 also retries a failing provider by default, so set `retry` on providers that sit on top of `ResilientCall` (see `riverpod-patterns`), or the attempts multiply.

---

## `pubspec.yaml` Dependencies

```yaml
dependencies:
  dio: 5.11.1
  firebase_core: 5.2.0
  firebase_crashlytics: 6.1.0
```

No additional packages needed — the circuit breaker is pure Dart. Versions resolved together on Flutter 3.50.1.

---

## Rules

- **Always pass `operationName`** — makes Crashlytics logs searchable by feature (it is required by the signature)
- **Classify by type and status, never by message text** — a substring check such as `e.toString().contains('network')` retries unrelated errors and can mask a needed sign-out
- **Use `maxRetries: 0`** for writes where idempotency is not guaranteed (e.g., Firestore `add()`)
- **Do not catch `CircuitOpenException` silently** — surface it to the user as a "service temporarily unavailable" message
- **One `ResilientCall` instance** — keep it a `keepAlive` Riverpod provider, not recreated per request
- **Adjust `failureThreshold`** for your SLA: 5 failures before opening is appropriate for consumer apps; tighten to 3 for payment flows

---

## Connectivity Is Not Reachability

A connectivity plugin reports that an interface is up, not that your backend answers (captive portals, flaky links, a server restart all look "online").

- Treat connectivity as a **hint to attempt** a request or drain; the **request outcome** is the truth.
- Assume "online" until the plugin's first emission arrives; expose one connectivity provider app-wide.
- Classify failures: no server answer (timeout, socket drop, DNS) is a **transport** failure — retry without spending retry budget; a 5xx/429 is a server-answered failure; a 4xx is permanent. A timeout is `timeout`, not "offline".
- Do not retry non-idempotent writes automatically unless the request carries an idempotency key (see [flutter-offline-reliability.md](flutter-offline-reliability.md) §3).
- Never map a network failure onto a domain error (offline → "invalid input").
