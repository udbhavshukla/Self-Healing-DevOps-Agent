"""Tests for WorkflowPlanner."""

import pytest

from backend.workflow.models import TaskRequest
from backend.workflow.planner import ALLOWED_ACTIONS, WorkflowPlanner


def _task(task_type="service_recovery"):
    return TaskRequest(
        task_id="t-1",
        description="service is down",
        task_type=task_type,
        parameters={"service_name": "api"},
    )


def test_planner_generates_health_check():
    planner = WorkflowPlanner()
    steps = planner.plan(_task())
    assert len(steps) == 1
    step = steps[0]
    assert step.action == "health_check"
    assert step.action in ALLOWED_ACTIONS
    assert step.step_id
    assert step.order == 1
    assert step.parameters["service_name"] == "api"


def test_planner_rejects_unsupported_task_type():
    planner = WorkflowPlanner()
    with pytest.raises(ValueError, match="Unsupported task_type"):
        planner.plan(_task(task_type="deploy_production"))


def test_planner_only_emits_controlled_actions():
    planner = WorkflowPlanner()
    steps = planner.plan(_task())
    for step in steps:
        assert step.action in ALLOWED_ACTIONS
