"""Controlled executor for Member 2 mock DevOps environment.

Public interface: Executor.execute(action_request) -> execution_result.

Only explicitly allowlisted actions may run. No shell execution,
no retry/escalation/verification logic. Reuses MockService,
health_checker, and recovery modules without duplicating logic.

Contract note: success=True means the TOOL executed successfully,
not that the application is healthy. E.g. a health check on an
unhealthy service returns success=True with
result={"http_status": 503, "health_status": "unhealthy"}.
"""

import logging

from .health_checker import check_health
from .mock_service import MockService
from .recovery import restart_service

logger = logging.getLogger(__name__)


class Executor:
    """Execute controlled action requests against a MockService."""

    ALLOWED_ACTIONS = frozenset(
        {"health_check", "restart", "inject_failure", "deploy"}
    )

    def __init__(self, service: MockService | None = None) -> None:
        """Create an executor bound to a service.

        Args:
            service: Existing MockService to use. A new healthy one
                is created when None.
        """
        self._service = service if service is not None else MockService()

    @property
    def service(self) -> MockService:
        """The bound mock service (for tests/inspection)."""
        return self._service

    def execute(self, action_request: dict) -> dict:
        """Execute one controlled action request.

        Args:
            action_request: Dict with task_id, step_id, action,
                and optional parameters/attempt keys.

        Returns:
            Dict following the execution_result contract with
            task_id, step_id, action, attempt, success, result, error.
        """
        task_id, step_id, action, parameters, attempt = self._parse_request(
            action_request
        )

        if action is None:
            logger.error("Invalid action request: %r", action_request)
            return self._error_result(
                task_id, step_id, "unknown", attempt,
                "Invalid action request: 'action' is required",
            )

        logger.info("Executing action: %s", action)

        if action not in self.ALLOWED_ACTIONS:
            logger.error("Unknown action requested: %s", action)
            return self._error_result(
                task_id, step_id, action, attempt,
                f"Unsupported action: {action}",
            )

        try:
            if action == "health_check":
                result = check_health(self._service)
            elif action == "restart":
                # Tool success even if recovered=False; the
                # recovery dict itself carries recovered/health_status.
                result = restart_service(self._service)
            elif action == "inject_failure":
                self._service.inject_failure()
                result = {
                    "action": "inject_failure",
                    "injected": True,
                    "health_status": self._service.get_status(),
                }
            elif action == "deploy":  # controlled simulated deploy
                version = parameters.get("version")
                new_version = self._service.deploy(version)
                result = {
                    "action": "deploy",
                    "version": new_version,
                    "health_status": self._service.get_status(),
                }
            else:  # pragma: no cover - guarded by allowlist above
                return self._error_result(
                    task_id, step_id, action, attempt,
                    f"Unsupported action: {action}",
                )
        except Exception as exc:  # never crash on a controlled action
            logger.error("Action %s failed: %s", action, exc)
            return self._error_result(
                task_id, step_id, action, attempt, f"Action failed: {exc}"
            )

        return {
            "task_id": task_id,
            "step_id": step_id,
            "action": action,
            "attempt": attempt,
            "success": True,
            "result": result,
            "error": None,
        }

    @staticmethod
    def _parse_request(request: object) -> tuple:
        """Safely extract (task_id, step_id, action, parameters, attempt).

        Malformed input yields 'unknown' ids and empty parameters
        instead of raising.
        """
        if not isinstance(request, dict):
            return ("unknown", "unknown", None, {}, 1)
        task_id = request.get("task_id", "unknown")
        step_id = request.get("step_id", "unknown")
        action = request.get("action")
        parameters = request.get("parameters", {})
        if not isinstance(parameters, dict):
            parameters = {}
        attempt = request.get("attempt", 1)
        if not isinstance(attempt, int):
            attempt = 1
        return (task_id, step_id, action, parameters, attempt)

    @staticmethod
    def _error_result(
        task_id: str, step_id: str, action: str, attempt: int, message: str
    ) -> dict:
        """Build a structured failure execution result."""
        return {
            "task_id": task_id,
            "step_id": step_id,
            "action": action,
            "attempt": attempt,
            "success": False,
            "result": None,
            "error": message,
        }
