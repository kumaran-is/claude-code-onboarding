#!/bin/bash
# Hook: PreToolUse - Detect prompt injection attempts in executed content
# Exit 0 = allow, Exit 2 = block (stderr shown to Claude)
#
# Scope (security model):
#   Bash / WebFetch : full injection checks on commands / URLs
#   Write / Edit    : ANSI escape check only
#
# Write/Edit skip text-pattern checks because writing a security script
# that lists injection patterns as string literals is legitimate work.
# Injection risk is from content Claude EXECUTES or FETCHES, not from
# files written to disk. Unicode injection covered by pre-unicode-injection.sh.
#
# BSD grep (macOS) note: -P is unavailable. Byte-level checks use python3.
#
# Registered in settings.json: PreToolUse matcher "Bash|Write|Edit|WebFetch"

set -e

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
TOOL_INPUT=$(echo "$INPUT" | jq -r '.tool_input // empty')

case "$TOOL_NAME" in
    Bash|Write|Edit|WebFetch) ;;
    *) exit 0 ;;
esac

# ── Write / Edit: ANSI escape only ──────────────────────────────────────────
if [[ "$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit" ]]; then
    CONTENT=""
    case "$TOOL_NAME" in
        Write) CONTENT=$(echo "$TOOL_INPUT" | jq -r '.content // empty') ;;
        Edit)  CONTENT=$(echo "$TOOL_INPUT" | jq -r '.new_string // empty') ;;
    esac
    if [[ -n "$CONTENT" ]]; then
        ESC=$(printf '\033')
        if [[ "$CONTENT" == *"${ESC}["* ]] || \
           [[ "$CONTENT" == *"${ESC}]"* ]] || \
           [[ "$CONTENT" == *"${ESC}("* ]]; then
            echo "BLOCKED: ANSI escape in file write - potential terminal injection" >&2
            exit 2
        fi
    fi
    exit 0
fi

# ── Bash / WebFetch: full checks ─────────────────────────────────────────────
CONTENT=""
case "$TOOL_NAME" in
    Bash)     CONTENT=$(echo "$TOOL_INPUT" | jq -r '.command // empty') ;;
    WebFetch) CONTENT=$(echo "$TOOL_INPUT" | jq -r '.url // empty') ;;
esac

[[ -z "$CONTENT" ]] && exit 0

CONTENT_LOWER=$(echo "$CONTENT" | tr '[:upper:]' '[:lower:]')

# ── Role-override patterns ────────────────────────────────────────────────────
ROLE_PATTERNS=(
    "ignore all previous"
    "ignore your instructions"
    "disregard previous"
    "disregard your instructions"
    "forget your instructions"
    "forget everything"
    "you are now"
    "act as if"
    "pretend you are"
    "pretend to be"
    "from now on you"
    "new instructions:"
    "override:"
    "system prompt:"
)
# "ignore previous instructions" split to avoid self-match in pattern list
IGNORE_PREV="ignore previous"
INSTRUCTIONS="instructions"
if [[ "$CONTENT_LOWER" == *"${IGNORE_PREV} ${INSTRUCTIONS}"* ]]; then
    echo "BLOCKED: Prompt injection - role override detected" >&2
    exit 2
fi
for pattern in "${ROLE_PATTERNS[@]}"; do
    if [[ "$CONTENT_LOWER" == *"$pattern"* ]]; then
        echo "BLOCKED: Prompt injection - role override: '$pattern'" >&2
        exit 2
    fi
done

# ── Jailbreak patterns ────────────────────────────────────────────────────────
JAILBREAK_PATTERNS=(
    "dan mode" "developer mode" "jailbreak" "do anything now"
    "no restrictions" "without restrictions" "unrestricted mode"
    "god mode" "sudo mode" "admin mode" "maintenance mode"
)
for pattern in "${JAILBREAK_PATTERNS[@]}"; do
    if [[ "$CONTENT_LOWER" == *"$pattern"* ]]; then
        echo "BLOCKED: Prompt injection - jailbreak: '$pattern'" >&2
        exit 2
    fi
done

# ── Delimiter injection ───────────────────────────────────────────────────────
DELIMITER_PATTERNS=(
    "</system>" "<|endoftext|>" "<|im_end|>" "[/INST]" "[INST]"
    "<<SYS>>" "<</SYS>>" "### System:" "### Human:" "### Assistant:"
    "SYSTEM:"
)
for pattern in "${DELIMITER_PATTERNS[@]}"; do
    if [[ "$CONTENT" == *"$pattern"* ]]; then
        echo "BLOCKED: Prompt injection - delimiter: '$pattern'" >&2
        exit 2
    fi
done

# ── Authority impersonation ───────────────────────────────────────────────────
AUTHORITY_PATTERNS=(
    "anthropic employee" "anthropic staff"
    "i am your creator" "i am your developer"
    "i have admin access" "authorized to bypass"
    "emergency override" "security exception"
)
for pattern in "${AUTHORITY_PATTERNS[@]}"; do
    if [[ "$CONTENT_LOWER" == *"$pattern"* ]]; then
        echo "BLOCKED: Prompt injection - authority impersonation: '$pattern'" >&2
        exit 2
    fi
done

# ── Base64 encoded payload (heuristic) ───────────────────────────────────────
if echo "$CONTENT" | grep -qE '[A-Za-z0-9+/]{50,}={0,2}'; then
    DECODED=$(echo "$CONTENT" | grep -oE '[A-Za-z0-9+/]{50,}={0,2}' | head -1 | base64 -d 2>/dev/null || true)
    DECODED_LOWER=$(echo "$DECODED" | tr '[:upper:]' '[:lower:]')
    for pattern in "ignore" "override" "system" "jailbreak" "dan mode"; do
        if [[ "$DECODED_LOWER" == *"$pattern"* ]]; then
            echo "BLOCKED: Prompt injection - encoded payload: '$pattern'" >&2
            exit 2
        fi
    done
fi

# ── ANSI escape sequences ─────────────────────────────────────────────────────
ESC=$(printf '\033')
if [[ "$CONTENT" == *"${ESC}["* ]] || \
   [[ "$CONTENT" == *"${ESC}]"* ]] || \
   [[ "$CONTENT" == *"${ESC}("* ]]; then
    echo "BLOCKED: ANSI escape in command - potential terminal injection" >&2
    exit 2
fi

# ── Null byte (Bash only; python3 for BSD grep compat) ───────────────────────
if [[ "$TOOL_NAME" == "Bash" ]]; then
    NULL_CHECK=$(python3 -c "
import sys
data = sys.stdin.buffer.read()
print('found' if b'\\x00' in data else 'clean')
" <<< "$CONTENT" 2>/dev/null || echo "clean")
    if [[ "$NULL_CHECK" == "found" ]]; then
        echo "BLOCKED: Null byte in Bash command - string truncation attack" >&2
        exit 2
    fi
fi

# Nested command execution ($(...), backticks): handled by pre-bash-guard.py, which parses the
# substitution and judges what it would do. The old text heuristic that lived here blocked any $(...)
# whose text merely contained a word like "bash" or "rm" (e.g. a file name) and was removed.

# ── Context manipulation (warn only) ─────────────────────────────────────────
CONTEXT_PATTERNS=(
    "you agreed to" "you already said" "you promised"
    "remember when you" "our agreement was"
)
for pattern in "${CONTEXT_PATTERNS[@]}"; do
    if [[ "$CONTENT_LOWER" == *"$pattern"* ]]; then
        echo '{"systemMessage": "Warning: Possible context manipulation in command. Verify legitimacy."}'
    fi
done

exit 0
