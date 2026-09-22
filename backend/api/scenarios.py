"""Scenario presets: initial MockService state only.

No workflow/orchestrator logic lives here. Each preset returns a
fresh ``MockService`` using Member 2's existing methods:

- normal:             service starts healthy.
- injected-failure:   service starts unhealthy (recovery should heal it).
- persistent-failure: service starts unhealthy AND restarts deterministically
  fail (workflow should exhaust retries and escalate).
"""

from __future__ import annotations

from backend.environment.mock_service import MockService

SCENARIOS = ("normal", "injected-failure", "persistent-failure")


def build_service(scenario: str) -> MockService:
    """Create a ``MockService`` preset for ``scenario``.

    Args:
        scenario: One of ``normal``, ``injected-failure``,
            ``persistent-failure``.

    Raises:
        ValueError: If the scenario name is unknown.
    """
    if scenario == "normal":
        return MockService()
    if scenario == "injected-failure":
        service = MockService()
        service.inject_failure()
        return service
    if scenario == "persistent-failure":
        service = MockService()
        service.inject_failure()
        service.set_fail_recovery_mode(True)
        return service
    raise ValueError(
        f"Unknown scenario: {scenario!r}. Supported: {list(SCENARIOS)}"
    )
