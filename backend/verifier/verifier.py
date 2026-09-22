"""Level 1 service verifier (Member 3).

Judges whether a recovery action actually restored the service, using
only service health evidence. Never trusts the executor's success flag
alone: ``success=True`` with ``{"http_status": 503,
"health_status": "unhealthy"}`` evidence verifies as FAILED.

Interface matches Member 1's ``Verifier`` protocol
(``backend/workflow/interfaces.py``)::

    result = verifier.verify(execution_result)
    if result.passed: ...

``verify`` accepts an ``ExecutionResult`` dataclass (Member 1 format)
or a plain dict (Member 2 format) and always returns Member 1's
``VerificationResult`` dataclass with a JSON-serializable ``evidence``
payload. It never raises on malformed input, never retries, never
escalates, and never decides recovery: those belong to Member 4's
orchestrator.
"""

from __future__ import annotations

from typing import Any

from backend.workflow.models import ExecutionResult, VerificationResult

from backend.verifier.evidence import normalize_evidence
from backend.verifier.rules import LEVEL_1_RULE, evaluate_level1


class Verifier:
    """Stateless Level 1 verifier."""

    #: Rule applied by :meth:`verify` (also reported in result evidence).
    RULE = LEVEL_1_RULE

    def verify(
        self, execution: ExecutionResult | dict[str, Any] | Any
    ) -> VerificationResult:
        """Verify an execution result against the Level 1 rule.

        Args:
            execution: An ``ExecutionResult`` dataclass or an
                equivalent dict with ``task_id``, ``step_id``,
                ``success`` and ``result`` keys.

        Returns:
            A ``VerificationResult`` whose ``passed`` flag the
            orchestrator can check directly. ``reason`` always
            explains the verdict; ``evidence`` carries the rule
            name, ``status``, normalized health values, and the
            executor's success flag for audit.
        """
        try:
            evidence = normalize_evidence(execution)
        except Exception as exc:  # never let malformed input crash a run
            return VerificationResult(
                task_id="unknown",
                step_id="unknown",
                passed=False,
                reason=f"verification failed: evidence unreadable ({exc})",
                evidence={
                    "rule": self.RULE,
                    "status": "failed",
                    "error": "evidence_unreadable",
                },
            )

        if not evidence.valid:
            reason = "verification failed: " + "; ".join(evidence.problems)
            passed = False
        else:
            passed, reason = evaluate_level1(
                evidence.http_status, evidence.health_status
            )

        return VerificationResult(
            task_id=evidence.task_id,
            step_id=evidence.step_id,
            passed=passed,
            reason=reason,
            evidence={
                "rule": self.RULE,
                "status": "passed" if passed else "failed",
                "action": evidence.action,
                "http_status": evidence.http_status,
                "health_status": evidence.health_status,
                "execution_success": evidence.execution_success,
            },
        )
