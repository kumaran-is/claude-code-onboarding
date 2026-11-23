# UI Accessibility Patterns

## Semantic Widget
```dart
Semantics(
  label: 'Add new item',
  button: true,
  enabled: true,
  onTapHint: 'Double tap to add',
  child: IconButton(
    onPressed: _addItem,
    icon: Icon(Icons.add),
  ),
)
```

## Reduced Motion
```dart
final reduceMotion = MediaQuery.disableAnimationsOf(context);
AnimatedContainer(
  duration: reduceMotion ? Duration.zero : Duration(milliseconds: 300),
  curve: Curves.easeInOut,
  // ...
)
```

## Touch Target (48x48 dp platform guideline; WCAG 2.5.8 AA floor is 24x24)
```dart
SizedBox(
  width: AppSize.touchTarget,
  height: AppSize.touchTarget,
  child: InkWell(
    onTap: _onTap,
    borderRadius: BorderRadius.circular(AppRadius.full),
    child: Icon(Icons.close),
  ),
)
```

## Color Contrast

- Text on background: minimum 4.5:1 ratio (WCAG AA)
- Large text (18sp+): minimum 3:1 ratio
- Interactive elements: minimum 3:1 ratio against adjacent colors
- Never rely on color alone to convey information

## Focus Management

```dart
// Ensure focus order is logical
FocusTraversalGroup(
  policy: OrderedTraversalPolicy(),
  child: Column(
    children: [
      FocusTraversalOrder(
        order: NumericFocusOrder(1),
        child: TextField(decoration: InputDecoration(labelText: 'Name')),
      ),
      FocusTraversalOrder(
        order: NumericFocusOrder(2),
        child: TextField(decoration: InputDecoration(labelText: 'Email')),
      ),
    ],
  ),
)
```

## Screen Reader Announcements

```dart
// Announce dynamic changes
SemanticsService.announce('Item deleted', TextDirection.ltr);

// Exclude decorative elements
ExcludeSemantics(
  child: Icon(Icons.decorative_icon),
)
```
