"""In-memory workflow store (Level 1: no database)."""

from __future__ import annotations

from typing import Any, Dict, Optional

_store: Dict[str, Dict[str, Any]] = {}


def save_workflow(task_id: str, payload: Dict[str, Any]) -> None:
    """Store a serialized ``WorkflowStatus`` payload by task id."""
    _store[task_id] = payload


def get_workflow(task_id: str) -> Optional[Dict[str, Any]]:
    """Return the stored payload for ``task_id``, or None if unknown."""
    return _store.get(task_id)


def clear_workflows() -> None:
    """Remove all stored payloads (used by tests)."""
    _store.clear()
