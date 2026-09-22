"""Offline resilience layer (internet outage survival).

Gemini enhances the system but the critical recovery path never
depends on it. When connectivity drops, the deterministic offline
policy takes over, events persist in SQLite, and synchronization
reconciles them automatically on reconnect.
"""

from backend.offline.connectivity import ConnectivityManager, get_manager
from backend.offline.event_store import EventStore
from backend.offline.offline_policy import OfflinePolicy
from backend.offline.sync_manager import SyncManager

__all__ = [
    "ConnectivityManager",
    "EventStore",
    "OfflinePolicy",
    "SyncManager",
    "get_manager",
]
