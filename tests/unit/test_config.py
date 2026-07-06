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

"""Unit tests for GenAI backend dynamic configuration in config.py."""

from __future__ import annotations

import os

import google.auth
from google.auth.exceptions import DefaultCredentialsError


def test_configure_genai_backend_vertex(monkeypatch) -> None:
    """Tests that configure_genai_backend sets up Vertex AI when ADC is present."""
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)

    # Mock google.auth.default to succeed
    monkeypatch.setattr(google.auth, "default", lambda: ("mock_creds", "mock-project-123"))

    from config import configure_genai_backend
    configure_genai_backend()

    assert os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "True"
    assert os.environ.get("GOOGLE_CLOUD_PROJECT") == "mock-project-123"
    assert os.environ.get("GOOGLE_CLOUD_LOCATION") == "global"


def test_configure_genai_backend_direct_fallback(monkeypatch) -> None:
    """Tests that configure_genai_backend falls back to direct API key when ADC is missing."""
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)

    # Mock google.auth.default to raise DefaultCredentialsError
    def mock_default():
        raise DefaultCredentialsError("Mock missing credentials")

    monkeypatch.setattr(google.auth, "default", mock_default)

    from config import configure_genai_backend
    configure_genai_backend()

    assert os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "False"
