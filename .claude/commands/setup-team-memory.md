---
name: setup-team-memory
description: One-shot setup of claude-mem + claude-mem-sync for team memory sharing. Installs, configures, and verifies end-to-end. Safe to run multiple times — skips steps already completed.
allowed-tools: Bash, Read, Write, Edit, Glob
---

# Setup Team Memory — claude-mem + claude-mem-sync

One-shot installer and verifier for your team memory stack.
Reference doc: `docs/workflows/setup-team-memory.md`

---

## Behaviour Rules

- Every step checks current state BEFORE acting — skip if already done
- Every action requires proof output before marking ✅
- If any prerequisite is missing → STOP immediately, report exactly what is needed
- Running this command twice must be safe (idempotent)
- Do NOT touch `.claude/rules/`, `CLAUDE.md`, or any existing hooks

---

## Step 1 — Detect Prerequisites

Run all detection checks. Collect results before proceeding.

```bash
echo "=== PREREQUISITE CHECK ==="

echo -n "Node.js: "
node --version 2>/dev/null || echo "MISSING"

echo -n "Bun: "
bun --version 2>/dev/null || echo "MISSING"

echo -n "GitHub CLI: "
gh --version 2>/dev/null | head -1 || echo "MISSING"

echo -n "npx: "
npx --version 2>/dev/null || echo "MISSING"

echo -n "Python3: "
python3 --version 2>/dev/null || echo "MISSING"
```

**Gate:** If Node.js is missing or version < 18, OR Bun is missing, OR gh is missing → STOP.
Report exactly:
```
BLOCKED — Prerequisites missing:
- [item]: install with [exact command]

Cannot proceed until prerequisites are resolved.
```

Do not continue to Step 2 until all prerequisites pass.

---

## Step 2 — Detect Current Installation State

Run all detection checks and build a state table.

```bash
echo "=== CURRENT STATE DETECTION ==="

echo -n "claude-mem worker: "
curl -s --max-time 3 http://localhost:37777/health 2>/dev/null && echo "" || echo "NOT_RUNNING"

echo -n "claude-mem DB: "
ls -lh ~/.claude-mem/claude-mem.db 2>/dev/null || echo "MISSING"

echo -n "claude-mem hooks in settings: "
grep -c "claude-mem" ~/.claude/settings.json 2>/dev/null || echo "0"

echo -n "claude-mem settings.json: "
ls ~/.claude-mem/settings.json 2>/dev/null || echo "MISSING"

echo -n "mem-sync CLI: "
mem-sync --version 2>/dev/null || echo "MISSING"

echo -n "mem-sync config: "
ls ~/.claude-mem-sync/config.json 2>/dev/null || echo "MISSING"

echo -n ".claude/memories/ folder: "
PROJ=$(git rev-parse --show-toplevel)
ls -d $PROJ/.claude/memories/ 2>/dev/null || echo "MISSING"

echo -n "GitHub Actions workflow: "
ls $PROJ/.github/workflows/merge-memories.yml 2>/dev/null || echo "MISSING"

echo -n ".gitignore entry: "
grep -c "memories/contributions" $PROJ/.gitignore 2>/dev/null || echo "0"

echo -n "Cron/launchd schedule: "
launchctl list 2>/dev/null | grep -i mem-sync | head -1 || crontab -l 2>/dev/null | grep mem-sync | head -1 || echo "NOT_SCHEDULED"
```

Print a detection summary table before proceeding:

```
DETECTION SUMMARY
─────────────────────────────────────────────────────
claude-mem worker        [RUNNING / NOT_RUNNING]
claude-mem DB            [EXISTS / MISSING]
claude-mem hooks         [N hooks / 0]
claude-mem configured    [EXISTS / MISSING]
mem-sync CLI             [vX.X.X / MISSING]
mem-sync config          [EXISTS / MISSING]
.claude/memories/        [EXISTS / MISSING]
merge-memories.yml       [EXISTS / MISSING]
.gitignore entry         [N / 0]
cron schedule            [SCHEDULED / NOT_SCHEDULED]
─────────────────────────────────────────────────────
```

---

## Step 3 — Install claude-mem

**Skip this step if:** claude-mem DB exists AND hook count > 0 AND worker responds.

If any of the three are missing, run:

```bash
echo "=== INSTALLING claude-mem ==="
npx claude-mem install
```

Wait for installer to complete, then verify:

```bash
echo "=== VERIFYING claude-mem INSTALL ==="

# Give worker time to start
sleep 5

echo -n "Worker health: "
curl -s --max-time 5 http://localhost:37777/health || echo "FAILED"

echo -n "DB created: "
ls -lh ~/.claude-mem/claude-mem.db 2>/dev/null || echo "FAILED — DB not created"

echo -n "Hooks registered: "
HOOK_COUNT=$(grep -c "claude-mem" ~/.claude/settings.json 2>/dev/null || echo "0")
echo "$HOOK_COUNT hooks found"
```

**Gate:** If `HOOK_COUNT` is 0 after install → STOP.
```
BLOCKED — claude-mem install did not register hooks.
Evidence: grep -c "claude-mem" ~/.claude/settings.json returned 0
Fix: Try running manually: npx claude-mem install
     Then check: cat ~/.claude/settings.json | grep claude-mem
```

---

## Step 4 — Configure claude-mem

**Skip this step if:** `~/.claude-mem/settings.json` already exists with `CLAUDE_MEM_FOLDER_CLAUDEMD_ENABLED` set to `"false"`.

Check first:
```bash
cat ~/.claude-mem/settings.json 2>/dev/null | grep -c "CLAUDE_MEM_FOLDER_CLAUDEMD_ENABLED" || echo "0"
```

If count is 0, write config:

```bash
echo "=== CONFIGURING claude-mem ==="

cat > ~/.claude-mem/settings.json << 'EOF'
{
  "CLAUDE_MEM_MODEL": "sonnet",
  "CLAUDE_MEM_PROVIDER": "claude",
  "CLAUDE_MEM_MODE": "code",
  "CLAUDE_MEM_CONTEXT_OBSERVATIONS": "50",
  "CLAUDE_MEM_WORKER_PORT": "37777",
  "CLAUDE_MEM_WORKER_HOST": "127.0.0.1",
  "CLAUDE_MEM_DATA_DIR": "~/.claude-mem",
  "CLAUDE_MEM_SKIP_TOOLS": "ListMcpResourcesTool,SlashCommand,Skill,TodoWrite,AskUserQuestion",
  "CLAUDE_MEM_FOLDER_CLAUDEMD_ENABLED": "false",
  "CLAUDE_MEM_LOG_LEVEL": "INFO",
  "CLAUDE_MEM_CONTEXT_SESSION_COUNT": "10",
  "CLAUDE_MEM_CONTEXT_FULL_COUNT": "5",
  "CLAUDE_MEM_CONTEXT_FULL_FIELD": "narrative"
}
EOF
```

Verify:
```bash
echo "Verifying settings.json..."
python3 -m json.tool ~/.claude-mem/settings.json > /dev/null && echo "CONFIG_VALID" || echo "CONFIG_INVALID — JSON syntax error"
cat ~/.claude-mem/settings.json
```

**Gate:** If `CONFIG_INVALID` → STOP and show exact file content for debugging.

Note: `CLAUDE_MEM_FOLDER_CLAUDEMD_ENABLED: false` prevents claude-mem from writing
its own CLAUDE.md files — this workspace already has a best-in-class `.claude/` setup.

---

## Step 5 — Install claude-mem-sync

**Skip this step if:** `mem-sync --version` succeeds.

```bash
echo "=== INSTALLING claude-mem-sync ==="

# Verify claude-mem DB exists first (required by claude-mem-sync)
if [ ! -f ~/.claude-mem/claude-mem.db ]; then
  echo "BLOCKED — claude-mem DB missing at ~/.claude-mem/claude-mem.db"
  echo "Complete Step 3 (install claude-mem) before installing claude-mem-sync"
  exit 1
fi

claude plugin marketplace add lopadova/claude-mem-sync
claude plugin install claude-mem-sync@claude-mem-sync
```

The plugin ships as TypeScript source — build and link the CLI after install:

```bash
cd ~/.claude/plugins/marketplaces/claude-mem-sync
# Each step's OWN exit code (a pipe into tail would report tail's status); stop at the first non-zero
bun install > /tmp/mem-sync-install.log 2>&1; echo "INSTALL EXIT:$?"; tail -3 /tmp/mem-sync-install.log
bun run build > /tmp/mem-sync-build.log 2>&1; echo "BUILD EXIT:$?"; tail -5 /tmp/mem-sync-build.log
npm link > /tmp/mem-sync-link.log 2>&1; echo "LINK EXIT:$?"; tail -3 /tmp/mem-sync-link.log
```

Verify:
```bash
echo -n "mem-sync version: "
mem-sync --version 2>/dev/null || echo "FAILED — mem-sync CLI not found after build+link"

echo -n "Plugin listed: "
claude plugin list 2>/dev/null | grep claude-mem-sync || echo "NOT FOUND in plugin list"
```

**Gate:** If `mem-sync --version` fails after build → STOP.
```
BLOCKED — claude-mem-sync build or link failed.
Fix: cd ~/.claude/plugins/marketplaces/claude-mem-sync && bun install && bun run build && npm link
     Then verify: mem-sync --version
```

---

## Step 6 — Create .claude/memories/ Folder Structure

**Skip this step if:** `.claude/memories/merged/your-project/` exists.

```bash
echo "=== CREATING MEMORIES FOLDER STRUCTURE ==="
PROJ=$(git rev-parse --show-toplevel)
PROJECT_NAME=$(basename $PROJ)

mkdir -p $PROJ/.claude/memories/merged/$PROJECT_NAME
mkdir -p $PROJ/.claude/memories/contributions

# Placeholder so merged dir is tracked by git
touch $PROJ/.claude/memories/merged/$PROJECT_NAME/.gitkeep

echo "Verifying folder structure..."
ls -la $PROJ/.claude/memories/
ls -la $PROJ/.claude/memories/merged/$PROJECT_NAME/
```

---

## Step 7 — Add GitHub Actions Workflow

**Skip this step if:** `.github/workflows/merge-memories.yml` already exists.

```bash
echo "=== ADDING GITHUB ACTIONS WORKFLOW ==="
PROJ=$(git rev-parse --show-toplevel)

mkdir -p $PROJ/.github/workflows

curl -sL https://raw.githubusercontent.com/lopadova/claude-mem-sync/main/templates/github-action/merge-memories.yml \
  -o $PROJ/.github/workflows/merge-memories.yml

echo -n "Workflow file lines: "
wc -l $PROJ/.github/workflows/merge-memories.yml

echo -n "Workflow content valid: "
python3 -c "
import sys
content = open('$PROJ/.github/workflows/merge-memories.yml').read()
checks = ['name: Merge Developer Memories', 'contributions/**/*.json', 'ci-merge', 'bun']
missing = [c for c in checks if c not in content]
if missing:
    print(f'INVALID — missing: {missing}')
    sys.exit(1)
print('VALID')
"

echo "First 10 lines of workflow:"
head -10 $PROJ/.github/workflows/merge-memories.yml
```

**Gate:** If line count is 0 → download failed → STOP.
```
BLOCKED — workflow file download failed (0 lines).
Check: curl connectivity to raw.githubusercontent.com
Manual fallback: download from https://github.com/lopadova/claude-mem-sync/blob/main/templates/github-action/merge-memories.yml
```

---

## Step 8 — Update .gitignore

**Skip this step if:** `.gitignore` already contains `memories/contributions`.

```bash
echo "=== UPDATING .gitignore ==="
PROJ=$(git rev-parse --show-toplevel)

ENTRY_COUNT=$(grep -c "memories/contributions" $PROJ/.gitignore 2>/dev/null || echo "0")

if [ "$ENTRY_COUNT" = "0" ]; then
  printf '\n# claude-mem-sync: raw contributions ignored, merged output committed\n.claude/memories/contributions/\n!.claude/memories/merged/\n' >> $PROJ/.gitignore
  echo "Entry added."
else
  echo "Entry already present — skipping."
fi

echo "Verifying .gitignore entries:"
grep -n "memories" $PROJ/.gitignore
```

---

## Step 9 — Write mem-sync config

**Skip this step if:** `~/.claude-mem-sync/config.json` already exists.

`mem-sync init` is an interactive wizard and cannot run non-interactively in a bash block.
Write the config directly instead — this is equivalent to running the wizard for your project.

The developer name defaults to the current user (`$USER`). Each developer will have their own
config with their own name — this is correct and expected.

```bash
echo "=== CONFIGURING mem-sync ==="

mkdir -p ~/.claude-mem-sync

DB_PATH=$(python3 -c "import os; print(os.path.expanduser('~/.claude-mem/claude-mem.db'))")
DEV_NAME="${USER}"

python3 - << PYEOF
import json, os

db_path = os.path.expanduser("~/.claude-mem/claude-mem.db")
dev_name = os.environ.get("USER", "developer")
config_path = os.path.expanduser("~/.claude-mem-sync/config.json")

config = {
    "global": {
        "devName": dev_name,
        "claudeMemDbPath": db_path,
        "mergeCapPerProject": 500,
        "exportSchedule": "friday:16:00",
        "distillation": {
            "enabled": False,
            "allowExternalApi": False
        }
    },
    "projects": {
        "your-project": {
            "enabled": True,
            "remote": {
                "type": "github",
                "repo": "your-org/your-project",
                "branch": "develop",
                "autoMerge": True
            },
            "export": {
                "types": ["decision", "bugfix", "feature", "discovery"],
                "keywords": ["architecture", "breaking", "migration", "uv", "melos", "adk"],
                "tags": ["#shared"]
            }
        }
    }
}

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)

print(f"Config written for dev: {dev_name}")
print(f"DB path: {db_path}")
PYEOF
```

Verify config written:
```bash
echo "=== VERIFYING mem-sync config ==="

echo -n "Config file exists: "
ls ~/.claude-mem-sync/config.json 2>/dev/null || echo "MISSING — write failed"

echo -n "Config JSON valid: "
python3 -m json.tool ~/.claude-mem-sync/config.json > /dev/null && echo "VALID" || echo "INVALID"

echo "Config contents:"
cat ~/.claude-mem-sync/config.json
```

**Gate:** If config missing after write → STOP.
```
BLOCKED — ~/.claude-mem-sync/config.json was not created.
Fix: Run the python3 block above manually in a terminal.
```

---

## Step 10 — Install Cron Schedule

**Skip this step if:** launchd or cron already has a mem-sync entry.

```bash
echo "=== INSTALLING SCHEDULE ==="

mem-sync schedule install

echo "Verifying schedule installed:"
launchctl list 2>/dev/null | grep -i mem-sync | head -3 \
  || crontab -l 2>/dev/null | grep mem-sync | head -3 \
  || echo "NOTE: Schedule may be installed but verification command differs on this OS."
```

---

## Step 11 — End-to-End Verification

Run all verification checks and produce the final report.

```bash
echo "=== END-TO-END VERIFICATION ==="

# 1. Node version
NODE_VER=$(node --version 2>/dev/null || echo "MISSING")
echo "Node.js: $NODE_VER"

# 2. Bun version
BUN_VER=$(bun --version 2>/dev/null || echo "MISSING")
echo "Bun: $BUN_VER"

# 3. Worker health
echo -n "claude-mem worker: "
WORKER=$(curl -s --max-time 3 http://localhost:37777/health 2>/dev/null && echo "HEALTHY" || echo "NOT_RUNNING")
echo "$WORKER"

# 4. DB size
echo -n "claude-mem DB: "
ls -lh ~/.claude-mem/claude-mem.db 2>/dev/null || echo "MISSING"

# 5. Hook count
HOOK_COUNT=$(grep -c "claude-mem" ~/.claude/settings.json 2>/dev/null || echo "0")
echo "claude-mem hooks registered: $HOOK_COUNT"

# 6. Settings config
echo -n "claude-mem settings: "
python3 -m json.tool ~/.claude-mem/settings.json > /dev/null 2>&1 && echo "VALID JSON" || echo "INVALID or MISSING"

# 7. mem-sync version
MEM_SYNC_VER=$(mem-sync --version 2>/dev/null || echo "MISSING")
echo "mem-sync: $MEM_SYNC_VER"

# 8. mem-sync config
echo -n "mem-sync config: "
python3 -m json.tool ~/.claude-mem-sync/config.json > /dev/null 2>&1 && echo "VALID JSON" || echo "INVALID or MISSING"

# 9. Memories folder
echo -n ".claude/memories/ folder: "
ls -d "$(git rev-parse --show-toplevel)/.claude/memories/" 2>/dev/null && echo "EXISTS" || echo "MISSING"

# 10. GitHub Actions workflow
echo -n "merge-memories.yml: "
wc -l "$(git rev-parse --show-toplevel)/.github/workflows/merge-memories.yml" 2>/dev/null || echo "MISSING"

# 11. .gitignore
echo -n ".gitignore entry: "
grep -c "memories/contributions" "$(git rev-parse --show-toplevel)/.gitignore" 2>/dev/null || echo "0"

# 12. mem-sync status
echo ""
echo "mem-sync status:"
mem-sync status 2>/dev/null || echo "status command failed"

# 13. Export preview (dry-run, no push)
echo ""
echo "Export preview (dry-run):"
mem-sync preview --project your-project 2>/dev/null || echo "preview failed — no observations yet is normal on first install"
```

---

## Step 12 — Final Report

Print a complete verdict table based on all Step 11 outputs:

```
══════════════════════════════════════════════════════════
  /setup-team-memory — Final Report
  Project: your-project
══════════════════════════════════════════════════════════

PREREQUISITES
  Node.js ≥18          [✅ vX.X.X  / ❌ MISSING]
  Bun                  [✅ vX.X.X  / ❌ MISSING]
  GitHub CLI           [✅ vX.X.X  / ❌ MISSING]

CLAUDE-MEM (individual session memory)
  Worker running       [✅ HEALTHY / ❌ NOT_RUNNING]
  Database             [✅ exists  / ❌ MISSING]
  Hooks registered     [✅ N hooks / ❌ 0 hooks]
  Settings configured  [✅ VALID   / ❌ MISSING]

CLAUDE-MEM-SYNC (team sharing layer)
  mem-sync CLI         [✅ vX.X.X  / ❌ MISSING]
  Config file          [✅ VALID   / ❌ MISSING]
  .claude/memories/    [✅ exists  / ❌ MISSING]
  GitHub Actions       [✅ N lines / ❌ MISSING]
  .gitignore updated   [✅ entry   / ❌ missing]
  Cron schedule        [✅ active  / ⚠️  verify manually]

══════════════════════════════════════════════════════════
  Overall: ✅ READY  /  ❌ NOT READY
══════════════════════════════════════════════════════════
```

If NOT READY, for each ❌ item report:
```
❌ [item]
   Evidence: [exact command output that showed failure]
   Fix: [exact command to resolve]
```

---

## Step 13 — Next Steps (Print After Successful Setup)

If overall verdict is READY, print:

```
══════════════════════════════════════════════════════════
  SETUP COMPLETE — What to do next
══════════════════════════════════════════════════════════

1. COMMIT the new files to develop:

   git add .claude/memories/ .github/workflows/merge-memories.yml .gitignore
   git commit -m "chore: add claude-mem-sync team memory infrastructure"
   git push origin develop

2. SHARE this doc with all 4 teammates:
   docs/workflows/setup-team-memory.md
   → Each teammate runs: /setup-team-memory

3. AFTER your first week of coding, share your observations:
   mem-sync preview --project your-project   # see what will be shared
   mem-sync export --project your-project    # push to team repo

4. IMPORT teammate observations after they export:
   mem-sync import --project your-project

5. WEEKLY (automated via cron):
   Export: Fridays 4pm
   Import: Saturdays 9am

6. MONTHLY (optional):
   mem-sync distill --project your-project   # extract rules → .claude/rules/

Full reference: docs/workflows/setup-team-memory.md
══════════════════════════════════════════════════════════
```

---

## Usage

```
/setup-team-memory
```

No arguments needed. Safe to run on any team member's machine.
Skips steps already completed — run again anytime to re-verify state.
