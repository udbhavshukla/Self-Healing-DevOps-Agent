"""Adapter bridging Member 1 (workflow) and Member 2 (executor).

Known mismatch (do NOT fix by editing Member 1 or Member 2):
- Member 1 calls ``executor.execute(ActionRequest)`` (dataclass) and uses
  the action name ``restart_service``.
- Member 2 expects ``executor.execute(dict)`` and accepts ``restart``.

This adapter translates both directions and maps ``restart_service``
back and forth so the orchestrator's identity check
(task_id/step_id/action/attempt echo) keeps passing.

Tool success vs. application health is preserved untouched: e.g. a
health check returning HTTP 503 stays ``success=True`` with an
unhealthy result payload.
"""

from __future__ import annotations

from backend.environment.executor import Executor as Member2Executor
from backend.workflow.models import ActionRequest, ExecutionResult

# Member 1 action name -> Member 2 action name.
ACTION_MAP = {"restart_service": "restart"}
REVERSE_ACTION_MAP = {v: k for k, v in ACTION_MAP.items()}


class Member2ExecutorAdapter:
    """Implement Member 1's ``Executor`` Protocol using Member 2's executor."""

    def __init__(self, executor: Member2Executor) -> None:
        """Wrap an existing Member 2 executor.

        Args:
            executor: The Member 2 executor bound to the scenario's service.
        """
        self.executor = executor

    def execute(self, action: ActionRequest) -> ExecutionResult:
        """Execute ``action`` via Member 2 and return an ``ExecutionResult``.

        Args:
            action: The Member 1 action request dataclass.

        Returns:
            ExecutionResult with task_id/step_id/action/attempt echoed
            exactly as received (using Member 1's action name).
        """
        member2_action = ACTION_MAP.get(action.action, action.action)
        request = {
            "task_id": action.task_id,
            "step_id": action.step_id,
            "action": member2_action,
            "parameters": dict(action.parameters),
            "attempt": action.attempt,
        }
        raw = self.executor.execute(request)
        result = raw.get("result")
        return ExecutionResult(
            task_id=raw.get("task_id", action.task_id),
            step_id=raw.get("step_id", action.step_id),
            # Echo Member 1's action name so the orchestrator's
            # identity check passes.
            action=action.action,
            attempt=raw.get("attempt", action.attempt),
            success=bool(raw.get("success", False)),
            result=dict(result) if isinstance(result, dict) else {},
            error=raw.get("error"),
        )
