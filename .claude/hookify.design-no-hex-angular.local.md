---
name: design-no-hex-angular
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: ^(?!.*(?:\.service\.ts|\.spec\.tsx?|\.test\.[jt]sx?|(?:^|/)[^/]*(?:tokens?|theme)[^/]*\.s?css)$)(?:.*(?:^|/)src/app/.*\.(?:html|scss|css|ts)|.*(?:^|/)src/(?!main/).*\.(?:css|scss)|.*\.(?:tsx|jsx))$
  - field: content
    operator: regex_match
    pattern: (?m)(?:\A|^(?![^\n]*ignore-design:\s*\S)[^\n]*\n)(?![^\n]*ignore-design:\s*\S)[^\n]*(?:\b(?:bg|text|border|ring|fill|stroke|from|via|to|outline|decoration|accent|caret|shadow)-\[(?:#|(?:rgba?|hsla?|oklch|oklab|hwb|lab|lch)\()|(?:background(?:-color)?|backgroundColor|(?<![a-z-])color|border(?:-[a-z]+)?(?:-color)?|border[A-Z][a-z]*Color|borderColor|outline(?:-color)?|fill|stroke|box-shadow|boxShadow)\s*:\s*['\"]?[^;'\"}\n]*?(?:#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|hwb|lab|lch)\())
---
Literal color (hex, rgb/hsl, oklch/oklab/hwb/lab/lch) in a web UI file (Angular `src/app/**`, React `*.tsx`/`*.jsx`, app stylesheets; specs and `*token*`/`*theme*` stylesheets are excluded because they define the tokens). Use theme tokens (daisyUI semantic classes, `var(--color-…)`, `color-mix(in oklch, var(--color-…) …)`) instead:
- `bg-primary` not `bg-[#3b82f6]`
- `text-base-content` not `text-[#333333]`
- `border-base-300` not `border-[#e5e7eb]`
- `text-primary` not `color: rgb(59, 130, 246)`
- `bg-accent` not `background: hsl(210, 80%, 55%)`
Reference: .claude/skills/angular-spa/reference/daisyui-v5-components.md lines 72-98
Exemption: a justified one-off may carry `ignore-design: <reason>` (reason required) on the same line or the line directly above. A marker elsewhere in the file does not exempt it.
