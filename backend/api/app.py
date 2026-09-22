"""FastAPI app for Member 4 (Level 1 local prototype).

Thin routes only: each endpoint constructs Member 1 / Member 2
objects (via the adapter) and calls the existing orchestrator.
No workflow, recovery, or verification logic lives in the routes.
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.api.adapter import Member2ExecutorAdapter
from backend.api.scenarios import SCENARIOS, build_service
from backend.api.store import get_workflow, save_workflow
from backend.environment.executor import Executor as Member2Executor
from backend.verifier.verifier import Verifier
from backend.workflow.models import TaskRequest, WorkflowStatus
from backend.workflow.orchestrator import WorkflowOrchestrator
from backend.workflow.planner import WorkflowPlanner
from backend.workflow.recovery_policy import RecoveryPolicy

ScenarioName = Literal["normal", "injected-failure", "persistent-failure"]

app = FastAPI(title="Self-Healing DevOps Agent (Level 1)")


class WorkflowRequest(BaseModel):
    """Body for POST /api/workflows."""

    task_id: Optional[str] = Field(
        default=None, description="Optional task id; generated when omitted."
    )
    task_type: str = Field(default="service_recovery")
    service_name: str = Field(default="demo-service")
    scenario: ScenarioName = Field(default="normal")


def serialize_status(status: WorkflowStatus) -> Dict[str, Any]:
    """Convert a ``WorkflowStatus`` into a JSON-serializable payload."""
    return {
        "task_id": status.task_id,
        "status": status.status.value,
        "current_step": status.current_step,
        "attempt": status.attempt,
        "history": status.history,
        "final_result": status.final_result,
        "error": status.error,
    }


def run_workflow(
    task_id: str,
    task_type: str,
    service_name: str,
    scenario: str,
) -> Dict[str, Any]:
    """Build the stack for ``scenario`` and run the orchestrator."""
    service = build_service(scenario)
    orchestrator = WorkflowOrchestrator(
        WorkflowPlanner(),
        Member2ExecutorAdapter(Member2Executor(service)),
        Verifier(),
        RecoveryPolicy(),
    )
    task = TaskRequest(
        task_id=task_id,
        description=f"{task_type} for {service_name} (scenario: {scenario})",
        task_type=task_type,
        parameters={"service_name": service_name},
    )
    status = orchestrator.run(task)
    payload = serialize_status(status)
    save_workflow(task_id, payload)
    return payload


@app.get("/api/health")
def health() -> Dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/api/workflows", status_code=201)
def start_workflow(request: WorkflowRequest) -> Dict[str, Any]:
    """Run a workflow for ``request.scenario`` and return its status."""
    if request.scenario not in SCENARIOS:
        raise HTTPException(
            status_code=422, detail=f"Unknown scenario: {request.scenario!r}"
        )
    task_id = request.task_id or f"task-{uuid4().hex[:8]}"
    return run_workflow(
        task_id, request.task_type, request.service_name, request.scenario
    )


@app.get("/api/workflows/{task_id}")
def get_workflow_status(task_id: str) -> Dict[str, Any]:
    """Return the stored workflow status for ``task_id``."""
    payload = get_workflow(task_id)
    if payload is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown task_id: {task_id!r}"
        )
    return payload
