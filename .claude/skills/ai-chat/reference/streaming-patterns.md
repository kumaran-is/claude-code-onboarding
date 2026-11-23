# Streaming UX Patterns

Covers: streaming message rendering, auto-scroll heuristics, stop generation, accessibility.

> `StreamingMessageComponent` and `MarkdownService` below are compiled and browser-tested (see the security section). The other snippets are illustrative (not compiled). `incomplete` and `error` are optional fields of the `ChatMessage` model below. Server contract (stop cancels the upstream model call; exactly one terminal `done`/`error` frame; the server stores the answer as `incomplete`): `streaming-protocols` §6a.

---

## Angular 22.x

### Rendering model output safely (security, read first)

Model text is untrusted: a prompt-injected document, tool result or user message can make the model emit HTML. `marked` does **not** sanitize (raw HTML, `on*` handlers and `javascript:` links pass through), so:

- **Never** pass rendered model or user markdown to `bypassSecurityTrustHtml` (or any `bypassSecurityTrust*`), `ElementRef.nativeElement.innerHTML =`, `Renderer2.setProperty(el, 'innerHTML', …)` or `insertAdjacentHTML`.
- **Simplest safe option:** render the text with interpolation (`{{ message().content }}`) and no markdown.
- **Markdown option (below):** `marked` → `DOMPurify.sanitize` with a strict allowlist → bind the resulting **string** to `[innerHTML]`, so Angular's own sanitizer runs as a second layer.
- Angular's sanitizer alone is not enough for chat: it keeps `<img src>` (a model-chosen image URL can carry chat data to an attacker in its query string) and keeps blocked links as `href="unsafe:javascript:…"`. The DOMPurify policy drops both.
- DOMPurify needs a DOM. With SSR, render chat messages only in the browser (or use a server-side DOM shim) — do not skip sanitizing on the server.

Historical evidence, not re-run on 22.3. Validated 2026-11-22 (Angular 21.2.26; marked 18.2.1, DOMPurify 3.5.0, Playwright 1.58.2, real Chromium): with this code, `<img src=x onerror>`, `[x](javascript:…)`, raw `<a href="javascript:…">`, `<script>` and `<svg onload>` produced no script execution and no `onerror`/`onload`/`javascript:`/`<img>`/`<svg>` in the DOM, while bold, emphasis, lists, fenced code and `https:` links rendered. Negative control: the previous `bypassSecurityTrustHtml(marked.parse(…))` version ran the `<img onerror>` handler on render and a `javascript:` link on click; the `<svg onload>` attribute survived in the DOM (execution not observed in that run), so it is unsafe either way.

### ChatMessage model

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// features/chat/models/chat-message.model.ts
export type ChatRole = 'user' | 'assistant';

export interface ChatMessage {
  readonly id: string;               // crypto.randomUUID(); stable `track` key
  readonly role: ChatRole;
  readonly content: string;          // raw model/user text; rendered via MarkdownService, never trusted HTML
  readonly isStreaming: boolean;     // true while chunks are still arriving
  readonly incomplete?: boolean;     // the user stopped generation; the server stored a partial answer
  readonly error?: 'stream_failed';  // terminal error frame or transport failure
}
```

### StreamingMessageComponent

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// features/chat/components/streaming-message.component.ts
import { Component, input, computed, inject } from '@angular/core';
import { MarkdownService } from '../services/markdown.service';
import { ChatMessage } from '../models/chat-message.model';

@Component({
  selector: 'app-streaming-message',
  template: `
    <div class="chat" [class.chat-start]="message().role === 'assistant'"
                      [class.chat-end]="message().role === 'user'">
      <div class="chat-bubble"
           [class.chat-bubble-primary]="message().role === 'user'"
           [attr.aria-label]="message().role + ' message'">
        <!-- A string bound to [innerHTML] still passes Angular's built-in sanitizer (second layer). -->
        <div class="chat-markdown" [innerHTML]="renderedContent()"></div>
        @if (message().isStreaming) {
          <span class="loading loading-dots loading-xs ml-1" aria-hidden="true"></span>
        }
      </div>
    </div>
  `,
})
export class StreamingMessageComponent {
  readonly message = input.required<ChatMessage>();

  private readonly markdownService = inject(MarkdownService);

  // Memoized: re-parses only when the message text changes. Type is string, NOT SafeHtml.
  readonly renderedContent = computed(() => this.markdownService.render(this.message().content));
}
```

### MarkdownService (marked → DOMPurify, memoized by the caller's `computed`)

*Not recompiled on Angular 22.3 (pre-22 snippet; `@Service()` conversions are mechanical).*

```typescript
// features/chat/services/markdown.service.ts
import { Service, ErrorHandler, inject } from '@angular/core';
import { marked } from 'marked';
import DOMPurify, { type Config } from 'dompurify';

// Model output is untrusted (prompt injection can make the model emit any HTML).
// marked does NOT sanitize: raw HTML, on* handlers and javascript: links pass through.
const CHAT_HTML_POLICY: Config = {
  ALLOWED_TAGS: [
    'p', 'br', 'strong', 'em', 'del', 'code', 'pre', 'blockquote', 'hr',
    'ul', 'ol', 'li', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
  ], // no img: a model-chosen image URL can exfiltrate chat data in its query string
  ALLOWED_ATTR: ['href', 'title'],
  ALLOWED_URI_REGEXP: /^(?:https:|mailto:)/i, // drops javascript:, data:, http: and relative hrefs
};

@Service()
export class MarkdownService {
  private readonly errorHandler = inject(ErrorHandler);

  /** Returns sanitized HTML as a plain string: bind it with [innerHTML], never bypassSecurityTrustHtml. */
  render(markdown: string): string {
    try {
      const html = marked.parse(markdown, { async: false, gfm: true });
      return DOMPurify.sanitize(html, CHAT_HTML_POLICY);
    } catch (err) {
      this.errorHandler.handleError(err); // logged, then degrade to escaped text
      return this.escapeHtml(markdown);
    }
  }

  private escapeHtml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
}
```

Dependencies: `npm install -E marked@18.2.1 dompurify@3.5.0` (DOMPurify 3.x ships its own types). Re-check the versions with `npm view marked version` / `npm view dompurify version` before pinning.

Test it the same way: a Playwright spec that renders a fixed payload message and asserts `innerHTML` contains no `onerror|onload|javascript:|<script|<svg|<img` and that no `window` flag set by a payload exists after activating every non-`https:` link. Keep a negative-control case (a component using the bypass) so the test is proven able to fail.

### Auto-Scroll Service (smart heuristic — 100px threshold)

*Not recompiled on Angular 22.3 (pre-22 snippet).*

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

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// features/chat/chat.component.ts
import {
  Component, signal, computed,
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

## Flutter 3.50.x (Riverpod)

Pins: `flutter_riverpod` 3.5.0, `riverpod_annotation` 4.0.8 / `riverpod_generator` 4.0.10, `freezed` 4.0.3 / `freezed_annotation` 3.1.0, `flutter_markdown_plus` 1.0.12, `image_picker` 1.2.4, `material_ui` 1.11.1. `ChatState`, `ChatMessage`, `ChatRepository`, `appLoggerProvider`, `scrollNotifierProvider` (a `NotifierProvider<ScrollNotifier, int>` whose `requestScroll()` bumps the state) and `AppSpacing` are app-owned; the Flutter snippets in this skill were compiled and widget-tested on Flutter 3.50.1 against minimal versions of them.

### ChatNotifier — AsyncNotifier with stream

```dart
// features/chat/presentation/providers/chat_notifier.dart
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/logging/app_logger.dart';
import '../../data/repositories/chat_repository.dart';
import '../../models/ai_error.dart';
import '../../models/chat_message.dart';
import '../../models/chat_state.dart';
import '../../models/token_usage.dart';
import 'scroll_notifier_provider.dart';

part 'chat_notifier.g.dart';

// riverpod_generator 4 drops the `Notifier` suffix: this generates `chatProvider`.
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
      final stream = ref
          .read(chatRepositoryProvider)
          .stream(messages: state.messages);

      await for (final chunk in stream) {
        if (!ref.mounted) return; // provider disposed mid-stream
        state = state.copyWith(
          messages: state.messages
              .map(
                (m) => m.id == assistantMsg.id
                    ? m.copyWith(content: m.content + chunk)
                    : m,
              )
              .toList(),
        );
        _scrollToBottom();
      }

      if (!ref.mounted) return;
      state = state.copyWith(
        messages: state.messages
            .map(
              (m) =>
                  m.id == assistantMsg.id ? m.copyWith(isStreaming: false) : m,
            )
            .toList(),
        isStreaming: false,
      );
    } catch (err, stack) {
      // Log, update error state — never swallow
      ref.read(appLoggerProvider).error('ChatNotifier.send failed', err, stack);
      if (!ref.mounted) return;
      state = state.copyWith(
        messages: state.messages
            .map(
              (m) => m.id == assistantMsg.id
                  ? m.copyWith(
                      isStreaming: false,
                      errorType: AiErrorType.streamFailed,
                    )
                  : m,
            )
            .toList(),
        isStreaming: false,
      );
    }
  }

  void stop() {
    ref.read(chatRepositoryProvider).cancelStream();
    // Keep the partial text, flagged incomplete; never act on partial structured output.
    state = state.copyWith(
      messages: state.messages
          .map(
            (m) => m.isStreaming
                ? m.copyWith(isStreaming: false, incomplete: true)
                : m,
          )
          .toList(),
      isStreaming: false,
    );
  }

  void _scrollToBottom() {
    // Notify scroll controller widget via a scroll notifier provider
    ref.read(scrollNotifierProvider.notifier).requestScroll();
  }


  // summarize(): context-management.md; regenerate(): feedback-loops.md
}
```

### StreamedMessageWidget

```dart
// features/chat/presentation/widgets/streamed_message_widget.dart
// flutter_markdown is discontinued; flutter_markdown_plus (1.0.12) is its named replacement.
// It still imports package:flutter/material.dart, so this is the ONE file that keeps a
// legacy-Material island (material_ui decision): without it MarkdownBody reads the default
// light theme and selectable text has no legacy Material ancestor.
// ignore: deprecated_member_use
import 'package:flutter/material.dart' as legacy;
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

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
          maxWidth: MediaQuery.sizeOf(context).width * 0.78,
        ),
        margin: const EdgeInsets.symmetric(
          vertical: AppSpacing.xs,
          horizontal: AppSpacing.md,
        ),
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: isUser
              ? colorScheme.primaryContainer
              : colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ignore: deprecated_member_use
            MaterialUiCompatibilityBridge(
              child: legacy.Material(
                type: legacy.MaterialType.transparency,
                child: MarkdownBody(data: message.content, selectable: true),
              ),
            ),
            if (message.isStreaming) ...[
              const SizedBox(height: AppSpacing.xs),
              SizedBox(
                width: AppSpacing.lg,
                height: AppSpacing.sm,
                child: LinearProgressIndicator(
                  color: colorScheme.primary,
                  backgroundColor: colorScheme.surfaceContainerHighest,
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
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

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
    ref.listenManual(scrollNotifierProvider, (_, _) => _maybeScrollToBottom());
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final distanceFromBottom =
        _scrollController.position.maxScrollExtent - _scrollController.offset;
    _userScrolledUp = distanceFromBottom > 100;
  }

  void _maybeScrollToBottom() {
    if (_userScrolledUp || !_scrollController.hasClients) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) return;
      final disableAnimations = MediaQuery.disableAnimationsOf(context);
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
