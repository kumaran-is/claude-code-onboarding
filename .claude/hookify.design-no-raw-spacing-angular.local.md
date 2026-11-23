---
name: design-no-raw-spacing-angular
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: ^(?!.*(?:\.spec\.tsx?|\.test\.[jt]sx?|(?:^|/)[^/]*(?:tokens?|theme)[^/]*\.s?css)$)(?:.*(?:^|/)src/app/.*\.html|.*\.(?:tsx|jsx))$
  - field: content
    operator: regex_match
    pattern: (?m)(?:\A|^(?![^\n]*ignore-design:\s*\S)[^\n]*\n)(?![^\n]*ignore-design:\s*\S)[^\n]*(?:(?:^|[\s\"'`:])-?(?:[mp][xytrblse]?|gap(?:-[xy])?|space-[xy]|inset(?:-[xy])?)-\[(?!var\()[^\]]+\]|style=\"[^\"]*\b(?:margin|padding|gap)[a-z-]*\s*:\s*-?[0-9.]+px|style=\{\{[^}]*\b(?:margin|padding|gap)[A-Za-z]*\s*:\s*['\"]?-?[0-9.]+)
---
Arbitrary spacing value detected in a web template (`p-[13px]`, `gap-[1.1rem]`, inline `style="margin: 12px"`).
Tailwind 4 numeric utilities (`p-4`, `gap-2`, `mt-6`) ARE the spacing scale: each is a multiple of the `--spacing` theme token, so use them, or daisyUI component spacing.
- `p-4` not `p-[16px]`; `gap-2` not `gap-[8px]`; a class not `style="padding: 12px"`
Reference: .claude/skills/angular-spa/reference/angular-conventions.md (spacing scale)
Exemption: a justified one-off may carry `ignore-design: <reason>` (reason required) on the same line or the line directly above. A marker elsewhere in the file does not exempt it.
