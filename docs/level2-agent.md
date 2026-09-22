# Level 2 — Intelligent Agent (user input + Gemini + evidence)

## 1. Level 2 architecture

```
USER INCIDENT (dashboard textarea or API "incident" field)
    ↓
FastAPI (backend/api/app.py)
    ↓
Incident Analyzer (backend/ai/) → Gemini (structured JSON)
    ↓ validated AIAnalysisResult (allowlisted action or rejection/fallback)
Orchestrator (unchanged) → Executor (unchanged) → MockService
    ↓
Real Verifier (unchanged, authoritative)
    ↓
Recovery Policy (unchanged, bounded) → fresh health check → re-verify
    ↓
Evidence chain (backend/api/evidence.py, from real history)
    ↓
Dashboard: incident + AI analysis + workflow + evidence + VERIFIED/ESCALATED
```

Central principle: **Gemini recommends. Policy validates. Executor
executes. Verifier verifies. Evidence proves.**

## 2. User input flow

1. User types an incident in the dashboard ("User incident" section) or
   POSTs `{"incident": "..."}` to `/api/workflows`.
2. The API snapshots current health (read-only pre-flight check),
   builds an `IncidentContext`, and asks Gemini for structured analysis.
3. The recommendation is validated against the executor allowlist
   (`health_check`, `restart`, `inject_failure`, `deploy`); anything
   else is recorded as rejected and never executed.
4. The existing orchestrator runs unchanged; AI findings travel as
   `incident_received` / `ai_analysis` history events plus an
   `ai_analysis` payload field.

## 3. Gemini integration

- `backend/ai/gemini_client.py`: transport only. Reads `GEMINI_API_KEY`
  from the environment, model from `GEMINI_MODEL` (default
  `gemini-2.0-flash`), requests `application/json` at temperature 0
  with a 20s timeout. Never logs keys, never executes anything.
- `backend/ai/incident_analyzer.py`: prompt building, pydantic
  validation, allowlist check, graceful fallback.
- `backend/ai/schemas.py`: `IncidentContext`, `AIRecommendation`,
  `AIAnalysisResult` (pydantic). Allowlist reuses Member 2's
  `Executor.ALLOWED_ACTIONS` — single source of truth.
- Dependency: `google-genai` (official SDK) in `requirements.txt`.

## 4. Structured AI response

```json
{
  "diagnosis": "Service is unhealthy and returning HTTP 503.",
  "recommended_action": "restart",
  "reason": "Restart is an allowed recovery action for this failure pattern.",
  "confidence": 0.91
}
```

Validated by pydantic (`confidence` in 0..1, all fields non-empty);
`recommended_action` must be allowlisted or it is rejected.

## 5. Safety boundary

Gemini can never reach the executor: the analyzer returns data, the
API records it, and only the deterministic orchestrator + recovery
policy trigger allowlisted actions. No shell, no subprocess, no code
execution anywhere. Gemini receives only incident text plus
non-sensitive health context — never keys, credentials, or env dumps.

## 6. Verification

Unchanged Member 3 verifier (`backend/verifier/`), rule
`http_200_and_healthy`. `success=True` with 503/unhealthy still
verifies as FAILED. The API never second-guesses verdicts.

## 7. Evidence

`backend/api/evidence.py` builds `{incident, ai_analysis, before,
recovery[], after, verification[], final}` strictly from the run's
real history (missing data stays null; `recorded_at` is the
API-observed completion time). The dashboard renders a numbered
human-readable chain plus collapsible raw JSON.

## 8. Recovery

Unchanged: policy approves `restart_service` only for failed
`health_check`s, max 3 attempts, fresh check after every restart,
escalation on exhaustion. AI output cannot widen this.

## 9. Fallback when Gemini is unavailable

Missing/invalid key, timeout, network/model error, or malformed
response → `ai_analysis: {available: false, error: ...}`, an
`ai_unavailable` history event, and the Level 1 policy continues
normally. The UI shows "AI analysis unavailable" instead of inventing
a response. Nothing is fabricated, nothing crashes.

## 10. Environment variables

See `.env.example`. `GEMINI_API_KEY` (required for live AI),
`GEMINI_MODEL` (optional, default `gemini-2.0-flash`). `.env` is
gitignored — never commit keys.

## 11. How to run locally

```bash
pip install -r requirements.txt
cp .env.example .env   # then set a real GEMINI_API_KEY (optional)
uvicorn backend.api.app:app --reload
npm install --prefix frontend && npm run dev --prefix frontend
```

Without a key the system runs fully in deterministic fallback mode.

## 12. Demo scenarios

Level 1 presets still work (`normal`, `injected-failure`,
`persistent-failure`). Level 2 incident demos (deterministic service
preset mapping, documented in `backend/api/scenarios.py`):

- A: "The service is returning HTTP 503." → recovery → VERIFIED.
- B: "The service is still unavailable after restart." → ESCALATED.
- C: "Check whether the service is healthy." → VERIFIED (no recovery).

A user-reported error status (e.g. HTTP 500) is preserved end to end:
the incident's first 4xx/5xx code becomes the simulated service's
failure status (`MockService(fail_http_status=...)`), so evidence
shows HTTP 500 before recovery and HTTP 200 after — never silently
converted to 503. Incidents without an error code use the 503 default.

## 13. How to test

```bash
python3 -m pytest -v                    # full backend suite
python3 -m pytest tests/test_level2.py -v   # Level 2 only
npm run build --prefix frontend         # tsc + Vite build
npm run check:labels --prefix frontend  # frontend label checks
```
