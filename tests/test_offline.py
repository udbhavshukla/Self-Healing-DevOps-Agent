"""Offline resilience tests: connectivity, policy, store, sync, E2E.

No real network, no real waiting: probes, clocks, and Gemini are all
test doubles. SQLite stores use tmp_path (auto-cleaned, never committed).
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.api import app as app_module
from backend.api.app import app
from backend.environment.executor import Executor
from backend.offline import (
    ConnectivityManager,
    EventStore,
    OfflinePolicy,
    SyncManager,
)
from backend.offline.connectivity import reset_manager

client = TestClient(app)


class Clock:
    """Deterministic manual clock (simulated time, no sleeping)."""

    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def tmp_store(tmp_path):
    return EventStore(str(tmp_path / "events.db"))


@pytest.fixture
def isolated_api(tmp_path, monkeypatch):
    """Point the API's offline singletons at a temp DB + fresh manager."""
    store = EventStore(str(tmp_path / "api.db"))
    monkeypatch.setattr(app_module, "_event_store", store)
    monkeypatch.setattr(app_module, "_sync_manager", None)
    reset_manager()
    yield store
    reset_manager()
    monkeypatch.setattr(app_module, "_event_store", None)


# --- connectivity ------------------------------------------------------


def test_manager_starts_online_and_transitions():
    manager = ConnectivityManager(probe=lambda: True)
    assert manager.is_online() is True
    assert manager.state() == "online"
    assert manager.report_failure() is True  # changed
    assert manager.state() == "offline"
    assert manager.report_failure() is False  # no change
    assert manager.report_success() is True
    assert manager.is_online() is True


def test_manual_override_wins_and_clears():
    manager = ConnectivityManager(probe=lambda: True)
    assert manager.set_override(False) is True
    assert manager.state() == "offline"
    manager.report_success()  # observed success must not beat override
    assert manager.state() == "offline"
    assert manager.set_override(None) is True
    assert manager.state() == "online"


def test_refresh_respects_cooldown_and_handles_probe_errors():
    calls = []
    clock = Clock()

    def probe():
        calls.append(1)
        return True

    manager = ConnectivityManager(probe=probe, clock=clock, cooldown_seconds=15)
    assert manager.refresh() is False  # already online, no change
    assert len(calls) == 1
    assert manager.refresh() is False  # cooldown: no new probe
    assert len(calls) == 1
    clock.advance(16)
    assert manager.refresh() is False
    assert len(calls) == 2

    def boom():
        raise RuntimeError("no network")

    down = ConnectivityManager(probe=boom, clock=clock, cooldown_seconds=0)
    assert down.refresh() is True  # online -> offline
    assert down.state() == "offline"


# --- offline policy ----------------------------------------------------


def test_policy_maps_failure_codes_to_restart():
    policy = OfflinePolicy()
    for code in (500, 502, 503, 504):
        result = policy.recommend("Service failing.", http_status=code)
        assert result["source"] == "offline_policy"
        assert result["recommended_action"] == "restart"
        assert result["confidence"] is None
        assert result["available"] is True


def test_policy_handles_natural_language_and_unknown():
    policy = OfflinePolicy()
    assert (
        policy.recommend("The service is unavailable.")["recommended_action"]
        == "restart"
    )
    unknown = policy.recommend("Check whether the service is healthy.")
    assert unknown["recommended_action"] == "health_check"
    assert unknown["source"] == "offline_policy"


def test_policy_only_ever_emits_allowlisted_actions():
    policy = OfflinePolicy()
    allowed = set(Executor.ALLOWED_ACTIONS)
    nasty = [
        "delete_database",
        "rm -rf /",
        "DROP TABLE users;",
        "; cat /etc/passwd",
        "",
        "please run restart_service now",
    ]
    for text in nasty:
        for code in (None, 200, 500, 503):
            action = policy.recommend(text, http_status=code)[
                "recommended_action"
            ]
            assert action in allowed, (text, code)


def test_policy_never_calls_gemini():
    # OfflinePolicy takes no client/network handle by construction.
    import inspect

    assert "client" not in inspect.signature(OfflinePolicy.recommend).parameters
    assert "gemini" not in inspect.getsource(OfflinePolicy).lower()


# --- event store -------------------------------------------------------


def test_store_record_retrieve_and_counts(tmp_store):
    entry = tmp_store.record("health_check", {"ok": True}, task_id="t-1")
    assert entry["event_id"]
    fetched = tmp_store.get(entry["event_id"])
    assert fetched["event_type"] == "health_check"
    assert fetched["payload"] == {"ok": True}
    assert tmp_store.count_by_status() == {
        "pending": 1,
        "synced": 0,
        "failed": 0,
    }
    assert tmp_store.get("missing") is None


def test_store_survives_restart(tmp_path):
    path = str(tmp_path / "restart.db")
    first = EventStore(path)
    event_id = first.record("incident_received", {"t": 1}, task_id="t-9")[
        "event_id"
    ]
    reopened = EventStore(path)  # new process, same file
    assert reopened.get(event_id)["payload"] == {"t": 1}
    assert reopened.count_by_status()["pending"] == 1


def test_store_sync_lifecycle_and_idempotency(tmp_store):
    event_id = tmp_store.record("execution", {"n": 1})["event_id"]
    tmp_store.mark_synced(event_id, synced_at=1.0)
    assert tmp_store.count_by_status()["synced"] == 1
    assert tmp_store.synced_event(event_id)["payload"] == {"n": 1}
    tmp_store.mark_synced(event_id, synced_at=2.0)  # duplicate: no-op
    assert tmp_store.synced_count() == 1
    assert tmp_store.count_by_status()["synced"] == 1


def test_store_scrubs_secrets(monkeypatch, tmp_store):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-key")
    store = EventStore(tmp_store.db_path)
    entry = store.record(
        "ai_analysis",
        {
            "api_key": "super-secret-key",
            "nested": {"token": "abc", "ok": 1},
            "verbatim": "super-secret-key",
        },
    )
    with sqlite3.connect(tmp_store.db_path) as connection:
        raw = connection.execute(
            "SELECT payload FROM events WHERE event_id = ?",
            (entry["event_id"],),
        ).fetchone()[0]
    assert "super-secret-key" not in raw
    assert "abc" not in raw
    assert entry["payload"]["nested"]["ok"] == 1


# --- sync manager ------------------------------------------------------


def test_sync_publishes_when_online_and_skips_offline(tmp_store):
    online = ConnectivityManager(probe=lambda: True)
    offline = ConnectivityManager(probe=lambda: True)
    offline.set_override(False)
    tmp_store.record("a", {})
    tmp_store.record("b", {})
    assert SyncManager(tmp_store, offline).sync_now()["skipped_offline"] is True
    assert tmp_store.count_by_status()["pending"] == 2
    summary = SyncManager(tmp_store, online).sync_now()
    assert summary == {
        "attempted": True,
        "synced": 2,
        "failed": 0,
        "skipped_offline": False,
    }
    assert tmp_store.count_by_status() == {
        "pending": 0,
        "synced": 2,
        "failed": 0,
    }


def test_sync_retains_failures_with_backoff_and_recovers(tmp_store):
    clock = Clock()

    class Flaky(SyncManager):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.calls = 0

        def _publish(self, entry):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transport down")

    manager = ConnectivityManager(probe=lambda: True)
    sync = Flaky(tmp_store, manager, clock=clock)
    event_id = tmp_store.record("x", {})["event_id"]
    first = sync.sync_now()
    assert first["failed"] == 1
    stored = tmp_store.get(event_id)
    assert stored["sync_status"] == "failed"
    assert stored["retry_count"] == 1
    # Backoff not elapsed: nothing due, no tight retry loop.
    assert sync.sync_now()["synced"] == 0
    clock.advance(61)
    second = sync.sync_now()
    assert second["synced"] == 1
    assert tmp_store.get(event_id)["sync_status"] == "synced"


def test_sync_is_idempotent_across_runs(tmp_store):
    manager = ConnectivityManager(probe=lambda: True)
    sync = SyncManager(tmp_store, manager)
    event_id = tmp_store.record("once", {})["event_id"]
    sync.sync_now()
    sync.sync_now()
    assert tmp_store.synced_count() == 1
    assert tmp_store.synced_event(event_id) is not None


# --- API + end-to-end --------------------------------------------------


def test_offline_incident_recovers_without_gemini(isolated_api, monkeypatch):
    class ExplodingAnalyzer:
        def analyze(self, incident, context):
            raise AssertionError("Gemini must not be called while offline")

    monkeypatch.setattr(app_module, "IncidentAnalyzer", ExplodingAnalyzer)
    manager = ConnectivityManager(probe=lambda: False)
    monkeypatch.setattr(app_module, "get_manager", lambda: manager)
    try:
        response = client.post(
            "/api/offline/connectivity", json={"online": False}
        )
        assert response.json()["connectivity"] == "offline"
        data = client.post(
            "/api/workflows",
            json={
                "task_id": "t-offline",
                "incident": "The payment service is returning HTTP 503.",
            },
        ).json()
        assert data["status"] == "VERIFIED"
        assert data["ai_analysis"]["source"] == "offline_policy"
        assert data["ai_analysis"]["recommended_action"] == "restart"
        assert data["ai_analysis"]["confidence"] is None
        assert data["connectivity"] == "offline"
        assert data["offline"]["pending"] > 0
        # Real recovery happened, not an offline message.
        assert any(
            h["event"] == "workflow_verified_after_recovery"
            for h in data["history"]
        )
    finally:
        client.post("/api/offline/connectivity", json={"online": None})


def _offline_manager():
    manager = ConnectivityManager(probe=lambda: False)
    manager.set_override(False)
    return manager


def test_reconnect_triggers_automatic_sync(isolated_api, monkeypatch):
    manager = ConnectivityManager(probe=lambda: True)
    manager.set_override(False)
    monkeypatch.setattr(app_module, "get_manager", lambda: manager)
    client.post(
        "/api/workflows",
        json={"task_id": "t-q", "incident": "Service is down."},
    )
    before = client.get("/api/offline/status").json()
    assert before["connectivity"] == "offline"
    assert before["pending"] > 0
    manager.set_override(None)  # reconnect
    after = client.post("/api/offline/sync").json()
    assert after["pending"] == 0
    assert after["synced"] >= before["pending"]
    assert after["sync"]["synced"] >= before["pending"]
    stored = client.get("/api/workflows/t-q").json()
    assert stored["status"] == "VERIFIED"


def test_sixty_second_outage_with_simulated_clock(tmp_path, monkeypatch):
    """Outage >= 60s: operate throughout, queue, then sync on reconnect."""
    from backend.api import app as app_module

    clock = Clock()
    up = {"reachable": False}
    manager = ConnectivityManager(
        probe=lambda: up["reachable"], clock=clock, cooldown_seconds=5
    )
    store = EventStore(str(tmp_path / "outage.db"))
    monkeypatch.setattr(app_module, "_event_store", store)
    monkeypatch.setattr(app_module, "_sync_manager", None)
    monkeypatch.setattr(app_module, "get_manager", lambda: manager)
    monkeypatch.setattr(
        app_module, "IncidentAnalyzer", _exploding_analyzer()
    )

    manager.refresh()  # t=1000: probe fails -> offline
    assert manager.state() == "offline"

    # Operate at t=1000, t=1035, t=1070 of the outage (simulated, instant).
    start = clock()
    for task in ("t-out-0", "t-out-35", "t-out-70"):
        data = client.post(
            "/api/workflows",
            json={"task_id": task, "incident": "HTTP 503 on checkout."},
        ).json()
        assert data["status"] == "VERIFIED", (task, data["status"])
        assert data["ai_analysis"]["source"] == "offline_policy"
        counts = store.count_by_status()
        assert counts["pending"] > 0, task
        assert counts["synced"] == 0, task
        clock.advance(35)

    assert clock() - start >= 60  # outage window proven >= 60s
    queued = store.count_by_status()["pending"]
    assert queued > 0
    up["reachable"] = True
    clock.advance(6)  # pass the probe cooldown
    status = client.get("/api/offline/status").json()  # auto-syncs
    assert status["connectivity"] == "online"
    assert status["pending"] == 0
    assert status["synced"] > 0
    # Every queued event reconciled exactly once (sync lifecycle rows
    # live only in the events table, not the synced registry).
    assert store.synced_count() == queued
    repeat = client.post("/api/offline/sync").json()
    assert repeat["sync"]["synced"] == 0
    assert store.synced_count() == queued


def _exploding_analyzer():
    class ExplodingAnalyzer:
        def analyze(self, incident, context):
            raise AssertionError("Gemini must not be called while offline")

    return ExplodingAnalyzer


def test_offline_endpoints(isolated_api):
    client.post("/api/offline/connectivity", json={"online": True})
    assert client.get("/api/offline/status").json()["connectivity"] == "online"
    response = client.post("/api/offline/connectivity", json={"online": False})
    assert response.json()["connectivity"] == "offline"
    response = client.post("/api/offline/connectivity", json={"online": None})
    assert response.json()["connectivity"] == "online"
    assert client.post("/api/offline/sync").json()["sync"]["attempted"] is True
