"""Recovery policy — kept separate from the orchestrator.

Level 1 rules:
- A failed health verification may allow a controlled ``restart_service``.
- Recovery must be followed by a fresh ``health_check`` (a successful
  restart is never treated as proof of service health).
- Retry limits are strictly enforced; when exhausted the workflow
  must escalate instead of retrying forever.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.workflow.models import ExecutionResult, VerificationResult, WorkflowStep

RECOVERY_ACTION = "restart_service"
FOLLOWUP_ACTION = "health_check"

# Only these execution actions are eligible to trigger recovery.
RECOVERABLE_ACTIONS = frozenset({"health_check"})


@dataclass
class RecoveryPolicy:
    """Decide whether recovery is allowed and what action is approved."""

    max_attempts: int = 3
    allowed_recovery_actions: tuple[str, ...] = field(
        default_factory=lambda: (RECOVERY_ACTION,)
    )

    def allow_recovery(
        self, verification: VerificationResult, recovery_attempts: int
    ) -> bool:
        """Return True if another recovery attempt is allowed."""
        if verification.passed:
            return False
        if recovery_attempts >= self.max_attempts:
            return False
        return True

    def get_recovery_action(
        self,
        verification: VerificationResult,
        execution: ExecutionResult,
        recovery_attempts: int,
    ) -> str | None:
        """Return the approved recovery action name, or None if not allowed.

        For Level 1 only a failed ``health_check`` verification maps to a
        ``restart_service``. Anything else (or exhausted retries) returns
        None so the orchestrator escalates / fails instead.
        """
        if not self.allow_recovery(verification, recovery_attempts):
            return None
        if execution.action not in RECOVERABLE_ACTIONS:
            return None
        if RECOVERY_ACTION not in self.allowed_recovery_actions:
            return None
        return RECOVERY_ACTION

    def should_escalate(
        self, verification: VerificationResult, recovery_attempts: int
    ) -> bool:
        """Return True when retries are exhausted after a failed verification."""
        return not verification.passed and recovery_attempts >= self.max_attempts

    def build_recovery_step(
        self,
        task_id: str,
        execution: ExecutionResult,
        recovery_attempts: int,
    ) -> WorkflowStep:
        """Build the approved ``restart_service`` step."""
        service_name = execution.result.get("service_name") or execution.result.get(
            "service", "app"
        )
        # execution.result may not carry the name; fall back to parameters hint.
        return WorkflowStep(
            step_id=f"{task_id}-recovery-{recovery_attempts + 1}",
            action=RECOVERY_ACTION,
            parameters={"service_name": service_name},
            order=900 + recovery_attempts,
            max_attempts=1,
        )

    def build_followup_health_check(
        self, task_id: str, execution: ExecutionResult, recovery_attempts: int
    ) -> WorkflowStep:
        """Build the mandatory fresh ``health_check`` after a restart."""
        service_name = execution.result.get("service_name") or execution.result.get(
            "service", "app"
        )
        return WorkflowStep(
            step_id=f"{task_id}-verify-{recovery_attempts + 1}",
            action=FOLLOWUP_ACTION,
            parameters={"service_name": service_name},
            order=950 + recovery_attempts,
            max_attempts=1,
        )
