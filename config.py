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
JINA_API_KEY: str | None = os.getenv("JINA_API_KEY")

# Google Cloud
GOOGLE_CLOUD_LOCATION: str = os.getenv("GOOGLE_CLOUD_LOCATION", "global")


def configure_genai_backend() -> None:
    """Configures the Google GenAI backend.

    Tries to detect ADC (Application Default Credentials). If found, defaults to Vertex AI.
    Otherwise, explicitly falls back to Gemini API direct access.
    """
    if "GOOGLE_GENAI_USE_VERTEXAI" in os.environ:
        return

    try:
        import google.auth
        from google.auth.exceptions import DefaultCredentialsError

        _, project_id = google.auth.default()
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
        if "GOOGLE_CLOUD_PROJECT" not in os.environ and project_id:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        if "GOOGLE_CLOUD_LOCATION" not in os.environ:
            os.environ["GOOGLE_CLOUD_LOCATION"] = GOOGLE_CLOUD_LOCATION
    except (DefaultCredentialsError, ValueError):
        # Fallback to direct Gemini API key authentication backend
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"


configure_genai_backend()

GOOGLE_CLOUD_PROJECT: str | None = os.getenv("GOOGLE_CLOUD_PROJECT")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", GOOGLE_CLOUD_LOCATION)

# ---------------------------------------------------------------------------
# Model Configuration
# ---------------------------------------------------------------------------
# Routing/classification (cheap): used for parse_course
MODEL_ROUTING: str = os.getenv("MODEL_ROUTING", "gemini-2.5-flash")

# Semantic judgment (capable): used for creator_verify, free_alt_score, verdict
MODEL_JUDGMENT: str = os.getenv("MODEL_JUDGMENT", "gemini-2.5-flash")

# ---------------------------------------------------------------------------
# Mock / Development
# ---------------------------------------------------------------------------
# Set USE_MOCK=0 to disable cached responses (default: 1 / True)
USE_MOCK: bool = os.getenv("USE_MOCK", "1") == "1"

# Cache directory for mock data
CACHE_DIR: str = os.getenv("CACHE_DIR", "cache")
