#!/bin/bash
# pre-commit — block commits containing secrets or credentials
#
# Patterns: OpenAI, Anthropic, GitHub tokens, AWS, GCP/Firebase,
#           database URLs, private keys, JWTs, generic api_key/secret/token.
#
# Never bypass with --no-verify: whitelist a false positive, remove and rotate a real secret.

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

# ── Patterns: parallel arrays (bash 3.2 compatible) ──────────────────────────
PATTERN_NAMES=(
    "OpenAI API Key"
    "Anthropic API Key"
    "GitHub Token ghp"
    "GitHub Token gho"
    "GitHub Token ghu"
    "GitHub Token ghs"
    "AWS Access Key ID"
    "Firebase API Key"
    "GCP Service Account"
    "Private Key Block"
    "Database URL with password"
    "JWT Token"
    "Generic api_key assignment"
    "Generic secret assignment"
    "Generic token assignment"
)
PATTERN_REGEXES=(
    "sk-[A-Za-z0-9]{48}"
    "sk-ant-[A-Za-z0-9-]{95,}"
    "ghp_[A-Za-z0-9]{36}"
    "gho_[A-Za-z0-9]{36}"
    "ghu_[A-Za-z0-9]{36}"
    "ghs_[A-Za-z0-9]{36}"
    "AKIA[A-Z0-9]{16}"
    "AIza[A-Za-z0-9_-]{35}"
    "\"type\":[[:space:]]*\"service_account\""
    "-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"
    "(postgres|mysql|mongodb)://[^:]+:[^@]+@"
    "eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}"
    "api[_-]?key[\"']?[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9]{20,}"
    "secret[\"']?[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9]{20,}"
    "token[\"']?[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9]{20,}"
)
# 1 = high-confidence (provider token shape or key block): also scanned in docs.
# 0 = noisy in prose (generic assignments, example JSON/URLs/JWTs): code files only.
PATTERN_HIGH_CONFIDENCE=(1 1 1 1 1 1 1 1 0 1 0 0 0 0 0)

# ── Whitelisted values (safe false-positives) ────────────────────────────────
WHITELIST=(
    "your_token_here"
    "your_key_here"
    "placeholder"
    "XXXXXX"
    "sk-ant-example"
    "test_token"
    "dummy"
    "fake"
    "<YOUR_"
    "YOUR_API"
    "EXAMPLE"        # AWS's documented sample access key ends in EXAMPLE
    "://[^:]+:[^@"   # regex source text inside secret scanners (e.g. stop-secret-scan.sh), not a credential
)

# ── File classes (shell globs matched against the file's basename) ───────────
# Docs are scanned with high-confidence patterns only: a real token pasted into a
# README is still a leak. Test fixtures and snapshots are skipped.
DOC_PATTERNS=("*.md" "*.txt" "*example*" "*template*" "*.sample")
SKIP_PATTERNS=("*.snap" "*_test.*" "*Test.*" "*Spec.*" "*spec.*")

matches_any() { # basename glob...
    local base="$1" pat
    shift
    for pat in "$@"; do
        # shellcheck disable=SC2053  # $pat is a glob on purpose
        [[ "$base" == $pat ]] && return 0
    done
    return 1
}

is_whitelisted() {
    local match="$1"
    for entry in "${WHITELIST[@]}"; do
        [[ "$match" == *"$entry"* ]] && return 0
    done
    return 1
}

# ── Main ──────────────────────────────────────────────────────────────────────
detect_secrets() {
    local files
    files=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null) || true

    [[ -z "$files" ]] && exit 0

    local found=0
    local report=""
    local i

    while IFS= read -r file; do
        local base="${file##*/}" doc=0
        matches_any "$base" "${SKIP_PATTERNS[@]}" && continue
        matches_any "$base" "${DOC_PATTERNS[@]}" && doc=1
        [[ -f "$file" ]] || continue

        local content
        content=$(git show ":$file" 2>/dev/null) || continue

        for i in "${!PATTERN_NAMES[@]}"; do
            [[ $doc -eq 1 && ${PATTERN_HIGH_CONFIDENCE[$i]} -eq 0 ]] && continue
            local name="${PATTERN_NAMES[$i]}"
            local regex="${PATTERN_REGEXES[$i]}"
            local matches
            # -e: the private-key pattern starts with '-' and would otherwise be parsed as an option
            matches=$(echo "$content" | grep -noE -e "$regex" 2>/dev/null) || true
            [[ -z "$matches" ]] && continue

            while IFS= read -r match; do
                local line="${match%%:*}"
                local text="${match#*:}"
                is_whitelisted "$text" && continue
                found=1
                report+="  ${file}:${line}  [${name}]\n"
                report+="  $(echo "$text" | cut -c1-60)\n\n"
            done <<< "$matches"
        done
    done <<< "$files"

    if [[ $found -eq 1 ]]; then
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${RED}  COMMIT BLOCKED — secrets detected in staged files${NC}"
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo
        echo -e "${YELLOW}Findings:${NC}"
        echo -e "$report"
        echo -e "${YELLOW}Fix options:${NC}"
        echo "  1. Remove the secret from the file"
        echo "  2. Use environment variables: process.env.X / os.environ['X'] / System.getenv(\"X\")"
        echo "  3. Store in .env (gitignored) — never commit .env files"
        echo "  4. Add false-positive values to WHITELIST in .git/hooks/pre-commit"
        echo
        echo "  A real secret: remove it from the commit and rotate it. Do not bypass this hook."
        echo
        exit 1
    fi

    echo -e "${GREEN}  pre-commit: no secrets detected${NC}"
    exit 0
}

# ── Self-test: bash git-hooks/pre-commit-secrets.sh --selftest ────────────────
# Fake values are assembled from parts so this file never contains a token shape.
selftest() {
    local self tmp fail=0
    self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
    bash -n "$self" || { echo "FAIL control 0: bash -n"; return 1; }
    tmp=$(mktemp -d)
    # shellcheck disable=SC2064  # expand $tmp now
    trap "rm -rf '$tmp'" EXIT INT TERM
    local gh aws pk kv
    gh="gh""p_$(printf 'a%.0s' $(seq 1 36))"
    aws="AK""IAQWERTYUIOPASDFGH"
    pk="-----BEGIN ""PRIVATE KEY-----"
    kv="api""_key = abcdefghijklmnopqrstuvwxyz"

    # case <expect-rc> <expected-text-or-empty> <file> <content>
    run_case() {
        local want="$1" text="$2" file="$3" body="$4" out rc
        rm -rf "$tmp/r" && mkdir -p "$tmp/r/$(dirname "$file")"
        (cd "$tmp/r" && git init -q . && printf '%s\n' "$body" > "$file" && git add -- "$file")
        out=$(cd "$tmp/r" && bash "$self" 2>&1) && rc=0 || rc=$?   # set -e safe
        if [[ $rc -ne $want ]] || { [[ -n "$text" ]] && [[ "$out" != *"$text"* ]]; }; then
            echo "FAIL: $file expected rc=$want${text:+ and '$text'}, got rc=$rc"; fail=1
        else
            echo "ok   $file rc=$rc"
        fi
    }
    run_case 1 "GitHub Token ghp"   "docs/notes.md"                "token: $gh"
    run_case 1 "Private Key Block"  "README.txt"                   "$pk"
    run_case 1 "AWS Access Key ID"  ".env.example"                 "KEY=$aws"
    run_case 1 "AWS Access Key ID"  "config/app.template.yaml"     "key: $aws"
    run_case 1 "GitHub Token ghp"   "src/client.ts"                "const t = '$gh'"
    run_case 1 "Generic api_key"    "src/app.py"                   "$kv"
    run_case 1 "Private Key Block"  "deploy/key.py"                "K='''$pk'''"   # code file too (option-parsing bug)
    # Basename globs are anchored: a code file whose name merely contains 'md' or 'spec'
    # keeps the full pattern set (generic assignments are code-only, so they prove the class).
    run_case 1 "Generic api_key"    "hooks/session-claudemd-scan.sh" "$kv"
    run_case 1 "Generic api_key"    "tools/inspect.sh"             "$kv"
    run_case 0 ""                   "docs/guide.md"                "$kv"        # generic assignment in prose: not flagged
    run_case 0 ""                   "docs/aws.md"                  "id: AK""IAIOSFODNN7EXAMPLE"
    run_case 0 ""                   "src/user_spec.ts"             "t='$gh'"     # test fixture: skipped
    run_case 0 ""                   "src/clean.py"                 "print('ok')"
    [[ $fail -eq 0 ]] && echo "selftest PASS" || echo "selftest FAIL"
    return $fail
}
if [[ "${1:-}" == "--selftest" ]]; then selftest; exit $?; fi

detect_secrets

# ── Claude pre-commit evaluator (opt-in: CLAUDE_PRECOMMIT_EVAL=1) ────────────
EVALUATOR="$(git rev-parse --show-toplevel 2>/dev/null)/git-hooks/pre-commit-evaluator.sh"
if [ -f "$EVALUATOR" ]; then
  bash "$EVALUATOR"
fi
