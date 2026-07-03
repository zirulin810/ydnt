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

"""PreToolUse hook: validates run_command calls before execution."""

from __future__ import annotations

import json
import re
import sys


def validate(tool_call: dict) -> dict:
    command = tool_call.get("command", "")

    # Block dangerous commands
    dangerous = ["rm -rf /", "format", "del /s /q"]
    for d in dangerous:
        if d in command.lower():
            return {"action": "block", "reason": f"Blocked dangerous command: {d}"}

    # Validate git commit message format (Conventional Commits)
    # Match both git commit -m "msg" and git commit -m 'msg'
    commit_match = re.search(r'git commit\s+.*-m\s+["\'](.+?)["\']', command)
    if commit_match:
        msg = commit_match.group(1)
        pattern = r"^(init|feat|fix|refactor|test|docs|chore|security)(\(.+?\))?:\s.+"
        if not re.match(pattern, msg):
            return {
                "action": "block",
                "reason": (
                    f"Commit message '{msg}' does not follow Conventional Commits format. "
                    "Expected format: <type>(<scope>): <description> or <type>: <description>\n"
                    "Allowed types: init, feat, fix, refactor, test, docs, chore, security"
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
