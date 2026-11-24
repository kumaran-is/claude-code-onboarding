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
# Provider token shapes come from the shared table every scanner uses
# (`.claude/hooks/post-edit-secrets-scan.sh --patterns`): they are high-confidence, scanned in docs too.
# Only the commit-time extras below live here; they are noisy in prose, so code files only.
PATTERN_NAMES=(); PATTERN_REGEXES=(); PATTERN_HIGH_CONFIDENCE=()
load_patterns() {
    # Always this repo's own table: no env override, so nothing can point the scan at an empty table.
    local scanner table label re rows
    scanner="$(git rev-parse --show-toplevel 2>/dev/null)/.claude/hooks/post-edit-secrets-scan.sh"
    if ! table=$(bash "$scanner" --patterns 2>/dev/null) || [[ -z "$table" ]]; then
        echo "pre-commit: BLOCKED: shared secret pattern table not found ($scanner). Restore .claude/hooks/ or reinstall the hook; refusing to commit unscanned." >&2
        exit 1
    fi
    rows=$(printf '%s\n' "$table" | grep -c $'\t' || true)
    if [[ "${rows:-0}" -lt 15 ]] || ! printf '%s\n' "$table" | grep -q '^AWS Access Key'; then
        echo "pre-commit: BLOCKED: shared secret pattern table is malformed (${rows:-0} label<TAB>regex rows, need >= 15 incl. AWS Access Key). Refusing to commit unscanned." >&2
        exit 1
    fi
    while IFS=$'\t' read -r label re; do
        [[ -n "$re" ]] || continue
        PATTERN_NAMES+=("$label"); PATTERN_REGEXES+=("$re")
        # noisy in prose (example URLs, assignments, bearer samples): code files only
        case "$label" in Hardcoded*|Literal*|Database*) PATTERN_HIGH_CONFIDENCE+=(0) ;; *) PATTERN_HIGH_CONFIDENCE+=(1) ;; esac
    done <<< "$table"
    PATTERN_NAMES+=("GCP Service Account" "JWT Token" "Generic api_key assignment" "Generic secret assignment" "Generic token assignment")
    PATTERN_REGEXES+=(
        "\"type\":[[:space:]]*\"service_account\""
        "eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}"
        "api[_-]?key[\"']?[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9]{20,}"
        "secret[\"']?[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9]{20,}"
        "token[\"']?[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9]{20,}"
    )
    PATTERN_HIGH_CONFIDENCE+=(1 0 0 0 0)
}

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
    load_patterns
    local files
    files=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null) || true

    [[ -z "$files" ]] && return 0   # return, not exit: the opt-in evaluator below must still run

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
            local flags=-noE; [[ "$name" == Hardcoded* ]] && flags=-noiE   # same case rule as the shared table
            matches=$(echo "$content" | grep "$flags" -e "$regex" 2>/dev/null) || true
            [[ -z "$matches" ]] && continue

            while IFS= read -r match; do
                local line="${match%%:*}"
                local text="${match#*:}"
                is_whitelisted "$text" && continue
                found=1
                report+="  ${file}:${line}  [${name}]\n"   # never the value: this output lands in transcripts and CI logs"
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
    return 0
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
    local gh aws pk kv ghpat
    local scanner_src; scanner_src="$(cd "$(dirname "$self")/.." && pwd)/.claude/hooks/post-edit-secrets-scan.sh"
    gh="gh""p_$(printf 'a%.0s' $(seq 1 36))"
    ghpat="github""_pat_$(printf 'A1_%.0s' $(seq 1 28))"
    aws="AK""IAQWERTYUIOPASDFGH"
    pk="-----BEGIN ""PRIVATE KEY-----"
    kv="api""_key = abcdefghijklmnopqrstuvwxyz"
    local dburl; dburl="post""gresql://app:$(printf 'p%.0s' $(seq 1 12))@db.internal:5432/app"

    # case <expect-rc> <expected-text-or-empty> <file> <content>
    run_case() {
        local want="$1" text="$2" file="$3" body="$4" out rc
        rm -rf "$tmp/r" && mkdir -p "$tmp/r/$(dirname "$file")"
        mkdir -p "$tmp/r/.claude/hooks" && cp "$scanner_src" "$tmp/r/.claude/hooks/"   # the hook reads the repo's own table
        (cd "$tmp/r" && git init -q . && printf '%s\n' "$body" > "$file" && git add -- "$file")
        out=$(cd "$tmp/r" && bash "$self" 2>&1) && rc=0 || rc=$?   # set -e safe
        if [[ $rc -ne $want ]] || { [[ -n "$text" ]] && [[ "$out" != *"$text"* ]]; }; then
            echo "FAIL: $file expected rc=$want${text:+ and '$text'}, got rc=$rc"; fail=1
        else
            echo "ok   $file rc=$rc"
        fi
    }
    run_case 1 "GitHub token"       "docs/notes.md"                "token: $gh"
    run_case 1 "GitHub token"       "docs/fine.md"                 "token: $ghpat"   # fine-grained PAT: was missed before the shared table
    run_case 1 "Private key"        "README.txt"                   "$pk"
    run_case 1 "AWS Access Key"     ".env.example"                 "KEY=$aws"
    run_case 1 "AWS Access Key"     "config/app.template.yaml"     "key: $aws"
    run_case 1 "GitHub token"       "src/client.ts"                "const t = '$gh'"
    run_case 1 "Generic api_key"    "src/app.py"                   "$kv"
    run_case 1 "Private key"        "deploy/key.py"                "K='''$pk'''"   # code file too (option-parsing bug)
    # Basename globs are anchored: a code file whose name merely contains 'md' or 'spec'
    # keeps the full pattern set (generic assignments are code-only, so they prove the class).
    run_case 1 "Generic api_key"    "hooks/session-claudemd-scan.sh" "$kv"
    run_case 1 "Generic api_key"    "tools/inspect.sh"             "$kv"
    run_case 0 ""                   "docs/guide.md"                "$kv"        # generic assignment in prose: not flagged
    run_case 0 ""                   "docs/aws.md"                  "id: AK""IAIOSFODNN7EXAMPLE"
    run_case 0 ""                   "src/user_spec.ts"             "t='$gh'"     # test fixture: skipped
    run_case 0 ""                   "src/clean.py"                 "print('ok')"
    run_case 0 ""                   "docs/setup.md"                "url: ${dburl}"   # example DB URL in prose: code files only
    run_case 1 "Database connection" "src/db.ts"                   "const u = '${dburl}'"
    local out rc
    run_case 1 "AWS Access Key"     "src/leak.py"                  "k = '$aws'"
    if [[ "$out" != *"$aws"* ]] && out=$(cd "$tmp/r" && bash "$self" 2>&1); [[ "$out" != *"$aws"* ]]; then echo "ok   the matched value is never printed"
    else echo "FAIL: secret value echoed in hook output"; fail=1; fi
    printf '#!/usr/bin/env bash\nfor i in $(seq 1 16); do printf "AWS Access Key\\tZZZ_NEVER_MATCHES\\n"; done\n' > "$tmp/fake.sh"
    out=$(cd "$tmp/r" && SECRET_PATTERN_SCANNER="$tmp/fake.sh" bash "$self" 2>&1) && rc=0 || rc=$?
    if [[ $rc -eq 1 ]]; then echo "ok   SECRET_PATTERN_SCANNER is ignored (no env bypass of the scan)"; else echo "FAIL: env override bypassed the scan (rc=$rc)"; fail=1; fi
    rm -f "$tmp/r/.claude/hooks/post-edit-secrets-scan.sh"
    out=$(cd "$tmp/r" && bash "$self" 2>&1) && rc=0 || rc=$?
    if [[ $rc -eq 1 && "$out" == *"shared secret pattern table not found"* ]]; then echo "ok   missing shared table -> commit refused (fail closed)"
    else echo "FAIL: missing table expected rc=1, got rc=$rc"; fail=1; fi
    printf '#!/usr/bin/env bash\necho "no tabs here"\n' > "$tmp/r/.claude/hooks/post-edit-secrets-scan.sh"
    out=$(cd "$tmp/r" && bash "$self" 2>&1) && rc=0 || rc=$?
    if [[ $rc -eq 1 && "$out" == *"malformed"* ]]; then echo "ok   a non-empty table with no usable rows -> commit refused"
    else echo "FAIL: malformed table expected rc=1, got rc=$rc ($out)"; fail=1; fi
    mkdir -p "$tmp/r/git-hooks"; printf '#!/usr/bin/env bash\necho EVALUATOR-RAN\n' > "$tmp/r/git-hooks/pre-commit-evaluator.sh"
    cp "$scanner_src" "$tmp/r/.claude/hooks/"; (cd "$tmp/r" && git rm -q --cached src/leak.py && printf 'x = 1\n' > src/ok.py && git add src/ok.py)
    out=$(cd "$tmp/r" && bash "$self" 2>&1) && rc=0 || rc=$?
    if [[ $rc -eq 0 && "$out" == *"EVALUATOR-RAN"* ]]; then echo "ok   a clean commit still reaches the opt-in evaluator"
    else echo "FAIL: evaluator not reached on a clean commit (rc=$rc)"; fail=1; fi
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
