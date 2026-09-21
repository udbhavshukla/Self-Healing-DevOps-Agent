"""Workflow planner (no LLM, no execution — planning only)."""

from __future__ import annotations

from backend.workflow.models import TaskRequest, WorkflowStep

# Controlled allow-list. The planner and orchestrator must never emit
# actions outside this set (no unrestricted shell / cloud ops).
ALLOWED_ACTIONS = frozenset({"health_check", "restart_service"})

SUPPORTED_TASK_TYPES = frozenset({"service_recovery"})


class WorkflowPlanner:
    """Generate a workflow plan from a :class:`TaskRequest`."""

    def plan(self, task: TaskRequest) -> list[WorkflowStep]:
        """Return an ordered list of :class:`WorkflowStep` objects.

        For Level 1 ``service_recovery`` the plan always starts with a
        basic ``health_check`` step. Whether a ``restart_service`` is
        required is decided later by :class:`RecoveryPolicy` after a
        failed verification — never speculatively by the planner.

        Raises:
            ValueError: If ``task.task_type`` is unsupported.
        """
        if task.task_type not in SUPPORTED_TASK_TYPES:
            raise ValueError(
                f"Unsupported task_type: {task.task_type!r}. "
                f"Supported: {sorted(SUPPORTED_TASK_TYPES)}"
            )

        if task.task_type == "service_recovery":
            return self._plan_service_recovery(task)

        # Defensive: keeps mypy / future task types explicit.
        raise ValueError(f"Unsupported task_type: {task.task_type!r}")

    def _plan_service_recovery(self, task: TaskRequest) -> list[WorkflowStep]:
        service_name = task.parameters.get("service_name", "app")
        return [
            WorkflowStep(
                step_id=f"{task.task_id}-step-1",
                action="health_check",
                parameters={"service_name": service_name},
                order=1,
                max_attempts=3,
            )
        ]
