"""Evidence schema and normalization (adapter) layer.

Member 2's executor emits plain dicts while Member 1's orchestrator
protocol uses the ``ExecutionResult`` dataclass. This module accepts
both shapes (plus malformed input) and normalizes them into a single
``NormalizedEvidence`` structure, so verification rules never depend
on a producer's container format.

Only evidence *containers* are adapted here. The health payload itself
must carry ``http_status`` / ``health_status`` (exactly what Member 2's
health checker produces); nothing is guessed from unrelated fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.workflow.models import ExecutionResult

HEALTHY = "healthy"
UNHEALTHY = "unhealthy"
VALID_HEALTH_STATUSES = frozenset({HEALTHY, UNHEALTHY})

HTTP_MIN = 100
HTTP_MAX = 599

# Tolerated alias for the HTTP status key (common JSON variance).
HTTP_STATUS_KEYS = ("http_status", "status_code")
HEALTH_STATUS_KEYS = ("health_status",)

UNKNOWN = "unknown"


@dataclass
class NormalizedEvidence:
    """Adapter output consumed by verification rules."""

    task_id: str = UNKNOWN
    step_id: str = UNKNOWN
    action: str = UNKNOWN
    execution_success: bool = False
    http_status: int | None = None
    health_status: str | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """True when the evidence is well-formed enough to judge."""
        return not self.problems


def normalize_evidence(
    execution: ExecutionResult | dict[str, Any] | Any,
) -> NormalizedEvidence:
    """Normalize an execution result into :class:`NormalizedEvidence`.

    Accepts an ``ExecutionResult`` dataclass (Member 1 format) or a
    plain dict (Member 2 format). Never raises: malformed input yields
    evidence with ``problems`` describing what is wrong.
    """
    if isinstance(execution, ExecutionResult):
        container: Any = {
            "task_id": execution.task_id,
            "step_id": execution.step_id,
            "action": execution.action,
            "success": execution.success,
            "result": execution.result,
            "error": execution.error,
        }
    elif isinstance(execution, dict):
        container = execution
    else:
        return NormalizedEvidence(
            problems=[
                "execution result missing or not a mapping: "
                f"got {type(execution).__name__}"
            ]
        )

    evidence = NormalizedEvidence(
        task_id=_as_text(container.get("task_id")),
        step_id=_as_text(container.get("step_id")),
        action=_as_text(container.get("action")),
        execution_success=bool(container.get("success", False)),
    )

    payload = container.get("result")
    if payload is None:
        evidence.problems.append("missing evidence payload ('result' is null)")
        return evidence
    if not isinstance(payload, dict):
        evidence.problems.append(
            "malformed evidence payload ('result' must be a mapping, "
            f"got {type(payload).__name__})"
        )
        return evidence

    http_raw = _first_present(payload, HTTP_STATUS_KEYS)
    health_raw = _first_present(payload, HEALTH_STATUS_KEYS)

    http_status, http_problem = _coerce_http_status(http_raw)
    if http_problem is not None:
        evidence.problems.append(http_problem)
    else:
        evidence.http_status = http_status

    health_status, health_problem = _coerce_health_status(health_raw)
    if health_problem is not None:
        evidence.problems.append(health_problem)
    else:
        evidence.health_status = health_status

    return evidence


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first present key's value, else None."""
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _as_text(value: Any) -> str:
    """Best-effort text coercion for identifier fields."""
    if isinstance(value, str) and value:
        return value
    if value is None:
        return UNKNOWN
    return str(value)


def _coerce_http_status(value: Any) -> tuple[int | None, str | None]:
    """Validate an HTTP status value.

    Returns (status, None) on success or (None, problem) on failure.
    Booleans are rejected explicitly (``True`` must not read as ``1``).
    Pure-digit strings are tolerated and coerced.
    """
    if value is None:
        return None, "missing required field 'http_status'"
    if isinstance(value, bool):
        return None, f"invalid 'http_status': boolean {value!r} is not a status code"
    if isinstance(value, int):
        status = value
    elif isinstance(value, str) and value.strip().isdigit():
        status = int(value.strip())
    else:
        return None, f"invalid 'http_status': {value!r} is not a status code"
    if not (HTTP_MIN <= status <= HTTP_MAX):
        return None, f"invalid 'http_status': {status} out of range 100-599"
    return status, None


def _coerce_health_status(value: Any) -> tuple[str | None, str | None]:
    """Validate a health status value (case/whitespace tolerant).

    Returns (status, None) on success or (None, problem) on failure.
    """
    if not isinstance(value, str):
        return None, f"invalid 'health_status': {value!r} is not a string"
    normalized = value.strip().lower()
    if normalized not in VALID_HEALTH_STATUSES:
        return (
            None,
            f"invalid 'health_status': {value!r} "
            f"(expected one of {sorted(VALID_HEALTH_STATUSES)})",
        )
    return normalized, None
