"""Tests for RecoveryPolicy."""

from backend.workflow.models import ExecutionResult, VerificationResult
from backend.workflow.recovery_policy import FOLLOWUP_ACTION, RECOVERY_ACTION, RecoveryPolicy


def _exec(action="health_check"):
    return ExecutionResult(
        task_id="t-1",
        step_id="t-1-step-1",
        action=action,
        attempt=1,
        success=False,
        result={"service_name": "api"},
    )


def _verif(passed=False):
    return VerificationResult(
        task_id="t-1",
        step_id="t-1-step-1",
        passed=passed,
        reason=None if passed else "service unhealthy",
        evidence={},
    )


def test_no_recovery_when_verification_passed():
    policy = RecoveryPolicy(max_attempts=3)
    assert policy.allow_recovery(_verif(passed=True), 0) is False
    assert policy.get_recovery_action(_verif(passed=True), _exec(), 0) is None


def test_failed_health_check_allows_restart():
    policy = RecoveryPolicy(max_attempts=3)
    assert policy.allow_recovery(_verif(passed=False), 0) is True
    assert (
        policy.get_recovery_action(_verif(passed=False), _exec("health_check"), 0)
        == RECOVERY_ACTION
    )


def test_retry_limit_blocks_recovery_and_escalates():
    policy = RecoveryPolicy(max_attempts=2)
    assert policy.allow_recovery(_verif(passed=False), 2) is False
    assert policy.get_recovery_action(_verif(passed=False), _exec(), 2) is None
    assert policy.should_escalate(_verif(passed=False), 2) is True
    assert policy.should_escalate(_verif(passed=False), 1) is False


def test_non_health_check_action_not_recoverable():
    policy = RecoveryPolicy(max_attempts=3)
    assert (
        policy.get_recovery_action(_verif(passed=False), _exec("restart_service"), 0)
        is None
    )


def test_recovery_steps_are_controlled_actions():
    policy = RecoveryPolicy(max_attempts=3)
    recovery = policy.build_recovery_step("t-1", _exec(), 0)
    followup = policy.build_followup_health_check("t-1", _exec(), 0)
    assert recovery.action == RECOVERY_ACTION == "restart_service"
    assert followup.action == FOLLOWUP_ACTION == "health_check"
