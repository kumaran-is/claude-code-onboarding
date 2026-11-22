# AI-Specific Error Handling Patterns

Covers: refusal, rate limit, context exceeded, stream timeout, hallucination flag, content policy.
These are NOT generic HTTP errors — each needs distinct UX treatment.

**Rule:** Every catch block must log + return error state or rethrow. NO silent failures.

---

## Error Type Enum (shared model)

### Angular

```typescript
// features/chat/models/ai-error.model.ts
export type AiErrorType =
  | 'refusal'           // Model declined to answer
  | 'rate_limit'        // 429 — too many requests
  | 'context_exceeded'  // 400/413 — prompt too long
  | 'stream_timeout'    // Network timeout during SSE
  | 'content_policy'    // Content filtered by provider
  | 'stream_failed';    // Generic stream error (fallback)

export interface AiError {
  type: AiErrorType;
  retryAfterSeconds?: number;  // for rate_limit
  partialContent?: string;     // for stream_timeout
}
```

### Flutter

```dart
// features/chat/models/ai_error.dart
import 'package:freezed_annotation/freezed_annotation.dart';

part 'ai_error.freezed.dart';

enum AiErrorType {
  refusal,
  rateLimit,
  contextExceeded,
  streamTimeout,
  contentPolicy,
  streamFailed,
}

@freezed
class AiError with _$AiError {
  const factory AiError({
    required AiErrorType type,
    int? retryAfterSeconds,
    String? partialContent,
  }) = _AiError;
}
```

---

## Angular 21.x — AiErrorComponent

```typescript
// features/chat/components/ai-error.component.ts
import { Component, ChangeDetectionStrategy, input, output, signal, computed, inject } from '@angular/core';
import { AiError, AiErrorType } from '../models/ai-error.model';
import { AppLogger } from '../../../core/logging/app-logger.service';

@Component({
  selector: 'app-ai-error',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="alert"
         [class.alert-info]="errorConfig().alertClass === 'alert-info'"
         [class.alert-warning]="errorConfig().alertClass === 'alert-warning'"
         [class.alert-error]="errorConfig().alertClass === 'alert-error'"
         role="alert"
         [attr.aria-label]="errorConfig().message">

      <span class="text-xl" aria-hidden="true">{{ errorConfig().icon }}</span>

      <div class="flex-1">
        <p class="font-semibold">{{ errorConfig().message }}</p>
        @if (errorConfig().suggestion) {
          <p class="text-sm opacity-80">{{ errorConfig().suggestion }}</p>
        }
        @if (isRateLimit() && countdown() > 0) {
          <p class="text-sm opacity-80">Retry in {{ countdown() }}s</p>
        }
      </div>

      <div class="flex gap-2">
        @if (showRetry()) {
          <button class="btn btn-sm btn-ghost" (click)="onRetry()"
                  [disabled]="isRateLimit() && countdown() > 0">
            Try again
          </button>
        }
        @if (error().partialContent) {
          <button class="btn btn-sm btn-ghost" (click)="onResume()">
            Resume from partial
          </button>
        }
        @if (isContextExceeded()) {
          <button class="btn btn-sm btn-ghost" (click)="onSummarize()">
            Summarize &amp; continue
          </button>
        }
      </div>
    </div>

    @if (showHallucinationFlag()) {
      <div class="mt-1">
        <button class="btn btn-xs btn-ghost text-warning gap-1"
                (click)="onFlagInaccurate()"
                aria-label="Flag this response as potentially inaccurate">
          <span aria-hidden="true">&#9873;</span> Flag as inaccurate
        </button>
      </div>
    }
  `
})
export class AiErrorComponent {
  readonly error = input.required<AiError>();
  readonly retry = output<void>();
  readonly resume = output<string>();
  readonly summarize = output<void>();
  readonly flagInaccurate = output<void>();

  private readonly logger = inject(AppLogger);
  private countdownTimer: ReturnType<typeof setInterval> | null = null;
  readonly countdown = signal(0);

  readonly isRateLimit = computed(() => this.error().type === 'rate_limit');
  readonly isContextExceeded = computed(() => this.error().type === 'context_exceeded');
  readonly showRetry = computed(() =>
    ['rate_limit', 'stream_timeout', 'stream_failed'].includes(this.error().type)
  );
  readonly showHallucinationFlag = computed(() =>
    this.error().type === 'refusal' || this.error().type === 'stream_failed'
  );

  readonly errorConfig = computed(() => {
    switch (this.error().type) {
      case 'refusal':
        return {
          icon: 'i',
          alertClass: 'alert-info',
          message: "I can't help with that request.",
          suggestion: 'Try rephrasing or asking about a related topic.',
        };
      case 'rate_limit':
        this.startCountdown(this.error().retryAfterSeconds ?? 30);
        return {
          icon: '!',
          alertClass: 'alert-warning',
          message: 'Too many requests.',
          suggestion: 'You have hit the usage limit. Please wait a moment.',
        };
      case 'context_exceeded':
        return {
          icon: '!',
          alertClass: 'alert-warning',
          message: 'Conversation is too long to continue.',
          suggestion: 'Summarize earlier messages to free up space.',
        };
      case 'stream_timeout':
        return {
          icon: '!',
          alertClass: 'alert-warning',
          message: 'Response interrupted.',
          suggestion: this.error().partialContent
            ? 'Partial response received. You can resume or retry.'
            : 'Connection timed out. Try again.',
        };
      case 'content_policy':
        return {
          icon: 'i',
          alertClass: 'alert-info',
          message: 'This response was not completed.',
          suggestion: "The content could not be generated. Try a different approach.",
        };
      default:
        return {
          icon: 'x',
          alertClass: 'alert-error',
          message: 'Something went wrong.',
          suggestion: 'Please try again.',
        };
    }
  });

  onRetry(): void {
    this.logger.info('[AiErrorComponent] User retried after error', { type: this.error().type });
    this.retry.emit();
  }

  onResume(): void {
    if (this.error().partialContent) {
      this.resume.emit(this.error().partialContent!);
    }
  }

  onSummarize(): void {
    this.summarize.emit();
  }

  onFlagInaccurate(): void {
    this.logger.info('[AiErrorComponent] User flagged response as inaccurate');
    this.flagInaccurate.emit();
  }

  private startCountdown(seconds: number): void {
    if (this.countdownTimer) return; // already running
    this.countdown.set(seconds);
    this.countdownTimer = setInterval(() => {
      this.countdown.update(n => {
        if (n <= 1) {
          clearInterval(this.countdownTimer!);
          this.countdownTimer = null;
          return 0;
        }
        return n - 1;
      });
    }, 1_000);
  }
}
```

---

## Flutter 3.41.x — AiErrorWidget

```dart
// features/chat/presentation/widgets/ai_error_widget.dart
import 'dart:async';
import 'package:flutter/material.dart';
import '../../models/ai_error.dart';
import '../../../../core/tokens/app_spacing.dart';

class AiErrorWidget extends StatefulWidget {
  const AiErrorWidget({
    super.key,
    required this.error,
    this.onRetry,
    this.onResume,
    this.onSummarize,
    this.onFlagInaccurate,
  });

  final AiError error;
  final VoidCallback? onRetry;
  final ValueChanged<String>? onResume;
  final VoidCallback? onSummarize;
  final VoidCallback? onFlagInaccurate;

  @override
  State<AiErrorWidget> createState() => _AiErrorWidgetState();
}

class _AiErrorWidgetState extends State<AiErrorWidget> {
  int _countdown = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    if (widget.error.type == AiErrorType.rateLimit) {
      _countdown = widget.error.retryAfterSeconds ?? 30;
      _timer = Timer.periodic(const Duration(seconds: 1), (_) {
        if (!mounted) return;
        setState(() => _countdown = (_countdown - 1).clamp(0, 999));
        if (_countdown == 0) _timer?.cancel();
      });
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  _ErrorConfig get _config {
    final colorScheme = Theme.of(context).colorScheme;
    switch (widget.error.type) {
      case AiErrorType.refusal:
        return _ErrorConfig(
          icon: Icons.info_outline,
          color: colorScheme.secondary,
          message: "I can't help with that request.",
          suggestion: 'Try rephrasing or asking about a related topic.',
        );
      case AiErrorType.rateLimit:
        return _ErrorConfig(
          icon: Icons.hourglass_empty,
          color: colorScheme.tertiary,
          message: 'Too many requests.',
          suggestion: _countdown > 0
            ? 'Retry in ${_countdown}s'
            : 'You can try again now.',
        );
      case AiErrorType.contextExceeded:
        return _ErrorConfig(
          icon: Icons.warning_amber_outlined,
          color: colorScheme.tertiary,
          message: 'Conversation is too long to continue.',
          suggestion: 'Summarize earlier messages to free up space.',
        );
      case AiErrorType.streamTimeout:
        return _ErrorConfig(
          icon: Icons.wifi_off_outlined,
          color: colorScheme.tertiary,
          message: 'Response interrupted.',
          suggestion: widget.error.partialContent != null
            ? 'Partial response received. You can resume or retry.'
            : 'Connection timed out. Please try again.',
        );
      case AiErrorType.contentPolicy:
        return _ErrorConfig(
          icon: Icons.block_outlined,
          color: colorScheme.secondary,
          message: 'This response was not completed.',
          suggestion: 'The content could not be generated. Try a different approach.',
        );
      default:
        return _ErrorConfig(
          icon: Icons.error_outline,
          color: colorScheme.error,
          message: 'Something went wrong.',
          suggestion: 'Please try again.',
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    final config = _config;
    final colorScheme = Theme.of(context).colorScheme;

    return Semantics(
      label: '${config.message} ${config.suggestion}',
      child: Container(
        margin: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.xs,
        ),
        padding: EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: config.color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          border: Border.all(color: config.color.withValues(alpha: 0.4)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(config.icon, color: config.color, size: AppSpacing.iconSm),
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(config.message,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: config.color,
                    fontWeight: FontWeight.w600,
                  )),
              ),
            ]),
            if (config.suggestion != null) ...[
              SizedBox(height: AppSpacing.xs),
              Text(config.suggestion!,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: colorScheme.onSurface.withValues(alpha: 0.7),
                )),
            ],
            SizedBox(height: AppSpacing.sm),
            Wrap(spacing: AppSpacing.sm, children: [
              if (widget.onRetry != null &&
                  [AiErrorType.rateLimit, AiErrorType.streamTimeout, AiErrorType.streamFailed]
                    .contains(widget.error.type))
                TextButton(
                  onPressed: _countdown > 0 ? null : widget.onRetry,
                  child: const Text('Try again'),
                ),
              if (widget.error.partialContent != null && widget.onResume != null)
                TextButton(
                  onPressed: () => widget.onResume!(widget.error.partialContent!),
                  child: const Text('Resume from partial'),
                ),
              if (widget.error.type == AiErrorType.contextExceeded && widget.onSummarize != null)
                TextButton(
                  onPressed: widget.onSummarize,
                  child: const Text('Summarize & continue'),
                ),
              if (widget.onFlagInaccurate != null)
                TextButton.icon(
                  onPressed: widget.onFlagInaccurate,
                  icon: const Icon(Icons.flag_outlined, size: 16),
                  label: const Text('Flag as inaccurate'),
                  style: TextButton.styleFrom(
                    foregroundColor: colorScheme.onSurface.withValues(alpha: 0.6),
                  ),
                ),
            ]),
          ],
        ),
      ),
    );
  }
}

class _ErrorConfig {
  const _ErrorConfig({
    required this.icon,
    required this.color,
    required this.message,
    this.suggestion,
  });
  final IconData icon;
  final Color color;
  final String message;
  final String? suggestion;
}
```

---

## Error Handling Rules

- **Refusal**: Info styling (not error red) — avoid user blame; offer rephrasing suggestion
- **Rate limit**: Warning styling; show live countdown; disable retry button until countdown reaches 0
- **Context exceeded**: Warning; only action is summarize — do not let user send more without acknowledging
- **Stream timeout**: Show partial content if available; offer resume (re-sends with partial as context prefix)
- **Hallucination flag**: Allow user to mark any assistant message as inaccurate; send flag to analytics
- **Content policy**: Never imply the user did something wrong; neutral, dignified message
- Every catch block must call logger before returning error state — no silent swallowing
