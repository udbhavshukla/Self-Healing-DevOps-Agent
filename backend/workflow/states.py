"""Workflow state machine with explicit transition validation."""

from __future__ import annotations

from enum import Enum


class WorkflowState(str, Enum):
    """Lifecycle states of a workflow run."""

    PLANNED = "PLANNED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RECOVERING = "RECOVERING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


# Explicit allow-list of transitions.
_ALLOWED_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.PLANNED: {WorkflowState.EXECUTING},
    WorkflowState.EXECUTING: {WorkflowState.VERIFYING},
    WorkflowState.VERIFYING: {
        WorkflowState.VERIFIED,
        WorkflowState.RECOVERING,
        WorkflowState.FAILED,
    },
    WorkflowState.RECOVERING: {
        WorkflowState.EXECUTING,
        WorkflowState.ESCALATED,
        WorkflowState.FAILED,
    },
    # Terminal states have no outgoing transitions.
    WorkflowState.VERIFIED: set(),
    WorkflowState.FAILED: set(),
    WorkflowState.ESCALATED: set(),
}

TERMINAL_STATES = frozenset(
    {WorkflowState.VERIFIED, WorkflowState.FAILED, WorkflowState.ESCALATED}
)


def can_transition(from_state: WorkflowState, to_state: WorkflowState) -> bool:
    """Return True if ``from_state -> to_state`` is allowed."""
    return to_state in _ALLOWED_TRANSITIONS.get(from_state, set())


def validate_transition(from_state: WorkflowState, to_state: WorkflowState) -> None:
    """Raise ``ValueError`` if the transition is not allowed.

    Terminal states (VERIFIED / FAILED / ESCALATED) can never restart.
    """
    if from_state in TERMINAL_STATES:
        raise ValueError(f"Terminal state {from_state.value} cannot transition to {to_state.value}")
    if not can_transition(from_state, to_state):
        raise ValueError(
            f"Invalid transition: {from_state.value} -> {to_state.value}"
        )
