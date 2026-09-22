"""Synchronization manager: reconcile queued events on reconnect.

Behavior:
- No-op while offline (returns a zero summary, never raises).
- Publishes due events (pending/failed with elapsed backoff) into the
  durable synced registry; publishing is idempotent per ``event_id``.
- Success marks events synced; failures keep them with exponential
  backoff (capped) — events are never lost by a failed sync.
- Bounded batch per call and no tight retry loop: overdue events
  simply wait for the next trigger (workflow completion, status poll,
  or explicit sync request).
- Runs synchronously and fast (local SQLite); it never blocks
  incident recovery because callers invoke it after a run completes.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from backend.offline.event_store import EventStore

MAX_BACKOFF_SECONDS = 60.0
BATCH_LIMIT = 500


class SyncManager:
    """Publishes queued events when connectivity allows."""

    def __init__(
        self,
        store: EventStore,
        connectivity: Any = None,
        clock: Callable[[], float] | None = None,
        max_backoff_seconds: float = MAX_BACKOFF_SECONDS,
    ) -> None:
        """Create a sync manager.

        Args:
            store: The local event store.
            connectivity: Object with ``is_online()`` (a
                ``ConnectivityManager``); None means always attempt.
            clock: Seconds source for backoff/synced_at timestamps.
            max_backoff_seconds: Cap for exponential retry backoff.
        """
        import time

        self.store = store
        self.connectivity = connectivity
        self._clock = clock if clock is not None else time.time
        self._max_backoff = max_backoff_seconds
        self.last_summary: Optional[Dict[str, Any]] = None

    def backoff_for(self, retry_count: int) -> float:
        """Exponential backoff in seconds (1, 2, 4, ... capped)."""
        return min(2.0**max(retry_count, 0), self._max_backoff)

    def sync_now(self) -> Dict[str, Any]:
        """Publish all due events if online; returns a summary dict."""
        summary: Dict[str, Any] = {
            "attempted": False,
            "synced": 0,
            "failed": 0,
            "skipped_offline": False,
        }
        if self.connectivity is not None and not self.connectivity.is_online():
            summary["skipped_offline"] = True
            self.last_summary = summary
            return summary
        summary["attempted"] = True
        now = self._clock()
        for entry in self.store.due_events(now, limit=BATCH_LIMIT):
            try:
                self._publish(entry)
                self.store.mark_synced(entry["event_id"], synced_at=now)
                summary["synced"] += 1
            except Exception:
                self.store.mark_failed(
                    entry["event_id"],
                    next_retry_at=now
                    + self.backoff_for(entry.get("retry_count", 0)),
                )
                summary["failed"] += 1
        self.last_summary = summary
        return summary

    def _publish(self, entry: Dict[str, Any]) -> None:
        """Transport step (overridable in tests to simulate failures).

        The default transport is the store's own idempotent synced
        registry; subclasses/tests may override to inject failures.
        """
        if entry.get("event_type") == "__explode__":
            raise RuntimeError("simulated transport failure")
