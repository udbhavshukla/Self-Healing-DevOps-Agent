"""Health checker for Member 2 mock environment.

Works with MockService. Deterministic mapping only:

- healthy   -> {"http_status": 200, "health_status": "healthy"}
- unhealthy -> {"http_status": 503, "health_status": "unhealthy"}

No verification, retry, or escalation logic lives here.
Tool execution success vs. application health is decided by
the caller (executor): this module only reports app health.
"""

import logging

from .mock_service import MockService

logger = logging.getLogger(__name__)


def check_health(service: MockService) -> dict:
    """Check the health of a MockService instance.

    Args:
        service: The mock service to check.

    Returns:
        Dict with http_status and health_status keys.
    """
    status = service.get_status()
    if status == MockService.HEALTHY:
        result = {"http_status": 200, "health_status": "healthy"}
    else:
        result = {"http_status": 503, "health_status": "unhealthy"}
    logger.info("Health check: %s", result["health_status"])
    return result


class HealthChecker:
    """Thin wrapper binding a checker to one service instance."""

    def __init__(self, service: MockService) -> None:
        """Bind this checker to a service.

        Args:
            service: The mock service to check.
        """
        self._service = service

    def check(self) -> dict:
        """Run a health check against the bound service.

        Returns:
            Dict with http_status and health_status keys.
        """
        return check_health(self._service)
