"""Dependency-injection interfaces for executor and verifier.

Member 2 (executor) and Member 3 (verifier) implement these protocols.
The orchestrator only depends on the protocols, never on concrete
implementations, so fakes can be injected in tests.
"""

from __future__ import annotations

from typing import Protocol

from backend.workflow.models import ActionRequest, ExecutionResult, VerificationResult


class Executor(Protocol):
    """Executes an approved action (implemented by Member 2)."""

    def execute(self, action: ActionRequest) -> ExecutionResult:
        """Execute ``action`` and return an :class:`ExecutionResult`.

        Args:
            action: The approved action to execute.

        Returns:
            The execution outcome. Implementations must not raise for
            expected action failures; they must return
            ``ExecutionResult(success=False, ...)`` instead.
        """
        ...  # pragma: no cover


class Verifier(Protocol):
    """Verifies an execution result (implemented by Member 3)."""

    def verify(self, result: ExecutionResult) -> VerificationResult:
        """Verify ``result`` and return a :class:`VerificationResult`.

        Args:
            result: The execution result to verify against evidence rules.

        Returns:
            The verification outcome (passed / failed with reason).
        """
        ...  # pragma: no cover
