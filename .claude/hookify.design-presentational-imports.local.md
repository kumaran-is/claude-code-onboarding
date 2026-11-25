---
name: design-presentational-imports
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: ^(?!.*(?:_test\.dart|\.g\.dart|\.freezed\.dart|\.(?:spec|test|stories)\.tsx?)$)(?!.*/(?:tokens|theme|themes)/)(?!.*/[^/]*(?:provider|context)[^/]*\.tsx$)(?:.*/packages/(?:shared_ui|ui|[a-z0-9_]+_ui)/lib/.+\.dart|.*/lib/design_system/components/.+\.dart|.*(?:^|/)src/app/(?:.*/)?shared/components/.+\.ts|.*(?:^|/)src/shared/ui/.+\.tsx)$
  - field: content
    operator: regex_match
    pattern: (?m)(?:\A|^(?![^\n]*ignore-design:\s*\S)[^\n]*\n)(?![^\n]*ignore-design:\s*\S)[^\n]*(?:import\s+['"]package:(?:flutter_riverpod|hooks_riverpod|riverpod|riverpod_annotation|dio|http|cloud_firestore|firebase_[a-z_]+|go_router|drift|shared_preferences|flutter_secure_storage|flutter_bloc|bloc|provider|get_it)/|import\s+['"][^'"\n]*/(?:features|data|repositories|providers|services)/|extends\s+(?:Hook)?Consumer(?:Stateful)?Widget\b|\bref\.(?:watch|read|listen)\(|from\s+['"]@angular/common/http['"]|\bhttpResource\b|from\s+['"]@ngrx/|\binject(?:<[^>\n]*>)?\(\s*(?!(?:ElementRef|DestroyRef|Renderer2|ChangeDetectorRef|Injector|NgZone|ViewContainerRef|TemplateRef|DOCUMENT|PLATFORM_ID|LOCALE_ID|DomSanitizer|NgControl|ControlContainer|FocusMonitor|LiveAnnouncer|Directionality|Overlay|DialogRef|BrnDialogRef)\b)[A-Za-z_]|(?:constructor\s*\(|,\s*)(?:private|public|protected)\s+(?:readonly\s+)?\w+\s*:\s*(?!(?:ElementRef|DestroyRef|Renderer2|ChangeDetectorRef|Injector|NgZone|ViewContainerRef|TemplateRef|DOCUMENT|PLATFORM_ID|LOCALE_ID|DomSanitizer|NgControl|ControlContainer|FocusMonitor|LiveAnnouncer|Directionality|Overlay|DialogRef|BrnDialogRef)\b)[A-Z]\w*\s*[,)]|from\s+(?:'|")(?:@tanstack/react-query|zustand|@reduxjs/toolkit|react-redux|jotai|swr|axios)['"/]|from\s+['"][^'"\n]*/(?:features|store|stores|api|data-access)(?:/|['"])|from\s+['"][^'"\n]*\.(?:service|store|facade|repository)['"]|\bfetch\(|\buse(?:Query|Mutation|SuspenseQuery|InfiniteQuery|Store|Selector|Dispatch|Navigate|Params)\()
---
Shared UI library component reaches state, data access or feature code. Library components are presentational: data in through inputs/props, events out through callbacks/outputs.
- Flutter: `StatelessWidget` (or `StatefulWidget` for local UI state), no Riverpod `ref`, no repositories, no `features/` imports.
- Angular: signal `input()`/`output()`, no `inject()` or constructor injection except DOM/forms/CDK tokens (`ElementRef`, `DestroyRef`, `NgControl`…), no `httpResource`.
- React: props in, callbacks out; no TanStack Query, global stores, `fetch` or `features/` imports.
Move the data work to the smart container in the feature layer and pass a semantic value (a tone/variant enum, not a colour).
Reference: .claude/skills/design-system/reference/atomic-decision-tree.md (Smart/dumb boundary). Gate: `python3 .claude/scripts/check-design-system.py` (rule DS-PRESENTATIONAL).
Exemption: `ignore-design: <reason>` on the same line or the line directly above.
