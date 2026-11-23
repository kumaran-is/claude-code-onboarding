---
description: Cancel an active Ralph loop immediately. Deletes the state file so the loop stops on the next turn exit.
allowed-tools: Bash, Read
---

# Cancel Ralph Loop

```bash
RALPH_STATE_FILE="$CLAUDE_PROJECT_DIR/.claude/ralph-loop.local.md"

if [[ -f "$RALPH_STATE_FILE" ]]; then
  ITERATION=$(grep '^iteration:' "$RALPH_STATE_FILE" | sed 's/iteration: *//')
  rm "$RALPH_STATE_FILE"
  echo "🛑 Ralph loop cancelled after iteration ${ITERATION:-?}."
  echo "   The loop will exit cleanly on the next turn."
else
  echo "ℹ️  No active Ralph loop found."
fi

# Surface progress + escalated items from the surviving state file
RALPH_PROGRESS_FILE="$CLAUDE_PROJECT_DIR/.claude/ralph-state.local.md"
if [[ -f "$RALPH_PROGRESS_FILE" ]]; then
  echo ""
  echo "📄 Progress preserved at .claude/ralph-state.local.md"
  echo "   (re-running /ralph-loop resumes from it; delete it for an unrelated task)"
  ESCALATED=$(awk '/^## Escalated to humans/{flag=1; next} /^## /{flag=0} flag && NF' "$RALPH_PROGRESS_FILE")
  if [[ -n "$ESCALATED" ]] && [[ "$ESCALATED" != "- (none)" ]]; then
    echo ""
    echo "⚠️  Items escalated to humans during this loop:"
    echo "$ESCALATED"
  fi
fi
```
