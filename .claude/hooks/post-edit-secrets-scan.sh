#!/usr/bin/env bash
# PostToolUse (Write|Edit): Scan file content Claude just wrote for secrets.
# Exit 0 = allow, Exit 2 = block the write and show error to Claude (reason on stderr; the value is never printed).
#
# Matching reads the content from a here-string, never `echo "$content" | grep -q`: under `set -o pipefail`,
# grep -q exits at the first match, echo dies of SIGPIPE on large files (status 141) and the pipeline reports
# "no match" -- a 1.2 MB file with a key on line 1 passed the old hook.
# Test: bash .claude/hooks/post-edit-secrets-scan.sh --selftest
set -uo pipefail

# label<TAB>ERE, checked in order; the first match wins. Specific token shapes only: this hook blocks.
# Pattern text is split where a literal would itself look like a credential to other scanners.
PATTERNS="AWS Access Key (AKIA...)	AKIA[0-9A-Z]{16}
Anthropic API key (sk-ant-...)	sk-ant-[a-zA-Z0-9_-]{20,}
OpenAI project/service key (sk-proj-/sk-svcacct-/sk-admin-)	sk-(proj|svcacct|admin)-[A-Za-z0-9_-]{40,}
OpenAI API key (sk-...)	sk-[a-zA-Z0-9]{40,}
Google API key (AIza...)	AIza[0-9A-Za-z_-]{35}
GitHub token (ghp_/gho_/ghu_/ghs_/ghr_/github_pat_)	gh[pousr]_[a-zA-Z0-9]{36,}|github_pat_[a-zA-Z0-9_]{80,}
GitLab personal access token (glpat-)	glpat-[A-Za-z0-9_-]{20,}
npm access token (npm_...)	npm_[A-Za-z0-9]{36}
npm registry auth token in .npmrc (_authToken=literal)	_authToken=[A-Za-z0-9._-]{20,}
Stripe live secret/restricted key	[sr]k_""live_[A-Za-z0-9]{20,}
Slack token (xox.-/xapp-)	xox[pboa]-[0-9]{10,}-[a-zA-Z0-9-]+|xapp-[0-9]+-[A-Za-z0-9-]{20,}
Hugging Face token (hf_...)	hf_[A-Za-z0-9]{34,}
HashiCorp Vault token (hvs./hvb.)	hv[sb]\.[A-Za-z0-9_-]{20,}
Private key (-----BEGIN ... PRIVATE KEY-----)	-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----
Database connection string with embedded credentials	(postgres|mongodb(\+srv)?)""://[^:/@[:space:]]+:[^@[:space:]\$]{6,}@[^[:space:]]+
Literal bearer token	[Bb]earer [A-Za-z0-9._~+/-]{40,}
Hardcoded secret assignment (key = \"...\")	(api_key|apikey|secret_key|access_token|auth_token|private_key|client_secret)[\"']?[[:space:]]*[=:][[:space:]]*[\"'][a-zA-Z0-9+/_-]{32,}[\"']"

scan() { # $1 file -> prints the matched label, returns 0 on a hit
  local file="$1" content label re flags
  case "$file" in
    *.png|*.jpg|*.jpeg|*.gif|*.ico|*.woff|*.woff2|*.ttf|*.eot|*.lock|*.map|*.bin|*.so|*.dylib|*.class|*.jar) return 1 ;;
  esac
  content=$(cat "$file" 2>/dev/null) || return 1
  [ -n "$content" ] || return 1
  while IFS="	" read -r label re; do
    [ -n "$re" ] || continue
    flags=-qE; case "$label" in Hardcoded*) flags=-qiE ;; esac # only the key-name rule is case-insensitive
    if grep "$flags" -e "$re" <<EOF_CONTENT
$content
EOF_CONTENT
    then
      printf '%s' "$label"; return 0
    fi
  done <<EOF_PATTERNS
$PATTERNS
EOF_PATTERNS
  return 1
}

run_hook() {
  local input file_path reason
  input=$(cat)
  file_path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // ""' 2>/dev/null) || file_path=""
  [ -n "$file_path" ] && [ -f "$file_path" ] || return 0
  reason=$(scan "$file_path") || return 0
  {
    echo ""
    echo "BLOCKED: Secret detected in $file_path"
    echo "Type: $reason"
    echo "Do not hardcode secrets in source files. Use environment variables, .env files (gitignored), or a secrets manager."
    echo ""
  } >&2
  return 2
}

selftest() {
  local self fail=0 tmp f out rc label value
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  probe() { printf '{"tool_input":{"file_path":"%s"}}' "$1" | "$BASH" "$self" 2>&1; }
  r() { printf "%0${1}d" 0 | tr 0 "$2"; } # $1 copies of char $2: probe values are built at runtime
  local p_aws="AK""IA" p_gho="gh""o_" p_glpat="gl""pat-" p_npm="np""m_" p_auth="_auth""Token=" p_stripe="sk""_live_" p_xapp="xa""pp-1-" p_hf="h""f_" p_oai="sk-pr""oj-" p_bearer="Bear""er " p_pg="postgres""://"
  # label substring | value (prefix pieces concatenated so this file holds no literal token)
  while IFS='|' read -r label value; do
    f="$tmp/pos.ts"; printf 'export const cfg = { k: "%s" };\n' "$value" > "$f"
    out=$(probe "$f"); rc=$?
    if [ "$rc" -eq 2 ] && printf '%s' "$out" | grep -qF "$label"; then echo "  ok   positive: $label blocked"
    else echo "  FAIL $label not blocked (exit $rc: $out)"; fail=1; fi
    if printf '%s' "$out" | grep -qF -- "$value"; then echo "  FAIL $label value echoed"; fail=1; fi
  done <<EOF_POS
AWS Access Key|${p_aws}$(r 16 Q)
GitHub token|${p_gho}$(r 36 a)
GitLab personal access token|${p_glpat}$(r 24 b)
npm access token|${p_npm}$(r 36 c)
npm registry auth token|//registry.npmjs.org/:${p_auth}$(r 36 d)
Stripe live|${p_stripe}$(r 24 e)
Slack token|${p_xapp}$(r 24 F)
Hugging Face token|${p_hf}$(r 34 g)
OpenAI project/service key|${p_oai}$(r 20 h)_$(r 30 i)
Literal bearer token|Authorization: ${p_bearer}$(r 48 j)
Database connection string|${p_pg}orders:$(r 12 k)@db.internal:5432/orders
EOF_POS
  # SIGPIPE regression: a key on line 1 of a >1 MB file (the old `echo | grep -q` pipeline passed this).
  f="$tmp/big.ts"; { printf 'const k = "%s%s";\n' "$p_aws" "$(r 16 Z)"; i=0; while [ $i -lt 20000 ]; do printf 'export const f%s = "%s";\n' "$i" "$(r 32 x)"; i=$((i + 1)); done; } > "$f"
  out=$(probe "$f"); rc=$?
  if [ "$rc" -eq 2 ]; then echo "  ok   positive: key on line 1 of a $(wc -c < "$f" | tr -d ' ')-byte file blocked (SIGPIPE regression)"; else echo "  FAIL large-file key missed (exit $rc)"; fail=1; fi
  # negatives: env references, placeholders and ordinary code must pass
  f="$tmp/neg.ts"
  {
    echo 'const key = process.env.STRIPE_SECRET_KEY;'
    echo '//registry.npmjs.org/:_authToken=${NPM_TOKEN}'
    echo 'headers: { Authorization: `Bearer ${token}` }'
    # Assembled from parts so the repo's own pre-commit secret scan does not read this fixture as a URL.
    printf '%s%s%s\n' 'const url = "postgres:' '//${DB_USER}:${DB_PASSWORD}' '@db:5432/app";'
    echo '"args": ["-y", "@acme/mcp@1.2.3"], "env": { "API_KEY": "${API_KEY}" }'
    echo 'export const skeleton = "sk-short";'
  } > "$f"
  out=$(probe "$f"); rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then echo "  ok   negative: env refs, \${VAR} placeholders and plain code pass"; else echo "  FAIL false positive (exit $rc: $out)"; fail=1; fi
  printf 'binary' > "$tmp/x.png"; out=$(probe "$tmp/x.png"); rc=$?
  [ "$rc" -eq 0 ] && echo "  ok   negative: binary/asset extensions skipped" || { echo "  FAIL asset not skipped"; fail=1; }
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit $?
