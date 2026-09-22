# Member 3 — Verifier Module

## 1. Purpose

Decides whether a recovery action actually restored the service, using
**service health evidence only**. Never trusts the executor's `success`
flag alone: Member 2 documents that `success=True` means the *tool* ran
fine, even when the application is still down (e.g. health check on an
unhealthy service returns `success=True` with
`{"http_status": 503, "health_status": "unhealthy"}`).

The Verifier does NOT retry, escalate, or choose recovery actions.
Those belong to Member 4's Workflow Orchestrator.

## 2. Level 1 rule

`http_200_and_healthy`: verification **passes** if and only if the
normalized evidence shows **HTTP status 200 AND `health_status`
`"healthy"`**. It **fails** when either condition is unmet, and it
fails safely on missing, malformed, or invalid evidence.

Example: executor reports restart successful but the fresh health check
reads HTTP 503 / unhealthy → verification **fails**.

## 3. Files (all under `backend/verifier/`)

| File | Responsibility |
|---|---|
| `evidence.py` | `NormalizedEvidence` schema + `normalize_evidence()` adapter (dataclass **or** dict input; tolerant `status_code` alias and digit-string coercion; rejects bools/out-of-range/invalid values with `problems`) |
| `rules.py` | `evaluate_level1(http_status, health_status) -> (passed, reason)` — pure rule matrix, no I/O |
| `verifier.py` | `Verifier.verify(execution) -> VerificationResult` — normalize → judge → build result; never raises |
| `__init__.py` | Public exports |

No new dependencies (stdlib only). No imports from
`backend.environment` (independent of executor internals) and no
imports into `backend.workflow` (no cycles, nothing rewritten).

## 4. Input contract

`verify(execution)` accepts:

- Member 1 shape: `ExecutionResult` dataclass (`task_id`, `step_id`,
  `action`, `attempt`, `success`, `result: dict`, `error`).
- Member 2 shape: equivalent plain dict (same keys; `result` may be
  `None` on tool errors).

Only the container format is adapted. The health payload itself must
carry `http_status` (int 100–599; `status_code` alias and digit strings
tolerated) and `health_status` (`"healthy"`/`"unhealthy"`,
case/whitespace tolerant). A restart payload such as
`{"recovered": True, "health_status": "healthy"}` has no HTTP status,
so it verifies as **failed** — the orchestrator must run a fresh
`health_check` after every restart (which Member 1's orchestrator
already does).

## 5. Output contract

Always Member 1's `VerificationResult` dataclass (reused, not
duplicated), JSON-serializable throughout:

```python
VerificationResult(
    task_id="task-001",          # echoed from the execution
    step_id="step-001",          # echoed from the execution
    passed=True,                 # the flag the orchestrator checks
    reason="verification passed: service healthy (...)",
    evidence={
        "rule": "http_200_and_healthy",
        "status": "passed",      # "passed" | "failed"
        "action": "health_check",
        "http_status": 200,
        "health_status": "healthy",
        "execution_success": True,  # executor's flag, for audit only
    },
)
```

`status` mirrors `passed`. `reason` always explains the verdict
(includes offending values and, for malformed input, each problem).

## 6. Assumptions

- One verification judges one execution's evidence (no history).
- Evidence reflects post-action service state (orchestrator orders it).
- `success=False` with healthy evidence still verifies as passed on
  evidence alone; Member 1's orchestrator additionally overrules that
  combination, so end-to-end behavior stays safe.

## 7. Example call (Member 4)

```python
from backend.verifier import Verifier

verifier = Verifier()

# Wiring A: Member 1 dataclass straight through
verification = verifier.verify(exec_result)          # ExecutionResult

# Wiring B: Member 2 raw dict straight through (no adapter needed)
verification = verifier.verify(executor.execute({...}))  # dict

if verification.passed:
    ...  # VERIFIED path
else:
    ...  # recovery / escalation path; see verification.reason
```

## 8. Tests

```bash
pip install -r requirements.txt
pytest tests/test_verifier.py -v   # verifier only (41 tests)
pytest -v                          # full suite
```

Covers: rule matrix (200/healthy, 503/unhealthy, 500/healthy,
200/unhealthy), executor-success-with-unhealthy-evidence,
missing/malformed payloads, invalid HTTP/health values, garbage input
(never raises), schema + JSON consistency, meaningful reasons,
mocked-orchestrator consumption, live Member 2 loop
(detect → recover → verify, incl. failed recovery), dataclass/dict
agreement, and restart-payload handling.
