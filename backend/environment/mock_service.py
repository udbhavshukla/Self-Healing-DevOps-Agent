"""Mock DevOps service for Member 2.

Deterministic in-memory simulation. Starts healthy by default.
Supports failure injection and restart/recovery, plus a
deterministic failed-recovery mode for testing.

This module has no external dependencies and never touches
real infrastructure (no AWS/GCP/K8s/Docker/shell).
"""

import logging

logger = logging.getLogger(__name__)


def _validate_http_status(value: int) -> int:
    """Validate a simulated HTTP status code.

    Raises:
        ValueError: If not an int in 100-599 (bools rejected).
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"Invalid HTTP status: {value!r} (must be an int 100-599)"
        )
    if not 100 <= value <= 599:
        raise ValueError(
            f"Invalid HTTP status: {value!r} (must be an int 100-599)"
        )
    return value


class MockService:
    """In-memory mock application/service."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"

    def __init__(self, version: str = "1.0.0", fail_http_status: int = 503) -> None:
        """Create a healthy service.

        Args:
            version: Simple version string for the mock app.
            fail_http_status: HTTP status reported by health checks
                while the service is unhealthy (default 503). Lets a
                simulated incident carry its own status code (e.g. 500)
                instead of always collapsing to 503.
        """
        self._status: str = self.HEALTHY
        self._version: str = version
        self.fail_http_status: int = _validate_http_status(fail_http_status)
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
            Dict with health_status, version, fail_http_status,
            and fail_recovery_mode.
        """
        return {
            "health_status": self._status,
            "version": self._version,
            "fail_http_status": self.fail_http_status,
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
            version: Optional new version string. Only a non-empty
                string is accepted; None keeps the current version.

        Returns:
            The active version after deploy.

        Raises:
            ValueError: If version is neither None nor a non-empty
                string. The service state is left unchanged.
        """
        if version is None:
            pass
        elif isinstance(version, str) and version:
            self._version = version
        else:
            raise ValueError(
                f"Invalid version: {version!r} (must be a non-empty string)"
            )
        self._status = self.HEALTHY
        logger.info("Deployed version %s", self._version)
        return self._version

    def set_fail_recovery_mode(self, enabled: bool) -> None:
        """Enable/disable deterministic failed-recovery simulation.

        Args:
            enabled: True to make the next restart() fail.
        """
        self.fail_recovery_mode = bool(enabled)
