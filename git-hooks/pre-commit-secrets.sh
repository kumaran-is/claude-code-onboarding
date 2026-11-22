#!/bin/bash
# pre-commit — block commits containing secrets or credentials
#
# Patterns: OpenAI, Anthropic, GitHub tokens, AWS, GCP/Firebase,
#           database URLs, private keys, JWTs, generic api_key/secret/token.
#
# Bypass (emergencies only): git commit --no-verify

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
    "://[^:]+:[^@"   # regex source text inside secret scanners (e.g. stop-secret-scan.sh), not a credential
)

# ── File patterns to skip (docs and test fixtures) ───────────────────────────
SKIP_PATTERNS=(
    "*.md" "*.txt" "*example*" "*template*"
    "*.sample" "*.snap" "*_test.*" "*Test.*" "*Spec.*" "*spec.*"
)

should_skip_file() {
    local file="$1"
    for pat in "${SKIP_PATTERNS[@]}"; do
        local re="${pat//\*/.*}"
        [[ "$file" =~ $re ]] && return 0
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
        should_skip_file "$file" && continue
        [[ -f "$file" ]] || continue

        local content
        content=$(git show ":$file" 2>/dev/null) || continue

        for i in "${!PATTERN_NAMES[@]}"; do
            local name="${PATTERN_NAMES[$i]}"
            local regex="${PATTERN_REGEXES[$i]}"
            local matches
            matches=$(echo "$content" | grep -noE "$regex" 2>/dev/null) || true
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
        echo -e "${YELLOW}Emergency bypass (use with caution):${NC}"
        echo "  git commit --no-verify"
        echo
        exit 1
    fi

    echo -e "${GREEN}  pre-commit: no secrets detected${NC}"
    exit 0
}

detect_secrets

# ── Claude pre-commit evaluator (opt-in: CLAUDE_PRECOMMIT_EVAL=1) ────────────
EVALUATOR="$(git rev-parse --show-toplevel 2>/dev/null)/git-hooks/pre-commit-evaluator.sh"
if [ -f "$EVALUATOR" ]; then
  bash "$EVALUATOR"
fi
