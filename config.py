"""Centralized configuration for the YDNT project.

Design: All environment variables, model names, and routing thresholds are
read here and only here. Other modules import from this module instead of
calling os.getenv() directly. This ensures a single source of truth and
fail-fast behavior when required variables are missing.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# API Keys & Tokens
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
YOUTUBE_API_KEY: str | None = os.getenv("YOUTUBE_API_KEY")
GITHUB_TOKEN: str | None = os.getenv("GITHUB_TOKEN")

# Google Cloud
GOOGLE_CLOUD_PROJECT: str | None = os.getenv("GOOGLE_CLOUD_PROJECT")
GOOGLE_CLOUD_LOCATION: str = os.getenv("GOOGLE_CLOUD_LOCATION", "global")

# ---------------------------------------------------------------------------
# Model Configuration
# ---------------------------------------------------------------------------
# Routing/classification (cheap): used for parse_course, budget_gate decisions
MODEL_ROUTING: str = os.getenv("MODEL_ROUTING", "gemini-2.5-flash")

# Semantic judgment (capable): used for instructor_verify, free_alt_score, verdict
MODEL_JUDGMENT: str = os.getenv("MODEL_JUDGMENT", "gemini-2.5-flash")

# ---------------------------------------------------------------------------
# Routing Thresholds
# ---------------------------------------------------------------------------
# Default budget cap in USD — below this AND low-risk → quick route (no LLM)
DEFAULT_BUDGET_CAP: float = float(os.getenv("DEFAULT_BUDGET_CAP", "50.0"))

# ---------------------------------------------------------------------------
# Mock / Development
# ---------------------------------------------------------------------------
# Set USE_MOCK=1 to use cached responses instead of real API calls
USE_MOCK: bool = os.getenv("USE_MOCK", "0") == "1"

# Cache directory for mock data
CACHE_DIR: str = os.getenv("CACHE_DIR", "cache")
