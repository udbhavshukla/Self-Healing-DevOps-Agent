"""Level 2 tests: AI schemas/client/analyzer, incident API, evidence.

Gemini is never called: a fake client stands in for success paths,
while missing keys / raising clients exercise the fallback. All
incident mapping and evidence assertions are deterministic.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.ai import incident_analyzer as analyzer_module
from backend.api import app as app_module
from backend.ai.gemini_client import AIUnavailableError, GeminiClient, _parse_json
from backend.ai.incident_analyzer import (
    IncidentAnalyzer,
    build_context,
    build_prompt,
)
from backend.ai.schemas import (
    AIAnalysisResult,
    AIRecommendation,
    IncidentContext,
)
from backend.api import store
from backend.api.app import app
from backend.api.evidence import build_evidence
from backend.api.scenarios import (
    build_service,
    extract_failure_status,
    map_incident_to_scenario,
)
from backend.environment.health_checker import check_health
from backend.environment.mock_service import MockService

client = TestClient(app)


def setup_function(_function):
    store.clear_workflows()


class FakeClient:
    """Test double for GeminiClient (no network)."""

    def __init__(self, payload=None, error=None, model="fake-model"):
        self.payload = payload
        self.error = error
        self.model = model
        self.prompts = []

    @property
    def available(self):
        return True

    def analyze_incident(self, prompt):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.payload


GOOD_PAYLOAD = {
    "diagnosis": "Service is unhealthy and returning HTTP 503.",
    "recommended_action": "restart",
    "reason": "Restart is an allowed recovery action.",
    "confidence": 0.91,
}


def _context():
    return build_context(
        "The service is returning HTTP 503.",
        health_status="unhealthy",
        http_status=503,
    )


# --- schemas -----------------------------------------------------------


def test_recommendation_schema_validates():
    rec = AIRecommendation.model_validate(GOOD_PAYLOAD)
    assert rec.recommended_action == "restart"
    assert rec.confidence == pytest.approx(0.91)


def test_recommendation_rejects_bad_confidence_and_blanks():
    with pytest.raises(ValidationError):
        AIRecommendation.model_validate({**GOOD_PAYLOAD, "confidence": 1.5})
    with pytest.raises(ValidationError):
        AIRecommendation.model_validate({**GOOD_PAYLOAD, "diagnosis": ""})
    with pytest.raises(ValidationError):
        AIRecommendation.model_validate(
            {k: v for k, v in GOOD_PAYLOAD.items() if k != "reason"}
        )


def test_context_lists_allowed_actions_and_no_secrets():
    ctx = _context()
    assert set(ctx.allowed_actions) == {
        "health_check",
        "restart",
        "inject_failure",
        "deploy",
    }
    prompt = build_prompt(ctx)
    assert "HTTP 503" in prompt
    for banned in ("GEMINI_API_KEY", "sk-", "secret", "token"):
        assert banned not in prompt


# --- client parsing ----------------------------------------------------


def test_parse_json_handles_prose_wrapping():
    parsed = _parse_json('Here you go:\n{"a": 1}\nDone.')
    assert parsed == {"a": 1}
    with pytest.raises(AIUnavailableError):
        _parse_json("no json here")
    with pytest.raises(AIUnavailableError):
        _parse_json("[1, 2]")


def test_client_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert GeminiClient().available is False
    with pytest.raises(AIUnavailableError):
        GeminiClient().analyze_incident("hi")


# --- analyzer ----------------------------------------------------------


def test_analyzer_accepts_valid_recommendation():
    result = IncidentAnalyzer(FakeClient(GOOD_PAYLOAD)).analyze(
        "The service is returning HTTP 503.", _context()
    )
    assert result.available is True
    assert result.source == "gemini"
    assert result.recommended_action == "restart"
    assert result.confidence == pytest.approx(0.91)


def test_analyzer_rejects_unknown_action():
    result = IncidentAnalyzer(
        FakeClient({**GOOD_PAYLOAD, "recommended_action": "delete_database"})
    ).analyze("boom", _context())
    assert result.available is True
    assert result.recommended_action is None
    assert result.rejected_action == "delete_database"
    assert "not in" in (result.error or "")


def test_analyzer_falls_back_on_client_errors():
    for error in (
        AIUnavailableError("nope"),
        TimeoutError("slow"),
        RuntimeError("bad"),
    ):
        result = IncidentAnalyzer(FakeClient(error=error)).analyze(
            "hi", _context()
        )
        assert result.available is False
        assert result.source == "unavailable"
        assert result.diagnosis is None
        assert result.error


def test_analyzer_rejects_malformed_payload_and_empty_incident():
    result = IncidentAnalyzer(FakeClient({"diagnosis": "x"})).analyze(
        "hi", _context()
    )
    assert result.available is False
    with pytest.raises(ValueError):
        IncidentAnalyzer(FakeClient(GOOD_PAYLOAD)).analyze("   ", _context())


def test_incident_mapping_is_deterministic():
    assert (
        map_incident_to_scenario("The service is returning HTTP 503.")
        == "injected-failure"
    )
    assert (
        map_incident_to_scenario("Still unavailable after restart.")
        == "persistent-failure"
    )
    assert (
        map_incident_to_scenario("Check whether the service is healthy.")
        == "normal"
    )


# --- API ---------------------------------------------------------------


def test_incident_request_verifies_with_ai_payload(monkeypatch):
    monkeypatch.setattr(
        app_module, "IncidentAnalyzer",
        lambda: IncidentAnalyzer(FakeClient(GOOD_PAYLOAD)),
    )
    response = client.post(
        "/api/workflows",
        json={
            "task_id": "t-incident",
            "incident": "The service is returning HTTP 503.",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "VERIFIED"
    ai = data["ai_analysis"]
    assert ai["available"] is True
    assert ai["recommended_action"] == "restart"
    events = [h["event"] for h in data["history"]]
    assert events[0] == "incident_received"
    assert "ai_analysis" in events
    assert data["evidence"]["before"]["http_status"] == 503
    assert data["evidence"]["after"]["http_status"] == 200
    assert data["evidence"]["final"]["status"] == "VERIFIED"


def test_incident_without_gemini_falls_back_and_still_verifies(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        app_module, "IncidentAnalyzer",
        lambda: IncidentAnalyzer(FakeClient(error=AIUnavailableError("down"))),
    )
    data = client.post(
        "/api/workflows",
        json={"task_id": "t-fallback", "incident": "Service is down."},
    ).json()
    assert data["status"] == "VERIFIED"
    assert data["ai_analysis"]["available"] is False
    assert "ai_unavailable" in [h["event"] for h in data["history"]]


def test_rejected_ai_action_is_recorded_not_executed(monkeypatch):
    monkeypatch.setattr(
        app_module, "IncidentAnalyzer",
        lambda: IncidentAnalyzer(
            FakeClient({**GOOD_PAYLOAD, "recommended_action": "delete_database"})
        ),
    )
    data = client.post(
        "/api/workflows",
        json={"task_id": "t-reject", "incident": "Service is down."},
    ).json()
    assert data["ai_analysis"]["rejected_action"] == "delete_database"
    assert "ai_action_rejected" in [h["event"] for h in data["history"]]
    executed = [
        h["result"]["action"]
        for h in data["history"]
        if h["event"] in ("execution", "recovery_execution")
    ]
    assert "delete_database" not in executed


def test_blank_incident_rejected_and_scenarios_untouched():
    response = client.post("/api/workflows", json={"incident": "   "})
    assert response.status_code == 422
    # Level 1 scenario-only requests keep working with null ai_analysis.
    data = client.post(
        "/api/workflows", json={"task_id": "t-plain", "scenario": "normal"}
    ).json()
    assert data["status"] == "VERIFIED"
    assert data["ai_analysis"] is None
    assert data["evidence"]["final"]["status"] == "VERIFIED"


def test_persistent_incident_escalates_with_evidence():
    data = client.post(
        "/api/workflows",
        json={
            "task_id": "t-persist",
            "incident": "Service still unavailable after restart.",
        },
    ).json()
    assert data["status"] == "ESCALATED"
    assert len(data["evidence"]["recovery"]) == 3
    assert data["evidence"]["after"]["http_status"] == 503
    assert data["evidence"]["final"]["error"] is not None


# --- evidence ----------------------------------------------------------


def test_evidence_before_after_recovery_from_real_history():
    data = client.post(
        "/api/workflows", json={"task_id": "t-ev", "scenario": "injected-failure"}
    ).json()
    ev = data["evidence"]
    assert ev["before"]["http_status"] == 503
    assert ev["before"]["health_status"] == "unhealthy"
    assert ev["after"]["http_status"] == 200
    assert ev["after"]["health_status"] == "healthy"
    assert ev["recovery"][0]["action"] == "restart_service"
    assert ev["recovery"][0]["recovered"] is True
    assert ev["verification"][0]["passed"] is False
    assert ev["verification"][-1]["passed"] is True
    assert ev["recorded_at"]


def test_build_evidence_never_fabricates():
    ev = build_evidence(
        task_id="t", status_value="FAILED", history=[],
        final_result=None, error="x",
    )
    assert ev["before"] is None
    assert ev["after"] is None
    assert ev["recovery"] == []
    assert ev["verification"] == []


# --- HTTP status preservation (500 vs 503) ------------------------------


def test_extract_failure_status():
    assert extract_failure_status(
        "The payment service started returning HTTP 500 errors "
        "after the latest deployment."
    ) == 500
    assert extract_failure_status("Service 503 unavailable") == 503
    assert extract_failure_status("Check whether the service is healthy.") is None
    assert extract_failure_status("Latency is 200ms, all good.") is None
    # First error code wins; 2xx codes are ignored.
    assert extract_failure_status("Was 200, now HTTP 502 bad gateway") == 502


def test_configurable_failure_status_defaults_to_503():
    default = MockService()
    default.inject_failure()
    assert check_health(default) == {
        "http_status": 503,
        "health_status": "unhealthy",
    }
    custom = MockService(fail_http_status=500)
    custom.inject_failure()
    assert check_health(custom) == {
        "http_status": 500,
        "health_status": "unhealthy",
    }
    assert custom.get_info()["fail_http_status"] == 500
    # Recovery still heals to 200/healthy regardless of failure code.
    custom.restart()
    assert check_health(custom)["http_status"] == 200


def test_invalid_failure_status_rejected():
    for bad in (99, 600, "500", True, None.__class__):
        with pytest.raises(ValueError):
            MockService(fail_http_status=bad)
    with pytest.raises(ValueError):
        build_service("injected-failure", http_status=99)


def test_build_service_carries_incident_status():
    service = build_service("injected-failure", http_status=500)
    assert check_health(service)["http_status"] == 500
    assert build_service("injected-failure") is not None
    defaulted = build_service("injected-failure")
    defaulted.inject_failure()
    assert check_health(defaulted)["http_status"] == 503


def test_http_500_incident_preserved_end_to_end(monkeypatch):
    monkeypatch.setattr(
        app_module, "IncidentAnalyzer",
        lambda: IncidentAnalyzer(FakeClient(GOOD_PAYLOAD)),
    )
    data = client.post(
        "/api/workflows",
        json={
            "task_id": "t-500",
            "incident": "The payment service started returning "
            "HTTP 500 errors after the latest deployment.",
        },
    ).json()
    assert data["status"] == "VERIFIED"
    # The user's 500 is preserved, not converted to 503.
    assert data["evidence"]["before"]["http_status"] == 500
    assert data["evidence"]["before"]["health_status"] == "unhealthy"
    assert data["evidence"]["after"]["http_status"] == 200
    checks = [
        h["result"]["result"]
        for h in data["history"]
        if h["event"] == "execution"
    ]
    assert checks and checks[0]["http_status"] == 500
    assert {c["http_status"] for c in checks} <= {500, 200}


def test_http_500_persistent_incident_escalates_with_500s():
    data = client.post(
        "/api/workflows",
        json={
            "task_id": "t-500-persist",
            "incident": "HTTP 500 errors still occurring after restart.",
        },
    ).json()
    assert data["status"] == "ESCALATED"
    assert data["evidence"]["before"]["http_status"] == 500
    assert data["evidence"]["after"]["http_status"] == 500


def test_reported_status_reaches_incident_context():
    ctx = build_context(
        "HTTP 500 errors", health_status="unhealthy", http_status=500,
        reported_http_status=500,
    )
    assert "User-reported HTTP status: 500" in build_prompt(ctx)
