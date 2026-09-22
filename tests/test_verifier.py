"""Member 3 pytest suite: Level 1 verifier.

Rule under test: pass iff HTTP status == 200 AND
health_status == "healthy", judged on service evidence only.

Covers the rule matrix, malformed evidence, schema consistency,
mocked-orchestrator consumption, and compatibility with Member 1
(dataclass) and Member 2 (dict + live Executor/MockService) formats.
Existing suites must keep passing (run the whole suite, not just this).
"""

import json

import pytest

from backend.environment.executor import Executor as Member2Executor
from backend.environment.mock_service import MockService
from backend.verifier import (
    LEVEL_1_RULE,
    Verifier,
    evaluate_level1,
    normalize_evidence,
)
from backend.workflow.models import ExecutionResult, VerificationResult


def make_execution(
    http_status=200,
    health_status="healthy",
    success=True,
    task_id="task-001",
    step_id="step-001",
    action="health_check",
):
    """Build a Member 1 ExecutionResult with controlled evidence."""
    return ExecutionResult(
        task_id=task_id,
        step_id=step_id,
        action=action,
        attempt=1,
        success=success,
        result={"http_status": http_status, "health_status": health_status},
    )


def make_dict_execution(payload, success=True):
    """Build a Member 2 style plain-dict execution result."""
    return {
        "task_id": "task-001",
        "step_id": "step-001",
        "action": "health_check",
        "attempt": 1,
        "success": success,
        "result": payload,
        "error": None,
    }


# Rule matrix ---------------------------------------------------------------


def test_200_and_healthy_passes():
    result = Verifier().verify(make_execution(200, "healthy"))
    assert result.passed is True
    assert isinstance(result, VerificationResult)


def test_503_and_unhealthy_fails():
    result = Verifier().verify(make_execution(503, "unhealthy"))
    assert result.passed is False


def test_500_and_healthy_fails():
    result = Verifier().verify(make_execution(500, "healthy"))
    assert result.passed is False
    assert "500" in (result.reason or "")


def test_200_and_unhealthy_fails():
    result = Verifier().verify(make_execution(200, "unhealthy"))
    assert result.passed is False
    assert "unhealthy" in (result.reason or "")


# Executor success must not decide ------------------------------------------------


def test_executor_success_with_unhealthy_evidence_fails():
    """Headline case: restart ok, service still 503/unhealthy -> FAILED."""
    execution = make_execution(503, "unhealthy", success=True, action="restart")
    result = Verifier().verify(execution)
    assert result.passed is False


def test_executor_failure_with_healthy_evidence_passes_on_evidence():
    """Evidence decides: healthy evidence verifies even if the tool flagged failure."""
    execution = make_execution(200, "healthy", success=False)
    result = Verifier().verify(execution)
    assert result.passed is True
    assert result.evidence["execution_success"] is False


# Missing / invalid evidence -------------------------------------------------------


@pytest.mark.parametrize("payload", [None, "oops", 42, ["http_status", 200]])
def test_missing_or_malformed_payload_fails(payload):
    result = Verifier().verify(make_dict_execution(payload, success=False))
    assert result.passed is False
    assert result.reason


@pytest.mark.parametrize("http_status", ["ok", True, False, 99, 600, 4.5, "", None])
def test_invalid_http_status_fails(http_status):
    result = Verifier().verify(make_execution(http_status, "healthy"))
    assert result.passed is False
    assert "http_status" in (result.reason or "")


@pytest.mark.parametrize(
    "health_status", ["unknown", "", None, 123, True, "HEALTHY ", " sick "]
)
def test_invalid_or_unexpected_health_status_fails(health_status):
    # Note: "HEALTHY " normalizes to "healthy" and passes; the rest fail.
    result = Verifier().verify(make_execution(200, health_status))
    if isinstance(health_status, str) and health_status.strip().lower() == "healthy":
        assert result.passed is True
    else:
        assert result.passed is False


def test_garbage_input_never_raises():
    verifier = Verifier()
    for bad in (None, "junk", 42, ["x"], {"nope": True}, object()):
        result = verifier.verify(bad)
        assert result.passed is False
        assert result.reason


# Schema consistency -------------------------------------------------------------


def test_success_and_failure_share_result_schema():
    passed = Verifier().verify(make_execution(200, "healthy"))
    failed = Verifier().verify(make_execution(503, "unhealthy"))
    for result in (passed, failed):
        assert isinstance(result.task_id, str)
        assert isinstance(result.step_id, str)
        assert isinstance(result.passed, bool)
        assert isinstance(result.reason, str) and result.reason
        assert isinstance(result.evidence, dict)
        assert result.evidence["rule"] == LEVEL_1_RULE
        assert result.evidence["status"] in ("passed", "failed")
        # JSON-serializable for the orchestrator / API layer.
        json.dumps(
            {
                "task_id": result.task_id,
                "step_id": result.step_id,
                "passed": result.passed,
                "reason": result.reason,
                "evidence": result.evidence,
            }
        )
    assert passed.evidence["status"] == "passed"
    assert failed.evidence["status"] == "failed"


def test_identity_echoed_from_execution():
    result = Verifier().verify(
        make_execution(200, "healthy", task_id="t-9", step_id="s-9")
    )
    assert (result.task_id, result.step_id) == ("t-9", "s-9")


def test_failure_reasons_are_meaningful():
    cases = [
        (make_execution(503, "unhealthy"), ("503", "unhealthy")),
        (make_execution(500, "healthy"), ("500",)),
        (make_execution(200, "unhealthy"), ("unhealthy",)),
        (make_dict_execution(None, success=False), ()),
    ]
    for execution, keywords in cases:
        reason = Verifier().verify(execution).reason or ""
        assert reason.startswith("verification failed")
        for keyword in keywords:
            assert keyword in reason


# Rule unit tests ------------------------------------------------------------------


@pytest.mark.parametrize(
    "http_status,health_status,expected",
    [(200, "healthy", True), (503, "unhealthy", False), (500, "healthy", False),
     (200, "unhealthy", False), (None, "healthy", False), (200, None, False)],
)
def test_evaluate_level1_matrix(http_status, health_status, expected):
    passed, reason = evaluate_level1(http_status, health_status)
    assert passed is expected
    assert isinstance(reason, str) and reason


# Mocked-orchestrator consumption ----------------------------------------------------


def test_mocked_orchestrator_consumes_passed_flag():
    """Simulate Member 4: build from executor output, branch on .passed."""

    def orchestrator_decide(execution):
        verification = Verifier().verify(execution)
        assert isinstance(verification.passed, bool)
        return "VERIFIED" if verification.passed else "RECOVER"

    assert orchestrator_decide(make_execution(200, "healthy")) == "VERIFIED"
    assert orchestrator_decide(make_execution(503, "unhealthy")) == "RECOVER"


def test_full_detect_recover_verify_loop_with_member2():
    """End-to-end with real Member 2 pieces (no mocks for them)."""
    service = MockService()
    executor = Member2Executor(service)
    verifier = Verifier()

    def request(action):
        return {"task_id": "t-loop", "step_id": "s-loop", "action": action,
                "parameters": {}}

    service.inject_failure()
    assert verifier.verify(executor.execute(request("health_check"))).passed is False

    executor.execute(request("restart"))
    assert verifier.verify(executor.execute(request("health_check"))).passed is True

    service.inject_failure()
    service.set_fail_recovery_mode(True)
    executor.execute(request("restart"))
    assert verifier.verify(executor.execute(request("health_check"))).passed is False


# Format compatibility -----------------------------------------------------------------


def test_member1_dataclass_and_member2_dict_agree():
    payload = {"http_status": 200, "health_status": "healthy"}
    from_dataclass = Verifier().verify(make_execution(200, "healthy"))
    from_dict = Verifier().verify(make_dict_execution(payload))
    assert from_dataclass.passed == from_dict.passed is True
    assert from_dataclass.evidence["rule"] == from_dict.evidence["rule"]


def test_member2_restart_payload_without_http_status_fails():
    """Restart evidence carries health only: not verifiable without a fresh check."""
    execution = make_dict_execution(
        {"action": "restart", "recovered": True, "health_status": "healthy"}
    )
    result = Verifier().verify(execution)
    assert result.passed is False
    assert "http_status" in (result.reason or "")


def test_member2_error_shape_fails():
    execution = make_dict_execution(None, success=False)
    execution["error"] = "Unsupported action: delete_database"
    result = Verifier().verify(execution)
    assert result.passed is False


def test_normalize_tolerates_status_code_alias_and_digit_string():
    evidence = normalize_evidence(
        make_dict_execution({"status_code": "200", "health_status": "Healthy "})
    )
    assert evidence.valid
    assert (evidence.http_status, evidence.health_status) == (200, "healthy")
