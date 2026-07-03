# YDNT Project Rules

## Security
1. No API keys, tokens, or secrets in source code. All secrets via `config.py`.
2. All external text (sales pages, user input) must pass through `security_screen` node before reaching any LLM agent.
3. All tool I/O and agent output must use Pydantic schemas. No raw dict/string parsing.

## Architecture
4. Module dependency direction (violations blocked by Hook):
   - `schemas.py` must not import any other `app/` module
   - `nodes.py` and `agents_llm.py` must not import each other
   - `mcp_server.py` must not import `agent.py`
5. Environment variables: only `config.py` and process entrypoints (`mcp_server.py`, `agent_runtime_app.py`) may call `os.getenv()`.

## Workflow
6. Git commits must follow Conventional Commits format (enforced by Hook).
7. Default to `USE_MOCK=1` during development to preserve YouTube API quota.

## Skills Reference
- Git conventions → `git-workflow` skill
- Python coding standards → `code-standards` skill
- Testing strategy → `testing-strategy` skill
