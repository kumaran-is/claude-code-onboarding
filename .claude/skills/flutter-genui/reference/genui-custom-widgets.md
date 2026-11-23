# GenUI Custom Widgets — Triage Example

## Overview

This example extends the standard GenUI widget catalog with 5 custom widget types designed for a maintenance triage flow. Each custom widget is registered as a `CatalogItem` with a JSON schema (for the AI model) and a Dart builder (for rendering).

## Architecture

```
widget_catalog.dart          # Catalog registration (all CatalogItems)
    |
widget_types.dart            # Custom widget implementations
    |-- TriagePhotoUpload    # Camera + gallery picker
    |-- TriageDropdown       # Native dropdown selector
    |-- TriageFreeText       # Text input field
    |-- TriageRating         # Star rating widget
    |-- TriageConfirmation   # Yes/No buttons
```

## Widget Implementations

### 1. PhotoUpload

Camera + gallery picker for issue photos.

```dart
// CatalogItem registration
CatalogItem photoUploadItem() => CatalogItem(
  name: 'photo_upload',
  description: 'Camera and gallery picker for capturing photos of maintenance issues. '
      'Use when visual evidence would help diagnose the problem.',
  schema: JsonSchema.object({
    'label': JsonSchema.string(description: 'Prompt text, e.g. "Take a photo of the leak"'),
    'maxPhotos': JsonSchema.number(description: 'Maximum photos allowed (default: 3)'),
    'required': JsonSchema.boolean(description: 'Whether at least one photo is required'),
  }, required: ['label']),
  builder: (context, properties) => TriagePhotoUpload(
    label: properties['label'] as String? ?? 'Upload a photo',
    maxPhotos: (properties['maxPhotos'] as num?)?.toInt() ?? 3,
    required: properties['required'] as bool? ?? false,
    onPhotosSelected: (photos) {
      // Photos are handled by the triage flow, not sent to the model directly
    },
  ),
);

// Widget implementation
class TriagePhotoUpload extends StatefulWidget {
  final String label;
  final int maxPhotos;
  final bool required;
  final ValueChanged<List<XFile>> onPhotosSelected;

  const TriagePhotoUpload({
    required this.label,
    required this.maxPhotos,
    required this.required,
    required this.onPhotosSelected,
    super.key,
  });

  @override
  State<TriagePhotoUpload> createState() => _TriagePhotoUploadState();
}

class _TriagePhotoUploadState extends State<TriagePhotoUpload> {
  final List<XFile> _photos = [];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          widget.label,
          style: theme.textTheme.bodyLarge,
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            ..._photos.map((photo) => _PhotoThumbnail(
              file: photo,
              onRemove: () => _removePhoto(photo),
            )),
            if (_photos.length < widget.maxPhotos)
              _AddPhotoButton(onTap: _pickPhoto),
          ],
        ),
        if (widget.required && _photos.isEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              'At least one photo is required',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.error,
              ),
            ),
          ),
      ],
    );
  }

  Future<void> _pickPhoto() async {
    // Use image_picker — standard Flutter pattern
    final picker = ImagePicker();
    final image = await picker.pickImage(
      source: ImageSource.camera,
      maxWidth: 1920,
      maxHeight: 1080,
      imageQuality: 85,
    );
    if (image != null && mounted) {
      setState(() => _photos.add(image));
      widget.onPhotosSelected(_photos);
    }
  }

  void _removePhoto(XFile photo) {
    setState(() => _photos.remove(photo));
    widget.onPhotosSelected(_photos);
  }
}
```

### 2. Dropdown

Native dropdown for multiple-choice questions.

```dart
CatalogItem dropdownItem() => CatalogItem(
  name: 'dropdown',
  description: 'A dropdown selector for multiple-choice questions. '
      'Use when presenting 2-6 options for the user to choose one.',
  schema: JsonSchema.object({
    'label': JsonSchema.string(description: 'Question text above the dropdown'),
    'options': JsonSchema.array(
      items: JsonSchema.string(),
      description: 'List of selectable options',
    ),
    'required': JsonSchema.boolean(description: 'Whether selection is mandatory'),
    'placeholder': JsonSchema.string(description: 'Hint text when nothing selected'),
  }, required: ['label', 'options']),
  builder: (context, properties) {
    final options = (properties['options'] as List?)?.cast<String>() ?? [];
    if (options.isEmpty) {
      return const Text('No options available');
    }
    return TriageDropdown(
      label: properties['label'] as String? ?? 'Select an option',
      options: options.take(20).toList(), // Cap at 20
      required: properties['required'] as bool? ?? false,
      placeholder: properties['placeholder'] as String?,
    );
  },
);

class TriageDropdown extends StatefulWidget {
  final String label;
  final List<String> options;
  final bool required;
  final String? placeholder;

  const TriageDropdown({
    required this.label,
    required this.options,
    this.required = false,
    this.placeholder,
    super.key,
  });

  @override
  State<TriageDropdown> createState() => _TriageDropdownState();
}

class _TriageDropdownState extends State<TriageDropdown> {
  String? _selected;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(widget.label, style: theme.textTheme.bodyLarge),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(
          value: _selected,
          hint: Text(widget.placeholder ?? 'Choose...'),
          decoration: InputDecoration(
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
            ),
            contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
          ),
          items: widget.options.map((opt) => DropdownMenuItem(
            value: opt,
            child: Text(opt),
          )).toList(),
          onChanged: (value) => setState(() => _selected = value),
          validator: widget.required
              ? (value) => value == null ? 'Please select an option' : null
              : null,
        ),
      ],
    );
  }
}
```

### 3. FreeText

Text input for open-ended responses.

```dart
CatalogItem freeTextItem() => CatalogItem(
  name: 'free_text',
  description: 'A text input field for open-ended responses. '
      'Use for descriptions, details, or any free-form answer.',
  schema: JsonSchema.object({
    'label': JsonSchema.string(description: 'Question text above the field'),
    'hint': JsonSchema.string(description: 'Placeholder text inside the field'),
    'maxLength': JsonSchema.number(description: 'Character limit (default: 500)'),
    'multiline': JsonSchema.boolean(description: 'Multi-line input (default: false)'),
  }, required: ['label']),
  builder: (context, properties) => TriageFreeText(
    label: properties['label'] as String? ?? 'Enter details',
    hint: properties['hint'] as String?,
    maxLength: (properties['maxLength'] as num?)?.toInt() ?? 500,
    multiline: properties['multiline'] as bool? ?? false,
  ),
);
```

### 4. Rating

Star rating for urgency/severity assessment.

```dart
CatalogItem ratingItem() => CatalogItem(
  name: 'rating',
  description: 'A star rating widget for severity or urgency assessment. '
      'Use when asking the user to rate something on a 1-5 scale.',
  schema: JsonSchema.object({
    'label': JsonSchema.string(description: 'Question text, e.g. "How urgent is this?"'),
    'maxStars': JsonSchema.number(description: 'Number of stars (default: 5)'),
    'required': JsonSchema.boolean(description: 'Whether rating is mandatory'),
  }, required: ['label']),
  builder: (context, properties) => TriageRating(
    label: properties['label'] as String? ?? 'Rate severity',
    maxStars: (properties['maxStars'] as num?)?.toInt() ?? 5,
    required: properties['required'] as bool? ?? false,
  ),
);
```

### 5. Confirmation

Yes/No buttons for binary questions.

```dart
CatalogItem confirmationItem() => CatalogItem(
  name: 'confirmation',
  description: 'Yes/No buttons for binary follow-up questions. '
      'Use when the answer is one of two options.',
  schema: JsonSchema.object({
    'label': JsonSchema.string(description: 'The yes/no question text'),
    'yesText': JsonSchema.string(description: 'Label for yes button (default: "Yes")'),
    'noText': JsonSchema.string(description: 'Label for no button (default: "No")'),
  }, required: ['label']),
  builder: (context, properties) => TriageConfirmation(
    label: properties['label'] as String? ?? 'Confirm',
    yesText: properties['yesText'] as String? ?? 'Yes',
    noText: properties['noText'] as String? ?? 'No',
  ),
);
```

## Connecting Widgets to the Conversation Loop

When a user interacts with a triage widget (selects a dropdown option, submits text, etc.), the response must be sent back to the Conversation:

```dart
/// Wrapper that connects custom triage widgets to the Conversation.
class TriageWidgetWrapper extends StatelessWidget {
  final Widget child;
  final String widgetId;
  final TriageConversationManager conversation;

  const TriageWidgetWrapper({
    required this.child,
    required this.widgetId,
    required this.conversation,
    super.key,
  });

  void _onUserResponse(String actionName, Map<String, dynamic> context) {
    conversation.sendAction(UserAction(
      name: actionName,
      surfaceId: 'triage',
      sourceComponentId: widgetId,
      timestamp: DateTime.now().toIso8601String(),
      context: context,
    ));
  }
}
```

## Testing Custom Widgets

```dart
void main() {
  group('TriageDropdown', () {
    testWidgets('renders all options', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: TriageDropdown(
            label: 'Severity',
            options: ['low', 'medium', 'high'],
          ),
        ),
      ));
      expect(find.text('Severity'), findsOneWidget);
      // Open dropdown
      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      expect(find.text('low'), findsOneWidget);
      expect(find.text('medium'), findsOneWidget);
      expect(find.text('high'), findsOneWidget);
    });

    testWidgets('handles empty options gracefully', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: TriageDropdown(
            label: 'Severity',
            options: [],
          ),
        ),
      ));
      // Should show fallback, not crash
      expect(find.text('No options available'), findsOneWidget);
    });
  });
}
```

---

## Standard A2UI v0.8 Catalog Widgets (Extended Set)

These map the A2UI standard catalog to Flutter widgets. Register them in `widget_catalog.dart` alongside custom widgets.

### `slider` — Numeric Range Input

```dart
CatalogItem(
  type: 'slider',
  schema: JsonSchema.object({
    'label': JsonSchema.string(description: 'Display label above slider'),
    'value': JsonSchema.object({}), // path or literalString for initial value
    'min': JsonSchema.number(description: 'Minimum value'),
    'max': JsonSchema.number(description: 'Maximum value'),
    'step': JsonSchema.number(description: 'Step increment (optional)'),
  }, required: ['label', 'min', 'max']),
  builder: (properties, conversation, dataModel) {
    final min = (properties['min'] as num? ?? 0).toDouble();
    final max = (properties['max'] as num? ?? 100).toDouble();
    final initial = (properties['value']?['literalString'] as num? ?? min).toDouble();
    return _SliderWidget(
      label: properties['label']?.toString() ?? '',
      min: min,
      max: max,
      initialValue: initial,
      divisions: properties['step'] != null
          ? ((max - min) / (properties['step'] as num)).round()
          : null,
      onChanged: (v) => conversation.updateDataModel(
        (properties['value']?['path'] as String? ?? '/slider'), v,
      ),
    );
  },
),
```

**Accessibility:** Use `Semantics(slider: true, value: '${value.round()}', label: label)`.

### `audio_player` — Audio Playback

```dart
CatalogItem(
  type: 'audio_player',
  schema: JsonSchema.object({
    'src': JsonSchema.object({}), // URL — validated before use
    'label': JsonSchema.string(description: 'Accessible label for the player'),
  }, required: ['src']),
  builder: (properties, conversation, dataModel) {
    final rawUrl = properties['src']?['literalString']?.toString() ?? '';
    // Validate: only allow https:// URLs
    if (!rawUrl.startsWith('https://')) {
      debugPrint('GenUI: audio_player src blocked — non-https URL rejected');
      return const SizedBox.shrink();
    }
    return _AudioPlayerWidget(url: rawUrl, label: properties['label']?.toString());
  },
),
```

**Security:** Always validate `src` URL — reject non-https. Use `just_audio` or `audioplayers` package.

### `video` — Video Playback

```dart
CatalogItem(
  type: 'video',
  schema: JsonSchema.object({
    'src': JsonSchema.object({}), // URL — validated before use
    'label': JsonSchema.string(description: 'Accessible label / alt text'),
    'autoPlay': JsonSchema.boolean(description: 'Auto-start playback (default false)'),
  }, required: ['src']),
  builder: (properties, conversation, dataModel) {
    final rawUrl = properties['src']?['literalString']?.toString() ?? '';
    if (!rawUrl.startsWith('https://')) {
      debugPrint('GenUI: video src blocked — non-https URL rejected');
      return const SizedBox.shrink();
    }
    return _VideoPlayerWidget(
      url: rawUrl,
      label: properties['label']?.toString(),
      autoPlay: properties['autoPlay'] as bool? ?? false,
    );
  },
),
```

**Security:** Validate URL before initializing the video controller. Use `video_player` package. Never auto-play audio on first render without user consent (accessibility + UX).

---

## Updated Catalog Registry

Add to `widget_catalog.dart` alongside triage widgets:

```dart
// Standard A2UI extended widgets
_buildSliderCatalogItem(),
_buildAudioPlayerCatalogItem(),
_buildVideoCatalogItem(),

// custom triage widgets
_buildPhotoUploadCatalogItem(),
_buildDropdownCatalogItem(),
_buildFreeTextCatalogItem(),
_buildRatingCatalogItem(),
_buildConfirmationCatalogItem(),
```

---

## Accessibility Requirements

All triage widgets must meet WCAG 2.2 AA:

- Touch targets >= 48dp
- All form fields have associated labels (Semantics)
- Dropdown uses `DropdownButtonFormField` (not `DropdownButton`) for form semantics
- Photo upload has screen reader descriptions for all states
- Rating widget uses `Semantics(label: 'Rate $i of ${widget.maxStars}')`
- Confirmation buttons use semantic labels for their purpose
