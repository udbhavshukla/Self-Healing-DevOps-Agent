"""Deterministic offline policy (used when Gemini is unreachable).

Pure local rules only: no network, no shell, no subprocess, no
executor calls. Output actions always come from the executor
allowlist (single source: Member 2), so unsafe or unrecognized input
can only ever yield a safe observation action — never arbitrary work.

The payload mirrors :class:`AIAnalysisResult` with
``source="offline_policy"`` and ``confidence=None`` (never fabricated),
so the dashboard and evidence chain render it through the same panels
while clearly distinguishing it from Gemini output.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.ai.schemas import ALLOWED_ACTIONS

SOURCE = "offline_policy"

# Deterministic mapping: observed failure signal -> safe allowed action.
# Unknown input falls through to a health check (observe, never act blind).
_STATUS_TO_ACTION = {
    500: "restart",
    502: "restart",
    503: "restart",
    504: "restart",
}

_UNAVAILABLE_MARKERS = (
    "unavailable",
    "unreachable",
    "connection refused",
    "timed out",
    "timeout",
    "no response",
    "not responding",
    "down",
)


class OfflinePolicy:
    """Local deterministic incident triage (no network required)."""

    def recommend(
        self,
        incident: str,
        http_status: Optional[int] = None,
        health_status: str = "unknown",
    ) -> Dict[str, Any]:
        """Recommend a safe action for ``incident``.

        Args:
            incident: Free-text user incident.
            http_status: Observed HTTP status, if known.
            health_status: Observed health string, if known.

        Returns:
            Payload with ``source="offline_policy"``, ``diagnosis``,
            ``recommended_action`` (always allowlisted),
            ``reason``, ``confidence=None``, ``available=True``.
        """
        text = (incident or "").strip()
        action = _STATUS_TO_ACTION.get(http_status or 0)
        if action is None:
            lowered = text.lower()
            if health_status == "unhealthy" or any(
                marker in lowered for marker in _UNAVAILABLE_MARKERS
            ):
                action = "restart"
            else:
                action = "health_check"
        assert action in ALLOWED_ACTIONS, action  # safety invariant
        if action == "restart":
            diagnosis = (
                f"Service reported failure (HTTP {http_status}) — local "
                "deterministic policy selected a controlled restart."
                if http_status
                else "Service reported unhealthy — local deterministic "
                "policy selected a controlled restart."
            )
            reason = (
                f"HTTP {http_status} maps to the local deterministic "
                "recovery policy (restart is allowlisted)."
                if http_status
                else "Unhealthy service maps to the local deterministic "
                "recovery policy (restart is allowlisted)."
            )
        else:
            diagnosis = (
                "Incident did not match a known failure pattern — local "
                "deterministic policy selected observation first."
            )
            reason = (
                "Unknown incidents start with an allowlisted health check; "
                "no recovery action is taken blind."
            )
        return {
            "available": True,
            "source": SOURCE,
            "diagnosis": diagnosis,
            "recommended_action": action,
            "reason": reason,
            "confidence": None,
            "model": "local-offline-policy",
            "error": None,
            "rejected_action": None,
        }
