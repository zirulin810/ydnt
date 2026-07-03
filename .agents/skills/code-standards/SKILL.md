name: code-standards
description: Python coding conventions for the YDNT project: naming, type annotations, docstrings, and design comments. Use when creating or modifying Python files.
version: 1.0.0

## Naming Conventions
| Type | Convention | Example |
|------|-----------|---------|
| Module/file | `snake_case.py` | `mcp_server.py` |
| Class | `PascalCase` | `CourseProfile` |
| Function | `snake_case` | `budget_gate` |
| Constant | `UPPER_SNAKE_CASE` | `USE_MOCK` |

## Type Annotations
- All public functions and methods MUST have full type annotations for parameters and return values.
- Use `from __future__ import annotations` at the top of each file.

## Docstrings (Google style)
- All public modules, functions, classes, and methods must have docstrings.
- Docstrings for non-trivial functions should explain Design and Behavior:
  - `Design:` Explain WHY a specific approach or design decision was made.
  - `Behavior:` Explain edge case behaviors and bounds.

## Code formatting
- Code should be formatted with `ruff format` (line length 88).
- Import sorting should be sorted using `isort` rules.
