# Context & Token Management Patterns

Covers: token usage indicator, threshold logic, user-friendly messaging, summarization trigger.

---

## Angular 22.x

### TokenIndicatorComponent

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// features/chat/components/token-indicator.component.ts
import { Component, input, computed } from '@angular/core';
import { TokenUsage } from '../models/token-usage.model';

// Thresholds
const WARN_THRESHOLD = 0.80;   // 80% — show warning state
const FULL_THRESHOLD = 1.00;   // 100% — show error state, disable input

// Approximate words per token (rough heuristic for user-friendly display)
const AVG_WORDS_PER_TOKEN = 0.75;
const AVG_WORDS_PER_MESSAGE = 40;

@Component({
  selector: 'app-token-indicator',
  template: `
    @if (isVisible()) {
      <div class="px-4 py-1 flex items-center gap-2"
           role="status"
           [attr.aria-label]="ariaLabel()">
        <!-- daisyUI progress bar -->
        <progress
          class="progress w-24 h-2"
          [class.progress-warning]="isWarning()"
          [class.progress-error]="isFull()"
          [value]="usage().used"
          [max]="usage().limit"
          aria-hidden="true">
        </progress>

        <span class="text-xs"
              [class.text-warning]="isWarning()"
              [class.text-error]="isFull()">
          {{ statusLabel() }}
        </span>

        @if (isFull()) {
          <button class="btn btn-xs btn-ghost text-error"
                  (click)="onSummarize()"
                  aria-label="Summarize conversation to free up context space">
            Summarize &amp; continue
          </button>
        }
      </div>
    }
  `
})
export class TokenIndicatorComponent {
  readonly usage = input.required<TokenUsage>();
  readonly summarize = output<void>();

  readonly ratio = computed(() => this.usage().used / this.usage().limit);
  readonly isVisible = computed(() => this.ratio() >= WARN_THRESHOLD);
  readonly isWarning = computed(() => this.ratio() >= WARN_THRESHOLD && this.ratio() < FULL_THRESHOLD);
  readonly isFull = computed(() => this.ratio() >= FULL_THRESHOLD);

  readonly messagesRemaining = computed(() => {
    const tokensLeft = this.usage().limit - this.usage().used;
    const wordsLeft = tokensLeft * AVG_WORDS_PER_TOKEN;
    return Math.max(0, Math.floor(wordsLeft / AVG_WORDS_PER_MESSAGE));
  });

  readonly statusLabel = computed(() => {
    if (this.isFull()) return 'Context full';
    return `~${this.messagesRemaining()} messages remaining`;
  });

  readonly ariaLabel = computed(() =>
    `Context window: ${this.statusLabel()}`
  );

  onSummarize(): void {
    this.summarize.emit();
  }
}
```

### TokenUsage model

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// features/chat/models/token-usage.model.ts
export interface TokenUsage {
  used: number;    // tokens consumed so far
  limit: number;   // model context window size
}
```

### Summarization trigger in ChatService

*Not recompiled on Angular 22.3 (pre-22 snippet; `@Service()` conversions are mechanical).*

```typescript
// features/chat/services/chat.service.ts (excerpt)
import { Service, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { AppLogger } from '../../../core/logging/app-logger.service';
import { TokenUsage } from '../models/token-usage.model';

@Service()
export class ChatService {
  private readonly http = inject(HttpClient);
  private readonly logger = inject(AppLogger);

  readonly currentTokenUsage = signal<TokenUsage>({ used: 0, limit: 128_000 });

  async summarizeConversation(messages: ChatMessage[]): Promise<ChatMessage[]> {
    try {
      const summary = await firstValueFrom(
        this.http.post<{ summary: string; tokenCount: number }>(
          '/api/chat/summarize',
          { messages }
        )
      );
      // Replace history with a single summary system message
      const summaryMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'system',
        content: `[Previous conversation summary]\n${summary.summary}`,
        isStreaming: false,
      };
      this.currentTokenUsage.set({ used: summary.tokenCount, limit: this.currentTokenUsage().limit });
      return [summaryMsg];
    } catch (err) {
      this.logger.error('ChatService.summarizeConversation failed', err);
      throw err; // Caller shows error state — no silent failure
    }
  }
}
```

---

## Flutter 3.50.x (Riverpod)

### TokenIndicatorWidget

```dart
// features/chat/presentation/widgets/token_indicator_widget.dart
import 'package:material_ui/material_ui.dart';

import '../../models/token_usage.dart';
import '../../../../core/tokens/app_spacing.dart';

const double _warnThreshold = 0.80;
const double _fullThreshold = 1.00;
const double _avgWordsPerToken = 0.75;
const double _avgWordsPerMessage = 40;

class TokenIndicatorWidget extends StatelessWidget {
  const TokenIndicatorWidget({
    super.key,
    required this.usage,
    this.onSummarize,
  });

  final TokenUsage usage;
  final VoidCallback? onSummarize;

  double get _ratio => usage.limit <= 0 ? 1.0 : usage.used / usage.limit;
  bool get _isVisible => _ratio >= _warnThreshold;
  bool get _isFull => _ratio >= _fullThreshold;

  int get _messagesRemaining {
    final tokensLeft = usage.limit - usage.used;
    final wordsLeft = tokensLeft * _avgWordsPerToken;
    return (wordsLeft / _avgWordsPerMessage).floor().clamp(0, 999);
  }

  String get _statusLabel {
    if (_isFull) return 'Context full';
    return '~$_messagesRemaining messages remaining';
  }

  @override
  Widget build(BuildContext context) {
    if (!_isVisible) return const SizedBox.shrink();

    final colorScheme = Theme.of(context).colorScheme;
    final indicatorColor = _isFull
        ? colorScheme.error
        : colorScheme.tertiary; // tertiary = warning-like semantic

    return Semantics(
      label: 'Context window: $_statusLabel',
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.xs,
        ),
        child: Row(
          children: [
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
                child: LinearProgressIndicator(
                  value: _ratio.clamp(0.0, 1.0),
                  color: indicatorColor,
                  backgroundColor: colorScheme.surfaceContainerHighest,
                  minHeight: AppSpacing.xs,
                ),
              ),
            ),
            SizedBox(width: AppSpacing.sm),
            Text(
              _statusLabel,
              style: Theme.of(context).textTheme.labelSmall
                  ?.copyWith(color: indicatorColor),
            ),
            if (_isFull && onSummarize != null) ...[
              SizedBox(width: AppSpacing.sm),
              TextButton(
                onPressed: onSummarize,
                child: Text(
                  'Summarize & continue',
                  style: Theme.of(context).textTheme.labelSmall
                      ?.copyWith(color: colorScheme.error),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
```

### TokenUsage model (Freezed)

```dart
// features/chat/models/token_usage.dart
import 'package:freezed_annotation/freezed_annotation.dart';

part 'token_usage.freezed.dart';

@freezed
abstract class TokenUsage with _$TokenUsage {
  const factory TokenUsage({
    required int used,
    required int
    limit, // the model's context window, from config — never hardcoded
  }) = _TokenUsage;
  const TokenUsage._();

  // A union case without `used`/`limit` would make `usage.used` a compile error.
  factory TokenUsage.initial({required int limit}) =>
      TokenUsage(used: 0, limit: limit);
}
```

### Summarization call in ChatNotifier (excerpt)

```dart
// In ChatNotifier — called when TokenIndicator emits summarize
Future<void> summarize() async {
  try {
    final summaryResult = await ref
        .read(chatRepositoryProvider)
        .summarize(messages: state.messages);

    state = state.copyWith(
      messages: [summaryResult.summaryMessage],
      tokenUsage: TokenUsage(
        used: summaryResult.tokenCount,
        limit: state.tokenUsage.limit,
      ),
    );
  } catch (err, stack) {
    ref
        .read(appLoggerProvider)
        .error('ChatNotifier.summarize failed', err, stack);
    // Show error state — user must see this failed
    state = state.copyWith(summarizeError: true);
    rethrow;
  }
}
```

---

## Design Rules

- Display "~N messages remaining" — never raw token numbers
- Show the indicator only at 80%+ — below that, no UI noise
- At 100%: disable the send button AND show "Summarize & continue" action
- Warning color (80–99%): `text-warning` (Angular) / `colorScheme.tertiary` (Flutter)
- Error color (100%): `text-error` (Angular) / `colorScheme.error` (Flutter)
- Never hardcode threshold colors — always derive from the design token system
