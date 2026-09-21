# Member 2 — Mock DevOps Environment & Recovery

## 1. Purpose

Deterministic in-memory simulation of a DevOps target service so the
team can demo detect → recover → verify without real infrastructure.
No AWS/GCP/Kubernetes/Docker, no shell execution, no randomness.

Member 2 owns the **tools and environment**. It does NOT decide
retries/escalation (Member 1) or verify outcomes (Member 3).

## 2. Architecture

```
Member 1 (orchestrator, future)
  → Executor.execute(action_request: dict) -> execution_result: dict
      → MockService (state)
      → check_health(service) (health_checker.py)
      → restart_service(service) (recovery.py)
```

Files (all under `backend/environment/`):

| File | Contents |
|---|---|
| `mock_service.py` | `MockService`: state, `inject_failure`, `restart`, `deploy`, `fail_recovery_mode` |
| `health_checker.py` | `check_health(service)` + `HealthChecker` wrapper |
| `recovery.py` | `restart_service(service)` + `Recovery` wrapper |
| `executor.py` | `Executor` with action allowlist |

## 3. MockService behavior

- Starts `healthy`, version `"1.0.0"` by default.
- `get_status() -> "healthy" | "unhealthy"`.
- `inject_failure()` → `unhealthy` (deterministic).
- `restart() -> bool` → `healthy` unless `fail_recovery_mode=True`,
  in which case it stays `unhealthy` and returns `False`.
- `deploy(version=None) -> str` → sets `healthy`, optionally bumps version.
- `set_fail_recovery_mode(bool)` toggles deterministic failed recovery.
- `get_info()` returns `{health_status, version, fail_recovery_mode}`.

## 4. Supported executor actions

Allowlist: `health_check`, `restart`, `inject_failure`, `deploy`.
Anything else (e.g. `delete_database`) is rejected with
`success=false` and never executed.

## 5. Health-check behavior

- Healthy → `{"http_status": 200, "health_status": "healthy"}`
- Unhealthy → `{"http_status": 503, "health_status": "unhealthy"}`

The checker only reports application health. Whether the *tool*
succeeded is expressed by the executor's `success` flag.

## 6. Failure injection

Via `inject_failure` action or `service.inject_failure()` directly.
Always deterministic: service becomes `unhealthy` immediately.

## 7. Restart / recovery

Via `restart` action → `restart_service(service)` →
`service.restart()`. Returns e.g.
`{"action": "restart", "recovered": true, "health_status": "healthy"}`.
No retry or escalation here — the orchestrator decides what to do next.

## 8. Deterministic failed recovery

For testing the orchestrator's retry/escalation path:

```python
service.set_fail_recovery_mode(True)
executor.execute({... "action": "restart" ...})
# → success=true, result.recovered=false, service stays unhealthy
service.set_fail_recovery_mode(False)  # later restarts recover again
```

No randomness is involved.

## 9. Execution result format

Request:

```json
{"task_id": "task-001", "step_id": "step-001",
 "action": "health_check", "parameters": {}}
```

Success response (note: unhealthy app, successful tool call):

```json
{"task_id": "task-001", "step_id": "step-001",
 "action": "health_check", "attempt": 1, "success": true,
 "result": {"http_status": 503, "health_status": "unhealthy"},
 "error": null}
```

Rejection response:

```json
{"task_id": "task-001", "step_id": "step-001",
 "action": "delete_database", "attempt": 1, "success": false,
 "result": null, "error": "Unsupported action: delete_database"}
```

Malformed requests (missing `action`, non-dict input) return
`success=false` with an explanatory `error` instead of raising.

## 10. Security

- Explicit `ALLOWED_ACTIONS` allowlist; nothing else can run.
- No `os.system`, no `subprocess`, no `shell=True`, no `eval`/`exec`.
- `parameters` values are data only (e.g. deploy `version`).

## 11. How to run the tests

```bash
pip install -r requirements.txt
pytest -v
# Member 2 only:
pytest tests/test_member2_environment.py -v
```
