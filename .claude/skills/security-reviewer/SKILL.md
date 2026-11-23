---
name: security-reviewer
description: Security vulnerability detection and remediation skill. Provides OWASP Top 10 checklists, secret scanning patterns, and security review methodology.
allowed-tools: Read, Bash, Grep, Glob
agent: security-reviewer
context: fork
metadata:
  triggers: security review, vulnerability, OWASP, security audit, injection, XSS, SSRF, secret scan, hardcoded secret, CSP, Trusted Types, XSRF, CSRF, open redirect, token storage, bypassSecurityTrust, dangerouslySetInnerHTML
  related-skills: sast-configuration, threat-modeling, code-reviewer
  domain: security
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-11-22"
---

# Security Review Skill

## Iron Law

**Never approve a security review with unresolved CRITICAL or HIGH findings; always escalate to the human before proceeding past a security gate.**

## Purpose

Provides security review methodology, vulnerability checklists, and remediation patterns for application code.

## Process

1. **Load checklist** -- Read the security review checklist for review categories and severity levels
2. **Scan code** -- Use Grep/Glob to find security-sensitive patterns
3. **Evaluate** -- Check each finding against the checklist
4. **Report** -- Output findings with severity and remediation guidance

For the complete security review checklist and methodology:

Read [reference/security-review-checklist.md](reference/security-review-checklist.md)

## Reference Files

| File | Content | Load When |
|------|---------|-----------|
| [reference/security-review-checklist.md](reference/security-review-checklist.md) | OWASP Top 10, secrets scanning, auth/authz, injection, data protection checklists | All security reviews |
| [reference/pci-dss-requirements.md](reference/pci-dss-requirements.md) | PCI DSS 12 requirements, compliance levels (L1-L4), SAQ types, prohibited data, audit log requirements, common violations | Any feature touching payment card data, payment processors, or billing |
| [reference/owasp-infrastructure-baseline.md](reference/owasp-infrastructure-baseline.md) | 15 OWASP-mapped infrastructure controls — encryption at rest/transit, IAM least-privilege, network hardening, audit logging, secret rotation | Any IaC review (Terraform, GCP, AWS), cloud config review, infrastructure security |
| [reference/agent-guardrails-checklist.md](reference/agent-guardrails-checklist.md) | 12-layer AI agent guardrail pipeline, prompt injection defense, output validation, async audit logging, Constitutional AI — agent-specific security controls | Any LangGraph agent, agentic AI service, or AI feature with tool use |
| [reference/web-frontend-security.md](reference/web-frontend-security.md) | Browser-side rules for Angular 21 / React SPAs and static sites: XSS sinks, CSP + critical-CSS trade-off (tested), Trusted Types, token storage and API-origin allowlist (tested), Angular XSRF scope (tested), guards vs authorization, open-redirect-safe `returnUrl` (tested), OAuth PKCE, uploads, iframes/postMessage, public bundles, headers, privacy-aware logging; severity summary | Any change to `*.ts`/`*.tsx`/`*.html` in a web app, `index.html`, `angular.json`, hosting config or auth/session code |
| [reference/mcp-security.md](reference/mcp-security.md) | MCP spec MUST vs recommended practice, MCP server and tool-execution severities, `.mcp.json` review | Any MCP server, MCP tool or `.mcp.json` change |
| [reference/claude-config-security.md](reference/claude-config-security.md) | Manual security audit checklist for `.claude/` config (settings.json, hooks, agents, MCP servers, CLAUDE.md) — workspace-specific allow/deny/ask list review, hook injection surface, MCP supply chain risks | Before committing any `.claude/` directory changes |

## Error Handling

If target files/directories don't exist, report "Target not found" with the paths searched.
If a scan produces no findings, report "No security issues detected" with scope of scan.
