# Shared contracts for the Self-Healing DevOps Agent (Level 1)

The Python dataclasses in `backend/workflow/models.py` are the contract.
Member 2, Member 3 and Member 4 must import them — never redefine them.

- `TaskRequest(task_id, description, task_type, parameters)`
- `WorkflowStep(step_id, action, parameters, order, max_attempts)`
- `ActionRequest(task_id, step_id, action, parameters, attempt)`
- `ExecutionResult(task_id, step_id, action, attempt, success, result, error=None)`
- `VerificationResult(task_id, step_id, passed, reason=None, evidence={})`
- `WorkflowStatus(task_id, status, current_step, attempt, history, final_result, error)`

States (`backend/workflow/states.py`): `PLANNED, EXECUTING, VERIFYING,
RECOVERING, VERIFIED, FAILED, ESCALATED` with explicit transition validation.

Controlled actions only: `health_check`, `restart_service`.

Contract rules enforced by the orchestrator:

- Executors must echo `task_id`, `step_id`, `action` and `attempt` from
  the `ActionRequest` into the `ExecutionResult`. Mismatches fail the
  workflow (`executor_identity_mismatch`, no verification performed).
- Executors must return `ExecutionResult(success=False, ...)` for action
  failures and raise only for crashes.
- Verifiers must only pass executions whose `success` is True. A
  `passed=True` verdict on a failed execution is overruled
  (`inconsistent_verification`) and can never produce VERIFIED.
- `WorkflowStatus.attempt` counts total executor invocations.
- `WorkflowStatus.final_result` is non-null only on VERIFIED.
