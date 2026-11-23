---
description: Autonomous metric-driven improvement loop. Measures codebase quality, proposes improvements, runs an implementer agent, keeps changes only if the metric improves — git reset on regression. Loops until stopped or max-iterations reached.
argument-hint: '[--metric METRIC] [--target N] [--max-iterations N]'
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent
---

# Autoresearch — Autonomous Improvement Loop

Measure → Improve → Verify → Keep or Rollback → Repeat.

Unlike `/ralph-loop` (which runs blind), this loop is **metric-gated**: changes are committed only when the score improves. Regressions are automatically rolled back with `git reset --hard`.

## Step 1 — Parse arguments and set defaults

```bash
# Arguments: $ARGUMENTS
# Claude: set these from the arguments above (defaults shown). No `$#`/`shift` loop: a Bash tool call has
# no positional parameters, so such a loop never runs and every option was silently ignored.
METRIC="all"              # --metric METRIC
TARGET_REDUCTION=5        # --target N
MAX_ITERATIONS=10         # --max-iterations N
ITERATION=1

echo ""
echo "🔬 Autoresearch loop starting"
echo "   Metric:         $METRIC"
echo "   Target/iter:    -$TARGET_REDUCTION issues per loop"
echo "   Max iterations: $MAX_ITERATIONS"
echo "   Stop:           /cancel-ralph  (shares the same cancel mechanism)"
echo ""
```

## Step 2 — Measure baseline

Run the baseline metric measurement now. Choose based on `$METRIC`:

**If `$METRIC` is `flutter` or `all`:**
```bash
FLUTTER_WARNINGS=$(flutter analyze 2>&1 | grep -c "warning\|error\|hint" || echo 0)
FLUTTER_TODOS=$(grep -r "TODO\|FIXME\|HACK" lib/ --include="*.dart" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
echo "Flutter warnings: $FLUTTER_WARNINGS"
echo "Flutter TODOs: $FLUTTER_TODOS"
```

**If `$METRIC` is `nestjs` or `all`:**
```bash
NESTJS_ANY=$(grep -r ": any\b\|as any\b" src/ --include="*.ts" 2>/dev/null | grep -v ".spec.ts" | wc -l | tr -d ' ' || echo 0)
NESTJS_CONSOLE=$(grep -r "console\.log\|console\.warn\|console\.error" src/ --include="*.ts" 2>/dev/null | grep -v ".spec.ts" | wc -l | tr -d ' ' || echo 0)
NESTJS_TODOS=$(grep -r "TODO\|FIXME" src/ --include="*.ts" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
echo "NestJS 'any' types: $NESTJS_ANY"
echo "NestJS console.log: $NESTJS_CONSOLE"
echo "NestJS TODOs: $NESTJS_TODOS"
```

**If `$METRIC` is `angular` or `all`:**
```bash
ANGULAR_ANY=$(grep -r ": any\b\|as any\b" projects/ --include="*.ts" 2>/dev/null | grep -v ".spec.ts" | wc -l | tr -d ' ' || echo 0)
ANGULAR_CONSOLE=$(grep -r "console\.log\|console\.warn\|console\.error" projects/ --include="*.ts" 2>/dev/null | grep -v ".spec.ts" | wc -l | tr -d ' ' || echo 0)
echo "Angular 'any' types: $ANGULAR_ANY"
echo "Angular console.log: $ANGULAR_CONSOLE"
```

**If `$METRIC` is `python` or `all`:**
```bash
PYTHON_TODOS=$(grep -r "TODO\|FIXME\|type: ignore" . --include="*.py" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
PYTHON_BARE_EXCEPT=$(grep -r "except:" . --include="*.py" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
echo "Python TODOs/type:ignore: $PYTHON_TODOS"
echo "Python bare except: $PYTHON_BARE_EXCEPT"
```

Compute total baseline score:
```bash
BASELINE_SCORE=$((${FLUTTER_WARNINGS:-0} + ${FLUTTER_TODOS:-0} + ${NESTJS_ANY:-0} + ${NESTJS_CONSOLE:-0} + ${NESTJS_TODOS:-0} + ${ANGULAR_ANY:-0} + ${ANGULAR_CONSOLE:-0} + ${PYTHON_TODOS:-0} + ${PYTHON_BARE_EXCEPT:-0}))
echo ""
echo "📊 Baseline score: $BASELINE_SCORE issues"
echo "   Target:         $((BASELINE_SCORE - TARGET_REDUCTION)) after this iteration"
echo ""
```

Save state:
```bash
mkdir -p "$CLAUDE_PROJECT_DIR/.claude"
cat > "$CLAUDE_PROJECT_DIR/.claude/autoresearch.local.md" <<EOF
---
active: true
iteration: 1
max_iterations: $MAX_ITERATIONS
metric: $METRIC
baseline_score: $BASELINE_SCORE
target_reduction: $TARGET_REDUCTION
started_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
---
EOF
```

## Step 3 — Improvement task for this iteration

Based on the metrics above, identify the **single highest-impact improvement** you can make this iteration:

**Priority order:**
1. `console.log` / `console.warn` / `console.error` in production TypeScript code → replace with proper NestJS `Logger` or Angular `ErrorHandler`
2. `: any` / `as any` type assertions → add proper TypeScript types
3. `TODO` / `FIXME` comments that have obvious fixes (not deferred decisions)
4. Flutter `warning`-level analyzer findings → fix the simplest ones
5. Python bare `except:` clauses → replace with typed `except ExceptionType:`

Pick **one category** per iteration. Fix the 3–5 easiest instances. Do not attempt to fix everything — small, reliable wins compound across iterations.

Make the changes now. Do not ask for confirmation — just fix.

## Step 4 — Re-measure and decide

After making changes, re-run the same measurement commands from Step 2.

```bash
NEW_SCORE=$((${FLUTTER_WARNINGS:-0} + ${FLUTTER_TODOS:-0} + ${NESTJS_ANY:-0} + ${NESTJS_CONSOLE:-0} + ${NESTJS_TODOS:-0} + ${ANGULAR_ANY:-0} + ${ANGULAR_CONSOLE:-0} + ${PYTHON_TODOS:-0} + ${PYTHON_BARE_EXCEPT:-0}))
DELTA=$((BASELINE_SCORE - NEW_SCORE))
```

**Decision gate:**

```bash
if [[ $NEW_SCORE -lt $BASELINE_SCORE ]]; then
  # ✅ IMPROVED — commit and continue
  git add -p   # stage only relevant changes
  git commit -m "refactor: autoresearch iteration $ITERATION — $DELTA issues resolved ($METRIC)

  Before: $BASELINE_SCORE issues | After: $NEW_SCORE issues | Delta: -$DELTA
  Loop: autoresearch iteration $ITERATION of $MAX_ITERATIONS"
  echo "✅ Iteration $ITERATION complete. Score: $BASELINE_SCORE → $NEW_SCORE (improved by $DELTA)"
else
  # ❌ NO IMPROVEMENT — rollback
  git reset --hard HEAD
  echo "❌ Iteration $ITERATION: no improvement (score unchanged or worse). Changes rolled back."
  echo "   Next iteration will attempt a different category."
fi
```

Update state file with new score:
```bash
sed -i '' "s/baseline_score: .*/baseline_score: $NEW_SCORE/" "$CLAUDE_PROJECT_DIR/.claude/autoresearch.local.md"
sed -i '' "s/iteration: .*/iteration: $((ITERATION + 1))/" "$CLAUDE_PROJECT_DIR/.claude/autoresearch.local.md"
```

## Step 5 — Loop or exit

```bash
NEXT_ITERATION=$((ITERATION + 1))

if [[ $NEXT_ITERATION -gt $MAX_ITERATIONS ]]; then
  rm -f "$CLAUDE_PROJECT_DIR/.claude/autoresearch.local.md"
  echo ""
  echo "🏁 Autoresearch complete after $MAX_ITERATIONS iterations."
  echo "   Final score: $NEW_SCORE (started at $BASELINE_SCORE)"
  echo "   Total improvement: $((BASELINE_SCORE - NEW_SCORE)) issues resolved"
else
  echo ""
  echo "🔄 Iteration $NEXT_ITERATION / $MAX_ITERATIONS starting..."
  echo "   Current score: $NEW_SCORE | Target: $((NEW_SCORE - TARGET_REDUCTION))"
fi
```

If `NEXT_ITERATION <= MAX_ITERATIONS`, go back to Step 3 with the new baseline score.

If `$NEXT_ITERATION > MAX_ITERATIONS` or the score has reached 0, clean up the state file and summarize total improvement.

## Rules

1. **One category per iteration** — fixing one type of issue reliably beats attempting everything poorly
2. **Never commit regressions** — `git reset --hard` is not failure, it's discipline
3. **Skip files you don't understand** — if fixing a `console.log` requires understanding complex business logic, move to the next instance
4. **No new functionality** — refactor only, no feature additions
5. **Run tests after each change** — if tests break, that counts as a regression, rollback
6. **Prefer quick wins** — 3 easy fixes > 1 hard fix per iteration
