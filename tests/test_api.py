"""Tests for the Member 4 API layer (FastAPI + adapter + scenarios)."""

from fastapi.testclient import TestClient

from backend.api import store
from backend.api.app import app

client = TestClient(app)


def setup_function(_function):
    store.clear_workflows()


def _payload(response):
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_health_returns_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_normal_scenario_verifies():
    data = _payload(
        client.post(
            "/api/workflows",
            json={"task_id": "t-normal", "scenario": "normal"},
        )
    )
    assert data["task_id"] == "t-normal"
    assert data["status"] == "VERIFIED"
    assert data["error"] is None
    assert data["final_result"] is not None


def test_injected_failure_recovers_and_verifies():
    data = _payload(
        client.post(
            "/api/workflows",
            json={"task_id": "t-heal", "scenario": "injected-failure"},
        )
    )
    assert data["status"] == "VERIFIED"
    events = [h["event"] for h in data["history"]]
    assert "recovery_approved" in events
    assert "workflow_verified_after_recovery" in events
    assert data["final_result"]["recovered_via"] is not None


def test_persistent_failure_escalates():
    data = _payload(
        client.post(
            "/api/workflows",
            json={"task_id": "t-escalate", "scenario": "persistent-failure"},
        )
    )
    assert data["status"] == "ESCALATED"
    assert data["final_result"] is None
    assert data["error"] is not None


def test_get_existing_workflow_returns_stored_status():
    created = _payload(
        client.post(
            "/api/workflows",
            json={"task_id": "t-stored", "scenario": "normal"},
        )
    )
    response = client.get("/api/workflows/t-stored")
    assert response.status_code == 200
    assert response.json() == created


def test_get_unknown_workflow_returns_404():
    response = client.get("/api/workflows/no-such-task")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_response_shape():
    data = _payload(
        client.post(
            "/api/workflows",
            json={"task_id": "t-shape", "scenario": "normal"},
        )
    )
    assert set(data.keys()) == {
        "task_id",
        "status",
        "current_step",
        "attempt",
        "history",
        "final_result",
        "error",
        # Level 2 additive fields (null when no incident is provided).
        "ai_analysis",
        "evidence",
        # Offline-resilience additive fields.
        "connectivity",
        "offline",
    }
    assert data["current_step"] is not None
    assert data["attempt"] >= 1
    assert isinstance(data["history"], list) and data["history"]


def test_task_id_generated_when_omitted():
    data = _payload(client.post("/api/workflows", json={"scenario": "normal"}))
    assert data["task_id"].startswith("task-")
    assert client.get(f"/api/workflows/{data['task_id']}").status_code == 200
