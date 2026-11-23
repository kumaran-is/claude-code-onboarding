#!/usr/bin/env bash
# PostToolUse -> Write|Edit: advisory — deterministic XSS / token-storage / code-execution sinks in web app code.
#
# Scope:  edited *.ts, *.tsx, *.js, *.jsx, *.mts, *.html inside an Angular or React web app: an ancestor directory
#         holds angular.json, vite.config.*, next.config.*, or a package.json depending on react / @angular/core.
#         NestJS, Node scripts and MCP servers (no such ancestor) are out of scope.
#         Skipped: *.spec.*, *.test.*, */e2e/*, */__tests__/*, *.d.ts, node_modules, dist.
# Flags (per line, POSIX ERE):
#   bypassSecurityTrust{Html,Script,Style,Url,ResourceUrl}(   Angular sanitizer turned off
#   [innerHTML]= bound to a non-literal                        Angular sanitizes it, but it renders HTML: prefer {{ }} text
#   .innerHTML/.outerHTML =, insertAdjacentHTML(, document.write(   raw DOM sinks, never sanitized
#   dangerouslySetInnerHTML                                    React raw HTML
#   localStorage/sessionStorage.setItem(<key with token|jwt|refresh|access|auth|session|bearer|credential>)
#   eval( / new Function(                                      string-to-code
# Sanitized lines: a hit whose line also calls DOMPurify.sanitize( / sanitize( is STILL reported, labelled
#         "sanitized — confirm" (lower wording): the sanitizer may be misconfigured, unpinned or bypassed later, and
#         the advisory cannot prove the input is the sanitized value. Decision recorded in .claude/rules/web-frontend.md.
# Exempt: `xss-reviewed: <reason>` (reason required) on the flagged line, or on a comment-only line directly above
#         (a trailing marker on a code line exempts that line only, never the next one).
# Comment lines (// … , * … , <!-- … -->) are ignored. Known limit: lines inside multi-line block comments or
#         template literals that do not start with a comment marker are still scanned (advisory false positive).
# Behavior: ADVISORY. Always exit 0, never blocks. Findings go to Claude as PostToolUse additionalContext JSON.
#         Fails open (says so on stderr) if jq is missing.
# Test:   bash .claude/hooks/post-edit-web-security-advisory.sh --selftest
set -uo pipefail

nearest_web_root() { # $1 start dir -> 0 if an ancestor is an Angular/React app root
  local d="$1" c
  while [ -n "$d" ] && [ "$d" != "/" ]; do
    [ -f "$d/angular.json" ] && return 0
    for c in "$d"/vite.config.* "$d"/next.config.*; do [ -f "$c" ] && return 0; done
    if [ -f "$d/package.json" ] && grep -qE '"(react|@angular/core)"[[:space:]]*:' "$d/package.json"; then
      grep -qE '"(react-native|@nestjs/core)"[[:space:]]*:' "$d/package.json" || return 0
    fi
    d=$(dirname "$d")
  done
  return 1
}

is_candidate() { # $1 path
  case "$1" in
    */node_modules/*|*/dist/*|*.d.ts|*.spec.*|*.test.*|*/e2e/*|*/__tests__/*) return 1 ;;
    *.ts|*.tsx|*.js|*.jsx|*.mts|*.html) ;;
    *) return 1 ;;
  esac
  nearest_web_root "$(dirname "$1")"
}

# scan_file <path> -> prints "line: [kind] text" for each un-exempted hit.
scan_file() {
  awk '
    function trim(s) { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return substr(s, 1, 160) }
    {
      line = $0; kind = ""
      if (line ~ /^[[:space:]]*(\/\/|\*|\/\*|<!--)/) { prevc = line; next }
      if (line ~ /bypassSecurityTrust(Html|Script|Style|Url|ResourceUrl)[[:space:]]*\(/) kind = "sanitizer bypass"
      else if (line ~ /dangerouslySetInnerHTML/) kind = "React raw HTML"
      else if (line ~ /\.(innerHTML|outerHTML)[[:space:]]*\+?=[^=]/ || line ~ /insertAdjacentHTML[[:space:]]*\(/ || line ~ /document\.write(ln)?[[:space:]]*\(/) kind = "raw DOM HTML sink"
      else if (tolower(line) ~ /\[innerhtml\][[:space:]]*=[[:space:]]*"[^"\x27]/ || tolower(line) ~ /[[:space:]]innerhtml[[:space:]]*=[[:space:]]*"[^"]*\{\{/) kind = "[innerHTML] binding"
      else if (line ~ /(localStorage|sessionStorage)\.setItem[[:space:]]*\(/ && tolower(line) ~ /setitem[[:space:]]*\([^,]*(token|jwt|refresh|access|auth|session|bearer|credential)/) kind = "token in web storage"
      else if (line ~ /(^|[^A-Za-z0-9_.])eval[[:space:]]*\(/ || line ~ /new[[:space:]]+Function[[:space:]]*\(/) kind = "string-to-code"
      if (kind != "" && !(line ~ /xss-reviewed:[[:space:]]*[^[:space:]]/ || prevc ~ /xss-reviewed:[[:space:]]*[^[:space:]]/)) {
        if (kind != "token in web storage" && kind != "string-to-code" && line ~ /sanitize[[:space:]]*\(/) kind = kind ", sanitized — confirm"
        printf "%d: [%s] %s\n", NR, kind, trim(line)
      }
      prevc = ""
    }
  ' "$1"
}

run_hook() {
  local input file hits msg
  input=$(cat)
  command -v jq >/dev/null 2>&1 || { echo "web-security-advisory: jq not found; check skipped" >&2; return 0; }
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || file=""
  [ -n "$file" ] && [ -f "$file" ] || return 0
  is_candidate "$file" || return 0
  hits=$(scan_file "$file")
  [ -n "$hits" ] || return 0
  msg="Web security sinks in $file (advisory, .claude/rules/web-frontend.md):
$hits
- Untrusted, API or model output: render as text ({{ }} / JSX text) or through a sanitizing markdown pipeline (DOMPurify, pinned); never bypassSecurityTrust* or dangerouslySetInnerHTML on it.
- Auth tokens: HttpOnly Secure cookie via the server/BFF, or in memory for a bearer token; never localStorage/sessionStorage.
- No eval / new Function. A reviewed, justified line may carry 'xss-reviewed: <reason>' on or above it."
  jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
  return 0
}

selftest() {
  local self fail=0 tmp out ng rx nest
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  ng="$tmp/ng"; rx="$tmp/rx"; nest="$tmp/nest"
  mkdir -p "$ng/src/app" "$rx/src" "$nest/src/modules"
  printf '{}\n' > "$ng/angular.json"
  printf 'export default {}\n' > "$rx/vite.config.ts"
  printf '{ "dependencies": { "@nestjs/core": "11.1.0" } }\n' > "$nest/package.json"
  # positives (one per sink)
  printf 'this.html = this.s.bypassSecurityTrustHtml(reply);\n' > "$ng/src/app/bypass.ts"
  printf '<div [innerHTML]="message.body"></div>\n' > "$ng/src/app/bind.component.html"
  printf 'el.nativeElement.innerHTML = text;\n' > "$ng/src/app/dom.ts"
  printf 'export const A = () => <div dangerouslySetInnerHTML={{ __html: md }} />;\n' > "$rx/src/Raw.tsx"
  printf "localStorage.setItem('access_token', t);\n" > "$rx/src/auth.ts"
  printf "sessionStorage.setItem(\"refreshToken\", t);\n" > "$rx/src/auth2.ts"
  printf 'const f = new Function("a", body);\nconst y = eval(src);\n' > "$rx/src/exec.ts"
  printf 'export const B = () => <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(md) }} />;\n' > "$rx/src/Sanitized.tsx"
  # negatives
  printf '<div [innerHTML]="%s"></div>\n<p>{{ message.body }}</p>\n' "'<b>static</b>'" > "$ng/src/app/literal.component.html"
  printf "el.textContent = text;\nlocalStorage.setItem('theme', 'dark');\nconst ok = a.evaluate(x);\n" > "$rx/src/benign.ts"
  printf '// never use dangerouslySetInnerHTML or eval( here\nexport const c = 1;\n' > "$rx/src/comment.ts"
  printf '// xss-reviewed: static, build-time constant HTML\nexport const D = () => <div dangerouslySetInnerHTML={{ __html: LEGAL }} />;\n' > "$rx/src/Exempt.tsx"
  printf 'export const E = () => <div dangerouslySetInnerHTML={{ __html: md }} />;\n' > "$rx/src/Raw.test.tsx"
  printf 'el.innerHTML = body;\n' > "$nest/src/modules/render.ts"
  printf 'el.innerHTML = body;\n' > "$tmp/loose.ts"
  printf 'el.innerHTML += chunk;\n' > "$ng/src/app/append.ts"
  printf '<div [innerHtml]="msg"></div>\n' > "$ng/src/app/camel.component.html"
  printf '<div innerHTML="{{ msg }}"></div>\n' > "$ng/src/app/interp.component.html"
  printf 'el.innerHTML = A; // xss-reviewed: constant\nel.innerHTML = userInput;\n' > "$ng/src/app/bleed.ts"
  probe() { # label file expect(advise|silent) [content-needle]
    out=$(printf '{"tool_input":{"file_path":"%s"}}' "$2" | bash "$self" 2>/dev/null)
    case "$3" in
      advise) if printf '%s' "$out" | jq -e --arg n "${4:-}" '.hookSpecificOutput.additionalContext | contains($n)' >/dev/null 2>&1; then echo "  ok   $1"; else echo "  FAIL $1 (got: $out)"; fail=1; fi ;;
      silent) if [ -z "$out" ]; then echo "  ok   $1"; else echo "  FAIL $1 (got: $out)"; fail=1; fi ;;
    esac
  }
  probe "positive: Angular bypassSecurityTrustHtml"        "$ng/src/app/bypass.ts"              advise "[sanitizer bypass]"
  probe "positive: [innerHTML] bound to data"              "$ng/src/app/bind.component.html"    advise "[[innerHTML] binding]"
  probe "positive: nativeElement.innerHTML ="              "$ng/src/app/dom.ts"                 advise "[raw DOM HTML sink]"
  probe "positive: React dangerouslySetInnerHTML"          "$rx/src/Raw.tsx"                    advise "[React raw HTML]"
  probe "positive: token in localStorage"                  "$rx/src/auth.ts"                    advise "[token in web storage]"
  probe "positive: refresh token in sessionStorage"        "$rx/src/auth2.ts"                   advise "[token in web storage]"
  probe "positive: new Function"                           "$rx/src/exec.ts"                    advise "1: [string-to-code]"
  probe "positive: eval("                                  "$rx/src/exec.ts"                    advise "2: [string-to-code]"
  probe "positive: DOMPurify line still flagged, softened" "$rx/src/Sanitized.tsx"              advise "sanitized — confirm"
  probe "positive: innerHTML +="                            "$ng/src/app/append.ts"             advise "[raw DOM HTML sink]"
  probe "positive: [innerHtml] (camel case)"               "$ng/src/app/camel.component.html"   advise "[[innerHTML] binding]"
  probe "positive: innerHTML=\"{{ }}\" interpolation"      "$ng/src/app/interp.component.html"  advise "[[innerHTML] binding]"
  probe "positive: trailing marker does not exempt next line" "$ng/src/app/bleed.ts"            advise "2: [raw DOM HTML sink]"
  probe "negative: literal [innerHTML] + text interpolation" "$ng/src/app/literal.component.html" silent
  probe "negative: textContent, theme key, .evaluate("     "$rx/src/benign.ts"                  silent
  probe "negative: comment lines ignored"                  "$rx/src/comment.ts"                 silent
  probe "negative: xss-reviewed marker exempts"            "$rx/src/Exempt.tsx"                 silent
  probe "negative: test file skipped"                      "$rx/src/Raw.test.tsx"               silent
  probe "negative: NestJS project out of scope"            "$nest/src/modules/render.ts"        silent
  probe "negative: no web-app ancestor"                    "$tmp/loose.ts"                      silent
  out=$(printf '{"tool_input":{"file_path":"%s"}}' "$rx/src/Raw.tsx" | bash "$self" 2>/dev/null); rc=$?
  if [ "$rc" -eq 0 ]; then echo "  ok   advisory only: exit 0 on a finding"; else echo "  FAIL exit $rc on a finding"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
