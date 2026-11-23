# Smart vs Dumb Widget Pattern

Container/Presentational widget separation for Flutter + Riverpod 3.x.

---

## 1. Pattern Definition

### Smart (Container) Widgets

- Extend `ConsumerWidget` or `ConsumerStatefulWidget`
- Call `ref.watch()` in `build()` to subscribe to provider state
- Call `ref.read()` in callbacks/handlers to trigger state changes
- Own screen-level orchestration logic
- Live in `apps/<app>/lib/screens/` or `apps/<app>/lib/features/<feature>/presentation/screens/`

### Dumb (Presentational) Widgets

- Extend `StatelessWidget` — **never** `ConsumerWidget`
- Receive ALL data via constructor parameters
- Emit user events via `VoidCallback` or `ValueChanged<T>` callbacks
- Contain zero `ref` usage and zero provider references
- Live in `packages/shared_ui/lib/src/widgets/` (shared across apps) or `apps/<app>/lib/widgets/` (app-local)

**Portability test:** A dumb widget is portable — copy it to any Flutter project that does not have Riverpod and it compiles without changes.

---

## Riverpod ↔ MVVM Terminology

Flutter's official architecture guide uses MVVM naming. In Riverpod, these map directly — you do not need to change anything, just recognize the names.

| MVVM Term | Riverpod / Flutter Equivalent | Location |
|-----------|-------------------------------|----------|
| **View** | `StatelessWidget` (Dumb) or `ConsumerWidget` (Smart screen) | `screens/`, `widgets/` |
| **ViewModel** | `AsyncNotifier` / `Notifier` provider | `presentation/providers/` |
| **Model** | Freezed domain entity + Repository | `domain/entities/`, `data/repositories/` |

---

## 2. Decision Tree

```
Is this widget a leaf UI element (button, card, tile, badge)
OR reused across 2+ screens?
    YES → Dumb widget
          - StatelessWidget
          - Constructor parameters only
          - No ref, no provider import
          - Goes in shared_ui/ or app widgets/

    NO → Is it a screen root or feature-level container?
          YES → Smart widget
                - ConsumerWidget
                - ref.watch() providers in build()
                - ref.read() in callbacks only
                - Composes dumb children
                - Goes in screens/

          NO → Prefer dumb; use ConsumerWidget only if
               local async data is unavoidable and the
               widget will never be reused elsewhere
```

---

## 3. Flutter + Riverpod 3.x Examples

### Smart Widget — Screen Level

```dart
// apps/mobile/lib/screens/tasks/tasks_screen.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart'; // flutter/material.dart is deprecated after 3.47
import 'package:mobile/screens/providers/tasks_provider.dart'; // package import, not ../
import 'package:shared_core/shared_core.dart';
import 'package:shared_ui/shared_ui.dart';

class TasksScreen extends ConsumerWidget {  // ✅ Smart: ConsumerWidget
  const TasksScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // ✅ Smart: ref.watch in build — reactive, rebuilds on change
    final tasksAsync = ref.watch(tasksProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Tasks')),
      body: tasksAsync.when(
        loading: () => const LoadingSpinner(),
        error: (e, _) => ErrorCard(message: e.toString()),
        data: (tasks) => ListView.builder(
          itemCount: tasks.length,
          itemBuilder: (_, i) => TaskCard(  // ✅ passes data DOWN to dumb widget
            task: tasks[i],
            onTap: () => ref  // ✅ ref.read in callback — not in build
                .read(tasksProvider.notifier)
                .select(tasks[i].id),
          ),
        ),
      ),
    );
  }
}
```

### Dumb Widget — Shared UI Package

```dart
// packages/shared_ui/lib/src/widgets/task_card.dart
import 'package:material_ui/material_ui.dart'; // shared_ui depends on material_ui: 1.11.1
import 'package:shared_core/shared_core.dart';   // domain model only

// ✅ Dumb: StatelessWidget — zero Riverpod dependency
class TaskCard extends StatelessWidget {
  const TaskCard({          // ✅ const constructor required
    super.key,
    required this.task,     // ✅ receives data via constructor
    required this.onTap,      // ✅ emits events via callback
  });

  final Task task;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    // NO ref, NO watch(), NO Provider.of(), NO import flutter_riverpod
    return Card(
      child: ListTile(
        title: Text(task.title),
        subtitle: Text(task.status.label),
        onTap: onTap,
      ),
    );
  }
}
```

### Smart Widget with ConsumerStatefulWidget — When Local Lifecycle Is Needed

```dart
// lib/features/orders/screens/order_detail_screen.dart
class OrderDetailScreen extends ConsumerStatefulWidget {
  const OrderDetailScreen({super.key, required this.orderId});
  final String orderId;

  @override
  ConsumerState<OrderDetailScreen> createState() =>
      _OrderDetailScreenState();
}

class _OrderDetailScreenState
    extends ConsumerState<OrderDetailScreen> {
  // Local state that belongs to this screen's lifecycle
  final _scrollController = ScrollController();

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // ✅ ref available via ConsumerState.ref — no parameter needed
    final orderAsync = ref.watch(orderDetailProvider(widget.orderId));

    return Scaffold(
      body: orderAsync.when(
        loading: () => const OrderDetailSkeleton(),
        error: (e, _) => ErrorCard(message: e.toString()),
        data: (order) => OrderInfoCard(  // ✅ dumb child
          order: order,
          onEditTap: () => ref
              .read(orderDetailProvider(widget.orderId).notifier)
              .startEdit(),
        ),
      ),
    );
  }
}
```

---

## 4. Hard Rules (Zero Tolerance)

### Dumb Widget Rules — StatelessWidget

```
❌ NEVER extend ConsumerWidget in shared_ui/ or app widgets/
❌ NEVER call ref.watch() / ref.read() / ref.listen() in a dumb widget
❌ NEVER import flutter_riverpod in a dumb widget file
❌ NEVER reference a Provider directly in a dumb widget
❌ NEVER use Provider.of<T>(context) — same violation as ref.watch()

✅ ALWAYS receive data via constructor parameters
✅ ALWAYS emit events via VoidCallback or ValueChanged<T>
✅ ALWAYS declare a const constructor
✅ ALWAYS use Theme.of(context) for colors and typography — no hardcoded values
```

### Smart Widget Rules — ConsumerWidget

```
✅ Allowed: extend ConsumerWidget or ConsumerStatefulWidget
✅ Allowed: ref.watch() for reactive data in build()
✅ Allowed: ref.read() in event handlers and callbacks
✅ Should compose dumb children — do not inline all rendering

❌ NEVER put smart widgets in packages/shared_ui/ — they go in individual apps
❌ NEVER call ref.read() inside build() — only in callbacks/handlers
❌ NEVER call ref.watch() inside a callback or event handler
❌ NEVER use Provider.of<T>(context) — use ref.watch()/ref.read()
```

---

## 5. ref.watch() vs ref.read() Placement Rules

```dart
// ❌ Wrong: ref.read in build — no reactivity, returns stale data on rebuild
@override
Widget build(BuildContext context, WidgetRef ref) {
  final data = ref.read(myProvider);   // ❌ stale after first build
  return Text(data.value);
}

// ❌ Wrong: ref.watch in callback — subscribes on every tap, leaks listeners
ElevatedButton(
  onPressed: () {
    final notifier = ref.watch(myProvider.notifier);  // ❌ watch in callback
    notifier.doSomething();
  },
)

// ✅ Correct: ref.watch in build for reactive data
//             ref.read in callbacks for imperative actions
@override
Widget build(BuildContext context, WidgetRef ref) {
  final data = ref.watch(myProvider);        // ✅ reactive — rebuilds on change
  return ElevatedButton(
    onPressed: () =>
        ref.read(myProvider.notifier).doSomething(),  // ✅ read in callback
    child: Text(data.value),
  );
}
```

---

## 6. File Location Rule

```
apps/<app>/lib/
├── screens/                    ← SMART widgets (ConsumerWidget, ref.watch)
│   └── <feature>/
│       └── <name>_screen.dart
└── widgets/                    ← DUMB widgets local to this app (StatelessWidget ONLY)
    └── <name>.dart

packages/shared_ui/lib/src/
└── widgets/                    ← DUMB widgets shared across all 3 apps (StatelessWidget ONLY)
    └── <name>.dart             ← ZERO ConsumerWidget here — enforced by riverpod-reviewer

packages/shared_core/lib/src/
└── providers/                  ← Providers consumed by smart widgets
    └── <name>_provider.dart
```

**Example app mapping:**

| App | Screens directory | Shared dumb widgets |
|-----|-------------------|---------------------|
| App A | `apps/app-a/lib/screens/` | `packages/shared_ui/lib/src/widgets/` |
| App B | `apps/app-b/lib/screens/` | `packages/shared_ui/lib/src/widgets/` |
| App C | `apps/app-c/lib/screens/` | `packages/shared_ui/lib/src/widgets/` |

---

## 7. Riverpod Review Gate

The `riverpod-reviewer` agent checks these as **blocking findings**:

| Finding | Severity |
|---------|----------|
| `ConsumerWidget` in `shared_ui/` or `lib/widgets/` | Blocking |
| `ref.read()` called inside `build()` | Blocking |
| `flutter_riverpod` imported in a dumb widget file | Blocking |
| Missing `const` constructor on `StatelessWidget` | Warning |
| `ref.watch()` called inside a callback or event handler | Blocking |

---

## 7b. When a Dumb Component Has a Parameter Callers Must Remember

**Symptom:** you are writing a doc comment such as "callers must pass X from provider Y", or the component renders plausible-but-wrong UI when X is omitted (for example a "last updated" label that shows nothing, or "now", when its timestamp is missing).

An optional parameter the caller must remember is a parameter nobody passes. Fix it in the same change:

1. Add a smart `<Name>Host` (a `ConsumerWidget`) in the screens layer. It reads the provider and passes X to the dumb component.
2. Gate the bare component out of feature code (a CI grep) with a reason-bearing hatch, e.g. `// ignore-host: <reason>`.
3. If X must always be supplied, make the parameter `required`. Never keep it optional with a default that looks valid.
4. Never thread X by hand at N call sites.

The same rule covers a component whose value is a channel a theme cannot express (intent, icon, semantics): ship the component with its enforcing gate in one change.

**Single owner for global chrome.** A persistent status band (offline, sync failure) has one owner, the shell scaffold. Feature screens supply copy, never their own banner. Fix the priority order once (a failure outranks offline). Stacked banners each add their own `SafeArea`, so the status-bar inset applies twice and paints an empty strip between them.

---

## 8. Pre-Submit Checklist

```
Before committing any widget:

□ Is it in shared_ui/ or lib/widgets/?
  → MUST extend StatelessWidget
  → MUST have zero ref usage
  → MUST NOT import flutter_riverpod

□ Does it call ref.watch()?
  → MUST be a screen (screens/ directory), NOT in shared_ui/ or widgets/

□ Does it call ref.read() in build()?
  → MOVE to a callback or event handler — never in build()

□ Does it import flutter_riverpod?
  → Only allowed in screens/ and ConsumerWidget subclasses

□ Does it have a const constructor?
  → Required for all StatelessWidget subclasses

□ Does it use Theme.of(context) for colors/typography?
  → No hardcoded Color() values or TextStyle(fontSize: ...) literals
```
