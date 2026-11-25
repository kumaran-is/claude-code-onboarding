# Atomic Decision Tree and Smart/Dumb Boundary

The shared UI library has exactly three tiers. Templates and pages are not tiers: they live in the app, router or feature layer.

## 1. Decide the tier (stop at the first yes)

```
Q1  Does it have zero child components of its own and wrap one primitive
    (button, text, icon, badge, skeleton bar, divider)?            → Atom
Q2  Does it compose 2–3 atoms for ONE focused interaction
    (labelled field, search bar, list tile, empty state)?           → Molecule
Q3  Does it compose molecules (and atoms) into a standalone section
    (app bar, bottom nav, filter panel, card list, shell)?          → Organism
Otherwise STOP: it is a template or page → feature layer, no tier marker.
```

- Composition decides the tier, not logic complexity or line count. When unsure, classify DOWN.
- An organism may contain organisms. A page-sized widget in the library is a misplacement, not a big organism.
- Spend at most a few minutes per decision; record a genuinely ambiguous one in the component's doc comment.

## 2. Marker and location

Line 1 of every shared-library component file is exactly `// Tier: Atom`, `// Tier: Molecule` or `// Tier: Organism` (capitalised, nothing before it). Folders are semantic (`buttons/`, `feedback/`, `inputs/`), not `atoms/`/`molecules/`. Barrels, tokens, theme, utils, tests and generated files carry no marker.

| Stack | Governed library (tier + presentational rules) | Exempt (vendored, CLI-owned) |
|---|---|---|
| Flutter workspace | `packages/shared_ui/lib/<area>/…` | `lib/<area>/tokens/`, `theme/`, `typography/` |
| Flutter single app | `lib/design_system/components/<area>/…` | `lib/design_system/{tokens,theme,typography}/` |
| Angular | `src/app/shared/components/<name>/` | Spartan helm/brain (`libs/ui/`) |
| React | `src/shared/ui/` (providers/contexts excluded) | `src/components/ui/` (shadcn) |

Enforced by: hookify `design-tier-comment-{dart,angular,react}` (on full-file writes) and `check-design-system.py` rule `DS-TIER`.

## 3. Smart/dumb boundary

| | Smart (container) | Dumb (presentational, every governed library file) |
|---|---|---|
| Lives in | feature / route / screen layer | shared library |
| Owns | fetching, cache, store/provider access, navigation, connectivity, derived view state | nothing but local UI state (focus, hover, expanded) |
| Talks via | passes values and semantic enums down, handles callbacks | inputs/props in, callbacks/outputs out |
| Flutter | `ConsumerWidget`, `ref.watch` | `StatelessWidget` (or `StatefulWidget` for local UI state); no `ref`, repositories, `features/` imports |
| Angular | route component, `inject(SomeService)`, `resource()` | signal `input()` / `output()` / `model()`; may inject DOM-level tokens (`ElementRef`, `DestroyRef`), never services, stores, `HttpClient`, `Router` |
| React | route component or feature hook, TanStack Query, stores | props and callbacks only; no query hooks, global stores, `fetch`, `features/` imports |

Semantics flow down as **tone/variant enums**, never colours: the dumb component maps `tone → colour token` in ONE exhaustive switch. A presentational component that needs an ambient value (connectivity, freshness) gets it as an input from a smart host that ships in the same change. Above ~6 content parameters use slots (`child`/`ng-content`/`children`) and move advanced options into a config object.

Enforced by: hookify `design-presentational-imports` (write-time advisory) and `check-design-system.py` rule `DS-PRESENTATIONAL` (blocking).

## 4. Pass / fail examples (the gate's selftest plants each one)

| Case | Verdict |
|---|---|
| Dumb button with `isBusy` / `tone` / `onPressed` and token spacing | PASS |
| Dumb component doing HTTP (`HttpClient`, `fetch`, `dio`) | FAIL `DS-PRESENTATIONAL` |
| Angular presentational component with `inject(OrderService)` | FAIL `DS-PRESENTATIONAL` |
| React shared badge importing a global store (`@/features/cart/store`, `zustand`) | FAIL `DS-PRESENTATIONAL` |
| Flutter shared atom importing a feature repository | FAIL `DS-PRESENTATIONAL` |
| Smart container passing a semantic status (`StatusBadge(tone: StatusTone.warning, …)`) | PASS |
| Raw hex passed for a business status (`StatusBadge(color: Color(0xFFE53935))`) | FLAG `DS-COLOR` |
| Library file without a line-1 tier, or `// Tier: atom` | FAIL `DS-TIER` |

```dart
// Tier: Atom
import 'package:material_ui/material_ui.dart';

import '../../tokens/app_radius.dart';
import '../../tokens/app_spacing.dart';
import '../../theme/status_colors.dart'; // the project's ThemeExtension for roles Material lacks

enum StatusTone { neutral, success, warning, danger }

class StatusBadge extends StatelessWidget {
  const StatusBadge({super.key, required this.label, this.tone = StatusTone.neutral});
  final String label;
  final StatusTone tone;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<StatusColors>()!; // success/warning live in the extension
    final (bg, fg) = switch (tone) { // the ONE tone → token mapping
      StatusTone.neutral => (scheme.surfaceContainerHighest, scheme.onSurface),
      StatusTone.success => (status.successContainer, status.onSuccessContainer),
      StatusTone.warning => (status.warningContainer, status.onWarningContainer),
      StatusTone.danger => (scheme.errorContainer, scheme.onErrorContainer),
    };
    return DecoratedBox(
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(AppRadius.full)),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
        child: Text(label, style: Theme.of(context).textTheme.labelMedium?.copyWith(color: fg)),
      ),
    );
  }
}
```

```ts
// Tier: Atom
import { Component, computed, input } from '@angular/core';

export type StatusTone = 'neutral' | 'success' | 'warning' | 'danger';

@Component({
  selector: 'app-status-badge', // OnPush is the v22 default: no changeDetection property
  template: `<span class="badge" [class]="toneClass()">{{ label() }}</span>`,
})
export class StatusBadge {
  readonly label = input.required<string>();
  readonly tone = input<StatusTone>('neutral');
  protected readonly toneClass = computed(() => ({
    neutral: 'badge-neutral', success: 'badge-success', warning: 'badge-warning', danger: 'badge-error',
  })[this.tone()]);
}
```

```tsx
// Tier: Atom
import { Badge } from '@/components/ui/badge';

export type StatusTone = 'neutral' | 'success' | 'warning' | 'danger';
const toneVariant = { neutral: 'secondary', success: 'default', warning: 'outline', danger: 'destructive' } as const;

export function StatusBadge({ label, tone = 'neutral' }: { label: string; tone?: StatusTone }) {
  return <Badge variant={toneVariant[tone]}>{label}</Badge>;
}
```

The colour of each tone is the project's decision (DESIGN.md); the mapping above is a placeholder that uses existing semantic roles only. Status is never colour alone: the label (required) carries the meaning, an icon or shape may reinforce it.
