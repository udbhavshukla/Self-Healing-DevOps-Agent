# Member 4 — Dashboard & API Integration

## 1. Architecture

```
React dashboard (frontend/src)
  → fetch client (api/client.ts) → FastAPI (backend/api/app.py)
      → Member2ExecutorAdapter (adapter.py): ActionRequest dataclass → dict,
        restart_service → restart, dict → ExecutionResult (Member 1 names kept)
      → Member 2 Executor + MockService (untouched)
      → Member 3 Verifier (`backend/verifier/verifier.py`: evidence-based
        Level 1 rule `http_200_and_healthy`; see `docs/verifier.md`)
      → Member 1 WorkflowOrchestrator (untouched)
      → in-memory store (store.py), scenario presets (scenarios.py)
```

The API layer is thin: routes build objects and call `orchestrator.run()`.
No workflow, recovery, or verification logic in routes or frontend.

## 2. Backend startup

```bash
pip install -r requirements.txt
uvicorn backend.api.app:app --reload   # serves http://localhost:8000
```

## 3. Frontend startup

```bash
npm install --prefix frontend
npm run dev --prefix frontend          # serves http://localhost:5173, /api proxied to :8000
npm run build --prefix frontend        # type-check (tsc) + production build
```

## 4. API endpoints

- `GET /api/health` → `{"status": "ok"}`.
- `POST /api/workflows` → body `{task_id?, task_type?, service_name?,
  scenario}` (`task_id` generated as `task-<8 hex>` when omitted;
  returns 201) → full `WorkflowStatus` payload
  `{task_id, status, current_step, attempt, history, final_result, error}`.
- `GET /api/workflows/{task_id}` → stored payload, or
  `404 {"detail": "Unknown task_id: ..."}`.

## 5. Scenario names

- `normal`: healthy service → `VERIFIED`, no recovery.
- `injected-failure`: unhealthy service → detect → `restart_service` →
  fresh `health_check` → `VERIFIED` with `final_result.recovered_via`.
- `persistent-failure`: unhealthy + deterministic failed recovery →
  retries exhausted → `ESCALATED`, `final_result: null`, `error` set.

## 6. Verifier (Member 3, integrated)

`backend/api/app.py` constructs Member 3's `Verifier`
(`backend/verifier/verifier.py`) directly — no adapter is needed because
it natively accepts Member 1's `ExecutionResult` dataclass and returns
Member 1's `VerificationResult` (same fields the dashboard already
renders: `task_id`, `step_id`, `passed`, `reason`, `evidence`).

Rule (`http_200_and_healthy`, see `docs/verifier.md`): pass if and only
if evidence shows HTTP 200 **and** `health_status "healthy"`. The
executor's `success` flag alone never passes — `success=True` with
HTTP 503/unhealthy verifies as FAILED. The verifier never retries,
recovers, or escalates; it only answers whether an execution satisfied
the rule. The former temporary `StubVerifier`
(`backend/api/stub_verifier.py`) was removed once the real verifier
landed; no route, store, adapter, or frontend change was required.

## 7. Complete demo

1. Start the backend, then the frontend (see above).
2. Open http://localhost:5173 (mock data shows by default).
3. Pick a scenario, press **Start Workflow** → live backend result renders:
   status panels, health, verification, recovery history, timeline,
   final result.
4. Repeat for all three scenarios. `persistent-failure` ends in
   `ESCALATED` with the retry-limit error and no final result.

## 8. Tests

```bash
python3 -m pytest -v                 # full suite (backend)
python3 -m pytest tests/test_api.py -v   # Member 4 API tests only
```

`tests/test_api.py` covers health, all three scenarios, stored-status
retrieval, 404 handling, response shape, and generated task ids.
