# MCP Server Evaluation -- Running Evaluations

## Setup

1. **Install Dependencies**

   ```bash
   uv venv -p 3.14 && uv pip install -r scripts/requirements.txt   # pins anthropic==2.12.0, mcp==2.3.0
   ```

   `connections.py` uses the MCP Python SDK v2 `Client`, which negotiates the protocol era itself (2026-07-28 via `server/discover`, falling back to `initialize` for 2025-era servers).

2. **Set API Key**

   ```bash
   export ANTHROPIC_API_KEY="$(your-secret-manager read anthropic-api-key)"   # never commit or paste the key
   ```

## Evaluation File Format

Evaluation files use XML format with `<qa_pair>` elements:

```xml
<evaluation>
   <qa_pair>
      <question>Find the project created in Q2 2024 with the highest number of completed tasks. What is the project name?</question>
      <answer>Website Redesign</answer>
   </qa_pair>
   <qa_pair>
      <question>Search for issues labeled as "bug" closed in March 2024. Which user closed the most? Provide their username.</question>
      <answer>sarah_dev</answer>
   </qa_pair>
</evaluation>
```

## Running Evaluations

The evaluation script (`scripts/evaluation.py`) supports the two current transports: stdio and Streamable HTTP. The deprecated HTTP+SSE transport is rejected with an error; migrate such servers to Streamable HTTP first.

**Important:**
- **stdio transport**: The script automatically launches and manages the MCP server process. Do not run the server manually.
- **http transport**: Start the MCP server separately before running the evaluation.

### 1. Local STDIO Server

```bash
uv run python scripts/evaluation.py \
  -t stdio \
  -c python \
  -a my_mcp_server.py \
  evaluation.xml
```

With environment variables:
```bash
uv run python scripts/evaluation.py \
  -t stdio \
  -c python \
  -a my_mcp_server.py \
  -e UPSTREAM_API_KEY="$UPSTREAM_API_KEY" \
  -e DEBUG=true \
  evaluation.xml
```

TypeScript server (build first; `-c` takes the Node binary, `-a` the compiled ESM entry):
```bash
npm run build
uv run python scripts/evaluation.py \
  -t stdio \
  -c node \
  -a dist/stdio.js \
  evaluation.xml
```

Verified 2026-11-23: the connection layer (`connections.create_connection`, Python SDK v2 `mcp==2.3.0`) spawned a Node 26.13.1 TypeScript SDK v2 server over stdio and listed its tools (exit 0); a missing entry file exited 1. The full model-driven run needs `ANTHROPIC_API_KEY` and was not run here.

### 2. Streamable HTTP

```bash
uv run python scripts/evaluation.py \
  -t http \
  -u https://example.com/mcp \
  -H "Authorization: Bearer $MCP_TOKEN" \
  evaluation.xml
```

## Command-Line Options

```
usage: evaluation.py [-h] [-t {stdio,http}] [-m MODEL] [-c COMMAND] [-a ARGS [ARGS ...]]
                     [-e ENV [ENV ...]] [-u URL] [-H HEADERS [HEADERS ...]] [-o OUTPUT]
                     eval_file

Evaluate MCP servers using test questions

positional arguments:
  eval_file             Path to evaluation XML file

options:
  -h, --help            show this help message and exit
  -t, --transport {stdio,http}
                        Transport type: stdio or http (Streamable HTTP). Default: stdio
  -m, --model MODEL     Claude model to use (default: claude-opus-5-5)
  -o, --output OUTPUT   Output file for evaluation report (default: stdout)

stdio options:
  -c, --command COMMAND
                        Command to run MCP server (stdio only)
  -a, --args ARGS [ARGS ...]
                        Arguments for the command (stdio only)
  -e, --env ENV [ENV ...]
                        Environment variables in KEY=VALUE format (stdio only)

http options:
  -u, --url URL         MCP server URL (http only)
  -H, --header HEADERS [HEADERS ...]
                        HTTP headers in 'Key: Value' format (http only)
```

Model behaviour: the default model is `claude-opus-5-5`. Requests enable the server-side refusal fallback (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`), so a declined turn may be completed by another model; a task the whole chain refuses is scored as no answer. Every run calls the Claude API and costs money: size the question set before running it repeatedly.

Tool results are sent back with the MCP `is_error` flag, and per-tool metrics count calls whose result had `is_error: true`. A tool that returns an error message without setting `isError` is counted as a success: if the summary shows failures the error count misses, fix the server.

## Output

The evaluation script generates a detailed report including:

- **Summary Statistics**: Accuracy (correct/total), average task duration, average tool calls per task, total tool calls
- **Per-Task Results**: Prompt, expected response, actual response, correct/incorrect, duration, tool call details, agent feedback

### Save Report to File

```bash
uv run python scripts/evaluation.py \
  -t stdio \
  -c python \
  -a my_server.py \
  -o evaluation_report.md \
  evaluation.xml
```

## Complete Example Workflow

1. **Create evaluation file** (`my_evaluation.xml`):

```xml
<evaluation>
   <qa_pair>
      <question>Find the user who created the most issues in January 2024. What is their username?</question>
      <answer>alice_developer</answer>
   </qa_pair>
   <qa_pair>
      <question>Among PRs merged in Q1 2024, which repository had the highest number? Provide the repository name.</question>
      <answer>backend-api</answer>
   </qa_pair>
</evaluation>
```

2. **Install dependencies and set API key**:
```bash
uv pip install -r scripts/requirements.txt
export ANTHROPIC_API_KEY="$(your-secret-manager read anthropic-api-key)"
```

3. **Run evaluation**:
```bash
uv run python scripts/evaluation.py \
  -t stdio \
  -c python \
  -a github_mcp_server.py \
  -e GITHUB_TOKEN="$GITHUB_TOKEN" \
  -o github_eval_report.md \
  my_evaluation.xml
```

4. **Review the report** to see which questions passed/failed, read agent feedback, and identify areas for improvement.

## Troubleshooting

### Connection Errors
- **STDIO**: Verify command and arguments are correct
- **HTTP**: Check the URL is reachable, the server allows your Host/Origin, and headers are correct. A `400` with code `-32022` means no shared protocol version: read `data.supported` in the error
- Ensure required API keys are set in environment variables or headers

### Low Accuracy
- Review agent feedback for each task
- Check if tool descriptions are clear and comprehensive
- Verify input parameters are well-documented
- Consider whether tools return too much or too little data
- Ensure error messages are actionable

### Timeout Issues
- Use a more capable model
- Check if tools return too much data
- Verify pagination is working correctly
- Consider simplifying complex questions
