---
name: domain-finder
description: This skill should be used when starting a new project or brand and needing to find a registrable domain. It brainstorms creative domain names and checks real availability via DNS/WHOIS.
argument-hint: "[project or brand keywords]"
allowed-tools: Bash, WebFetch, WebSearch
metadata:
  triggers: domain name, domain availability, brand name, domain registration, DNS check, domain search, check domain
  related-skills: architecture-design, ddd-architect, documentation-generation
  domain: workflow
  role: specialist
  scope: analysis
  output-format: report
last-reviewed: "2026-03-15"
---

## Iron Law

Never register a domain without verifying availability via live lookup; never suggest a domain based on pattern-matching alone.

# Domain Finder Skill

Generate creative, brandable domain names and verify which ones are actually available to register.

## Workflow

### Step 1 — Understand the Project
Gather from the user (ask if not provided):
- What they're building (product, SaaS, agency, portfolio, etc.)
- Target audience (developers, consumers, enterprise, etc.)
- Preferred keywords or themes (optional)
- TLD preferences (default: .com, .io, .dev, .ai, .app)
- Constraints (max length, no hyphens, must include a word, etc.)

### Step 2 — Generate Names
Create 15–20 candidates across these categories:

- **Descriptive** — says what it does (e.g. `codeshare`, `snippetbox`)
- **Compound** — two short words fused (e.g. `devpaste`, `buildkit`)
- **Invented** — brandable neologisms (e.g. `codezy`, `snipflow`)
- **Short & punchy** — ≤ 8 chars, memorable (e.g. `clipp`, `patchd`)

**Naming rules:**
- Under 15 characters (shorter is better)
- No hyphens — hard to say out loud
- No numbers — confusing verbally
- Easy to spell and pronounce
- Doesn't accidentally spell something bad in another language

### Step 3 — Check Availability

Read `reference/domain-check-scripts.md` for DNS batch check scripts, WHOIS deep check commands, and result interpretation guide.

**Quick DNS check (inline example):**
```bash
# Check a single domain — NXDOMAIN means available; any A/CNAME record means taken
dig +short codeshare.io A
# Returns empty → likely available
# Returns an IP   → registered

# Batch check multiple names
for d in codeshare.io devpaste.io snipflow.app; do
  result=$(dig +short "$d" A)
  if [ -z "$result" ]; then echo "AVAILABLE: $d"; else echo "TAKEN:     $d"; fi
done
```

> Note: A clean DNS response does not guarantee the domain is unregistered — some registered domains have no DNS records. Always follow up with a WHOIS check for any candidate before presenting it as available.

### Step 4 — Present Results

Read `reference/domain-check-scripts.md` for the output format template and TLD quick reference table.

### Step 5 — Social Handle Check (Optional)

Read `reference/domain-check-scripts.md` for social media handle checking scripts.

## Reference Files

| File | Content |
|------|---------|
| `reference/domain-check-scripts.md` | DNS/WHOIS scripts, TLD reference, output template, social handle checks |

## Error Handling

**DNS lookup failures**: Retry with a different DNS resolver. Timeout does not mean the domain is available — treat timeouts as "status unknown."

**WHOIS rate limiting**: Space queries at least 2 seconds apart. If rate-limited, report partial results and retry later.

**All candidates taken (no available domains found)**:
Stop. Do not present taken domains as options. Report: "All N candidates are registered. Generating N more names — adjusting strategy to [shorter / different root word / invented neologisms]." Re-run Step 2 with a new naming strategy before presenting results.

**Domain lookup returns no results / tool unavailable**:
If `dig` and `whois` are both unavailable (sandboxed environment), fall back to `WebFetch` against a registrar availability API (e.g., `https://instantdomainsearch.com/?q=<name>`) and parse the response. If no lookup method is available, state this explicitly: "Cannot verify availability in this environment — presenting name candidates only. Verify each at a registrar before use."
