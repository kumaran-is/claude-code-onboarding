# Accessibility Audit Checklist (WCAG 2.2 AA — Flutter)

> Canonical cross-stack checklist: `.claude/skills/accessibility-audit/reference/wcag22-checklist.md`. This file holds the Flutter-specific checks.

## 1. Semantics Widget Usage

- [ ] Interactive elements have semantic labels
- [ ] Images have `Semantics(image: true, label: ...)`
- [ ] Decorative elements use `excludeSemantics: true`
- [ ] Buttons use `Semantics(button: true, ...)`
- [ ] Live regions for dynamic content updates

## 2. Color Contrast (WCAG 2.2 AA)

- [ ] Normal text: minimum 4.5:1 ratio
- [ ] Large text (18pt+): minimum 3:1 ratio
- [ ] UI components: minimum 3:1 ratio
- [ ] Using `ColorScheme` for accessible defaults
- [ ] Not relying on color alone to convey information

## 3. Touch Targets

- [ ] Minimum 48x48 dp tap targets
- [ ] Adequate spacing between interactive elements
- [ ] `IconButton` or padded `GestureDetector` used
- [ ] Both floors asserted: Android 48dp and iOS 44pt (a 44dp control passes iOS, fails Android)
- [ ] If the child owns the semantics node (e.g. `TextField`), the child itself is >= 48 — an outer wrapper does not enlarge the node; verify with `meetsGuideline(androidTapTargetGuideline)`

## 4. Dynamic Text Scaling

- [ ] Uses `MediaQuery.textScalerOf(context)`
- [ ] No fixed heights that clip scaled text
- [ ] Text readable at 200% scale
- [ ] `ConstrainedBox` instead of fixed `SizedBox` for text
- [ ] Label beside a badge/chip sits in a `Wrap`, not `Row(Flexible(label), chip)`, so it never breaks mid-word
- [ ] Status/action labels wrap (`maxLines` >= 2) rather than ellipsize; chip padding grows vertically, not horizontally
- [ ] Sibling tiles whose labels can wrap are equal height (`IntrinsicHeight` + `CrossAxisAlignment.stretch`)
- [ ] Final reflow check on a real font (widget tests render in a different test font — see [flutter-testing-traps.md](flutter-testing-traps.md))

## 5. Focus Management

- [ ] Logical focus order with `FocusTraversalGroup`
- [ ] Focus visible indicators present
- [ ] Programmatic focus management where needed
- [ ] Modal dialogs trap focus appropriately

## 6. Screen Reader Support

- [ ] `SemanticsService.sendAnnouncement(View.of(context), ...)` for important updates (`announce()` is deprecated since 3.35)
- [ ] Form fields have `labelText` in `InputDecoration`
- [ ] Error messages announced to screen readers
- [ ] `MergeSemantics` groups related *non-interactive* elements. Never inside a tappable (`InkWell`, card with `onTap`, `ListTile`): the tappable already merges its descendants, and a nested merge leaves the button without a label
- [ ] Self-merging tiles (`ListTile`, `RadioListTile`, `CheckboxListTile`, `SwitchListTile`) own their accessible name: never wrap one in a labelled `Semantics`; put extra meaning in the title via `Text(label, semanticsLabel: ...)`
- [ ] Upper-cased display text (`toUpperCase()`) passes the original-case string as `semanticsLabel` (screen readers may spell short all-caps runs letter by letter)
- [ ] Section/group headings use `Semantics(header: true, ...)` (including date headers in grouped lists)
- [ ] No double announcement: `SnackBar` is already a live region, so do not also call `SemanticsService.sendAnnouncement` with the same text (verify against the current SDK)
- [ ] Custom list rows put one composed `semanticLabel` on the tappable; decorative glyphs use `ExcludeSemantics`
- [ ] Dump the semantics tree before reaching for `container: true` — it can put the value before its title in reading order

## Output Format

```markdown
## Accessibility Audit Results

### Critical (Blocks users)
- **[A11Y-001]** Missing semantic label on button
  - File: `file_path:line_number`
  - Issue: IconButton without semantic label
  - Fix: Add `Semantics(label: 'Submit login', button: true, child: ...)`

### Important (Degrades experience)
- **[A11Y-002]** Low color contrast
  - File: `file_path:line_number`
  - Ratio: 3.2:1 (required: 4.5:1 for normal text)
  - Fix: Use `colorScheme.onSurface` for text

### Suggestions
- **[A11Y-003]** Consider adding live region
  - File: `file_path:line_number`
  - Recommendation: Add `Semantics(liveRegion: true, ...)` for dynamic updates
```

## Testing Recommendations

- [ ] Test with TalkBack (Android)
- [ ] Test with VoiceOver (iOS)
- [ ] Test at 200% font scale
- [ ] Test with high contrast mode
- [ ] Automated floor in each screen test: the four `meetsGuideline` matchers, contrast in light AND dark — see [flutter-a11y-automated.md](../../accessibility-audit/reference/flutter-a11y-automated.md) §2b
