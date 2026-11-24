#!/usr/bin/env bash
# Negative controls for the AC-01..AC-18 fixture: disable one deterministic control at a time; pytest MUST
# exit 1 for each. Exit 0 = every control is load-bearing, 1 = a control can be removed without a test failing.
# Logs go to LOG_DIR (default: a new temp dir); keep the venv out of the repo with UV_PROJECT_ENVIRONMENT.
set -u
cd "$(dirname "$0")"
log_dir="${LOG_DIR:-$(mktemp -d)}"
controls=(least_privilege quarantine authority_per_turn state_machine canary_detector secret_scanner caller_bound_scope
  authz_before_retrieval outbound_allowlist surface_lock strict_schema batch_limit confirmation audit ingestion_review
  ingestion_sanitize suppress_global_metadata input_cap budget max_output_tokens model_registry tool_server_intake
  html_encoding parameterized_sql no_shell min_fields pii_secret_scanner grounding per_key_quota ui_schema)
fail=0
for ctl in "${controls[@]}"; do
  DISABLE_CONTROL="$ctl" PYTHONDONTWRITEBYTECODE=1 uvx --from uv==0.13.9 uv run --frozen --python 3.14.10 pytest -rf > "$log_dir/neg-$ctl.log" 2>&1
  rc=$?
  failed=$(grep -E '^FAILED' "$log_dir/neg-$ctl.log" | sed 's/^FAILED test_attack_classes.py:://; s/ - .*//' | tr '\n' ' ')
  if [ "$rc" -eq 1 ]; then printf 'NEG-OK\t%s\texit=%s\t%s\n' "$ctl" "$rc" "$failed"
  else printf 'NEG-MISSING\t%s\texit=%s\n' "$ctl" "$rc"; fail=1; fi
done
echo "logs: $log_dir"
exit $fail
