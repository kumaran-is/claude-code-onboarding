# Streaming UX Patterns

Covers: streaming message rendering, auto-scroll heuristics, stop generation, accessibility.

> Illustrative (not compiled). `incomplete` is a field you add to the message model. Server contract (stop cancels the upstream model call; exactly one terminal `done`/`error` frame; the server stores the answer as `incomplete`): `streaming-protocols` §6a.

---

## Angular 21.x

### StreamingMessageComponent

```typescript
// features/chat/components/streaming-message.component.ts
import { Component, ChangeDetectionStrategy, input, computed, inject } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { MarkdownService } from '../services/markdown.service';
import { ChatMessage } from '../models/chat-message.model';

@Component({
  selector: 'app-streaming-message',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="chat" [class.chat-start]="message().role === 'assistant'"
                      [class.chat-end]="message().role === 'user'">
      <div class="chat-bubble"
           [class.chat-bubble-primary]="message().role === 'user'"
           [attr.aria-label]="message().role + ' message'">
        @if (message().isStreaming) {
          <span [innerHTML]="renderedContent()"></span>
          <span class="loading loading-dots loading-xs ml-1" aria-hidden="true"></span>
        } @else {
          <span [innerHTML]="renderedContent()"></span>
        }
      </div>
    </div>
  `
})
export class StreamingMessageComponent {
  readonly message = input.required<ChatMessage>();

  private readonly sanitizer = inject(DomSanitizer);
  private readonly markdownService = inject(MarkdownService);

  // Memoized: only re-parses when message text actually changes
  readonly renderedContent = computed<SafeHtml>(() => {
    const html = this.markdownService.render(this.message().content);
    return this.sanitizer.bypassSecurityTrustHtml(html);
  });
}
```

### MarkdownService (memoized, no re-parse per chunk)

```typescript
// features/chat/services/markdown.service.ts
import { Injectable, ErrorHandler, inject } from '@angular/core';
import { marked } from 'marked';

@Injectable({ providedIn: 'root' })
export class MarkdownService {
  private readonly errorHandler = inject(ErrorHandler);

  // Cache last rendered result — computed() handles change detection
  render(markdown: string): string {
    try {
      return marked.parse(markdown, { async: false }) as string;
    } catch (err) {
      // Log via Angular ErrorHandler — never swallow; return safe fallback
      this.errorHandler.handleError(err);
      return this.escapeHtml(markdown);
    }
  }

  private escapeHtml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
}
```

### Auto-Scroll Service (smart heuristic — 100px threshold)

```typescript
// features/chat/services/auto-scroll.service.ts
import { Injectable, NgZone, inject } from '@angular/core';

const SCROLL_THRESHOLD_PX = 100;

@Injectable()
export class AutoScrollService {
  private readonly ngZone = inject(NgZone);
  private container: HTMLElement | null = null;
  private userScrolledUp = false;

  attach(container: HTMLElement): void {
    this.container = container;
    // Detect user scrolling away from bottom
    container.addEventListener('scroll', () => {
      const distanceFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      this.userScrolledUp = distanceFromBottom > SCROLL_THRESHOLD_PX;
    }, { passive: true });
  }

  scrollToBottom(): void {
    if (!this.container || this.userScrolledUp) return;
    // Run outside Angular zone — pure DOM, no CD needed
    this.ngZone.runOutsideAngular(() => {
      this.container!.scrollTo({ top: this.container!.scrollHeight, behavior: 'smooth' });
    });
  }

  // Call when new message is sent — always scroll to bottom on user action
  forceScrollToBottom(): void {
    this.userScrolledUp = false;
    this.scrollToBottom();
  }
}
```

### ChatComponent — wiring streaming + auto-scroll + stop

```typescript
// features/chat/chat.component.ts
import {
  Component, ChangeDetectionStrategy, signal, computed,
  viewChild, ElementRef, afterNextRender, inject, OnDestroy, ErrorHandler
} from '@angular/core';
import { AutoScrollService } from './services/auto-scroll.service';
import { ChatService } from './services/chat.service';
import { StreamingMessageComponent } from './components/streaming-message.component';
import { ChatInputComponent } from './components/chat-input.component';
import { TokenIndicatorComponent } from './components/token-indicator.component';
import { ChatMessage } from './models/chat-message.model';

@Component({
  selector: 'app-chat',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [AutoScrollService],
  imports: [StreamingMessageComponent, ChatInputComponent, TokenIndicatorComponent],
  template: `
    <div class="flex flex-col h-full overflow-hidden">
      <app-token-indicator [usage]="tokenUsage()" />

      <!-- ARIA live region — screen readers announce new assistant messages -->
      <div #scrollContainer
           class="flex-1 overflow-y-auto p-4 space-y-2"
           role="log"
           aria-live="polite"
           aria-label="Conversation history"
           aria-relevant="additions">
        @for (msg of messages(); track msg.id) {
          <app-streaming-message [message]="msg" />
        }
      </div>

      <app-chat-input
        [streaming]="isStreaming()"
        (send)="onSend($event)"
        (stop)="onStop()" />
    </div>
  `
})
export class ChatComponent implements OnDestroy {
  private readonly chatService = inject(ChatService);
  private readonly scrollService = inject(AutoScrollService);
  private readonly errorHandler = inject(ErrorHandler);
  private readonly scrollContainerRef = viewChild<ElementRef<HTMLElement>>('scrollContainer');
  private abortController: AbortController | null = null;

  readonly messages = signal<ChatMessage[]>([]);
  readonly isStreaming = signal(false);
  readonly tokenUsage = computed(() => this.chatService.currentTokenUsage());

  constructor() {
    afterNextRender(() => {
      const el = this.scrollContainerRef()?.nativeElement;
      if (el) this.scrollService.attach(el);
    });
  }

  async onSend(text: string): Promise<void> {
    this.abortController = new AbortController();
    this.isStreaming.set(true);
    this.scrollService.forceScrollToBottom();

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: text, isStreaming: false };
    this.messages.update(msgs => [...msgs, userMsg]);

    const assistantMsg: ChatMessage = { id: crypto.randomUUID(), role: 'assistant', content: '', isStreaming: true };
    this.messages.update(msgs => [...msgs, assistantMsg]);

    try {
      for await (const chunk of this.chatService.stream(text, this.abortController.signal)) {
        this.messages.update(msgs =>
          msgs.map(m => m.id === assistantMsg.id ? { ...m, content: m.content + chunk } : m)
        );
        this.scrollService.scrollToBottom();
      }
      this.messages.update(msgs =>
        msgs.map(m => m.id === assistantMsg.id ? { ...m, isStreaming: false } : m)
      );
    } catch (err: unknown) {
      if ((err as Error).name === 'AbortError') {
        // Stopped by the user: keep the text, mark it incomplete. Never parse, persist
        // or act on partial structured output (tool args, JSON, citations).
        this.messages.update(msgs =>
          msgs.map(m => m.id === assistantMsg.id ? { ...m, isStreaming: false, incomplete: true } : m)
        );
      } else {
        // Non-abort errors: update error state + log via Angular ErrorHandler
        this.messages.update(msgs =>
          msgs.map(m => m.id === assistantMsg.id
            ? { ...m, isStreaming: false, error: 'stream_failed' }
            : m)
        );
        this.errorHandler.handleError(err);
      }
    } finally {
      this.isStreaming.set(false);
      this.abortController = null;
    }
  }

  onStop(): void {
    this.abortController?.abort();
  }

  ngOnDestroy(): void {
    this.abortController?.abort();
  }
}
```

---

## Flutter 3.41.x (Riverpod)

### ChatNotifier — AsyncNotifier with stream

```dart
// features/chat/presentation/providers/chat_notifier.dart
import 'package:riverpod_annotation/riverpod_annotation.dart';
import '../../data/repositories/chat_repository.dart';
import '../models/chat_state.dart';
import '../models/chat_message.dart';

part 'chat_notifier.g.dart';

@riverpod
class ChatNotifier extends _$ChatNotifier {
  @override
  ChatState build() => const ChatState.initial();

  Future<void> send(String text) async {
    final userMsg = ChatMessage.user(text);
    final assistantMsg = ChatMessage.assistant('', isStreaming: true);

    state = state.copyWith(
      messages: [...state.messages, userMsg, assistantMsg],
      isStreaming: true,
    );

    _scrollToBottom(); // trigger scroll after frame

    try {
      final stream = ref.read(chatRepositoryProvider).stream(
        messages: state.messages,
      );

      await for (final chunk in stream) {
        state = state.copyWith(
          messages: state.messages.map((m) =>
            m.id == assistantMsg.id
              ? m.copyWith(content: m.content + chunk)
              : m
          ).toList(),
        );
        _scrollToBottom();
      }

      state = state.copyWith(
        messages: state.messages.map((m) =>
          m.id == assistantMsg.id ? m.copyWith(isStreaming: false) : m
        ).toList(),
        isStreaming: false,
      );
    } catch (err, stack) {
      // Log, update error state — never swallow
      ref.read(appLoggerProvider).error('ChatNotifier.send failed', err, stack);
      state = state.copyWith(
        messages: state.messages.map((m) =>
          m.id == assistantMsg.id
            ? m.copyWith(isStreaming: false, errorType: AiErrorType.streamFailed)
            : m
        ).toList(),
        isStreaming: false,
      );
    }
  }

  void stop() {
    ref.read(chatRepositoryProvider).cancelStream();
    // Keep the partial text, flagged incomplete; never act on partial structured output.
    state = state.copyWith(
      messages: state.messages.map((m) => m.isStreaming ? m.copyWith(isStreaming: false, incomplete: true) : m).toList(),
      isStreaming: false,
    );
  }

  void _scrollToBottom() {
    // Notify scroll controller widget via a scroll notifier provider
    ref.read(scrollNotifierProvider.notifier).requestScroll();
  }
}
```

### StreamedMessageWidget

```dart
// features/chat/presentation/widgets/streamed_message_widget.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../../models/chat_message.dart';
import '../../../../core/tokens/app_spacing.dart';

class StreamedMessageWidget extends ConsumerWidget {
  const StreamedMessageWidget({super.key, required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isUser = message.role == ChatRole.user;
    final colorScheme = Theme.of(context).colorScheme;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.78,
        ),
        margin: EdgeInsets.symmetric(
          vertical: AppSpacing.xs,
          horizontal: AppSpacing.md,
        ),
        padding: EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: isUser
            ? colorScheme.primaryContainer
            : colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // flutter_markdown handles memoization internally via StringBuffer
            MarkdownBody(
              data: message.content,
              selectable: true,
            ),
            if (message.isStreaming) ...[
              SizedBox(height: AppSpacing.xs),
              SizedBox(
                width: AppSpacing.lg,
                height: AppSpacing.sm,
                child: LinearProgressIndicator(
                  color: colorScheme.primary,
                  backgroundColor: colorScheme.surfaceVariant,
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

### Auto-Scroll with reduced-motion check

```dart
// features/chat/presentation/widgets/chat_message_list.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/scroll_notifier_provider.dart';
import 'streamed_message_widget.dart';
import '../../models/chat_message.dart';

class ChatMessageList extends ConsumerStatefulWidget {
  const ChatMessageList({super.key, required this.messages});
  final List<ChatMessage> messages;

  @override
  ConsumerState<ChatMessageList> createState() => _ChatMessageListState();
}

class _ChatMessageListState extends ConsumerState<ChatMessageList> {
  final _scrollController = ScrollController();
  bool _userScrolledUp = false;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);

    // Listen to scroll requests from ChatNotifier
    ref.listenManual(scrollNotifierProvider, (_, __) => _maybeScrollToBottom());
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final distanceFromBottom = _scrollController.position.maxScrollExtent
        - _scrollController.offset;
    _userScrolledUp = distanceFromBottom > 100;
  }

  void _maybeScrollToBottom() {
    if (_userScrolledUp || !_scrollController.hasClients) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final disableAnimations =
          MediaQuery.of(context).disableAnimations;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: disableAnimations
          ? Duration.zero
          : const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Conversation history',
      liveRegion: true,
      child: ListView.builder(
        controller: _scrollController,
        itemCount: widget.messages.length,
        itemBuilder: (context, index) =>
          StreamedMessageWidget(message: widget.messages[index]),
      ),
    );
  }
}
```
