"""Data models for the Workflow Orchestrator.

These models are the shared contract between Member 1 (orchestrator),
Member 2 (executor), Member 3 (verifier) and Member 4 (frontend).

They are intentionally independent of any executor / verifier
implementation so fakes can be injected for testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.workflow.states import WorkflowState


@dataclass
class TaskRequest:
    """Structured task accepted by the orchestrator."""

    task_id: str
    description: str
    task_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowStep:
    """A single planned step (controlled action only)."""

    step_id: str
    action: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    order: int = 0
    max_attempts: int = 3


@dataclass
class ActionRequest:
    """Request handed to the executor interface."""

    task_id: str
    step_id: str
    action: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    attempt: int = 1


@dataclass
class ExecutionResult:
    """Result returned by the executor interface."""

    task_id: str
    step_id: str
    action: str
    attempt: int
    success: bool
    result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class VerificationResult:
    """Result returned by the verifier interface."""

    task_id: str
    step_id: str
    passed: bool
    reason: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowStatus:
    """Structured status consumed by the frontend (Member 4)."""

    task_id: str
    status: WorkflowState = WorkflowState.PLANNED
    current_step: Optional[str] = None
    attempt: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    final_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
