"""Tests for WorkflowOrchestrator with fake executor / verifier.

No dependency on Member 2 / Member 3 code — fakes are defined locally.
"""

import pytest

from backend.workflow.models import (
    ActionRequest,
    ExecutionResult,
    TaskRequest,
    VerificationResult,
)
from backend.workflow.orchestrator import WorkflowOrchestrator
from backend.workflow.planner import WorkflowPlanner
from backend.workflow.recovery_policy import RecoveryPolicy
from backend.workflow.states import (
    WorkflowState,
    can_transition,
    validate_transition,
)


class FakeExecutor:
    """Fake Member 2 executor driven by a handler callable."""

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[ActionRequest] = []

    def execute(self, action: ActionRequest) -> ExecutionResult:
        self.calls.append(action)
        return self.handler(action)


class FakeVerifier:
    """Fake Member 3 verifier driven by a handler callable."""

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


def _ok_execution(action: ActionRequest) -> ExecutionResult:
    return ExecutionResult(
        task_id=action.task_id,
        step_id=action.step_id,
        action=action.action,
        attempt=action.attempt,
        success=True,
        result={"service_name": "api", "healthy": True},
    )


def _pass_verification(result: ExecutionResult) -> VerificationResult:
    return VerificationResult(
        task_id=result.task_id,
        step_id=result.step_id,
        passed=True,
        reason="healthy",
        evidence={"healthy": True},
    )


def _fail_verification(result: ExecutionResult) -> VerificationResult:
    return VerificationResult(
        task_id=result.task_id,
        step_id=result.step_id,
        passed=False,
        reason="service unhealthy",
        evidence={"healthy": False},
    )


def test_successful_workflow_marks_verified():
    executor = FakeExecutor(_ok_execution)
    verifier = FakeVerifier(_pass_verification)
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), executor, verifier, RecoveryPolicy(max_attempts=3)
    )
    status = orch.run(_task())
    assert status.status == WorkflowState.VERIFIED
    assert status.error is None
    assert status.final_result is not None
    assert status.history  # history preserved
    assert status.history[0]["event"] == "task_received"


def test_failed_health_check_triggers_recovery_and_succeeds():
    """First health check fails -> restart approved -> fresh check passes."""
    state = {"health_calls": 0}

    def exec_handler(action: ActionRequest) -> ExecutionResult:
        if action.action == "health_check":
            state["health_calls"] += 1
            healthy = state["health_calls"] >= 2  # fresh check after restart is healthy
            return ExecutionResult(
                task_id=action.task_id,
                step_id=action.step_id,
                action=action.action,
                attempt=action.attempt,
                success=healthy,
                result={"service_name": "api", "healthy": healthy},
            )
        if action.action == "restart_service":
            return ExecutionResult(
                task_id=action.task_id,
                step_id=action.step_id,
                action=action.action,
                attempt=action.attempt,
                success=True,
                result={"service_name": "api", "restarted": True},
            )
        raise AssertionError(f"unexpected action {action.action}")

    def verify_handler(result: ExecutionResult) -> VerificationResult:
        if result.action == "restart_service":
            return VerificationResult(
                task_id=result.task_id,
                step_id=result.step_id,
                passed=True,
                reason="restart executed",
                evidence={"restarted": True},
            )
        healthy = bool(result.result.get("healthy"))
        return VerificationResult(
            task_id=result.task_id,
            step_id=result.step_id,
            passed=healthy,
            reason="healthy" if healthy else "service unhealthy",
            evidence={"healthy": healthy},
        )

    executor = FakeExecutor(exec_handler)
    verifier = FakeVerifier(verify_handler)
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), executor, verifier, RecoveryPolicy(max_attempts=3)
    )
    status = orch.run(_task())

    assert status.status == WorkflowState.VERIFIED
    events = [h["event"] for h in status.history]
    assert "recovery_approved" in events
    assert "fresh_health_check_scheduled" in events
    assert "workflow_verified_after_recovery" in events
    assert status.final_result is not None
    assert status.final_result["recovered_via"] is not None


def test_restart_success_alone_does_not_verify():
    """Even when restart verification passes, a fresh health check must run."""
    executor = FakeExecutor(
        lambda a: ExecutionResult(
            task_id=a.task_id,
            step_id=a.step_id,
            action=a.action,
            attempt=a.attempt,
            success=True,
            result={"service_name": "api", "healthy": False},
        )
    )
    verifier = FakeVerifier(
        lambda r: VerificationResult(
            task_id=r.task_id,
            step_id=r.step_id,
            passed=(r.action == "restart_service"),  # restart "passes", health fails
            reason="restart ok" if r.action == "restart_service" else "still down",
            evidence={},
        )
    )
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), executor, verifier, RecoveryPolicy(max_attempts=1)
    )
    status = orch.run(_task())
    # Fresh health check still fails -> must escalate, never VERIFIED.
    assert status.status == WorkflowState.ESCALATED
    actions = [c.action for c in executor.calls]
    assert "restart_service" in actions
    assert actions.count("health_check") >= 2  # initial + fresh


def test_recovery_fails_and_escalates():
    executor = FakeExecutor(
        lambda a: ExecutionResult(
            task_id=a.task_id,
            step_id=a.step_id,
            action=a.action,
            attempt=a.attempt,
            success=(a.action == "restart_service"),
            result={"service_name": "api", "healthy": False},
        )
    )
    verifier = FakeVerifier(_fail_verification)
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), executor, verifier, RecoveryPolicy(max_attempts=1)
    )
    status = orch.run(_task())
    assert status.status == WorkflowState.ESCALATED
    assert status.error is not None


def test_retry_limits_are_enforced():
    executor = FakeExecutor(
        lambda a: ExecutionResult(
            task_id=a.task_id,
            step_id=a.step_id,
            action=a.action,
            attempt=a.attempt,
            success=False,
            result={"service_name": "api"},
            error="down",
        )
    )
    verifier = FakeVerifier(_fail_verification)
    max_attempts = 2
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), executor, verifier, RecoveryPolicy(max_attempts=max_attempts)
    )
    status = orch.run(_task())
    assert status.status == WorkflowState.ESCALATED
    # Bounded calls: 1 initial + max_attempts * (restart + fresh check).
    assert len(executor.calls) == 1 + max_attempts * 2


def test_invalid_state_transitions_rejected():
    with pytest.raises(ValueError):
        validate_transition(WorkflowState.PLANNED, WorkflowState.VERIFIED)
    with pytest.raises(ValueError):
        validate_transition(WorkflowState.EXECUTING, WorkflowState.ESCALATED)
    with pytest.raises(ValueError):
        validate_transition(WorkflowState.VERIFIED, WorkflowState.EXECUTING)
    with pytest.raises(ValueError):
        validate_transition(WorkflowState.FAILED, WorkflowState.EXECUTING)
    with pytest.raises(ValueError):
        validate_transition(WorkflowState.ESCALATED, WorkflowState.EXECUTING)
    assert can_transition(WorkflowState.PLANNED, WorkflowState.EXECUTING)
    assert can_transition(WorkflowState.VERIFYING, WorkflowState.RECOVERING)
    assert can_transition(WorkflowState.RECOVERING, WorkflowState.EXECUTING)


def test_executor_errors_mark_failed():
    class BoomExecutor:
        def execute(self, action):
            raise RuntimeError("executor crashed")

    orch = WorkflowOrchestrator(
        WorkflowPlanner(), BoomExecutor(), FakeVerifier(_pass_verification),
        RecoveryPolicy(),
    )
    status = orch.run(_task())
    assert status.status == WorkflowState.FAILED
    assert "Executor" in (status.error or "")
    assert any(h["event"] == "executor_error" for h in status.history)


def test_verifier_errors_mark_failed():
    class BoomVerifier:
        def verify(self, result):
            raise RuntimeError("verifier crashed")

    orch = WorkflowOrchestrator(
        WorkflowPlanner(), FakeExecutor(_ok_execution), BoomVerifier(),
        RecoveryPolicy(),
    )
    status = orch.run(_task())
    assert status.status == WorkflowState.FAILED
    assert "Verifier" in (status.error or "")
    assert any(h["event"] == "verifier_error" for h in status.history)


def test_unsupported_task_type_marks_failed():
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), FakeExecutor(_ok_execution),
        FakeVerifier(_pass_verification), RecoveryPolicy(),
    )
    bad = TaskRequest(
        task_id="t-bad", description="x", task_type="nope", parameters={}
    )
    status = orch.run(bad)
    assert status.status == WorkflowState.FAILED
    assert "Planning failed" in (status.error or "")


def test_history_preservation():
    executor = FakeExecutor(_ok_execution)
    verifier = FakeVerifier(_pass_verification)
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), executor, verifier, RecoveryPolicy()
    )
    status = orch.run(_task())
    events = [h["event"] for h in status.history]
    for required in (
        "task_received",
        "plan_created",
        "executing",
        "execution",
        "verification",
        "workflow_verified",
    ):
        assert required in events
    # State transitions are recorded too.
    assert any(h["event"] == "state_transition" for h in status.history)
    # attempt counter reflects real executions.
    assert status.attempt == len(executor.calls) == 1
