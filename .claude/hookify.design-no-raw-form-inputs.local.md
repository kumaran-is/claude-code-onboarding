---
name: design-no-raw-form-inputs
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: src/app/features/.*\.html$
  - field: content
    operator: regex_match
    pattern: (?m)(?:\A|^(?![^\n]*ignore-design:\s*\S)[^\n]*\n)(?![^\n]*ignore-design:\s*\S)[^\n]*(?:<input\s(?![^>]*formControl)|<select\s(?![^>]*formControl)|<textarea\s(?![^>]*formControl))
---
Raw form input detected without reactive form binding. Use daisyUI form components with Angular reactive forms:
- `<input class="input input-bordered" formControlName="...">` not bare `<input>`
- `<select class="select select-bordered" formControlName="...">` not bare `<select>`
- Wrap in `<label class="form-control">` for consistent spacing and labels
- For Flutter: use shared form field wrapper widgets, not raw `TextFormField`
Reference: .claude/skills/angular-spa/reference/angular-conventions.md
Exemption: a justified one-off may carry `ignore-design: <reason>` (reason required) on the same line or the line directly above. A marker elsewhere in the file does not exempt it.
