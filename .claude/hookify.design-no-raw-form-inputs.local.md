---
name: design-no-raw-form-inputs
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: (?:^|/)src/app/features/.*\.html$
  - field: content
    operator: regex_match
    pattern: (?m)(?:\A|^(?![^\n]*ignore-design:\s*\S)[^\n]*\n)(?![^\n]*ignore-design:\s*\S)[^\n]*(?:<input\s(?![^>]*(?:formControl|formField|ngModel|type=\"(?:checkbox|radio|file|hidden|submit|button|range)\"))|<select\s(?![^>]*(?:formControl|formField|ngModel))|<textarea\s(?![^>]*(?:formControl|formField|ngModel)))
---
Form input without a form binding detected in an Angular feature template. Bind it to a form model (reactive `formControlName`/`[formControl]`, template `ngModel`, or experimental Signal Forms `[formField]`) and use daisyUI form classes:
- `<input class="input" formControlName="...">` not bare `<input>` (daisyUI 5: `input-bordered` no longer exists)
- `<select class="select" formControlName="...">` not bare `<select>`
- Group with `<fieldset class="fieldset">` + `<legend class="fieldset-legend">`, and give every control a `<label class="label" for="...">` (daisyUI 5 replaces `form-control`)
Reference: .claude/skills/angular-spa/reference/angular-conventions.md
Exemption: a justified one-off may carry `ignore-design: <reason>` (reason required) on the same line or the line directly above. A marker elsewhere in the file does not exempt it.
