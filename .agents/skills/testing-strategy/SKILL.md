name: testing-strategy
description: Testing strategy for the YDNT project: test layers, mock-first principle, and evaluation targets. Use when writing tests or running evaluations.
version: 1.0.0

## Test Layers
1. **Unit (pytest)**: Focuses on pure logic in `nodes.py` (e.g. sentence stripping, budget logic) and `score.py`.
2. **Integration (USE_MOCK=1)**: Uses `agents-cli run` to verify the entire DAG workflow executes from end-to-end.
3. **Eval (agents-cli eval)**: Runs structured datasets to test routing and security behavior under LLM-as-Judge.
4. **Security**: Semgrep rules scan for hardcoded keys, while PreToolUse hooks block unsafe actions.

## Mock-First Principle
- Default to `USE_MOCK=1` in your local `.env` or run command to avoid YouTube API quota exhaustion.
- Use live API only when rebuilding mock JSON cache files or recording demo execution.

## Eval Targets
- Routing accuracy: 5/5 cases route to the correct path (cheap -> quick path, expensive -> full path).
- Security assertion: Malicious prompt injection pages trigger `security_flag` and do not corrupt the verdict.
- Fairness regression: Verifies cases 1 & 2 raise red flags (Mode A) and cases 3 & 4 pass (Mode B).
