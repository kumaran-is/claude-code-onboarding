# AI Chat Quick Start

Minimal wiring for Angular 22.x and Flutter 3.50.x. Load this when starting a new chat feature from scratch.

---

## Angular 22

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// features/chat/chat.component.ts — entry point
@Component({
  selector: 'app-chat',
  imports: [StreamingMessageComponent, ChatInputComponent, TokenIndicatorComponent],
  template: `
    <div class="flex flex-col h-full">
      <app-token-indicator [usage]="tokenUsage()" />
      <div #scrollContainer class="flex-1 overflow-y-auto p-4 space-y-2"
           role="log" aria-live="polite" aria-label="Conversation">
        @for (msg of messages(); track msg.id) {
          <app-streaming-message [message]="msg" />
        }
      </div>
      <app-chat-input (send)="onSend($event)" (stop)="onStop()" [streaming]="isStreaming()" />
    </div>
  `
})
export class ChatComponent { ... }
```

Full implementation with `AbortController`, `AutoScrollService`, and `ErrorHandler` → `reference/streaming-patterns.md`

---

## Flutter 3.50.x

```dart
// features/chat/presentation/screens/chat_screen.dart — entry point
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../providers/chat_notifier.dart';
import '../widgets/chat_input_widget.dart';
import '../widgets/chat_message_list.dart';
import '../widgets/token_indicator_widget.dart';

class ChatScreen extends ConsumerWidget {
  const ChatScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(
      chatProvider,
    ); // generated from `class ChatNotifier`
    final chat = ref.read(chatProvider.notifier);
    return Column(
      children: [
        TokenIndicatorWidget(
          usage: state.tokenUsage,
          onSummarize: chat.summarize,
        ),
        Expanded(child: ChatMessageList(messages: state.messages)),
        ChatInputWidget(
          // Attachments go to your repository's multimodal upload; text-only send shown here.
          onSend: (text, attachments) => chat.send(text),
          onStop: chat.stop,
          isStreaming: state.isStreaming,
        ),
      ],
    );
  }
}
```

Full implementation with `AsyncNotifier`, `ScrollController`, and reduced-motion check → `reference/streaming-patterns.md`
