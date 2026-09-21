"""Controlled recovery operations for Member 2.

Primary action: restart (delegates to MockService.restart()).

Respects MockService.fail_recovery_mode for deterministic
failed-recovery simulation. No retry, escalation, or
verification logic lives here.
"""

import logging

from .mock_service import MockService

logger = logging.getLogger(__name__)


def restart_service(service: MockService) -> dict:
    """Attempt a controlled restart of the service.

    Args:
        service: The mock service to recover.

    Returns:
        Dict with action, recovered flag, and resulting health_status.
        Example success: {"action": "restart", "recovered": True,
                          "health_status": "healthy"}
        Example failure: {"action": "restart", "recovered": False,
                          "health_status": "unhealthy"}
    """
    logger.info("Executing recovery: restart")
    recovered = service.restart()
    result = {
        "action": "restart",
        "recovered": recovered,
        "health_status": service.get_status(),
    }
    if recovered:
        logger.info("Service recovered")
    else:
        logger.warning("Service recovery failed")
    return result


class Recovery:
    """Thin wrapper binding recovery ops to one service instance."""

    def __init__(self, service: MockService) -> None:
        """Bind this recovery helper to a service.

        Args:
            service: The mock service to recover.
        """
        self._service = service

    def restart(self) -> dict:
        """Perform a controlled restart.

        Returns:
            Dict with action, recovered flag, and health_status.
        """
        return restart_service(self._service)
