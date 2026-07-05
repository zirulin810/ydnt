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

"""Deterministic scoring engine for the course rubric skill.

Design: Parses course profile, instructor evidence, and free alternatives data
to compute flags across 6+1 due diligence axes. Emits JSON verdict output.
"""

from __future__ import annotations

import json
import sys


def parse_json_arg(arg: str) -> dict:
    """Helper to parse a JSON string or load a JSON file path."""
    try:
        # Try loading directly as JSON string
        return json.loads(arg)
    except json.JSONDecodeError:
        # Try loading as file path
        try:
            with open(arg, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error parsing argument: {e}", file=sys.stderr)
            return {}


def main():
    if len(sys.argv) < 4:
        print(
            "Usage: python score.py <profile_json_or_file> <instructor_json_or_file> <freealt_json_or_file>",
            file=sys.stderr,
        )
        sys.exit(1)

    profile = parse_json_arg(sys.argv[1])
    instructor = parse_json_arg(sys.argv[2])
    free_alt = parse_json_arg(sys.argv[3])

    # ---------------------------------------------------------------------------
    # 6+1 Axes Scoring Logic
    # ---------------------------------------------------------------------------
    red_flags = []
    green_flags = []

    # Axis 1: 主題遞迴性 (Recursive Theme)
    promised_outcome = profile.get("promised_outcome", "unknown")
    syllabus = profile.get("syllabus", [])
    syllabus_str = " ".join(syllabus).lower()
    recursive_keywords = [
        "audience",
        "sell course",
        "monetize",
        "make money online",
        "grow following",
        "passive income",
    ]
    is_recursive = promised_outcome == "income" and any(
        k in syllabus_str for k in recursive_keywords
    )
    if is_recursive:
        red_flags.append(
            "Recursive Theme: Course syllabus focuses heavily on audience monetization and selling courses."
        )
    else:
        green_flags.append("Teaches concrete technical or business skills.")

    # Axis 2: 獨立足跡 (Independent Footprint)
    footprint = instructor.get("footprint", "weak")
    github_real_work = instructor.get("github_real_work", False)
    verifiable_employment = instructor.get("verifiable_employment", False)
    only_sells_courses = instructor.get("only_sells_courses", False)

    if footprint == "weak" and only_sells_courses:
        red_flags.append(
            "Weak Footprint: Instructor has no notable independent footprint; primary presence is selling courses."
        )
    elif github_real_work or verifiable_employment:
        green_flags.append(
            "Credible Instructor: Verifiable professional employment or active GitHub contributions found."
        )

    # Axis 3: 承諾結果 (Promised Outcome)
    if promised_outcome == "income":
        red_flags.append(
            "Income Promises: Course marketing promises specific financial earnings or financial freedom."
        )
    elif promised_outcome == "skill":
        green_flags.append("Result Promise: Focuses on tangible skill acquisition.")

    # Axis 4: 免費內容深度 (Free Alternatives depth)
    free_items = free_alt.get("items", [])
    any_content_farm = any(item.get("content_farm_flag", False) for item in free_items)
    if any_content_farm:
        red_flags.append(
            "Content Farm Alternatives: Free options include low-quality content farms (automated voiceovers, no demos)."
        )

    # Axis 5: 稀缺操弄 (Scarcity Manipulation)
    scarcity_signals = profile.get("scarcity_signals", [])
    if scarcity_signals:
        red_flags.append(
            f"Scarcity Manipulation: Uses marketing scarcity tags: {', '.join(scarcity_signals)}."
        )

    # Axis 6: 招募機制 (Recruitment MLM)
    recruitment_signal = profile.get("recruitment_signal", False)
    if recruitment_signal:
        red_flags.append(
            "Recruitment MLM: Promotes students to become resellers or certified coaches for this course."
        )

    # Axis 7 (+1): 萃取成本 (Extraction Cost)
    best_coverage_pct = free_alt.get("best_coverage_pct", 0)
    high_extraction_cost = any(
        item.get("extraction_cost") == "high" for item in free_items
    )
    if best_coverage_pct < 60:
        red_flags.append(
            f"Low Free Coverage: Free alternatives cover only {best_coverage_pct}% of the syllabus."
        )
    elif high_extraction_cost:
        red_flags.append(
            "High Extraction Cost: Free alternatives are unstructured and require significant search/time effort."
        )

    # ---------------------------------------------------------------------------
    # Verdict Decision Matrix
    # ---------------------------------------------------------------------------
    # Mode A: Deceptive/MLM/Deceptive scarcity
    if is_recursive or recruitment_signal or (promised_outcome == "income" and scarcity_signals):
        mode = "should_not"
    # Mode B: Good free alternatives available
    elif best_coverage_pct >= 70 and not high_extraction_cost and not any_content_farm:
        mode = "need_not"
    # Worth Buying: High credential, low-priced, messy alternatives
    elif footprint in ["strong", "medium"] and best_coverage_pct < 80 and high_extraction_cost:
        mode = "worth_buying"
    else:
        mode = "need_not"  # Default fallback

    # Money vs. Time comparison explanation
    if high_extraction_cost:
        money_vs_time = (
            "Free alternatives exist but are highly unstructured. Your time cost to compile "
            "and learn from them is high. Paying for this course might save time."
        )
    else:
        money_vs_time = (
            "High-quality free tutorials cover the course syllabus comprehensively. "
            "You do not need to spend money; self-paced learning is highly efficient."
        )

    # Final verdict JSON structure
    verdict = {
        "mode": mode,
        "red_flags": red_flags,
        "green_flags": green_flags,
        "money_vs_time": money_vs_time,
        "conclusion": (
            "Based on structural due diligence: "
            + (
                "Do not purchase. The course has severe marketing red flags or MLM structures."
                if mode == "should_not"
                else (
                    "Do not purchase. High-quality free alternatives cover this content with low extraction cost."
                    if mode == "need_not"
                    else "Recommended purchase. The course saves significant time compared to messy free alternatives."
                )
            )
        ),
        "confidence": "high" if len(red_flags) + len(green_flags) > 3 else "medium",
    }

    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()
