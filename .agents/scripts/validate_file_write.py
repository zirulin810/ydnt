# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PreToolUse hook: validates write_file and code edit tools."""

from __future__ import annotations

import json
import re
import sys

# Forbidden import statements in specific modules
FORBIDDEN_IMPORTS = {
    "schemas.py": ["from app.nodes", "from app.agents", "from app.agent"],
    "nodes.py": ["from app.agents_llm"],
    "agents_llm.py": ["from app.nodes"],
    "mcp_server.py": ["from app.agent"],
}

# Entrypoint files that are allowed to call os.getenv() or access os.environ
ENTRYPOINT_FILES = {"config.py", "mcp_server.py", "agent_runtime_app.py"}

# Patterns for hardcoded API keys
API_KEY_PATTERNS = [
    r"AIzaSy[A-Za-z0-9_\-]{33}",
    r"['\"]sk-[A-Za-z0-9]{32,}['\"]",
    r"api_key\s*=\s*['\"][A-Za-z0-9]",
]


def validate(tool_call: dict) -> dict:
    arguments = tool_call.get("Arguments", {})
    if not arguments:
        arguments = tool_call  # fallback if arguments are flat

    filepath = arguments.get("TargetFile") or arguments.get("Target") or ""
    filename = filepath.split("/")[-1].split("\\")[-1]

    # Combine content to check (creation content or replacement chunk)
    content = arguments.get("CodeContent") or ""
    if not content:
        # Check replacement chunks if using code editing tool
        chunks = arguments.get("ReplacementChunks", [])
        if chunks:
            content = " ".join([chunk.get("ReplacementContent", "") for chunk in chunks])
        else:
            content = arguments.get("ReplacementContent") or ""

    # 1. Check forbidden module dependencies
    if filename in FORBIDDEN_IMPORTS:
        for forbidden in FORBIDDEN_IMPORTS[filename]:
            if forbidden in content:
                return {
                    "action": "block",
                    "reason": f"Dependency violation: {filename} must not import '{forbidden}'. Check AGENTS.md.",
                }

    # 2. Check hardcoded API keys
    for pattern in API_KEY_PATTERNS:
        if re.search(pattern, content):
            return {
                "action": "block",
                "reason": "Hardcoded API key detected. All secrets must be loaded from config.py.",
            }

    # 3. Check direct os.getenv() or os.environ usage (restricted to entrypoints)
    if filename.endswith(".py") and filename not in ENTRYPOINT_FILES:
        if "os.getenv(" in content or "os.environ[" in content:
            return {
                "action": "block",
                "reason": (
                    f"Direct environment variable access in {filename} is forbidden. "
                    "All env var reads must go through config.py."
                ),
            }

    return {"action": "allow"}


if __name__ == "__main__":
    try:
        tool_call = json.loads(sys.stdin.read())
        result = validate(tool_call)
        print(json.dumps(result))
    except Exception as e:
        # Fallback to allow if hook execution fails, but log error
        print(json.dumps({"action": "allow", "warning": f"Hook error: {e}"}))
