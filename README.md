# Self-Healing-DevOps-Agent
A self-healing DevOps agent that accepts an incident, analyzes it using an LLM, executes controlled recovery actions, verifies the result, and provides evidence of what happened.

```
USER INCIDENT
    ↓
GEMINI ANALYSIS (recommends; never executes)
    ↓
WORKFLOW / ORCHESTRATOR (plans, bounded retries)
    ↓
ALLOWLISTED EXECUTOR (health_check / restart / inject_failure / deploy)
    ↓
REAL VERIFIER (HTTP 200 + healthy proves recovery)
    ↓
RECOVERY POLICY → FRESH HEALTH CHECK → RE-VERIFY
    ↓
EVIDENCE CHAIN (before / recovery / after / verification / final)
    ↓
DASHBOARD → VERIFIED or ESCALATED
```

Principle: **AI recommends, deterministic systems control, execution is
allowlisted, verification proves the result, and evidence makes the
workflow auditable.**

## Quickstart

```bash
pip install -r requirements.txt
uvicorn backend.api.app:app --reload          # http://localhost:8000
npm install --prefix frontend
npm run dev --prefix frontend                 # http://localhost:5173
python3 -m pytest -v                          # backend tests
```

Optional LLM: copy `.env.example` to `.env` and set `GEMINI_API_KEY`
(see `docs/level2-agent.md`). Without a key the agent runs fully on its
deterministic policy and reports AI as unavailable.

## Offline Resilience

The critical recovery workflow (detect → restart → verify → evidence)
runs without internet. When connectivity drops, a local deterministic
policy replaces Gemini, events persist in SQLite (`data/`, gitignored),
and synchronization reconciles them idempotently on reconnect — see
`docs/offline-resilience.md` and the dashboard's Offline Resilience
panel.

## Docs

- `docs/offline-resilience.md` — outage survival, event store, sync, demo

- `docs/level2-agent.md` — Level 2 architecture, Gemini setup, evidence, demos
- `docs/member4-dashboard.md` — dashboard + API reference
- `docs/verifier.md` — Member 3 verification rules
- `docs/member2-environment.md` — mock DevOps environment
- `INTEGRATION.md` — orchestrator integration contract
- `contracts/README.md` — shared dataclass contracts
