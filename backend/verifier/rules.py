"""Level 1 verification rules (pure, side-effect free).

LEVEL 1 RULE: verification passes if and only if the service evidence
shows HTTP status 200 AND health_status "healthy". The executor's own
success flag is deliberately NOT part of this rule: a tool can execute
fine while the application is still down (Member 2 documents exactly
this case), so only service evidence decides.

Malformed evidence (missing/invalid fields) always fails; the
normalization layer in ``evidence.py`` reports the details.
"""

from __future__ import annotations

LEVEL_1_RULE = "http_200_and_healthy"

REQUIRED_HTTP_STATUS = 200
REQUIRED_HEALTH_STATUS = "healthy"


def evaluate_level1(
    http_status: int | None, health_status: str | None
) -> tuple[bool, str]:
    """Apply the Level 1 rule to normalized evidence values.

    Args:
        http_status: Normalized HTTP status code (None when
            missing/invalid).
        health_status: Normalized health string (None when
            missing/invalid).

    Returns:
        (passed, reason) with a human-readable reason in both cases.
    """
    if http_status is None or health_status is None:
        missing = []
        if http_status is None:
            missing.append("http_status")
        if health_status is None:
            missing.append("health_status")
        return False, (
            "verification failed: incomplete evidence "
            f"(missing or invalid: {', '.join(missing)})"
        )
    http_ok = http_status == REQUIRED_HTTP_STATUS
    health_ok = health_status == REQUIRED_HEALTH_STATUS
    if http_ok and health_ok:
        return True, (
            "verification passed: service healthy "
            "(HTTP 200 and health_status 'healthy')"
        )
    if not http_ok and not health_ok:
        return False, (
            "verification failed: HTTP status "
            f"{http_status} (expected 200) and health_status "
            f"{health_status!r} (expected 'healthy')"
        )
    if not http_ok:
        return False, (
            f"verification failed: HTTP status {http_status} (expected 200)"
        )
    return False, (
        f"verification failed: health_status {health_status!r} "
        "(expected 'healthy')"
    )
