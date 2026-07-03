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

"""Helper script to validate commit messages against Conventional Commits."""

from __future__ import annotations

import re
import sys


def validate_message(msg: str) -> bool:
    pattern = r"^(init|feat|fix|refactor|test|docs|chore|security)(\(.+?\))?:\s.+"
    return bool(re.match(pattern, msg))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_commit_msg.py '<message>'")
        sys.exit(1)

    msg = sys.argv[1]
    if validate_message(msg):
        print("Validation passed.")
        sys.exit(0)
    else:
        print(
            f"Validation failed. Message '{msg}' does not follow Conventional Commits format.\n"
            "Format: <type>(<scope>): <description> or <type>: <description>\n"
            "Types: init, feat, fix, refactor, test, docs, chore, security"
        )
        sys.exit(1)
