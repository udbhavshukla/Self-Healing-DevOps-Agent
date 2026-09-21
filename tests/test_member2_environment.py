"""Member 2 pytest suite: mock DevOps environment & recovery.

Deterministic. Each test uses fresh MockService/Executor instances.
Covers: healthy start, failure injection, health checks (200/503),
restart recovery, deterministic failed recovery, executor allowlist,
invalid/malformed rejection, and execution_result contract shape.
"""

from backend.environment.executor import Executor
from backend.environment.health_checker import check_health
from backend.environment.mock_service import MockService
from backend.environment.recovery import restart_service


def make_request(action, task_id="task-001", step_id="step-001", parameters=None):
    """Build a minimal action_request dict."""
    return {
        "task_id": task_id,
        "step_id": step_id,
        "action": action,
        "parameters": parameters or {},
    }


# TEST 1: service starts healthy
def test_1_service_starts_healthy():
    service = MockService()
    assert service.get_status() == "healthy"


# TEST 2: failure injection makes service unhealthy
def test_2_inject_failure_makes_unhealthy():
    service = MockService()
    service.inject_failure()
    assert service.get_status() == "unhealthy"


# TEST 3: healthy health check returns HTTP 200
def test_3_healthy_check_returns_200():
    service = MockService()
    assert check_health(service) == {
        "http_status": 200,
        "health_status": "healthy",
    }


# TEST 4: unhealthy health check returns HTTP 503
def test_4_unhealthy_check_returns_503():
    service = MockService()
    service.inject_failure()
    assert check_health(service) == {
        "http_status": 503,
        "health_status": "unhealthy",
    }


# TEST 5: restart recovers an unhealthy service
def test_5_restart_recovers_service():
    service = MockService()
    service.inject_failure()
    result = restart_service(service)
    assert result["recovered"] is True
    assert result["health_status"] == "healthy"
    assert service.get_status() == "healthy"


# TEST 6: health check after restart returns HTTP 200
def test_6_health_check_after_restart_returns_200():
    service = MockService()
    service.inject_failure()
    restart_service(service)
    assert check_health(service) == {
        "http_status": 200,
        "health_status": "healthy",
    }


# TEST 7: fail_recovery_mode causes deterministic failed recovery
def test_7_failed_recovery_leaves_service_unhealthy():
    service = MockService()
    service.inject_failure()
    service.set_fail_recovery_mode(True)
    result = restart_service(service)
    assert result["recovered"] is False
    assert result["health_status"] == "unhealthy"
    assert service.get_status() == "unhealthy"
    # Disabling the flag lets a later restart recover (deterministic).
    service.set_fail_recovery_mode(False)
    result = restart_service(service)
    assert result["recovered"] is True
    assert service.get_status() == "healthy"


# TEST 8: executor accepts all supported controlled actions
def test_8_executor_accepts_supported_actions():
    for action in ("health_check", "restart", "inject_failure", "deploy"):
        executor = Executor(MockService())
        res = executor.execute(make_request(action))
        assert res["success"] is True, action
        assert res["action"] == action
        assert res["error"] is None


# TEST 9: executor rejects unsupported actions
def test_9_executor_rejects_invalid_action():
    executor = Executor(MockService())
    res = executor.execute(make_request("delete_database"))
    assert res["success"] is False
    assert res["result"] is None
    assert "Unsupported action" in res["error"]


# TEST 10: malformed/missing requests rejected safely (no crash)
def test_10_malformed_requests_rejected_safely():
    executor = Executor(MockService())
    for bad in ({}, {"task_id": "t"}, {"task_id": "t", "step_id": "s"}, "not-a-dict", None):
        res = executor.execute(bad)
        assert res["success"] is False
        assert res["result"] is None
        assert res["error"] is not None


# TEST 11: execution result follows the agreed structure
def test_11_execution_result_structure():
    executor = Executor(MockService())
    res = executor.execute(make_request("health_check"))
    assert set(res.keys()) == {
        "task_id",
        "step_id",
        "action",
        "attempt",
        "success",
        "result",
        "error",
    }
    assert res["task_id"] == "task-001"
    assert res["step_id"] == "step-001"
    assert res["action"] == "health_check"
    assert res["attempt"] == 1


# TEST 12: tool success is separate from application health
def test_12_unhealthy_check_still_tool_success():
    executor = Executor(MockService())
    executor.execute(make_request("inject_failure"))
    res = executor.execute(make_request("health_check"))
    assert res["success"] is True
    assert res["result"]["health_status"] == "unhealthy"
    assert res["result"]["http_status"] == 503


# TEST 13 (G1): deploy payload carries the new version and heals
def test_13_deploy_payload_and_version():
    executor = Executor(MockService())
    res = executor.execute(make_request("deploy", parameters={"version": "2.0.0"}))
    assert res["success"] is True
    assert res["action"] == "deploy"
    assert res["result"]["version"] == "2.0.0"
    assert res["result"]["health_status"] == "healthy"
    assert executor.service.version == "2.0.0"


# TEST 14 (G2): executor-level failed recovery (Member 1 retry path)
def test_14_executor_failed_recovery():
    executor = Executor(MockService())
    executor.execute(make_request("inject_failure"))
    executor.service.set_fail_recovery_mode(True)
    res = executor.execute(
        {"task_id": "task-001", "step_id": "step-002",
         "action": "restart", "parameters": {}}
    )
    assert res["success"] is True
    assert res["result"]["recovered"] is False
    assert res["result"]["health_status"] == "unhealthy"
    assert executor.service.get_status() == "unhealthy"


# TEST 15 (G3): attempt passthrough, default stays 1
def test_15_attempt_passthrough():
    executor = Executor(MockService())
    res = executor.execute(
        {"task_id": "task-001", "step_id": "step-003",
         "action": "health_check", "attempt": 3, "parameters": {}}
    )
    assert res["success"] is True
    assert res["attempt"] == 3
    # Missing/invalid attempt still defaults to 1.
    assert executor.execute(make_request("health_check"))["attempt"] == 1
    res_bad = executor.execute(
        {"task_id": "t", "step_id": "s", "action": "health_check",
         "attempt": "three", "parameters": {}}
    )
    assert res_bad["attempt"] == 1


# TEST 16 (I1): invalid deploy version is rejected without state change
def test_16_invalid_deploy_version_rejected():
    executor = Executor(MockService())
    executor.execute(make_request("inject_failure"))
    for bad_version in (123, [], {}, True, ""):
        res = executor.execute(
            make_request("deploy", parameters={"version": bad_version})
        )
        assert res["success"] is False, bad_version
        assert res["result"] is None
        assert "Invalid version" in res["error"]
    # State uncorrupted: version kept, service untouched by failed deploys.
    assert executor.service.version == "1.0.0"
    assert executor.service.get_status() == "unhealthy"
