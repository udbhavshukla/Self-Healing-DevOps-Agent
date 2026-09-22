"""Connectivity manager: online/offline state without blocking work.

Design:
- State is a cached flag, so the critical workflow only ever reads it
  (never waits on the network).
- ``refresh()`` actively probes at most once per cooldown window, so
  there are no excessive network requests.
- Outcomes observed elsewhere (Gemini success/failure, manual demo
  override) update the state without any probing at all.
- Probe and clock are injectable, making every transition unit
  testable with a deterministic simulated clock.

State transitions are reported back to callers (``changed`` flag) so
the API can record ``connectivity_changed`` events.
"""

from __future__ import annotations

import os
import socket
import time
from typing import Callable, Optional

PROBE_HOST = os.environ.get("CONNECTIVITY_PROBE_HOST", "8.8.8.8")
PROBE_PORT = int(os.environ.get("CONNECTIVITY_PROBE_PORT", "53"))
PROBE_TIMEOUT_SECONDS = 2.0
PROBE_COOLDOWN_SECONDS = 15.0


def default_probe() -> bool:
    """Fast TCP check (no HTTP, no DNS, no credentials involved)."""
    try:
        with socket.create_connection(
            (PROBE_HOST, PROBE_PORT), timeout=PROBE_TIMEOUT_SECONDS
        ):
            return True
    except Exception:
        return False


class ConnectivityManager:
    """Tracks whether external (Gemini/internet) dependencies are reachable."""

    def __init__(
        self,
        probe: Callable[[], bool] | None = None,
        clock: Callable[[], float] | None = None,
        cooldown_seconds: float = PROBE_COOLDOWN_SECONDS,
        initial_online: bool = True,
    ) -> None:
        """Create a manager.

        Args:
            probe: Zero-arg reachability check (defaults to a fast TCP
                probe). Tests inject fakes here — no real network needed.
            clock: Zero-arg seconds source (defaults to ``time.time``).
                Tests inject a manual clock to simulate long outages.
            cooldown_seconds: Minimum interval between active probes.
            initial_online: Assumed state until first evidence arrives.
        """
        self._probe = probe if probe is not None else default_probe
        self._clock = clock if clock is not None else time.time
        self._cooldown = cooldown_seconds
        self._online = initial_online
        self._override: Optional[bool] = None
        self._last_probe_at: Optional[float] = None
        self._last_change_at: float = self._clock()

    # -- state ---------------------------------------------------------

    def is_online(self) -> bool:
        """Current state (manual override wins over observed state)."""
        if self._override is not None:
            return self._override
        return self._online

    def state(self) -> str:
        """``"online"`` or ``"offline"`` for API/frontend display."""
        return "online" if self.is_online() else "offline"

    @property
    def last_change_at(self) -> float:
        """Timestamp (clock seconds) of the last state change."""
        return self._last_change_at

    # -- updates -------------------------------------------------------

    def _apply(self, online: bool) -> bool:
        if online != self.is_online():
            self._online = online
            self._last_change_at = self._clock()
            return True
        self._online = online
        return False

    def refresh(self) -> bool:
        """Actively probe (at most once per cooldown). Returns state changed."""
        now = self._clock()
        if (
            self._last_probe_at is not None
            and now - self._last_probe_at < self._cooldown
        ):
            return False
        self._last_probe_at = now
        try:
            reachable = bool(self._probe())
        except Exception:
            reachable = False
        return self._apply(reachable)

    def report_success(self) -> bool:
        """Record an observed external success (e.g. Gemini answered)."""
        return self._apply(True)

    def report_failure(self) -> bool:
        """Record an observed external failure (e.g. Gemini errored)."""
        return self._apply(False)

    def set_override(self, online: Optional[bool]) -> bool:
        """Force a state for demos/tests (None clears). Returns changed."""
        before = self.is_online()
        self._override = online
        after = self.is_online()
        if before != after:
            self._last_change_at = self._clock()
            return True
        return False


_manager: Optional[ConnectivityManager] = None


def get_manager() -> ConnectivityManager:
    """Process-wide singleton used by the API layer."""
    global _manager
    if _manager is None:
        _manager = ConnectivityManager()
    return _manager


def reset_manager() -> None:
    """Drop the singleton (used by tests)."""
    global _manager
    _manager = None
