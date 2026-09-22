"""TEMPORARY stub verifier for Member 4 E2E development.

TODO(Member 3): Replace ``StubVerifier`` with the real verification
engine (evidence collection + deterministic verification rules).
The replacement must implement the same ``Verifier`` Protocol from
``backend/workflow/interfaces.py`` — ``verify(result)`` returning a
``VerificationResult`` — so neither the API layer (``app.py``) nor
the frontend needs to change when it lands.

Rules implemented here (minimal, deterministic):
- Never executes actions (pure function of the ExecutionResult).
- A failed tool execution (``success=False``) never passes.
- ``health_check``: HTTP 200 + healthy -> pass; otherwise fail.
- ``restart_service`` / ``restart``: ``recovered=True`` -> pass;
  otherwise fail.
- Unknown actions fail closed with a reason.
"""

from __future__ import annotations

from backend.workflow.models import ExecutionResult, VerificationResult


class StubVerifier:
    """Minimal deterministic verifier (Member 3 will replace this)."""

    def verify(self, result: ExecutionResult) -> VerificationResult:
        """Verify ``result`` against stub rules.

        Args:
            result: The execution result to verify.

        Returns:
            VerificationResult preserving task_id/step_id with
            passed/reason/evidence filled in.
        """
        evidence = dict(result.result)
        if not result.success:
            return VerificationResult(
                task_id=result.task_id,
                step_id=result.step_id,
                passed=False,
                reason=f"Execution failed: {result.error or 'unknown error'}",
                evidence=evidence,
            )
        if result.action == "health_check":
            healthy = (
                evidence.get("http_status") == 200
                and evidence.get("health_status") == "healthy"
            )
            return VerificationResult(
                task_id=result.task_id,
                step_id=result.step_id,
                passed=healthy,
                reason="healthy" if healthy else "service unhealthy",
                evidence=evidence,
            )
        if result.action in ("restart_service", "restart"):
            recovered = evidence.get("recovered") is True
            return VerificationResult(
                task_id=result.task_id,
                step_id=result.step_id,
                passed=recovered,
                reason="restart executed" if recovered else "restart did not recover",
                evidence=evidence,
            )
        return VerificationResult(
            task_id=result.task_id,
            step_id=result.step_id,
            passed=False,
            reason=f"Unsupported action for verification: {result.action}",
            evidence=evidence,
        )
