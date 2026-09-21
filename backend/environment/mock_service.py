"""Mock DevOps service for Member 2.

Deterministic in-memory simulation. Starts healthy by default.
Supports failure injection and restart/recovery, plus a
deterministic failed-recovery mode for testing.

This module has no external dependencies and never touches
real infrastructure (no AWS/GCP/K8s/Docker/shell).
"""

import logging

logger = logging.getLogger(__name__)


class MockService:
    """In-memory mock application/service."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"

    def __init__(self, version: str = "1.0.0") -> None:
        """Create a healthy service.

        Args:
            version: Simple version string for the mock app.
        """
        self._status: str = self.HEALTHY
        self._version: str = version
        # When True, restart() deterministically does NOT recover
        # the service (used to simulate failed recovery in tests).
        self.fail_recovery_mode: bool = False

    @property
    def status(self) -> str:
        """Current status: 'healthy' or 'unhealthy'."""
        return self._status

    @property
    def version(self) -> str:
        """Current version string."""
        return self._version

    def get_status(self) -> str:
        """Return current service status.

        Returns:
            'healthy' or 'unhealthy'.
        """
        return self._status

    def get_info(self) -> dict:
        """Return a snapshot of service state.

        Returns:
            Dict with health_status, version, and fail_recovery_mode.
        """
        return {
            "health_status": self._status,
            "version": self._version,
            "fail_recovery_mode": self.fail_recovery_mode,
        }

    def inject_failure(self) -> None:
        """Make the service unhealthy (deterministic)."""
        self._status = self.UNHEALTHY
        logger.info("Failure injected")

    def restart(self) -> bool:
        """Attempt to recover the service via restart.

        If fail_recovery_mode is True, the service deterministically
        stays unhealthy and False is returned. Otherwise the service
        becomes healthy and True is returned.

        Returns:
            True if the service is healthy after restart, else False.
        """
        if self.fail_recovery_mode:
            logger.info("Restart attempted but recovery failed (fail_recovery_mode=True)")
            return False
        self._status = self.HEALTHY
        logger.info("Service recovered")
        return True

    def deploy(self, version: str | None = None) -> str:
        """Simulate a controlled deploy.

        A deploy sets the service healthy and optionally bumps
        the version string.

        Args:
            version: Optional new version string.

        Returns:
            The active version after deploy.
        """
        if version:
            self._version = version
        self._status = self.HEALTHY
        logger.info("Deployed version %s", self._version)
        return self._version

    def set_fail_recovery_mode(self, enabled: bool) -> None:
        """Enable/disable deterministic failed-recovery simulation.

        Args:
            enabled: True to make the next restart() fail.
        """
        self.fail_recovery_mode = bool(enabled)
