"""Scenario presets: initial MockService state only.

No workflow/orchestrator logic lives here. Each preset returns a
fresh ``MockService`` using Member 2's existing methods:

- normal:             service starts healthy.
- injected-failure:   service starts unhealthy (recovery should heal it).
- persistent-failure: service starts unhealthy AND restarts deterministically
  fail (workflow should exhaust retries and escalate).
"""

from __future__ import annotations

import re

from backend.environment.mock_service import MockService

SCENARIOS = ("normal", "injected-failure", "persistent-failure")

# Deterministic keyword mapping from a free-text user incident to a demo
# service preset. This only selects the *initial service state* for the
# demo; it is not AI reasoning and never influences recovery decisions.
_PERSISTENT_MARKERS = (
    "still ",
    "still unavailable",
    "after restart",
    "keeps failing",
    "keeps coming back",
    "won't recover",
    "will not recover",
    "persistent",
    "again and again",
    "repeatedly",
)

_FAILURE_MARKERS = (
    "503",
    "500",
    "unhealthy",
    "down",
    "unavailable",
    "failing",
    "failure",
    "failed",
    "error",
    "crash",
    "outage",
    "after deploy",
    "after the latest deployment",
    "after deployment",
    "not responding",
)


def build_service(scenario: str, http_status: int | None = None) -> MockService:
    """Create a ``MockService`` preset for ``scenario``.

    Args:
        scenario: One of ``normal``, ``injected-failure``,
            ``persistent-failure``.
        http_status: Optional simulated failure HTTP status for the
            unhealthy presets (e.g. 500 from a user incident).
            Defaults to the service default (503) when omitted.

    Raises:
        ValueError: If the scenario name is unknown or the status
            code is invalid.
    """
    if scenario == "normal":
        return MockService()
    kwargs = {} if http_status is None else {"fail_http_status": http_status}
    if scenario == "injected-failure":
        service = MockService(**kwargs)
        service.inject_failure()
        return service
    if scenario == "persistent-failure":
        service = MockService(**kwargs)
        service.inject_failure()
        service.set_fail_recovery_mode(True)
        return service
    raise ValueError(
        f"Unknown scenario: {scenario!r}. Supported: {list(SCENARIOS)}"
    )


def map_incident_to_scenario(incident: str) -> str:
    """Map a user incident to a demo service preset (deterministic).

    Persistent-failure markers win over generic failure markers so
    "still unavailable after restart" demos escalation. Anything
    without failure markers maps to ``normal``.

    Args:
        incident: Free-text user incident (assumed non-empty).

    Returns:
        One of ``normal``, ``injected-failure``, ``persistent-failure``.
    """
    text = incident.lower()
    if any(marker in text for marker in _PERSISTENT_MARKERS):
        return "persistent-failure"
    if any(marker in text for marker in _FAILURE_MARKERS):
        return "injected-failure"
    return "normal"


_STATUS_CODE_RE = re.compile(r"\b([1-5]\d{2})\b")


def extract_failure_status(incident: str) -> int | None:
    """Extract a user-reported failure HTTP status from incident text.

    Returns the first 4xx/5xx code mentioned (e.g. 500), so the
    simulated environment reports the user's actual status instead of
    silently converting it to 503. Returns None when no error status
    is mentioned (2xx/3xx codes and plain text map to None).

    Args:
        incident: Free-text user incident.

    Returns:
        An int status code, or None.
    """
    for match in _STATUS_CODE_RE.finditer(incident):
        code = int(match.group(1))
        if 400 <= code <= 599:
            return code
    return None
