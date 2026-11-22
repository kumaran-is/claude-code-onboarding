# Multi-Modal Input Patterns

Covers: file/image attachments, preview chips, auto-expanding textarea/field, keyboard shortcuts.

---

## Angular 21.x — ChatInputComponent

```typescript
// features/chat/components/chat-input.component.ts
import {
  Component, ChangeDetectionStrategy, input, output, signal, computed,
  viewChild, ElementRef, inject, effect
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AppLogger } from '../../../core/logging/app-logger.service';

export interface AttachedFile {
  id: string;
  file: File;
  previewUrl: string | null; // non-null for images
}

const ACCEPTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const ACCEPTED_DOC_TYPES = ['application/pdf', 'text/plain'];
const MAX_FILE_SIZE_MB = 20;

@Component({
  selector: 'app-chat-input',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule],
  template: `
    <div class="border-t border-base-300 bg-base-100 p-3 flex flex-col gap-2">

      <!-- File previews -->
      @if (attachments().length > 0) {
        <div class="flex flex-wrap gap-2" role="list" aria-label="Attached files">
          @for (attachment of attachments(); track attachment.id) {
            <div class="chip chip-sm gap-1 bg-base-200 flex items-center" role="listitem">
              @if (attachment.previewUrl) {
                <img [src]="attachment.previewUrl" [alt]="attachment.file.name"
                     class="w-6 h-6 rounded object-cover" />
              } @else {
                <svg class="w-4 h-4 text-base-content opacity-60" fill="none"
                     stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                </svg>
              }
              <span class="text-xs max-w-24 truncate">{{ attachment.file.name }}</span>
              <button class="btn btn-xs btn-ghost btn-circle ml-1"
                      [attr.aria-label]="'Remove ' + attachment.file.name"
                      (click)="removeAttachment(attachment.id)">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
              </button>
            </div>
          }
        </div>
      }

      <!-- Drag-drop zone + textarea row -->
      <div class="flex gap-2 items-end"
           (dragover)="onDragOver($event)"
           (dragleave)="onDragLeave($event)"
           (drop)="onDrop($event)"
           [class.ring-2]="isDragging()"
           [class.ring-primary]="isDragging()"
           [class.rounded-lg]="isDragging()">

        <!-- Hidden file input -->
        <input #fileInput type="file"
               class="hidden"
               [accept]="acceptedTypes"
               multiple
               (change)="onFileInputChange($event)"
               aria-hidden="true" />

        <!-- Attach button -->
        <button class="btn btn-sm btn-ghost flex-shrink-0 self-end mb-1"
                aria-label="Attach file"
                [disabled]="isStreaming()"
                (click)="fileInput.click()">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"/>
          </svg>
        </button>

        <!-- Auto-expanding textarea -->
        <textarea #textarea
                  class="textarea textarea-bordered flex-1 resize-none min-h-10 max-h-48 overflow-y-auto"
                  [class.textarea-disabled]="isStreaming()"
                  placeholder="Message..."
                  rows="1"
                  [disabled]="isStreaming()"
                  [(ngModel)]="textValue"
                  (input)="autoResize()"
                  (keydown)="onKeydown($event)"
                  aria-label="Chat message input"
                  aria-multiline="true">
        </textarea>

        <!-- Send / Stop button -->
        @if (isStreaming()) {
          <button class="btn btn-sm btn-error flex-shrink-0 self-end mb-1"
                  aria-label="Stop generation"
                  (click)="stop.emit()">
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="6" y="6" width="12" height="12" rx="1"/>
            </svg>
          </button>
        } @else {
          <button class="btn btn-sm btn-primary flex-shrink-0 self-end mb-1"
                  aria-label="Send message"
                  [disabled]="!canSend()"
                  (click)="onSend()">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
            </svg>
          </button>
        }
      </div>

      <p class="text-xs text-base-content opacity-50 text-center">
        Enter to send &middot; Shift+Enter for new line &middot; Max {{ MAX_FILE_SIZE_MB }}MB per file
      </p>
    </div>
  `
})
export class ChatInputComponent {
  readonly isStreaming = input(false);
  readonly send = output<{ text: string; attachments: AttachedFile[] }>();
  readonly stop = output<void>();

  protected readonly MAX_FILE_SIZE_MB = MAX_FILE_SIZE_MB;
  protected readonly acceptedTypes = [...ACCEPTED_IMAGE_TYPES, ...ACCEPTED_DOC_TYPES].join(',');

  readonly textValue = signal('');
  readonly attachments = signal<AttachedFile[]>([]);
  readonly isDragging = signal(false);

  readonly canSend = computed(() =>
    (this.textValue().trim().length > 0 || this.attachments().length > 0) && !this.isStreaming()
  );

  private readonly textareaRef = viewChild<ElementRef<HTMLTextAreaElement>>('textarea');
  private readonly logger = inject(AppLogger);

  onSend(): void {
    if (!this.canSend()) return;
    this.send.emit({ text: this.textValue().trim(), attachments: this.attachments() });
    this.textValue.set('');
    this.attachments.set([]);
    // Reset textarea height
    const el = this.textareaRef()?.nativeElement;
    if (el) { el.style.height = 'auto'; }
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.onSend();
    }
    // Shift+Enter: browser default adds newline — no intervention needed
  }

  autoResize(): void {
    const el = this.textareaRef()?.nativeElement;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }

  onFileInputChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files) return;
    this.processFiles(Array.from(input.files));
    // Reset so same file can be re-attached
    input.value = '';
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragging.set(true);
  }

  onDragLeave(event: DragEvent): void {
    this.isDragging.set(false);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragging.set(false);
    const files = event.dataTransfer?.files;
    if (files) this.processFiles(Array.from(files));
  }

  removeAttachment(id: string): void {
    this.attachments.update(list => list.filter(a => a.id !== id));
  }

  private processFiles(files: File[]): void {
    for (const file of files) {
      if (!this.validateFile(file)) continue;
      const previewUrl = ACCEPTED_IMAGE_TYPES.includes(file.type)
        ? URL.createObjectURL(file)
        : null;
      this.attachments.update(list => [
        ...list,
        { id: crypto.randomUUID(), file, previewUrl }
      ]);
    }
  }

  private validateFile(file: File): boolean {
    const isAccepted = [...ACCEPTED_IMAGE_TYPES, ...ACCEPTED_DOC_TYPES].includes(file.type);
    const isUnderLimit = file.size <= MAX_FILE_SIZE_MB * 1024 * 1024;

    if (!isAccepted) {
      this.logger.warn('[ChatInputComponent] unsupported file type', { type: file.type, sizeBytes: file.size });
      // Caller shows error toast via event — not swallowed here
      return false;
    }
    if (!isUnderLimit) {
      this.logger.warn('[ChatInputComponent] file exceeds size limit', { type: file.type, sizeMb: (file.size / 1024 / 1024).toFixed(1) });
      return false;
    }
    return true;
  }
}
```

---

## Flutter 3.41.x — ChatInputWidget

```dart
// features/chat/presentation/widgets/chat_input_widget.dart
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'dart:io';
import '../../models/chat_attachment.dart';
import '../../../../core/tokens/app_spacing.dart';

class ChatInputWidget extends StatefulWidget {
  const ChatInputWidget({
    super.key,
    required this.onSend,
    this.onStop,
    this.isStreaming = false,
  });

  final void Function(String text, List<ChatAttachment> attachments) onSend;
  final VoidCallback? onStop;
  final bool isStreaming;

  @override
  State<ChatInputWidget> createState() => _ChatInputWidgetState();
}

class _ChatInputWidgetState extends State<ChatInputWidget> {
  final _controller = TextEditingController();
  final _focusNode = FocusNode();
  final _picker = ImagePicker();
  List<ChatAttachment> _attachments = [];

  bool get _canSend =>
    (_controller.text.trim().isNotEmpty || _attachments.isNotEmpty)
    && !widget.isStreaming;

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _send() {
    if (!_canSend) return;
    HapticFeedback.lightImpact();
    widget.onSend(_controller.text.trim(), List.unmodifiable(_attachments));
    _controller.clear();
    setState(() => _attachments = []);
  }

  Future<void> _pickImage() async {
    try {
      final result = await _picker.pickMultiImage(
        imageQuality: 85,
        maxWidth: 2048,
      );
      if (result.isEmpty) return;
      setState(() {
        _attachments = [
          ..._attachments,
          ...result.map((x) => ChatAttachment.image(
            id: UniqueKey().toString(),
            path: x.path,
            name: x.name,
          )),
        ];
      });
    } catch (err) {
      // Log and surface — never swallow
      debugPrint('[ChatInputWidget] image pick failed: ${err.runtimeType}'); // no paths/names in logs
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not attach image. Please try again.')),
        );
      }
    }
  }

  void _removeAttachment(String id) {
    setState(() => _attachments = _attachments.where((a) => a.id != id).toList());
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Container(
      decoration: BoxDecoration(
        border: Border(
          top: BorderSide(color: colorScheme.outlineVariant),
        ),
        color: colorScheme.surface,
      ),
      padding: EdgeInsets.all(AppSpacing.md),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Attachment previews
          if (_attachments.isNotEmpty)
            SizedBox(
              height: 72,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: _attachments.length,
                separatorBuilder: (_, __) => SizedBox(width: AppSpacing.sm),
                itemBuilder: (context, i) => _AttachmentChip(
                  attachment: _attachments[i],
                  onRemove: () => _removeAttachment(_attachments[i].id),
                ),
              ),
            ),

          if (_attachments.isNotEmpty)
            SizedBox(height: AppSpacing.sm),

          // Input row
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              // Attach button
              IconButton(
                icon: Icon(
                  Icons.attach_file,
                  color: widget.isStreaming
                    ? colorScheme.onSurface.withValues(alpha: 0.3)
                    : colorScheme.onSurface.withValues(alpha: 0.6),
                ),
                tooltip: 'Attach image',
                onPressed: widget.isStreaming ? null : _pickImage,
              ),

              // Auto-expanding TextField
              Expanded(
                child: TextField(
                  controller: _controller,
                  focusNode: _focusNode,
                  maxLines: null,        // auto-expanding
                  keyboardType: TextInputType.multiline,
                  textInputAction: TextInputAction.newline,
                  enabled: !widget.isStreaming,
                  onChanged: (_) => setState(() {}),
                  decoration: InputDecoration(
                    hintText: 'Message...',
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
                    ),
                    contentPadding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.md,
                      vertical: AppSpacing.sm,
                    ),
                  ),
                ),
              ),

              SizedBox(width: AppSpacing.sm),

              // Send / Stop
              widget.isStreaming
                ? IconButton.filled(
                    style: IconButton.styleFrom(
                      backgroundColor: colorScheme.error,
                    ),
                    icon: Icon(Icons.stop, color: colorScheme.onError),
                    tooltip: 'Stop generation',
                    onPressed: widget.onStop,
                  )
                : IconButton.filled(
                    style: IconButton.styleFrom(
                      backgroundColor: _canSend
                        ? colorScheme.primary
                        : colorScheme.onSurface.withValues(alpha: 0.12),
                    ),
                    icon: Icon(
                      Icons.send,
                      color: _canSend
                        ? colorScheme.onPrimary
                        : colorScheme.onSurface.withValues(alpha: 0.38),
                    ),
                    tooltip: 'Send message',
                    onPressed: _canSend ? _send : null,
                  ),
            ],
          ),
        ],
      ),
    );
  }
}

class _AttachmentChip extends StatelessWidget {
  const _AttachmentChip({required this.attachment, required this.onRemove});

  final ChatAttachment attachment;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Stack(
      children: [
        Container(
          width: 64,
          height: 64,
          decoration: BoxDecoration(
            color: colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            image: attachment.isImage
              ? DecorationImage(
                  image: FileImage(File(attachment.path)),
                  fit: BoxFit.cover,
                )
              : null,
          ),
          child: !attachment.isImage
            ? Icon(Icons.insert_drive_file_outlined,
                color: colorScheme.onSurface.withValues(alpha: 0.6))
            : null,
        ),
        Positioned(
          top: 2,
          right: 2,
          child: GestureDetector(
            onTap: onRemove,
            child: Container(
              width: 18,
              height: 18,
              decoration: BoxDecoration(
                color: colorScheme.surface,
                shape: BoxShape.circle,
                border: Border.all(color: colorScheme.outline),
              ),
              child: Icon(Icons.close, size: 12, color: colorScheme.onSurface),
            ),
          ),
        ),
      ],
    );
  }
}
```

### ChatAttachment model

```dart
// features/chat/models/chat_attachment.dart
import 'package:freezed_annotation/freezed_annotation.dart';

part 'chat_attachment.freezed.dart';

@freezed
class ChatAttachment with _$ChatAttachment {
  const factory ChatAttachment.image({
    required String id,
    required String path,
    required String name,
  }) = _ImageAttachment;

  const factory ChatAttachment.document({
    required String id,
    required String path,
    required String name,
  }) = _DocumentAttachment;
}

extension ChatAttachmentX on ChatAttachment {
  bool get isImage => this is _ImageAttachment;
}
```

---

## Design Rules

- **Enter = send, Shift+Enter = newline** (Angular keyboard shortcut — Flutter uses `TextInputAction.newline`)
- **File validation**: client checks MIME type AND size for UX only; log rejections with type/size, never file names or paths; never silently skip
- **Server re-validates (OPTIONAL multimodal path)**: size cap before buffering, magic bytes not the declared MIME, strip EXIF/location, treat text inside images/PDFs as untrusted input (prompt injection); consent + retention TTL for stored uploads
- **Preview chips**: show image thumbnail for images; doc icon for PDFs/text; always show filename + remove button
- **Auto-expand**: textarea/TextField grows up to a max height (`max-h-48` / ~200dp), then scrolls
- **Stop button**: replaces send button while streaming — color `error`/`btn-error`; always visible to allow cancellation
- **Send button disabled** (not hidden) when text is empty and no attachments — lets user see it exists
- **Haptic feedback** (Flutter only): `HapticFeedback.lightImpact()` on send tap; **max file size** 20MB — reject and log; user sees a snackbar / toast
