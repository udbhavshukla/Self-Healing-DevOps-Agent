"""Strict structured models for Level 2 AI incident analysis.

Uses pydantic (already a project dependency). The recommender output
is validated here; ``recommended_action`` is additionally checked
against the executor allowlist by the analyzer (never trusted blindly).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from backend.environment.executor import Executor as Member2Executor

#: Single source of truth for executable actions (owned by Member 2).
ALLOWED_ACTIONS: frozenset = Member2Executor.ALLOWED_ACTIONS


class IncidentContext(BaseModel):
    """Structured context sent to Gemini (no secrets, no internals)."""

    incident: str
    service_name: str = "demo-service"
    health_status: str = "unknown"
    http_status: Optional[int] = None
    reported_http_status: Optional[int] = None
    verification: str = "unknown"
    previous_action: Optional[str] = None
    recovery_attempts: int = 0
    allowed_actions: List[str] = Field(
        default_factory=lambda: sorted(ALLOWED_ACTIONS)
    )

    def to_prompt_section(self) -> str:
        """Render the context as a prompt section for Gemini."""
        lines = [
            f"Service: {self.service_name}",
            f"User incident: {self.incident}",
            f"Current health: {self.health_status}",
            f"HTTP status: {self.http_status if self.http_status is not None else 'unknown'}",
            f"Verification: {self.verification}",
            f"Previous recovery attempts: {self.recovery_attempts}",
            f"Allowed actions: {', '.join(self.allowed_actions)}",
        ]
        if self.previous_action:
            lines.append(f"Previous action: {self.previous_action}")
        if self.reported_http_status is not None:
            lines.append(
                f"User-reported HTTP status: {self.reported_http_status}"
            )
        return "\n".join(lines)


class AIRecommendation(BaseModel):
    """Validated structured recommendation produced by Gemini."""

    diagnosis: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    model: str = ""

    @field_validator("recommended_action")
    @classmethod
    def _strip_action(cls, value: str) -> str:
        return value.strip()


class AIAnalysisResult(BaseModel):
    """Outcome of incident analysis (Gemini or graceful fallback)."""

    available: bool
    source: Literal["gemini", "offline_policy", "unavailable"] = "unavailable"
    diagnosis: Optional[str] = None
    recommended_action: Optional[str] = None
    reason: Optional[str] = None
    confidence: Optional[float] = None
    model: str = ""
    error: Optional[str] = None
    rejected_action: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        """JSON-serializable form stored on the workflow payload."""
        return self.model_dump()
