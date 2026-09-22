# INTEGRATION.md — Workflow Orchestrator (Member 1)

Branch: `feature/workflow`. Do not modify `main`.

## 1. What the orchestrator provides

`backend/workflow/orchestrator.py` → `WorkflowOrchestrator(planner, executor, verifier, recovery_policy)`

- `run(task: TaskRequest) -> WorkflowStatus` executes:
  plan → execute → verify → VERIFIED, or on failure → approved `restart_service`
  → fresh `health_check` → re-verify → VERIFIED / ESCALATED / FAILED.
- Guarantees: bounded retries (no infinite loops), full `history`, fresh
  health check after every recovery (restart success alone never verifies),
  structured `WorkflowStatus` for the frontend.
- Safety guards (enforced before/without calling Member 2/3 code):
  action allow-list (`health_check`, `restart_service` only — anything
  else is blocked and the workflow FAILS without executing it),
  `ExecutionResult` identity check (`task_id`/`step_id`/`action`/`attempt`
  must echo the request or the workflow FAILS without verifying),
  verifier guard (`success=False` can never become VERIFIED even if the
  verifier returns `passed=True`).
- Other modules: `models.py` (shared dataclasses), `states.py`
  (`WorkflowState` + transition validation), `interfaces.py`
  (`Executor` / `Verifier` Protocols), `planner.py` (`service_recovery` →
  `health_check`), `recovery_policy.py` (retry limits, approved action).

## 2. How Member 2 implements the Executor

Implement the `Executor` Protocol from `backend/workflow/interfaces.py`:

```python
from backend.workflow.models import ActionRequest, ExecutionResult

class MyExecutor:
    def execute(self, action: ActionRequest) -> ExecutionResult:
        if action.action == "health_check":
            healthy = ...  # check the service, True/False
            return ExecutionResult(
                task_id=action.task_id, step_id=action.step_id,
                action=action.action, attempt=action.attempt,
                success=healthy,
                result={"service_name": "api", "healthy": healthy},
                error=None if healthy else "service unhealthy",
            )
        elif action.action == "restart_service":
            restarted = ...  # restart the service, True/False
            return ExecutionResult(
                task_id=action.task_id, step_id=action.step_id,
                action=action.action, attempt=action.attempt,
                success=restarted,
                result={"service_name": "api", "restarted": restarted},
                error=None if restarted else "restart failed",
            )
        return ExecutionResult(
            task_id=action.task_id, step_id=action.step_id,
            action=action.action, attempt=action.attempt,
            success=False, result={}, error="unsupported action",
        )
```

Rules: only handle `health_check` / `restart_service` (any other
requested action is blocked by the orchestrator's allow-list and never
reaches you); echo back `task_id`, `step_id`, `action` and `attempt`
exactly as received (mismatches fail the workflow); return
`ExecutionResult(success=False, ...)` for action failures (raise only for
crashes — the orchestrator converts crashes to FAILED); never import the
orchestrator.

Wire-up:

```python
orch = WorkflowOrchestrator(WorkflowPlanner(), MyExecutor(), verifier, RecoveryPolicy())
```

## 3. How Member 3 implements the Verifier

Implement the `Verifier` Protocol:

```python
from backend.workflow.models import ExecutionResult, VerificationResult

class MyVerifier:
    def verify(self, result: ExecutionResult) -> VerificationResult:
        passed = bool(result.success and result.result.get("healthy"))
        return VerificationResult(
            task_id=result.task_id, step_id=result.step_id,
            passed=passed, reason="healthy" if passed else "service unhealthy",
            evidence=dict(result.result),
        )
```

Rules: base the verdict on evidence in `ExecutionResult`; always set
`passed` + `reason`; `passed=True` requires `result.success` to be True
(the orchestrator overrules a `passed=True` verdict on a failed
execution and routes it to the failure / recovery path); never execute
actions.

## 4. Shared models

Import from `backend.workflow.models` (see `contracts/README.md`).
`WorkflowStatus.status` is a `WorkflowState`; `history` is a list of event
dicts. Complete event list (every `event` value the orchestrator emits):

- `task_received`, `plan_created`, `planning_failed`
- `executing`, `execution`, `verification`
- `step_passed` (multi-step advance), `verification_failed`
- `recovery_approved`, `recovery_execution`, `recovery_verification`
- `fresh_health_check_scheduled`, `recovery_cycle_failed`
- `workflow_verified`, `workflow_verified_after_recovery`
- `workflow_escalated`, `workflow_failed`, `internal_error`
- `state_transition` (`from`/`to`), `executor_error`, `verifier_error`
- Guard events: `unapproved_action`, `executor_identity_mismatch`,
  `inconsistent_verification`

## 5. How Member 4 consumes workflow status

`run()` returns `WorkflowStatus`. Field semantics:

- `attempt`: total number of executor invocations so far (1 per
  execution: initial check + 2 per recovery cycle). Equals
  `len` of the executor's call log in normal runs.
- `final_result`: non-null **only** on `VERIFIED` (a dict with
  `step_id`, `action`, `execution`, `evidence`, `reason`, plus
  `recovered_via` when verification came after recovery). It is `None`
  on `FAILED` / `ESCALATED` / non-terminal states — the frontend must
  handle null and read `error` instead.
- `current_step`: the last step the orchestrator acted on.
- Terminal states only: `VERIFIED`, `FAILED`, `ESCALATED`.

## 5. How Member 4 consumes workflow status

`run()` returns `WorkflowStatus`:

```python
status = orch.run(task)
payload = {
    "task_id": status.task_id,
    "status": status.status.value,  # e.g. "VERIFIED"
    "current_step": status.current_step,
    "attempt": status.attempt,
    "history": status.history,
    "final_result": status.final_result,
    "error": status.error,
}
```

Poll or render `status` / `history` / `error` directly; states are terminal
only at `VERIFIED`, `FAILED`, `ESCALATED`.

## 6. How to run tests

```powershell
pip install -r requirements.txt
python -m pytest -v
```

Tests use local fake executor / verifier classes (see
`tests/test_orchestrator.py`) and do not need Member 2 / 3 code.
