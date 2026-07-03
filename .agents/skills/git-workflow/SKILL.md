name: git-workflow
description: Git workflow conventions for the YDNT project: branch naming, commit message format (Conventional Commits), and merge checklist. Use when performing any git operation.
version: 1.0.0

## Branch Naming
- `feat/*` for features, `fix/*` for fixes, `chore/*` for tooling/config.
- Always branch from `main` and merge back to `main`.

## Commit Message Format (Conventional Commits)
- Format: `<type>(<scope>): <description>` or `<type>: <description>`
- Types: init, feat, fix, refactor, test, docs, chore, security
- Scopes: nodes, agents, mcp, schemas, skill, eval, security, deploy
- You can validate your message format using: `python scripts/validate_commit_msg.py "<msg>"`

## Pre-Merge Checklist
Ensure all checks pass before merging or final submission:
1. `agents-cli lint` → no lint errors
2. `pytest tests/ -v` → all unit tests pass
3. `semgrep --error --config .semgrep/rules.yaml .` → no API key leaks
4. `agents-cli eval run` → 5/5 cases pass in evaluation
