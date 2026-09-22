"""Persistent local event store (SQLite).

Survives process restarts: events generated offline live in a local
SQLite file (configurable via ``OFFLINE_DB_PATH``, default
``data/offline_events.db``), never in a bare in-memory list.

Schema:
- ``events``: every recorded workflow/connectivity/sync event with a
  stable ``event_id`` primary key, ``sync_status`` (pending/synced/
  failed), ``retry_count`` and ``next_retry_at`` for backoff.
- ``synced_events``: the durable "server-side" history. Publishing is
  ``INSERT OR IGNORE`` keyed by ``event_id``, which makes
  synchronization idempotent by construction.

Secret hygiene: payloads are scrubbed before storage — values matching
the configured Gemini key (or keys named like *api_key*/*token*/
*secret*) are redacted, so credentials can never land in SQLite.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional
from uuid import uuid4

DEFAULT_DB_PATH = os.environ.get("OFFLINE_DB_PATH", "data/offline_events.db")

PENDING = "pending"
SYNCED = "synced"
FAILED = "failed"

_SENSITIVE_KEYS = ("api_key", "apikey", "token", "secret", "credential", "password")


def _scrub(value: Any, secrets: tuple = ()) -> Any:
    if isinstance(value, dict):
        scrubbed = {}
        for key, val in value.items():
            if any(s in str(key).lower() for s in _SENSITIVE_KEYS):
                scrubbed[key] = "***REDACTED***"
            elif isinstance(val, str) and val and val in secrets:
                scrubbed[key] = "***REDACTED***"
            else:
                scrubbed[key] = _scrub(val, secrets)
        return scrubbed
    if isinstance(value, list):
        return [_scrub(item, secrets) for item in value]
    if isinstance(value, str) and value and value in secrets:
        return "***REDACTED***"
    return value


class EventStore:
    """SQLite-backed durable event log with a synced-events registry."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Open (creating parent dirs) the store at ``db_path``."""
        self.db_path = db_path or DEFAULT_DB_PATH
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._lock = threading.Lock()
        self._known_secrets: tuple = tuple(
            s for s in (os.environ.get("GEMINI_API_KEY", ""),) if s
        )
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    task_id TEXT,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    sync_status TEXT NOT NULL DEFAULT 'pending',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    next_retry_at REAL NOT NULL DEFAULT 0
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS synced_events (
                    event_id TEXT PRIMARY KEY,
                    task_id TEXT,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    synced_at REAL NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    # -- recording -----------------------------------------------------

    def record(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        timestamp: Optional[str] = None,
        event_id: Optional[str] = None,
        sync_status: str = PENDING,
    ) -> Dict[str, Any]:
        """Persist one event (payload scrubbed of secrets)."""
        from datetime import datetime, timezone

        entry = {
            "event_id": event_id or f"evt-{uuid4().hex[:12]}",
            "task_id": task_id,
            "event_type": event_type,
            "timestamp": timestamp
            or datetime.now(timezone.utc).isoformat(),
            "payload": json.dumps(
                _scrub(payload or {}, self._known_secrets)
            ),
            "sync_status": sync_status,
            "retry_count": 0,
            "next_retry_at": 0.0,
        }
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO events
                   (event_id, task_id, event_type, timestamp, payload,
                    sync_status, retry_count, next_retry_at)
                   VALUES (:event_id, :task_id, :event_type, :timestamp,
                           :payload, :sync_status, :retry_count,
                           :next_retry_at)""",
                entry,
            )
        return {**entry, "payload": json.loads(entry["payload"])}

    def get(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Fetch one event by id (payload decoded), or None."""
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM events WHERE event_id = ?", (event_id,)
            ).fetchone()
        if row is None:
            return None
        entry = dict(row)
        entry["payload"] = json.loads(entry["payload"])
        return entry

    def due_events(self, now: float, limit: int = 200) -> List[Dict[str, Any]]:
        """Pending/failed events whose backoff has elapsed (oldest first)."""
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM events
                   WHERE sync_status IN ('pending', 'failed')
                     AND next_retry_at <= ?
                   ORDER BY timestamp ASC LIMIT ?""",
                (now, limit),
            ).fetchall()
        out = []
        for row in rows:
            entry = dict(row)
            entry["payload"] = json.loads(entry["payload"])
            out.append(entry)
        return out

    def count_by_status(self) -> Dict[str, int]:
        """``{pending: n, synced: n, failed: n}`` (zero-filled)."""
        counts = {PENDING: 0, SYNCED: 0, FAILED: 0}
        with self._lock, self._connect() as connection:
            for row in connection.execute(
                "SELECT sync_status, COUNT(*) AS n FROM events GROUP BY sync_status"
            ):
                if row["sync_status"] in counts:
                    counts[row["sync_status"]] = row["n"]
        return counts

    # -- sync transitions ----------------------------------------------

    def mark_synced(self, event_id: str, synced_at: float) -> None:
        """Publish to the synced registry (idempotent) and mark synced."""
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM events WHERE event_id = ?", (event_id,)
            ).fetchone()
            if row is None:
                return
            connection.execute(
                """INSERT OR IGNORE INTO synced_events
                   (event_id, task_id, event_type, timestamp, payload, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    row["event_id"],
                    row["task_id"],
                    row["event_type"],
                    row["timestamp"],
                    row["payload"],
                    synced_at,
                ),
            )
            connection.execute(
                "UPDATE events SET sync_status = 'synced' WHERE event_id = ?",
                (event_id,),
            )

    def mark_failed(self, event_id: str, next_retry_at: float) -> None:
        """Keep the event for retry with backoff (never dropped)."""
        with self._lock, self._connect() as connection:
            connection.execute(
                """UPDATE events SET sync_status = 'failed',
                   retry_count = retry_count + 1,
                   next_retry_at = ? WHERE event_id = ?""",
                (next_retry_at, event_id),
            )

    def synced_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a published event by id (idempotency proof), or None."""
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM synced_events WHERE event_id = ?", (event_id,)
            ).fetchone()
        if row is None:
            return None
        entry = dict(row)
        entry["payload"] = json.loads(entry["payload"])
        return entry

    def synced_count(self) -> int:
        """Number of events in the synced registry."""
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM synced_events"
            ).fetchone()
        return row["n"]
