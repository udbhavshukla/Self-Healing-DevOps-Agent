"""Workflow orchestrator — the agent brain (Member 1).

Flow:
  TaskRequest -> plan -> execute (Executor) -> verify (Verifier)
  -> VERIFIED | recovery (restart + fresh health check) | FAILED | ESCALATED.

Rules enforced here:
- No infinite loops (bounded recovery attempts + iteration guard).
- No silent retries (every attempt is recorded in history).
- A successful restart is never treated as proof of health; a fresh
  health check + verification is always required after recovery.
"""

from __future__ import annotations

from typing import Any

from backend.workflow.interfaces import Executor, Verifier
from backend.workflow.models import (
    ActionRequest,
    ExecutionResult,
    TaskRequest,
    VerificationResult,
    WorkflowStatus,
    WorkflowStep,
)
from backend.workflow.planner import ALLOWED_ACTIONS, WorkflowPlanner
from backend.workflow.recovery_policy import RecoveryPolicy
from backend.workflow.states import WorkflowState, validate_transition


class WorkflowOrchestrator:
    """Modular orchestrator using dependency injection."""

    def __init__(
        self,
        planner: WorkflowPlanner,
        executor: Executor,
        verifier: Verifier,
        recovery_policy: RecoveryPolicy,
    ) -> None:
        self.planner = planner
        self.executor = executor
        self.verifier = verifier
        self.recovery_policy = recovery_policy

    # -- public API ----------------------------------------------------

    def run(self, task: TaskRequest) -> WorkflowStatus:
        """Run the full workflow for ``task`` and return a :class:`WorkflowStatus`."""
        status = WorkflowStatus(task_id=task.task_id, status=WorkflowState.PLANNED)
        status.history.append(
            {
                "event": "task_received",
                "task_type": task.task_type,
                "description": task.description,
                "parameters": dict(task.parameters),
            }
        )

        # 1. Plan. A planning failure happens before the state machine
        # starts, so the status is recorded as FAILED directly (there is
        # intentionally no PLANNED -> FAILED transition).
        try:
            plan = self.planner.plan(task)
        except Exception as exc:  # noqa: BLE001 - surface any planner error
            status.status = WorkflowState.FAILED
            status.error = f"Planning failed: {exc}"
            status.history.append({"event": "planning_failed", "error": str(exc)})
            return status

        if not plan:
            status.status = WorkflowState.FAILED
            status.error = "Planner returned an empty plan"
            status.history.append({"event": "planning_failed", "error": status.error})
            return status

        status.history.append(
            {
                "event": "plan_created",
                "steps": [
                    {
                        "step_id": s.step_id,
                        "action": s.action,
                        "parameters": dict(s.parameters),
                        "order": s.order,
                    }
                    for s in plan
                ],
            }
        )

        # 2. PLANNED -> EXECUTING
        self._transition(status, WorkflowState.EXECUTING)

        plan_pos = 0
        recovery_attempts = 0
        max_iterations = (self.recovery_policy.max_attempts * 2) + len(plan) + 10

        for _ in range(max_iterations):
            step = plan[plan_pos]
            status.current_step = step.step_id

            # Ensure we are in EXECUTING before every execution.
            if status.status == WorkflowState.RECOVERING:
                self._transition(status, WorkflowState.EXECUTING)
            elif status.status != WorkflowState.EXECUTING:
                status.status = WorkflowState.FAILED
                status.error = f"Unexpected state before execution: {status.status.value}"
                status.history.append({"event": "internal_error", "error": status.error})
                return status

            # 3. Execute current step.
            status.attempt += 1
            action_request = ActionRequest(
                task_id=task.task_id,
                step_id=step.step_id,
                action=step.action,
                parameters=dict(step.parameters),
                attempt=status.attempt,
            )
            status.history.append(
                {
                    "event": "executing",
                    "step_id": step.step_id,
                    "action": step.action,
                    "attempt": status.attempt,
                }
            )
            try:
                exec_result = self._guarded_execute(status, action_request)
            except Exception as exc:  # noqa: BLE001 - executor crash -> FAILED
                status.history.append(
                    {
                        "event": "executor_error",
                        "step_id": step.step_id,
                        "error": str(exc),
                    }
                )
                # EXECUTING has no direct edge to FAILED, so move through
                # VERIFYING with a synthetic failure (fully recorded).
                synthetic = ExecutionResult(
                    task_id=task.task_id,
                    step_id=step.step_id,
                    action=step.action,
                    attempt=status.attempt,
                    success=False,
                    result={},
                    error=f"Executor raised: {exc}",
                )
                status.history.append(
                    {"event": "execution", "result": _dump_execution(synthetic)}
                )
                self._transition(status, WorkflowState.VERIFYING)
                self._transition(status, WorkflowState.FAILED)
                status.error = f"Executor error on {step.step_id}: {exc}"
                status.history.append(
                    {"event": "workflow_failed", "error": status.error}
                )
                return status

            if exec_result is None:
                # Blocked by the allow-list guard (already FAILED).
                return status
            if not self._check_identity(status, action_request, exec_result):
                return status

            status.history.append(
                {"event": "execution", "result": _dump_execution(exec_result)}
            )

            # 4. EXECUTING -> VERIFYING, then verify.
            self._transition(status, WorkflowState.VERIFYING)
            try:
                verification = self.verifier.verify(exec_result)
            except Exception as exc:  # noqa: BLE001 - verifier crash -> FAILED
                status.history.append(
                    {
                        "event": "verifier_error",
                        "step_id": step.step_id,
                        "error": str(exc),
                    }
                )
                self._transition(status, WorkflowState.FAILED)
                status.error = f"Verifier error on {step.step_id}: {exc}"
                status.history.append(
                    {"event": "workflow_failed", "error": status.error}
                )
                return status

            verification = self._effective_verification(
                status, exec_result, verification
            )
            status.history.append(
                {"event": "verification", "result": _dump_verification(verification)}
            )

            # 5. Verification passed.
            if verification.passed:
                # Recovery follow-up health checks also land here: a pass
                # means the service is verified healthy.
                if plan_pos + 1 < len(plan):
                    # Advance to the next planned step via the only legal
                    # bridge: VERIFYING -> RECOVERING -> EXECUTING.
                    status.history.append(
                        {
                            "event": "step_passed",
                            "step_id": step.step_id,
                            "next_step": plan[plan_pos + 1].step_id,
                        }
                    )
                    self._transition(status, WorkflowState.RECOVERING)
                    plan_pos += 1
                    continue
                self._transition(status, WorkflowState.VERIFIED)
                status.final_result = {
                    "step_id": step.step_id,
                    "action": exec_result.action,
                    "execution": dict(exec_result.result),
                    "evidence": dict(verification.evidence),
                    "reason": verification.reason,
                }
                status.history.append({"event": "workflow_verified"})
                return status

            # 6. Verification failed -> VERIFYING -> RECOVERING, then a
            # bounded inner recovery loop (restart + fresh health check
            # per attempt). The loop reuses the latest failed health
            # result and never re-executes the original plan step, so
            # total executions = 1 initial + max_attempts * 2.
            self._transition(status, WorkflowState.RECOVERING)
            cur_exec = exec_result
            cur_verif = verification
            cur_step_id = step.step_id
            while True:
                status.history.append(
                    {
                        "event": "verification_failed",
                        "step_id": cur_step_id,
                        "reason": cur_verif.reason,
                        "recovery_attempts": recovery_attempts,
                    }
                )

                recovery_action = self.recovery_policy.get_recovery_action(
                    cur_verif, cur_exec, recovery_attempts
                )
                if recovery_action is None:
                    if self.recovery_policy.should_escalate(
                        cur_verif, recovery_attempts
                    ):
                        self._transition(status, WorkflowState.ESCALATED)
                        status.error = (
                            f"Retry limit reached ({recovery_attempts}/"
                            f"{self.recovery_policy.max_attempts}); escalating."
                        )
                        status.history.append(
                            {"event": "workflow_escalated", "error": status.error}
                        )
                    else:
                        self._transition(status, WorkflowState.FAILED)
                        status.error = (
                            f"Verification failed for {cur_step_id}: "
                            f"{cur_verif.reason or 'no reason'}; "
                            "no recovery action approved."
                        )
                        status.history.append(
                            {"event": "workflow_failed", "error": status.error}
                        )
                    return status

                # 7. Approved recovery: execute restart ...
                recovery_step = self.recovery_policy.build_recovery_step(
                    task.task_id, cur_exec, recovery_attempts
                )
                # Force the approved action (policy is authoritative).
                recovery_step.action = recovery_action
                status.history.append(
                    {
                        "event": "recovery_approved",
                        "action": recovery_action,
                        "step_id": recovery_step.step_id,
                        "recovery_attempts": recovery_attempts,
                    }
                )
                self._transition(status, WorkflowState.EXECUTING)
                status.attempt += 1
                status.current_step = recovery_step.step_id
                restart_request = ActionRequest(
                    task_id=task.task_id,
                    step_id=recovery_step.step_id,
                    action=recovery_step.action,
                    parameters=dict(recovery_step.parameters),
                    attempt=status.attempt,
                )
                try:
                    restart_result = self._guarded_execute(status, restart_request)
                except Exception as exc:  # noqa: BLE001
                    status.history.append(
                        {"event": "executor_error", "step_id": recovery_step.step_id, "error": str(exc)}
                    )
                    restart_result = ExecutionResult(
                        task_id=task.task_id,
                        step_id=recovery_step.step_id,
                        action=recovery_step.action,
                        attempt=status.attempt,
                        success=False,
                        result={},
                        error=f"Executor raised during recovery: {exc}",
                    )
                if restart_result is None:
                    # Blocked by the allow-list guard (already FAILED).
                    return status
                if not self._check_identity(status, restart_request, restart_result):
                    return status
                status.history.append(
                    {"event": "recovery_execution", "result": _dump_execution(restart_result)}
                )
                self._transition(status, WorkflowState.VERIFYING)
                try:
                    restart_verification = self.verifier.verify(restart_result)
                except Exception as exc:  # noqa: BLE001
                    status.history.append(
                        {"event": "verifier_error", "step_id": recovery_step.step_id, "error": str(exc)}
                    )
                    self._transition(status, WorkflowState.FAILED)
                    status.error = f"Verifier error during recovery: {exc}"
                    return status
                restart_verification = self._effective_verification(
                    status, restart_result, restart_verification
                )
                status.history.append(
                    {
                        "event": "recovery_verification",
                        "result": _dump_verification(restart_verification),
                    }
                )

                # 8. ... then a FRESH health check (restart success alone
                # proves nothing about service health).
                followup = self.recovery_policy.build_followup_health_check(
                    task.task_id, cur_exec, recovery_attempts
                )
                status.history.append(
                    {
                        "event": "fresh_health_check_scheduled",
                        "step_id": followup.step_id,
                    }
                )
                # VERIFYING -> RECOVERING -> EXECUTING bridge to the fresh check.
                self._transition(status, WorkflowState.RECOVERING)
                self._transition(status, WorkflowState.EXECUTING)
                status.attempt += 1
                status.current_step = followup.step_id
                followup_request = ActionRequest(
                    task_id=task.task_id,
                    step_id=followup.step_id,
                    action=followup.action,
                    parameters=dict(followup.parameters),
                    attempt=status.attempt,
                )
                try:
                    fresh_result = self._guarded_execute(status, followup_request)
                except Exception as exc:  # noqa: BLE001
                    status.history.append(
                        {"event": "executor_error", "step_id": followup.step_id, "error": str(exc)}
                    )
                    fresh_result = ExecutionResult(
                        task_id=task.task_id,
                        step_id=followup.step_id,
                        action=followup.action,
                        attempt=status.attempt,
                        success=False,
                        result={},
                        error=f"Executor raised during fresh health check: {exc}",
                    )
                if fresh_result is None:
                    # Blocked by the allow-list guard (already FAILED).
                    return status
                if not self._check_identity(status, followup_request, fresh_result):
                    return status
                status.history.append(
                    {"event": "execution", "result": _dump_execution(fresh_result)}
                )
                self._transition(status, WorkflowState.VERIFYING)
                try:
                    fresh_verification = self.verifier.verify(fresh_result)
                except Exception as exc:  # noqa: BLE001
                    status.history.append(
                        {"event": "verifier_error", "step_id": followup.step_id, "error": str(exc)}
                    )
                    self._transition(status, WorkflowState.FAILED)
                    status.error = f"Verifier error on fresh health check: {exc}"
                    return status
                fresh_verification = self._effective_verification(
                    status, fresh_result, fresh_verification
                )
                status.history.append(
                    {"event": "verification", "result": _dump_verification(fresh_verification)}
                )

                if fresh_verification.passed:
                    self._transition(status, WorkflowState.VERIFIED)
                    status.final_result = {
                        "step_id": followup.step_id,
                        "action": fresh_result.action,
                        "execution": dict(fresh_result.result),
                        "evidence": dict(fresh_verification.evidence),
                        "reason": fresh_verification.reason,
                        "recovered_via": recovery_step.step_id,
                    }
                    status.history.append({"event": "workflow_verified_after_recovery"})
                    return status

                # Fresh check still failing: consume one recovery attempt.
                recovery_attempts += 1
                status.history.append(
                    {
                        "event": "recovery_cycle_failed",
                        "recovery_attempts": recovery_attempts,
                        "max_attempts": self.recovery_policy.max_attempts,
                    }
                )
                self._transition(status, WorkflowState.RECOVERING)
                if recovery_attempts >= self.recovery_policy.max_attempts:
                    self._transition(status, WorkflowState.ESCALATED)
                    status.error = (
                        f"Recovery exhausted after {recovery_attempts} attempt(s); escalating."
                    )
                    status.history.append(
                        {"event": "workflow_escalated", "error": status.error}
                    )
                    return status
                # Next inner-loop cycle reuses the fresh failure directly —
                # no re-execution of the original plan step.
                cur_exec = fresh_result
                cur_verif = fresh_verification
                cur_step_id = followup.step_id

        # Safety net: iteration guard tripped (should be unreachable in
        # normal Level 1 flows because recovery_attempts is bounded).
        self._transition_to_terminal_guard(status)
        status.error = "Iteration guard tripped; escalating to avoid infinite loop."
        status.history.append({"event": "workflow_escalated", "error": status.error})
        return status

    # -- helpers -------------------------------------------------------

    def _guarded_execute(
        self, status: WorkflowStatus, request: ActionRequest
    ) -> ExecutionResult | None:
        """Allow-list gate around :meth:`Executor.execute`.

        Returns the :class:`ExecutionResult`, or None when an unapproved
        action was blocked. On block the workflow is already moved to
        FAILED with an ``unapproved_action`` history event, and the
        executor is never called.
        """
        if request.action not in ALLOWED_ACTIONS:
            status.history.append(
                {
                    "event": "unapproved_action",
                    "step_id": request.step_id,
                    "action": request.action,
                    "allowed": sorted(ALLOWED_ACTIONS),
                }
            )
            self._abort_failed(
                status,
                f"Unapproved action blocked: {request.action!r}. "
                f"Allowed: {sorted(ALLOWED_ACTIONS)}",
            )
            return None
        return self.executor.execute(request)

    def _check_identity(
        self, status: WorkflowStatus, request: ActionRequest, result: ExecutionResult
    ) -> bool:
        """Validate that ``result`` answers ``request``.

        Checks task_id, step_id, action and attempt. On mismatch the
        result is never verified: an ``executor_identity_mismatch``
        event is recorded and the workflow moves to FAILED.
        """
        problems: list[str] = []
        if result.task_id != request.task_id:
            problems.append(
                f"task_id mismatch: expected {request.task_id!r}, got {result.task_id!r}"
            )
        if result.step_id != request.step_id:
            problems.append(
                f"step_id mismatch: expected {request.step_id!r}, got {result.step_id!r}"
            )
        if result.action != request.action:
            problems.append(
                f"action mismatch: expected {request.action!r}, got {result.action!r}"
            )
        if result.attempt != request.attempt:
            problems.append(
                f"attempt mismatch: expected {request.attempt!r}, got {result.attempt!r}"
            )
        if problems:
            status.history.append(
                {
                    "event": "executor_identity_mismatch",
                    "step_id": request.step_id,
                    "problems": problems,
                    "received": _dump_execution(result),
                }
            )
            self._abort_failed(
                status,
                f"Executor identity mismatch on {request.step_id}: "
                + "; ".join(problems),
            )
            return False
        return True

    def _effective_verification(
        self,
        status: WorkflowStatus,
        exec_result: ExecutionResult,
        verification: VerificationResult,
    ) -> VerificationResult:
        """Defensive guard: ``success=False`` can never verify.

        If the verifier returns ``passed=True`` for a failed execution,
        the verdict is corrected to failed (with an
        ``inconsistent_verification`` history event) so the workflow
        takes the failure / recovery path instead of VERIFIED.
        """
        if verification.passed and not exec_result.success:
            status.history.append(
                {
                    "event": "inconsistent_verification",
                    "step_id": exec_result.step_id,
                    "execution_success": exec_result.success,
                    "verifier_passed": verification.passed,
                    "verifier_reason": verification.reason,
                }
            )
            return VerificationResult(
                task_id=verification.task_id,
                step_id=verification.step_id,
                passed=False,
                reason=(
                    "Inconsistent verifier result ignored "
                    f"(execution success=False): {verification.reason or 'no reason'}"
                ),
                evidence=dict(verification.evidence),
            )
        return verification

    def _abort_failed(self, status: WorkflowStatus, error: str) -> None:
        """Move to FAILED from any non-terminal state via a legal path."""
        if status.status == WorkflowState.EXECUTING:
            # EXECUTING has no direct edge to FAILED.
            self._transition(status, WorkflowState.VERIFYING)
            self._transition(status, WorkflowState.FAILED)
        elif status.status in (WorkflowState.VERIFYING, WorkflowState.RECOVERING):
            self._transition(status, WorkflowState.FAILED)
        elif status.status not in (
            WorkflowState.VERIFIED,
            WorkflowState.FAILED,
            WorkflowState.ESCALATED,
        ):
            status.status = WorkflowState.FAILED
            status.history.append(
                {"event": "state_transition", "from": "UNKNOWN", "to": "FAILED"}
            )
        status.error = error
        status.history.append({"event": "workflow_failed", "error": error})

    @staticmethod
    def _transition(status: WorkflowStatus, to_state: WorkflowState) -> None:
        validate_transition(status.status, to_state)
        from_state = status.status
        status.status = to_state
        status.history.append(
            {"event": "state_transition", "from": from_state.value, "to": to_state.value}
        )

    def _transition_to_terminal_guard(self, status: WorkflowStatus) -> None:
        """Force a terminal state from the iteration guard legally."""
        if status.status == WorkflowState.VERIFYING:
            self._transition(status, WorkflowState.RECOVERING)
            self._transition(status, WorkflowState.ESCALATED)
        elif status.status == WorkflowState.RECOVERING:
            self._transition(status, WorkflowState.ESCALATED)
        elif status.status == WorkflowState.EXECUTING:
            self._transition(status, WorkflowState.VERIFYING)
            self._transition(status, WorkflowState.RECOVERING)
            self._transition(status, WorkflowState.ESCALATED)
        elif status.status not in (
            WorkflowState.VERIFIED,
            WorkflowState.FAILED,
            WorkflowState.ESCALATED,
        ):
            status.status = WorkflowState.ESCALATED
            status.history.append(
                {"event": "state_transition", "from": "UNKNOWN", "to": "ESCALATED"}
            )


def _dump_execution(result: ExecutionResult) -> dict[str, Any]:
    return {
        "task_id": result.task_id,
        "step_id": result.step_id,
        "action": result.action,
        "attempt": result.attempt,
        "success": result.success,
        "result": dict(result.result),
        "error": result.error,
    }


def _dump_verification(result: VerificationResult) -> dict[str, Any]:
    return {
        "task_id": result.task_id,
        "step_id": result.step_id,
        "passed": result.passed,
        "reason": result.reason,
        "evidence": dict(result.evidence),
    }
