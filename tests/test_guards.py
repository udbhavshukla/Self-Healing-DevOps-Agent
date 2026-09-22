"""Safety-guard tests: allow-list, identity validation, verifier guard.

Covers review Parts 1-3. Fakes are defined locally; no dependency on
Member 2 / Member 3 code.
"""

from backend.workflow.models import (
    ActionRequest,
    ExecutionResult,
    TaskRequest,
    VerificationResult,
)
from backend.workflow.orchestrator import WorkflowOrchestrator
from backend.workflow.planner import WorkflowPlanner
from backend.workflow.recovery_policy import RecoveryPolicy
from backend.workflow.states import WorkflowState


class FakeExecutor:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[ActionRequest] = []

    def execute(self, action: ActionRequest) -> ExecutionResult:
        self.calls.append(action)
        return self.handler(action)


class FakeVerifier:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[ExecutionResult] = []

    def verify(self, result: ExecutionResult) -> VerificationResult:
        self.calls.append(result)
        return self.handler(result)


def _task():
    return TaskRequest(
        task_id="t-1",
        description="service down",
        task_type="service_recovery",
        parameters={"service_name": "api"},
    )


def _fail_verification(result: ExecutionResult) -> VerificationResult:
    return VerificationResult(
        task_id=result.task_id,
        step_id=result.step_id,
        passed=False,
        reason="service unhealthy",
        evidence={"healthy": False},
    )


def _pass_verification(result: ExecutionResult) -> VerificationResult:
    return VerificationResult(
        task_id=result.task_id,
        step_id=result.step_id,
        passed=True,
        reason="looks fine",
        evidence={},
    )


def _unhealthy_execution(action: ActionRequest) -> ExecutionResult:
    return ExecutionResult(
        task_id=action.task_id,
        step_id=action.step_id,
        action=action.action,
        attempt=action.attempt,
        success=False,
        result={"service_name": "api", "healthy": False},
    )


# -- Part 1: allow-list -------------------------------------------------


def test_unapproved_recovery_action_never_executed():
    """A rogue policy action must be blocked before executor.execute()."""

    class RoguePolicy(RecoveryPolicy):
        def get_recovery_action(self, verification, execution, recovery_attempts):
            return "delete_database"

    executor = FakeExecutor(_unhealthy_execution)
    verifier = FakeVerifier(_fail_verification)
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), executor, verifier, RoguePolicy(max_attempts=3)
    )
    status = orch.run(_task())

    assert status.status == WorkflowState.FAILED
    assert "Unapproved action" in (status.error or "")
    # Only the initial health check ran; the rogue action never did.
    assert [c.action for c in executor.calls] == ["health_check"]
    assert any(h["event"] == "unapproved_action" for h in status.history)


def test_unapproved_planned_action_blocked():
    """A rogue planner action must also be blocked, not executed."""

    class RoguePlanner(WorkflowPlanner):
        def plan(self, task):
            from backend.workflow.models import WorkflowStep

            return [
                WorkflowStep(
                    step_id=f"{task.task_id}-step-1",
                    action="run_shell",
                    parameters={},
                    order=1,
                )
            ]

    executor = FakeExecutor(_unhealthy_execution)
    verifier = FakeVerifier(_pass_verification)
    orch = WorkflowOrchestrator(
        RoguePlanner(), executor, verifier, RecoveryPolicy()
    )
    status = orch.run(_task())

    assert status.status == WorkflowState.FAILED
    assert executor.calls == []
    assert any(h["event"] == "unapproved_action" for h in status.history)


# -- Part 2: identity validation ----------------------------------------


def _identity_case(field, wrong):
    def handler(action: ActionRequest) -> ExecutionResult:
        kwargs = {
            "task_id": action.task_id,
            "step_id": action.step_id,
            "action": action.action,
            "attempt": action.attempt,
        }
        kwargs[field] = wrong
        return ExecutionResult(
            success=True,
            result={"service_name": "api", "healthy": True},
            **kwargs,
        )

    return handler


def test_mismatched_task_id_fails_without_verification():
    executor = FakeExecutor(_identity_case("task_id", "WRONG-TASK"))
    verifier = FakeVerifier(_pass_verification)
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), executor, verifier, RecoveryPolicy()
    )
    status = orch.run(_task())

    assert status.status == WorkflowState.FAILED
    assert "identity mismatch" in (status.error or "").lower()
    # The corrupt result must never reach the verifier.
    assert verifier.calls == []
    assert any(
        h["event"] == "executor_identity_mismatch" for h in status.history
    )


def test_mismatched_step_id_fails_without_verification():
    executor = FakeExecutor(_identity_case("step_id", "WRONG-STEP"))
    verifier = FakeVerifier(_pass_verification)
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), executor, verifier, RecoveryPolicy()
    )
    status = orch.run(_task())

    assert status.status == WorkflowState.FAILED
    assert "identity mismatch" in (status.error or "").lower()
    assert verifier.calls == []
    assert any(
        h["event"] == "executor_identity_mismatch" for h in status.history
    )


def test_mismatched_action_fails():
    executor = FakeExecutor(_identity_case("action", "restart_service"))
    verifier = FakeVerifier(_pass_verification)
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), executor, verifier, RecoveryPolicy()
    )
    status = orch.run(_task())

    assert status.status == WorkflowState.FAILED
    assert verifier.calls == []


def test_mismatched_attempt_fails():
    executor = FakeExecutor(_identity_case("attempt", 999))
    verifier = FakeVerifier(_pass_verification)
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), executor, verifier, RecoveryPolicy()
    )
    status = orch.run(_task())

    assert status.status == WorkflowState.FAILED
    assert verifier.calls == []


# -- Part 3: verifier guard ----------------------------------------------


def test_failed_execution_cannot_become_verified():
    """success=False + passed=True must never yield VERIFIED."""
    executor = FakeExecutor(_unhealthy_execution)
    verifier = FakeVerifier(_pass_verification)  # dishonest / buggy verifier
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), executor, verifier, RecoveryPolicy(max_attempts=2)
    )
    status = orch.run(_task())

    assert status.status != WorkflowState.VERIFIED
    assert status.status == WorkflowState.ESCALATED
    assert any(
        h["event"] == "inconsistent_verification" for h in status.history
    )
    # Bounded: 1 initial + max_attempts * (restart + fresh check).
    assert len(executor.calls) == 1 + 2 * 2
