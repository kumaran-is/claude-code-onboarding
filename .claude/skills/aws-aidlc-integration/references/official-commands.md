# Official AWS AI-DLC commands (do not fork)

Source of truth: [Getting Started](https://awslabs.github.io/aidlc-workflows/guide/01-getting-started/) and
[Install and Lifecycle](https://awslabs.github.io/aidlc-workflows/guide/18-install-and-lifecycle/).
Repository: https://github.com/awslabs/aidlc-workflows

Discover the current **stable** tag at run time. Do not bake a release id into this toolkit.

```bash
gh release view --repo github.com/awslabs/aidlc-workflows --json tagName,isPrerelease --jq '{tag:.tagName,pre:.isPrerelease}'
# or: python3 .../check-aidlc-setup.py --latest-stable
```

Skip preview tags (`*-preview.*`, `prerelease: true`). Pin with `--pin X.Y.Z` when the team requires it.

## Install (native CLI) — download, inspect, attest, then run

**Never pipe the remote installer into a shell.** Official lifecycle docs show writing `install.sh` to a file first. Preferred when `gh` can attest:

```bash
tag="$(gh release view --repo github.com/awslabs/aidlc-workflows --json tagName --jq .tagName)"
# refuse if the tag contains "preview"
tmp="$(mktemp -d)"
gh release download "$tag" --repo github.com/awslabs/aidlc-workflows --dir "$tmp" \
  --pattern install.sh --pattern aidlc-release.intoto.jsonl
# INSPECT "$tmp/install.sh" before continuing
gh attestation verify "$tmp/install.sh" \
  --bundle "$tmp/aidlc-release.intoto.jsonl" \
  --repo awslabs/aidlc-workflows \
  --signer-workflow awslabs/aidlc-workflows/.github/workflows/release.yml \
  --hostname github.com \
  --source-ref "refs/tags/$tag"
# human approval, then:
sh "$tmp/install.sh" --version "${tag#v}"
rm -rf "$tmp"
export PATH="$HOME/.local/bin:$PATH"
aidlc version
```

Pin: pass that exact `--version`. Windows: download `install.ps1` the same way, then `& install.ps1 -Version X.Y.Z` (not `iex`).

The installer still verifies SHA-256 even when `gh` attestation is unavailable. Missing `gh` is a warning, not a reason to pipe.

## Configure a Claude Code project

From the **project root** (AI-DLC does not walk up to a git root):

```bash
aidlc config --harness claude --dry-run
# human approval of create/update/merge counts
aidlc config --harness claude --mcp none --yes
aidlc doctor
```

`--yes` does not enable MCP servers. `--mcp defaults` needs an extra explicit ask.
`--force` is forbidden on a toolkit project.

Pin a project: `aidlc config --pin X.Y.Z` then refresh. Commit only `.aidlc-version`.

## Upgrade

```bash
aidlc update
aidlc config --harness claude --dry-run
aidlc config --harness claude --mcp none --yes
aidlc doctor
```

Do not overwrite team customizations; official config merges `.claude/settings.json` by entry.

## Health and versions

```bash
aidlc version          # installed
aidlc doctor
# available: GitHub releases/latest (stable only)
```

`/aidlc` is the upstream Claude Code command after config. `/aidlc --doctor` is also documented by AWS.

## Uninstall / recovery

```bash
aidlc uninstall
# leftover paths are reported; --purge still does not delete unrelated content
```

Partial setup (workspace without CLI, or CLI without `aidlc/`): see `check-aidlc-setup.py --recovery`. Do not delete `aidlc/` on a guess.

Docs: [Install and Lifecycle](https://awslabs.github.io/aidlc-workflows/guide/18-install-and-lifecycle/).
