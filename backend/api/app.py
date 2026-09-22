"""FastAPI app (Level 2: incident input + AI analysis + evidence).

Thin routes only: each endpoint constructs Member 1 / Member 2
objects (via the adapter) and calls the existing orchestrator.
No workflow, recovery, or verification logic lives in the routes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.ai.incident_analyzer import IncidentAnalyzer, build_context
from backend.api.adapter import Member2ExecutorAdapter
from backend.api.evidence import build_evidence
from backend.api.scenarios import (
    SCENARIOS,
    build_service,
    extract_failure_status,
    map_incident_to_scenario,
)
from backend.api.store import get_workflow, save_workflow
from backend.environment.executor import Executor as Member2Executor
from backend.offline import (
    EventStore,
    OfflinePolicy,
    SyncManager,
    get_manager,
)
from backend.verifier.verifier import Verifier
from backend.workflow.models import TaskRequest, WorkflowStatus
from backend.workflow.orchestrator import WorkflowOrchestrator
from backend.workflow.planner import WorkflowPlanner
from backend.workflow.recovery_policy import RecoveryPolicy

ScenarioName = Literal["normal", "injected-failure", "persistent-failure"]

app = FastAPI(title="Self-Healing DevOps Agent (offline-resilient)")


_event_store: Optional[EventStore] = None
_sync_manager: Optional[SyncManager] = None


def get_event_store() -> EventStore:
    """Process-wide SQLite event store (tests may reset it)."""
    global _event_store
    if _event_store is None:
        _event_store = EventStore()
    return _event_store


def get_sync_manager() -> SyncManager:
    """Sync manager bound to the event store and connectivity state."""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = SyncManager(get_event_store(), get_manager())
    return _sync_manager


def reset_offline_layer() -> None:
    """Drop offline singletons (used by tests)."""
    global _event_store, _sync_manager
    _event_store = None
    _sync_manager = None


def offline_summary() -> Dict[str, Any]:
    """Pending/synced/failed counts plus connectivity for payloads."""
    counts = get_event_store().count_by_status()
    manager = get_manager()
    return {
        "connectivity": manager.state(),
        "pending": counts["pending"],
        "synced": counts["synced"],
        "failed": counts["failed"],
        "last_sync": get_sync_manager().last_summary,
    }


def _record_event(
    task_id: Optional[str],
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    sync_status: str = "pending",
) -> Dict[str, Any]:
    return get_event_store().record(
        event_type, payload or {}, task_id=task_id, sync_status=sync_status
    )


def _record_run_events(task_id: str, history: list) -> None:
    """Persist a completed run's history (payloads scrubbed of secrets)."""
    for entry in history:
        if not isinstance(entry, dict):
            continue
        _record_event(
            task_id, str(entry.get("event", "unknown")), dict(entry)
        )


def _sync_and_record(task_id: Optional[str] = None) -> Dict[str, Any]:
    """Attempt synchronization; record lifecycle; return the summary."""
    manager = get_manager()
    if not manager.is_online():
        return get_sync_manager().sync_now()
    _record_event(task_id, "sync_started", {}, sync_status="synced")
    summary = get_sync_manager().sync_now()
    _record_event(
        task_id,
        "sync_completed" if summary["failed"] == 0 else "sync_failed",
        dict(summary),
        sync_status="synced",
    )
    return summary


class WorkflowRequest(BaseModel):
    """Body for POST /api/workflows."""

    task_id: Optional[str] = Field(
        default=None, description="Optional task id; generated when omitted."
    )
    task_type: str = Field(default="service_recovery")
    service_name: str = Field(default="demo-service")
    scenario: ScenarioName = Field(default="normal")
    incident: Optional[str] = Field(
        default=None,
        description="Optional free-text user incident (Level 2).",
    )


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
    incident: Optional[str] = None,
    scenario_explicit: bool = False,
) -> Dict[str, Any]:
    """Build the stack for ``scenario`` and run the orchestrator.

    With ``incident``, the AI analyzer is consulted first (graceful
    fallback when Gemini is unavailable) and the result plus an
    evidence chain are attached to the payload. The orchestrator,
    recovery policy, and verifier run unchanged either way.
    """
    effective_scenario = scenario
    scenario_mapped = False
    reported_http_status: Optional[int] = None
    if incident is not None:
        reported_http_status = extract_failure_status(incident)
        if not scenario_explicit:
            effective_scenario = map_incident_to_scenario(incident)
            scenario_mapped = True
    # The simulated failure carries the user-reported status (e.g. 500)
    # instead of silently collapsing to the 503 default.
    service = build_service(effective_scenario, http_status=reported_http_status)
    executor = Member2Executor(service)
    manager = get_manager()

    ai_analysis: Optional[Dict[str, Any]] = None
    prefix: list = []
    if incident is not None:
        prefix.append(
            {
                "event": "incident_received",
                "incident": incident,
                "scenario": effective_scenario,
                "scenario_mapped": scenario_mapped,
                "reported_http_status": reported_http_status,
            }
        )
        # Pre-flight health snapshot feeds the incident context. This is
        # a read-only observation on the scenario service; the workflow
        # itself still starts from the planner's health check.
        snapshot = executor.execute(
            {
                "task_id": task_id,
                "step_id": f"{task_id}-prefetch",
                "action": "health_check",
                "parameters": {},
            }
        )
        snap_result = snapshot.get("result") or {}
        context = build_context(
            incident,
            service_name=service_name,
            health_status=str(snap_result.get("health_status", "unknown")),
            http_status=snap_result.get("http_status"),
            reported_http_status=reported_http_status,
        )
        if manager.is_online():
            # Online: Gemini advises (existing Level 2 behavior). A
            # confirmed Gemini answer re-affirms observed connectivity;
            # anything else keeps the prior ai_unavailable semantics.
            analysis = IncidentAnalyzer().analyze(incident, context)
            if analysis.source == "gemini":
                manager.report_success()
            ai_analysis = analysis.to_payload()
            if analysis.available and analysis.rejected_action is None:
                prefix.append({"event": "ai_analysis", "result": ai_analysis})
            elif analysis.rejected_action is not None:
                prefix.append(
                    {"event": "ai_action_rejected", "result": ai_analysis}
                )
            else:
                prefix.append({"event": "ai_unavailable", "result": ai_analysis})
        else:
            # Offline: Gemini is never called; the local policy advises.
            policy = OfflinePolicy().recommend(
                incident,
                http_status=(
                    reported_http_status or snap_result.get("http_status")
                ),
                health_status=str(snap_result.get("health_status", "unknown")),
            )
            ai_analysis = policy
            prefix.append({"event": "offline_policy", "result": policy})

    orchestrator = WorkflowOrchestrator(
        WorkflowPlanner(),
        Member2ExecutorAdapter(executor),
        Verifier(),
        RecoveryPolicy(),
    )
    description = f"{task_type} for {service_name} (scenario: {effective_scenario})"
    if incident is not None:
        description = f"Incident: {incident} [{description}]"
    task = TaskRequest(
        task_id=task_id,
        description=description,
        task_type=task_type,
        parameters={"service_name": service_name},
    )
    status = orchestrator.run(task)
    payload = serialize_status(status)
    payload["history"] = prefix + payload["history"]
    payload["ai_analysis"] = ai_analysis
    # Durable audit: persist the run's history, then synchronize when
    # online (events stay pending while offline — nothing is lost).
    _record_run_events(task_id, payload["history"])
    payload["history"].append(
        {
            "event": "final_result",
            "status": payload["status"],
            "error": payload["error"],
        }
    )
    _record_event(
        task_id,
        "final_result",
        {"status": payload["status"], "error": payload["error"]},
    )
    sync_summary = _sync_and_record(task_id)
    payload["evidence"] = build_evidence(
        task_id=task_id,
        status_value=payload["status"],
        history=payload["history"],
        final_result=payload["final_result"],
        error=payload["error"],
        incident=incident,
        service_name=service_name,
        ai_analysis=ai_analysis,
        recorded_at=datetime.now(timezone.utc).isoformat(),
        synchronization=dict(sync_summary),
    )
    payload["connectivity"] = get_manager().state()
    payload["offline"] = offline_summary()
    save_workflow(task_id, payload)
    return payload


@app.get("/api/health")
def health() -> Dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/api/workflows", status_code=201)
def start_workflow(request: WorkflowRequest) -> Dict[str, Any]:
    """Run a workflow for ``request.scenario`` and/or ``request.incident``."""
    if request.scenario not in SCENARIOS:
        raise HTTPException(
            status_code=422, detail=f"Unknown scenario: {request.scenario!r}"
        )
    if request.incident is not None and not request.incident.strip():
        raise HTTPException(
            status_code=422, detail="Incident must be a non-empty string."
        )
    task_id = request.task_id or f"task-{uuid4().hex[:8]}"
    return run_workflow(
        task_id,
        request.task_type,
        request.service_name,
        request.scenario,
        incident=request.incident,
        scenario_explicit="scenario" in request.model_fields_set,
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


class ConnectivityOverride(BaseModel):
    """Body for POST /api/offline/connectivity (demo/test override)."""

    online: Optional[bool] = Field(
        default=None,
        description="Force online/offline; null clears the override.",
    )


@app.get("/api/offline/status")
def offline_status() -> Dict[str, Any]:
    """Connectivity state plus queue counts (auto-syncs when online)."""
    manager = get_manager()
    changed = manager.refresh()
    if changed:
        _record_event(
            None,
            "connectivity_changed",
            {"connectivity": manager.state(), "observed": "probe"},
            sync_status="synced",
        )
    summary = _sync_and_record(None)
    counts = get_event_store().count_by_status()
    return {
        "connectivity": manager.state(),
        "pending": counts["pending"],
        "synced": counts["synced"],
        "failed": counts["failed"],
        "last_sync": summary,
        "last_change_at": manager.last_change_at,
    }


@app.post("/api/offline/sync")
def trigger_sync() -> Dict[str, Any]:
    """Attempt synchronization now (no-op while offline)."""
    summary = _sync_and_record(None)
    counts = get_event_store().count_by_status()
    return {
        "connectivity": get_manager().state(),
        "sync": summary,
        "pending": counts["pending"],
        "synced": counts["synced"],
        "failed": counts["failed"],
    }


@app.post("/api/offline/connectivity")
def set_connectivity(override: ConnectivityOverride) -> Dict[str, Any]:
    """Force or clear the connectivity state (demo/test hook)."""
    manager = get_manager()
    changed = manager.set_override(override.online)
    if changed:
        store = get_event_store()
        store.record(
            "connectivity_changed",
            {"connectivity": manager.state(), "observed": "manual-override"},
            sync_status="synced" if manager.is_online() else "pending",
        )
    if manager.is_online():
        _sync_and_record(None)
    return {"connectivity": manager.state(), **offline_summary()}
