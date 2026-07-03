name: course-rubric
description: Scores an online course profile against 6+1 verifiable due-diligence axes. Use when evaluating whether a paid course is worth buying.
version: 1.0.0
allowed-tools: run_command

## Instructions
1. Do NOT hand-evaluate or make up scores yourself.
2. Run: python scripts/score.py <profile_json> <instructor_json> <freealt_json>
3. The script will output JSON scores on stdout.
4. Interpret the JSON output and present it to the user. Never re-derive the rules yourself.
