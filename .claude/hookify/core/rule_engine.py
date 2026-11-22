#!/usr/bin/env python3
"""Rule evaluation engine for hookify."""

import re
import sys
from functools import lru_cache
from typing import List, Dict, Any, Optional

from hookify.core.config_loader import Rule, Condition


@lru_cache(maxsize=128)
def compile_regex(pattern: str) -> re.Pattern:
    """Compile regex pattern with caching."""
    return re.compile(pattern, re.IGNORECASE)


class RuleEngine:
    """Evaluates rules against hook input data."""

    def evaluate_rules(self, rules: List[Rule], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate all rules and return combined results.

        Blocking rules take priority over warning rules.
        All matching rule messages are combined.

        Args:
            rules: List of Rule objects to evaluate
            input_data: Hook input JSON (tool_name, tool_input, etc.)

        Returns:
            Response dict with systemMessage, hookSpecificOutput, etc.
            Empty dict {} if no rules match.
        """
        hook_event = input_data.get('hook_event_name', '')
        blocking_rules = []
        warning_rules = []

        for rule in rules:
            if self._rule_matches(rule, input_data):
                if rule.action == 'block':
                    blocking_rules.append(rule)
                else:
                    warning_rules.append(rule)

        if blocking_rules:
            messages = [f"**[{r.name}]**\n{r.message}" for r in blocking_rules]
            combined_message = "\n\n".join(messages)

            if hook_event == 'Stop':
                return {
                    "decision": "block",
                    "reason": combined_message,
                    "systemMessage": combined_message
                }
            elif hook_event == 'PreToolUse':
                return {
                    "hookSpecificOutput": {
                        "hookEventName": hook_event,
                        "permissionDecision": "deny",
                        "permissionDecisionReason": combined_message
                    },
                    "systemMessage": combined_message
                }
            elif hook_event in ['PostToolUse', 'UserPromptSubmit']:
                # permissionDecision is PreToolUse-only; these events block via decision/reason.
                return {
                    "decision": "block",
                    "reason": combined_message,
                    "systemMessage": combined_message
                }
            else:
                return {"systemMessage": combined_message}

        if warning_rules:
            messages = [f"**[{r.name}]**\n{r.message}" for r in warning_rules]
            combined_message = "\n\n".join(messages)
            response = {"systemMessage": combined_message}  # shown to the user only
            if hook_event in ['PreToolUse', 'PostToolUse', 'UserPromptSubmit']:
                # additionalContext is the supported channel that reaches Claude.
                response["hookSpecificOutput"] = {
                    "hookEventName": hook_event,
                    "additionalContext": combined_message
                }
            return response

        return {}

    def _rule_matches(self, rule: Rule, input_data: Dict[str, Any]) -> bool:
        """Check if rule matches input data."""
        tool_name = input_data.get('tool_name', '')
        tool_input = input_data.get('tool_input', {})

        if rule.tool_matcher:
            if not self._matches_tool(rule.tool_matcher, tool_name):
                return False

        if not rule.conditions:
            return False

        return all(
            self._check_condition(c, tool_name, tool_input, input_data)
            for c in rule.conditions
        )

    def _matches_tool(self, matcher: str, tool_name: str) -> bool:
        """Check if tool_name matches the matcher pattern (e.g., "Bash", "Edit|Write", "*")."""
        if matcher == '*':
            return True
        return tool_name in matcher.split('|')

    def _check_condition(self, condition: Condition, tool_name: str,
                         tool_input: Dict[str, Any], input_data: Dict[str, Any] = None) -> bool:
        """Check if a single condition matches."""
        field_value = self._extract_field(condition.field, tool_name, tool_input, input_data)
        if field_value is None:
            return False

        operator = condition.operator
        pattern = condition.pattern

        if operator == 'regex_match':
            return self._regex_match(pattern, field_value)
        elif operator == 'contains':
            return pattern in field_value
        elif operator == 'equals':
            return pattern == field_value
        elif operator == 'not_contains':
            return pattern not in field_value
        elif operator == 'starts_with':
            return field_value.startswith(pattern)
        elif operator == 'ends_with':
            return field_value.endswith(pattern)
        return False

    def _extract_field(self, field: str, tool_name: str,
                       tool_input: Dict[str, Any], input_data: Dict[str, Any] = None) -> Optional[str]:
        """Extract field value from tool input or hook input data."""
        # Direct tool_input fields
        if field in tool_input:
            value = tool_input[field]
            return value if isinstance(value, str) else str(value)

        # Stop and UserPromptSubmit event fields
        if input_data:
            if field == 'reason':
                return input_data.get('reason', '')
            elif field == 'user_prompt':
                return input_data.get('user_prompt', '')
            elif field == 'transcript':
                transcript_path = input_data.get('transcript_path')
                if transcript_path:
                    try:
                        with open(transcript_path, 'r') as f:
                            return f.read()
                    except (IOError, OSError, UnicodeDecodeError) as e:
                        print(f"Warning: Cannot read transcript {transcript_path}: {e}", file=sys.stderr)
                        return ''

        # Tool-specific field aliases
        if tool_name == 'Bash' and field == 'command':
            return tool_input.get('command', '')

        if tool_name in ['Write', 'Edit']:
            if field in ('content', 'new_text', 'new_string'):
                return tool_input.get('content') or tool_input.get('new_string', '')
            elif field in ('old_text', 'old_string'):
                return tool_input.get('old_string', '')
            elif field == 'file_path':
                return tool_input.get('file_path', '')

        if tool_name == 'MultiEdit':
            if field == 'file_path':
                return tool_input.get('file_path', '')
            elif field in ('new_text', 'content'):
                edits = tool_input.get('edits', [])
                return ' '.join(e.get('new_string', '') for e in edits)

        return None

    def _regex_match(self, pattern: str, text: str) -> bool:
        """Check if pattern matches text using cached compiled regex."""
        try:
            return bool(compile_regex(pattern).search(text))
        except re.error as e:
            print(f"Invalid regex pattern '{pattern}': {e}", file=sys.stderr)
            return False
