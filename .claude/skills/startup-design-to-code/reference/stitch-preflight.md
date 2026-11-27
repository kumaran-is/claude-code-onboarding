# Stitch MCP preflight (G1)

Do not hardcode **tool names**, model IDs or auth header **values**. Official pages change. The toolkit already registers the server in `.mcp.json`.

## Toolkit registration

`.mcp.json` server `stitch`: HTTP `https://stitch.googleapis.com/mcp`, header `X-Goog-Api-Key: ${STITCH_API_KEY}`. Source: https://stitch.google.com/docs/mcp/setup (canonical title “Stitch via MCP”; GET of the MCP URL returns 405, which is expected for Streamable HTTP). Create the key in Stitch Settings; export `STITCH_API_KEY` in the environment. Never write the key into git.

## Live sources (re-fetch this session)

1. Stitch MCP setup: https://stitch.google.com/docs/mcp/setup/
2. DESIGN.md overview: https://stitch.google.com/docs/design-md/overview/
3. Stitch skills: https://stitch.google.com/docs/skills/get-started/
4. Skills catalog: https://github.com/google-labs-code/stitch-skills
5. DESIGN.md format + CLI: https://github.com/google-labs-code/design.md

If a fetch returns empty or contradicts a blog post, **the official page wins**, then the GitHub README. Third-party setup posts are not evidence.

## Procedure

1. Inspect the agent's current MCP catalog (Cursor: dynamic namespaces; Claude Code: `/mcp` or `claude mcp list`).
2. Find the `stitch` server. If it is missing or disconnected: **G1 BLOCKED**. Typical cause is an unset `STITCH_API_KEY`. Do not invent screens. Do not add a second Stitch server or write keys into `.mcp.json`.
3. List the **actual** tools and read each schema before the first call. Record names in `stitch.tools_discovered`. Set `mcp_evidence: discovered`.
4. Prefer a harmless discovery/list call. Never log response bodies that might contain keys.
5. Official skills (`stitch::generate-design`, `stitch::design-md`, `stitch::extract-design-md`, …) are **optional**. Check whether they are already installed before suggesting `npx plugins add google-labs-code/stitch-skills`. Do not vendor them into this toolkit. They do not replace Flutter/Angular translation (no official Flutter/Angular Stitch skill is assumed).
6. Auth lives in the user's environment or user-scope MCP config. Never write keys into the manifest, DESIGN.md, screen inventory, git, or command transcripts.

## When BLOCKED

Keep G0/G2 files. Mark G3–G5 `NOT_RUN` or `BLOCKED` with the same reason. If the key is missing: `export STITCH_API_KEY=…` from Stitch Settings (https://stitch.google.com/docs/mcp/setup), restart the session, then `/startup-design resume`.

## Mapping jobs to *discovered* tools

The Stitch SDK README currently documents example tool names (`create_project`, `list_projects`, `generate_screen_from_text`, `get_screen`, `edit_screens`, `generate_variants`). Treat those as **hints**, not a guarantee — bind jobs by **capability** from this session's `tools/list`:

| Job | Bind a discovered tool that |
|---|---|
| Create/select project | creates or lists a design project |
| Generate screen | creates a screen from a brief |
| Edit screen | patches one screen |
| Variants | generates alternatives of one screen |
| Fetch reference | returns preview, HTML, or metadata for a screen ID |

If a job has no matching tool, that job is BLOCKED; the others may continue.
