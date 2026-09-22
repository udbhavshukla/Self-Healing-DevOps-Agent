"""Edge-case tests for the Workflow Orchestrator (review Part 4).

Fakes are defined locally; no dependency on Member 2 / Member 3 code.
"""

from backend.workflow.models import (
    ActionRequest,
    ExecutionResult,
    TaskRequest,
    VerificationResult,
    WorkflowStep,
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


def _unhealthy_execution(action: ActionRequest) -> ExecutionResult:
    return ExecutionResult(
        task_id=action.task_id,
        step_id=action.step_id,
        action=action.action,
        attempt=action.attempt,
        success=False,
        result={"service_name": "api", "healthy": False},
    )


# 1. Empty plan -> FAILED -------------------------------------------------


def test_empty_plan_marks_failed():
    class EmptyPlanner(WorkflowPlanner):
        def plan(self, task):
            return []

    orch = WorkflowOrchestrator(
        EmptyPlanner(),
        FakeExecutor(_ok_execution),
        FakeVerifier(_pass_verification),
        RecoveryPolicy(),
    )
    status = orch.run(_task())

    assert status.status == WorkflowState.FAILED
    assert "empty plan" in (status.error or "").lower()
    assert any(h["event"] == "planning_failed" for h in status.history)


# 2. No approved recovery actions -> FAILED --------------------------------


def test_no_approved_recovery_actions_marks_failed():
    executor = FakeExecutor(_unhealthy_execution)
    orch = WorkflowOrchestrator(
        WorkflowPlanner(),
        executor,
        FakeVerifier(_fail_verification),
        RecoveryPolicy(max_attempts=3, allowed_recovery_actions=()),
    )
    status = orch.run(_task())

    assert status.status == WorkflowState.FAILED
    assert "no recovery action approved" in (status.error or "").lower()
    # No recovery was attempted: only the initial health check ran.
    assert [c.action for c in executor.calls] == ["health_check"]


# 3. Executor crash during restart ------------------------------------------


def test_executor_crash_during_restart_terminates_safely():
    class CrashOnRestart:
        def __init__(self):
            self.calls: list[ActionRequest] = []

        def execute(self, action: ActionRequest) -> ExecutionResult:
            self.calls.append(action)
            if action.action == "restart_service":
                raise RuntimeError("restart blew up")
            return _unhealthy_execution(action)

    executor = CrashOnRestart()
    orch = WorkflowOrchestrator(
        WorkflowPlanner(),
        executor,
        FakeVerifier(_fail_verification),
        RecoveryPolicy(max_attempts=1),
    )
    status = orch.run(_task())

    # Crash is contained: initial check + restart attempt + fresh check,
    # then the exhausted policy escalates. Never hangs, never VERIFIED.
    assert status.status == WorkflowState.ESCALATED
    assert len(executor.calls) == 3
    assert any(h["event"] == "executor_error" for h in status.history)


# 4. Verifier crashes during recovery ----------------------------------------


def test_verifier_crash_during_restart_marks_failed():
    def flaky_verify(result: ExecutionResult) -> VerificationResult:
        if result.action == "restart_service":
            raise RuntimeError("verifier crashed on restart")
        return _fail_verification(result)

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
    orch = WorkflowOrchestrator(
        WorkflowPlanner(), executor, FakeVerifier(flaky_verify), RecoveryPolicy()
    )
    status = orch.run(_task())

    assert status.status == WorkflowState.FAILED
    assert "Verifier error during recovery" in (status.error or "")
    assert any(h["event"] == "verifier_error" for h in status.history)


def test_verifier_crash_during_fresh_check_marks_failed():
    def flaky_verify(result: ExecutionResult) -> VerificationResult:
        if result.step_id.startswith("t-1-verify-"):
            raise RuntimeError("verifier crashed on fresh check")
        if result.action == "restart_service":
            return VerificationResult(
                task_id=result.task_id,
                step_id=result.step_id,
                passed=True,
                reason="restart executed",
                evidence={"restarted": True},
            )
        return _fail_verification(result)

    state = {"n": 0}

    def exec_handler(action: ActionRequest) -> ExecutionResult:
        if action.action == "restart_service":
            return ExecutionResult(
                task_id=action.task_id,
                step_id=action.step_id,
                action=action.action,
                attempt=action.attempt,
                success=True,
                result={"service_name": "api", "restarted": True},
            )
        state["n"] += 1
        return _unhealthy_execution(action)

    orch = WorkflowOrchestrator(
        WorkflowPlanner(),
        FakeExecutor(exec_handler),
        FakeVerifier(flaky_verify),
        RecoveryPolicy(),
    )
    status = orch.run(_task())

    assert status.status == WorkflowState.FAILED
    assert "fresh health check" in (status.error or "").lower()
    assert any(h["event"] == "verifier_error" for h in status.history)


# 5. Multi-step workflow -------------------------------------------------------


def test_two_step_workflow_verifies():
    class TwoStepPlanner(WorkflowPlanner):
        def plan(self, task):
            return [
                WorkflowStep("s-1", "health_check", {"service_name": "api"}, 1, 3),
                WorkflowStep("s-2", "health_check", {"service_name": "api"}, 2, 3),
            ]

    executor = FakeExecutor(_ok_execution)
    orch = WorkflowOrchestrator(
        TwoStepPlanner(),
        executor,
        FakeVerifier(_pass_verification),
        RecoveryPolicy(),
    )
    status = orch.run(_task())

    assert status.status == WorkflowState.VERIFIED
    assert [c.step_id for c in executor.calls] == ["s-1", "s-2"]
    assert status.final_result is not None
    assert status.final_result["step_id"] == "s-2"


# 6. max_attempts=0 boundary -----------------------------------------------------


def test_max_attempts_zero_escalates_without_recovery():
    executor = FakeExecutor(_unhealthy_execution)
    orch = WorkflowOrchestrator(
        WorkflowPlanner(),
        executor,
        FakeVerifier(_fail_verification),
        RecoveryPolicy(max_attempts=0),
    )
    status = orch.run(_task())

    assert status.status == WorkflowState.ESCALATED
    # No recovery attempted: exactly one execution.
    assert len(executor.calls) == 1


# 7. final_result semantics --------------------------------------------------------


def test_final_result_semantics():
    ok_orch = lambda policy: WorkflowOrchestrator(  # noqa: E731
        WorkflowPlanner(),
        FakeExecutor(_ok_execution),
        FakeVerifier(_pass_verification),
        policy,
    )
    verified = ok_orch(RecoveryPolicy()).run(_task())
    assert verified.status == WorkflowState.VERIFIED
    assert verified.final_result is not None
    assert verified.final_result["step_id"] == "t-1-step-1"
    assert "evidence" in verified.final_result

    bad_task = TaskRequest(
        task_id="t-bad", description="x", task_type="nope", parameters={}
    )
    failed = ok_orch(RecoveryPolicy()).run(bad_task)
    assert failed.status == WorkflowState.FAILED
    assert failed.final_result is None
    assert failed.error is not None

    escalated = WorkflowOrchestrator(
        WorkflowPlanner(),
        FakeExecutor(_unhealthy_execution),
        FakeVerifier(_fail_verification),
        RecoveryPolicy(max_attempts=1),
    ).run(_task())
    assert escalated.status == WorkflowState.ESCALATED
    assert escalated.final_result is None
    assert escalated.error is not None
