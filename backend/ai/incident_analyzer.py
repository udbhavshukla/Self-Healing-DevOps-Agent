"""Incident analyzer: user incident + context -> validated recommendation.

Flow: build prompt from :class:`IncidentContext` -> Gemini (JSON) ->
validate with :class:`AIRecommendation` -> check ``recommended_action``
against the executor allowlist. Invalid actions are reported as
``rejected_action`` and never executed. Any Gemini failure degrades to
``available=False`` (never fabricated, never raised to callers).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import ValidationError

from backend.ai.gemini_client import AIUnavailableError, GeminiClient
from backend.ai.schemas import (
    ALLOWED_ACTIONS,
    AIAnalysisResult,
    AIRecommendation,
    IncidentContext,
)

SYSTEM_INSTRUCTIONS = """\
You are a DevOps incident triage assistant. Analyze the incident and
respond with a single JSON object and nothing else:
{"diagnosis": "<one-sentence diagnosis>", "recommended_action": "<one of: {ALLOWED}>",
 "reason": "<why this action is appropriate>", "confidence": <0.0-1.0>}
Rules: recommend exactly one action, only from the allowed list. \
Base the diagnosis strictly on the provided context. \
Be concise.\
"""


def build_prompt(context: IncidentContext) -> str:
    """Render the full Gemini prompt (context contains no secrets)."""
    instructions = SYSTEM_INSTRUCTIONS.replace(
        "{ALLOWED}", ", ".join(context.allowed_actions)
    )
    return f"{instructions}\n\nIncident context:\n{context.to_prompt_section()}"


def build_context(
    incident: str,
    service_name: str = "demo-service",
    health_status: str = "unknown",
    http_status: Optional[int] = None,
    verification: str = "unknown",
    previous_action: Optional[str] = None,
    recovery_attempts: int = 0,
    reported_http_status: Optional[int] = None,
) -> IncidentContext:
    """Assemble an :class:`IncidentContext` from known system facts."""
    return IncidentContext(
        incident=incident,
        service_name=service_name,
        health_status=health_status,
        http_status=http_status,
        reported_http_status=reported_http_status,
        verification=verification,
        previous_action=previous_action,
        recovery_attempts=recovery_attempts,
    )


class IncidentAnalyzer:
    """Coordinates Gemini analysis with strict output validation."""

    def __init__(self, client: Optional[GeminiClient] = None) -> None:
        """Create an analyzer (a test double client may be injected)."""
        self.client = client if client is not None else GeminiClient()

    def analyze(
        self, incident: str, context: IncidentContext | Dict[str, Any]
    ) -> AIAnalysisResult:
        """Analyze ``incident`` and return a validated result.

        Raises:
            ValueError: If ``incident`` is empty/blank.
        """
        if not isinstance(incident, str) or not incident.strip():
            raise ValueError("Incident must be a non-empty string.")
        if isinstance(context, dict):
            context = IncidentContext(incident=incident.strip(), **context)
        prompt = build_prompt(context)
        try:
            raw = self.client.analyze_incident(prompt)
        except AIUnavailableError as exc:
            return AIAnalysisResult(
                available=False, source="unavailable", error=str(exc)
            )
        except Exception as exc:  # never let the client crash the workflow
            return AIAnalysisResult(
                available=False,
                source="unavailable",
                error=f"AI analysis unavailable: unexpected error ({type(exc).__name__}).",
            )
        try:
            rec = AIRecommendation.model_validate(raw)
        except ValidationError as exc:
            return AIAnalysisResult(
                available=False,
                source="unavailable",
                error=f"AI analysis unavailable: invalid response ({exc.errors()[0]['msg']}).",
            )
        if rec.recommended_action not in ALLOWED_ACTIONS:
            return AIAnalysisResult(
                available=True,
                source="gemini",
                rejected_action=rec.recommended_action,
                error=(
                    f"AI-recommended action rejected: {rec.recommended_action!r} "
                    f"is not in {sorted(ALLOWED_ACTIONS)}."
                ),
            )
        return AIAnalysisResult(
            available=True,
            source="gemini",
            diagnosis=rec.diagnosis,
            recommended_action=rec.recommended_action,
            reason=rec.reason,
            confidence=rec.confidence,
            model=getattr(self.client, "model", ""),
        )
