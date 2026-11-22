# Feedback Loop Patterns

Covers: thumbs up/down, copy to clipboard, share, regenerate, hallucination flag.

---

## Angular 21.x — FeedbackComponent

```typescript
// features/chat/components/feedback.component.ts
import {
  Component, ChangeDetectionStrategy, input, output, signal, computed, inject
} from '@angular/core';
import { Clipboard } from '@angular/cdk/clipboard';
import { AppLogger } from '../../../core/logging/app-logger.service';
import { ChatMessage } from '../models/chat-message.model';

type ThumbState = 'up' | 'down' | null;

@Component({
  selector: 'app-feedback',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [],   // Clipboard is a service, no module import needed
  template: `
    <div class="flex items-center gap-1 mt-1" role="group"
         [attr.aria-label]="'Feedback for message ' + message().id">

      <!-- Thumbs Up -->
      <button class="btn btn-xs btn-ghost"
              [class.text-success]="thumb() === 'up'"
              [attr.aria-pressed]="thumb() === 'up'"
              aria-label="Mark response as helpful"
              (click)="onThumb('up')">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21H5a2 2 0 01-2-2v-7a2 2 0 012-2h2.924L10 4h1a3 3 0 013 3v3z"/>
        </svg>
      </button>

      <!-- Thumbs Down -->
      <button class="btn btn-xs btn-ghost"
              [class.text-error]="thumb() === 'down'"
              [attr.aria-pressed]="thumb() === 'down'"
              aria-label="Mark response as unhelpful"
              (click)="onThumb('down')">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3H19a2 2 0 012 2v7a2 2 0 01-2 2h-2.924L14 20h-1a3 3 0 01-3-3v-3z"/>
        </svg>
      </button>

      <!-- Copy -->
      <button class="btn btn-xs btn-ghost"
              aria-label="Copy message to clipboard"
              (click)="onCopy()">
        @if (copied()) {
          <svg class="w-4 h-4 text-success" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
          </svg>
        } @else {
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
          </svg>
        }
      </button>

      <!-- Regenerate -->
      @if (showRegenerate()) {
        <button class="btn btn-xs btn-ghost"
                aria-label="Regenerate this response"
                [disabled]="isStreaming()"
                (click)="onRegenerate()">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
          </svg>
        </button>
      }
    </div>
  `
})
export class FeedbackComponent {
  readonly message = input.required<ChatMessage>();
  readonly isStreaming = input(false);
  readonly showRegenerate = input(true);

  readonly thumbChanged = output<ThumbState>();
  readonly regenerate = output<void>();
  readonly copied = signal(false);

  private copyResetTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly clipboard = inject(Clipboard);
  private readonly logger = inject(AppLogger);

  readonly thumb = signal<ThumbState>(null);

  onThumb(value: 'up' | 'down'): void {
    // Toggle: clicking same thumb deselects it
    const next: ThumbState = this.thumb() === value ? null : value;
    this.thumb.set(next);
    this.thumbChanged.emit(next);
    this.logger.info('[FeedbackComponent] thumb vote', { messageId: this.message().id, vote: next });
  }

  onCopy(): void {
    const success = this.clipboard.copy(this.message().content);
    if (!success) {
      this.logger.error('[FeedbackComponent] clipboard copy failed', { messageId: this.message().id });
      return;
    }
    this.copied.set(true);
    if (this.copyResetTimer) clearTimeout(this.copyResetTimer);
    this.copyResetTimer = setTimeout(() => this.copied.set(false), 2_000);
  }

  onRegenerate(): void {
    if (this.isStreaming()) return;
    this.logger.info('[FeedbackComponent] regenerate requested', { messageId: this.message().id });
    this.regenerate.emit();
  }
}
```

### Regenerate wiring in ChatComponent

```typescript
// In ChatComponent — onRegenerate finds the preceding user message and re-streams
onRegenerate(assistantMessageId: string): void {
  const msgs = this.messages();
  const assistantIdx = msgs.findIndex(m => m.id === assistantMessageId);
  if (assistantIdx < 1) return;

  // Find nearest preceding user message
  const userMsg = [...msgs].slice(0, assistantIdx).reverse()
    .find(m => m.role === 'user');
  if (!userMsg) return;

  // Remove assistant message and re-send
  this.messages.update(ms => ms.filter(m => m.id !== assistantMessageId));
  this.onSend(userMsg.content);
}
```

---

## Flutter 3.41.x — FeedbackBar Widget

```dart
// features/chat/presentation/widgets/feedback_bar.dart
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../models/chat_message.dart';
import '../../../../core/tokens/app_spacing.dart';

enum ThumbState { up, down, none }

class FeedbackBar extends StatefulWidget {
  const FeedbackBar({
    super.key,
    required this.message,
    this.isStreaming = false,
    this.showRegenerate = true,
    this.onThumbChanged,
    this.onRegenerate,
  });

  final ChatMessage message;
  final bool isStreaming;
  final bool showRegenerate;
  final ValueChanged<ThumbState>? onThumbChanged;
  final VoidCallback? onRegenerate;

  @override
  State<FeedbackBar> createState() => _FeedbackBarState();
}

class _FeedbackBarState extends State<FeedbackBar> {
  ThumbState _thumb = ThumbState.none;
  bool _copied = false;

  void _onThumb(ThumbState value) {
    HapticFeedback.lightImpact();
    final next = _thumb == value ? ThumbState.none : value;
    setState(() => _thumb = next);
    widget.onThumbChanged?.call(next);
  }

  Future<void> _onCopy() async {
    await Clipboard.setData(ClipboardData(text: widget.message.content));
    HapticFeedback.lightImpact();
    if (!mounted) return;
    setState(() => _copied = true);
    await Future.delayed(const Duration(seconds: 2));
    if (mounted) setState(() => _copied = false);
  }

  void _onRegenerate() {
    if (widget.isStreaming) return;
    HapticFeedback.lightImpact();
    widget.onRegenerate?.call();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Semantics(
      label: 'Message feedback controls',
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Thumbs Up
          _FeedbackButton(
            icon: Icons.thumb_up_outlined,
            activeIcon: Icons.thumb_up,
            isActive: _thumb == ThumbState.up,
            activeColor: colorScheme.primary,
            tooltip: 'Mark as helpful',
            onTap: () => _onThumb(ThumbState.up),
          ),
          SizedBox(width: AppSpacing.xs),

          // Thumbs Down
          _FeedbackButton(
            icon: Icons.thumb_down_outlined,
            activeIcon: Icons.thumb_down,
            isActive: _thumb == ThumbState.down,
            activeColor: colorScheme.error,
            tooltip: 'Mark as unhelpful',
            onTap: () => _onThumb(ThumbState.down),
          ),
          SizedBox(width: AppSpacing.xs),

          // Copy
          Tooltip(
            message: _copied ? 'Copied!' : 'Copy to clipboard',
            child: IconButton(
              icon: Icon(
                _copied ? Icons.check : Icons.copy_outlined,
                color: _copied
                  ? colorScheme.primary
                  : colorScheme.onSurface.withValues(alpha: 0.6),
                size: AppSpacing.iconSm,
              ),
              onPressed: _onCopy,
            ),
          ),

          // Regenerate
          if (widget.showRegenerate) ...[
            SizedBox(width: AppSpacing.xs),
            Tooltip(
              message: 'Regenerate response',
              child: IconButton(
                icon: Icon(
                  Icons.refresh,
                  color: widget.isStreaming
                    ? colorScheme.onSurface.withValues(alpha: 0.3)
                    : colorScheme.onSurface.withValues(alpha: 0.6),
                  size: AppSpacing.iconSm,
                ),
                onPressed: widget.isStreaming ? null : _onRegenerate,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _FeedbackButton extends StatelessWidget {
  const _FeedbackButton({
    required this.icon,
    required this.activeIcon,
    required this.isActive,
    required this.activeColor,
    required this.tooltip,
    required this.onTap,
  });

  final IconData icon;
  final IconData activeIcon;
  final bool isActive;
  final Color activeColor;
  final String tooltip;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Tooltip(
      message: tooltip,
      child: IconButton(
        icon: Icon(
          isActive ? activeIcon : icon,
          color: isActive
            ? activeColor
            : colorScheme.onSurface.withValues(alpha: 0.6),
          size: AppSpacing.iconSm,
        ),
        onPressed: onTap,
      ),
    );
  }
}
```

### Regenerate in ChatNotifier (excerpt)

```dart
// In ChatNotifier
Future<void> regenerate(String assistantMessageId) async {
  final msgs = state.messages;
  final assistantIdx = msgs.indexWhere((m) => m.id == assistantMessageId);
  if (assistantIdx < 1) return;

  // Find nearest preceding user message
  final userMsg = msgs.sublist(0, assistantIdx).reversed
      .firstWhere((m) => m.role == ChatRole.user, orElse: () => throw StateError('No user message found'));

  // Remove old assistant message and re-stream
  state = state.copyWith(
    messages: msgs.where((m) => m.id != assistantMessageId).toList(),
  );
  await send(userMsg.content);
}
```

---

## Design Rules

- **Toggle behavior**: clicking the active thumb again deselects it (state goes to null/none)
- **Copy feedback**: show a checkmark for 2 seconds, then restore the copy icon — no toast needed
- **Regenerate**: disabled (not hidden) while streaming — user can see it but cannot activate it
- **Haptic** (Flutter only): `HapticFeedback.lightImpact()` on thumb press and regenerate tap
- **Active color**: thumbs up = `primary`/`text-success`, thumbs down = `error`/`text-error`
- **Inactive color**: `onSurface` at 60% opacity — low-prominence until interacted
- Feedback event fields: message id, trace id, prompt name + version, model id, vote, optional reason code — never message content, so feedback joins to the exact trace and release
- Thumbs-down / hallucination flags feed a sampled human triage; a verified failure becomes a golden-set case through a reviewed PR (never auto-added) — `deployment-ci-cd/reference/llmops-release-and-rollout.md` §8
- Feedback on an `incomplete` (stopped) answer is recorded but never used as a completed example
