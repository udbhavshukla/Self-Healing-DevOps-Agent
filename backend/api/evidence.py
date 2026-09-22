"""Evidence chain builder (Level 2).

Derives a human- and machine-readable evidence chain strictly from
actual workflow data (history events, final result, incident, AI
analysis). Nothing is fabricated: absent data stays null, and
``recorded_at`` is the API-observed completion time (passed in, not
invented per event).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _results(history: List[Dict[str, Any]], events: tuple) -> List[Dict[str, Any]]:
    out = []
    for entry in history:
        if entry.get("event") in events and isinstance(entry.get("result"), dict):
            out.append(entry["result"])
    return out


def _summarize_execution(exec_payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not exec_payload:
        return None
    result = exec_payload.get("result") or {}
    return {
        "step_id": exec_payload.get("step_id"),
        "action": exec_payload.get("action"),
        "attempt": exec_payload.get("attempt"),
        "success": exec_payload.get("success"),
        "http_status": result.get("http_status"),
        "health_status": result.get("health_status"),
    }


def build_evidence(
    task_id: str,
    status_value: str,
    history: List[Dict[str, Any]],
    final_result: Optional[Dict[str, Any]],
    error: Optional[str],
    incident: Optional[str] = None,
    service_name: str = "demo-service",
    ai_analysis: Optional[Dict[str, Any]] = None,
    recorded_at: Optional[str] = None,
    synchronization: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the evidence chain for a completed workflow run."""
    executions = _results(history, ("execution", "recovery_execution"))
    verifications = _results(history, ("verification", "recovery_verification"))
    recovery_runs = _results(history, ("recovery_execution",))
    approvals = [
        e for e in history if e.get("event") == "recovery_approved"
    ]

    recovery = []
    for i, approval in enumerate(approvals):
        run = recovery_runs[i] if i < len(recovery_runs) else {}
        run_result = run.get("result") or {}
        recovery.append(
            {
                "attempt": i + 1,
                "action": approval.get("action"),
                "step_id": approval.get("step_id"),
                "executed": bool(run),
                "execution_success": run.get("success"),
                "recovered": run_result.get("recovered"),
                "health_status": run_result.get("health_status"),
            }
        )

    return {
        "task_id": task_id,
        "recorded_at": recorded_at,
        "incident": (
            {"text": incident, "service_name": service_name}
            if incident
            else None
        ),
        "ai_analysis": ai_analysis,
        "before": _summarize_execution(executions[0] if executions else None),
        "recovery": recovery,
        "after": _summarize_execution(executions[-1] if executions else None),
        "verification": [
            {
                "step_id": v.get("step_id"),
                "passed": v.get("passed"),
                "reason": v.get("reason"),
            }
            for v in verifications
        ],
        "final": {
            "status": status_value,
            "outcome": "VERIFIED" if status_value == "VERIFIED" else status_value,
            "error": error,
            "recovered_via": (final_result or {}).get("recovered_via"),
        },
        "synchronization": synchronization,
    }
