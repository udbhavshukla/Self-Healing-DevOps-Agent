"""Gemini client (transport only: no analysis, no execution).

- API key comes from ``GEMINI_API_KEY`` (never hardcoded, never logged).
- Model configurable via ``GEMINI_MODEL`` (default ``gemini-2.0-flash``).
- Structured JSON output (``response_mime_type="application/json"``),
  temperature 0 for determinism.
- Every failure mode (missing key, missing SDK, network/timeout/model
  error, malformed JSON) raises :class:`AIUnavailableError` with a safe
  message so callers can fall back without crashing the app.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_TIMEOUT_SECONDS = 20


class AIUnavailableError(Exception):
    """Raised when Gemini cannot produce an analysis for any reason."""


class GeminiClient:
    """Thin wrapper around the Google GenAI SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Create a client. Missing key/SDK means unavailable, not an error.

        Args:
            api_key: Explicit key (tests); defaults to ``GEMINI_API_KEY``.
            model: Explicit model; defaults to ``GEMINI_MODEL`` or
                ``gemini-2.0-flash``.
            timeout_seconds: Request timeout for Gemini calls.
        """
        self._api_key = api_key if api_key is not None else os.environ.get(
            "GEMINI_API_KEY", ""
        )
        self.model = (
            model or os.environ.get("GEMINI_MODEL", "") or DEFAULT_MODEL
        )
        self.timeout_seconds = timeout_seconds

    @property
    def available(self) -> bool:
        """True when a key is configured AND the SDK imports."""
        if not self._api_key:
            return False
        try:
            from google import genai  # noqa: F401

            return True
        except Exception:
            return False

    def analyze_incident(self, prompt: str) -> Dict[str, Any]:
        """Send ``prompt`` to Gemini and return the parsed JSON object.

        Raises:
            AIUnavailableError: On any failure (no key/SDK, network,
                timeout, model error, non-JSON response).
        """
        if not self.available:
            raise AIUnavailableError(
                "AI analysis unavailable: GEMINI_API_KEY is not configured."
            )
        try:
            from google import genai
            from google.genai import types
        except Exception as exc:
            raise AIUnavailableError(
                f"AI analysis unavailable: SDK import failed ({exc})."
            ) from exc
        try:
            client = genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0,
                    http_options=types.HttpOptions(
                        timeout=self.timeout_seconds * 1000
                    ),
                ),
            )
            return _parse_json(getattr(response, "text", "") or "")
        except AIUnavailableError:
            raise
        except Exception as exc:
            raise AIUnavailableError(
                f"AI analysis unavailable: request failed ({type(exc).__name__})."
            ) from exc

    def __repr__(self) -> str:  # never leak key material
        return f"GeminiClient(model={self.model!r}, key_set={bool(self._api_key)})"


def _parse_json(text: str) -> Dict[str, Any]:
    """Parse Gemini's JSON response, tolerating surrounding prose."""
    cleaned = text.strip()
    if not cleaned:
        raise AIUnavailableError("AI analysis unavailable: empty response.")
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise AIUnavailableError(
                "AI analysis unavailable: malformed (non-JSON) response."
            )
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AIUnavailableError(
                "AI analysis unavailable: malformed (non-JSON) response."
            ) from exc
    if not isinstance(parsed, dict):
        raise AIUnavailableError(
            "AI analysis unavailable: response was not a JSON object."
        )
    return parsed
