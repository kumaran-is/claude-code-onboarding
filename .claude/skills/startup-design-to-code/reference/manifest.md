# Workflow manifest

Path: `<product-root>/.startup-design/manifest.json`. Schema: `assets/manifest.schema.json`. Gate: `scripts/check-startup-design.py`.

Never store secrets, API keys, `Authorization` headers, or personal data. Stitch IDs are identifiers, not credentials.

## Fields

| Field | Role |
|---|---|
| `mode` | `standalone` (default) or `aidlc` — see [aidlc-and-standalone.md](aidlc-and-standalone.md) |
| `aidlc` | Bound intent dir, consumed files, handoff path (null in standalone) |
| `current_stage` | Highest gate the operator should resume |
| `stages.G*.status` | `NOT_RUN` · `IN_PROGRESS` · `PASS` · `FAIL` · `BLOCKED` |
| `artifacts` | Relative paths to brief, inventory, DESIGN.md, prototype |
| `decisions.g5` | `PROCEED` · `ITERATE` · `STOP` · `null` |
| `decisions.platform` | `flutter` · `angular` · `react` · `null` |
| `decisions.production_approved` | Human said yes to production translation |
| `stitch.tools_discovered` | Names returned by live MCP inspection this session |
| `mcp_evidence` | `none` · `discovered` · `mocked` |

`mcp_evidence: mocked` is for skill selftests only. A `PASS` on G3/G4/G5 with mocked evidence is a gate failure unless `--allow-mock`.

## Stage dependencies

```
G0 (brief) ──► G1 (Stitch preflight) ──► G3 (screens)
           └─► G2 (screen briefs)   ──┘
G3 PASS ──► G4 DESIGN.md ──► G5 prototype + g5 decision
G5 PROCEED ──► G6 architecture
G6 PASS AND production_approved ──► G7…G10   (standalone only)
G5 PROCEED ──► --handoff-aidlc               (aidlc mode; G7–G10 stay NOT_RUN)
```

- G1 may be `BLOCKED` after G0 `PASS`. Leave G0 artifacts in place.
- G3 cannot `PASS` while G1 is `BLOCKED` or `mcp_evidence` is `none`.
- G4 cannot `PASS` while DESIGN.md still lists token families in `omitted:`.
- G6 cannot `PASS` unless `decisions.g5 == PROCEED` and `decisions.platform` is set (Angular also needs `angular_ui_mode`).
- Standalone only: G7–G10 cannot leave `NOT_RUN` unless `production_approved` is true.
- Aidlc mode: G7–G10 stay `NOT_RUN` after `--handoff-aidlc`. Construction stays `/aidlc`.

Resume is idempotent: re-running a `PASS` stage must not wipe later evidence. Re-running `FAIL`/`BLOCKED` keeps artifacts and overwrites only that stage's status, reason and evidence list.

## Init

```bash
python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py \
  --root <product> --init --slug <slug> --idea "<one paragraph>"
python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py \
  --root <product> --set-stage G0 --stage-status PASS --evidence PRODUCT_BRIEF.md
python3 .claude/skills/startup-design-to-code/scripts/check-startup-design.py \
  --root <product> --init --slug <slug> --idea "<one paragraph>" --mode aidlc --bind-aidlc
```
