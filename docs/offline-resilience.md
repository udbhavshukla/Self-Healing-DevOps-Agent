# Offline Resilience (internet-outage survival)

```
                    USER INCIDENT
                         |
                         v
               Connectivity Manager
                    /          \
               ONLINE          OFFLINE
                 |                |
                 v                v
              Gemini      Local Offline Policy
              (advisory)  (deterministic, allowlisted)
                 |                |
                 +-------+--------+
                         v
              Deterministic Orchestrator (unchanged)
                         v
              Executor (allowlist unchanged)
                         v
              Verifier (unchanged, authoritative)
                         v
              Local Event Store (SQLite)
                    /          \
               ONLINE         OFFLINE
                  |               |
                  v               v
            Sync (idempotent)  Queue (pending)
```

## 1. Critical offline function

Incident detection → deterministic recovery execution → verification →
evidence generation. When the network drops, Gemini is skipped entirely
and `OfflinePolicy` (pure local rules: 5xx/unhealthy → `restart`,
unknown → `health_check`, always from `Executor.ALLOWED_ACTIONS`)
advises instead. The orchestrator, recovery policy, retry limits, and
verifier run exactly as online — the recovery path never needs the
internet.

## 2. Connectivity detection (`backend/offline/connectivity.py`)

`ConnectivityManager` keeps a cached flag: the workflow only reads it,
never waits on it. `refresh()` probes (fast TCP connect, default
`8.8.8.8:53`, 2s timeout) at most once per 15s cooldown — no excessive
requests. Gemini outcomes (`report_success`) and the demo override
endpoint reaffirm/force state without probing. Probe and clock are
injectable for deterministic tests. `GET /api/offline/status` refreshes
opportunistically, so dashboard polling detects real Wi-Fi drops.

## 3. Local policy (`backend/offline/offline_policy.py`)

No network, no shell, no executor calls. Returns an `AIAnalysisResult`
-shaped payload with `source="offline_policy"` and `confidence=None`
(never fabricated) so the dashboard renders it through the same panel
while labeling it as local, not Gemini.

## 4. SQLite event store (`backend/offline/event_store.py`)

Default `data/offline_events.db` (env `OFFLINE_DB_PATH`; `data/` and
`*.db` are gitignored). Tables: `events(event_id PK, task_id,
event_type, timestamp, payload, sync_status, retry_count,
next_retry_at)` and `synced_events` (durable server-side history).
Payloads are scrubbed of API keys/secrets before storage. Every run's
history + `final_result` is recorded; file persistence means events
survive process restarts (tested by reopening the DB).

## 5. Queue

While offline, rows stay `pending` (dashboard shows the count).
Workflows complete normally — queueing never blocks recovery.

## 6. Synchronization (`backend/offline/sync_manager.py`)

On reconnect (detected by poll/probe or the override endpoint),
`sync_now()` publishes due events via `INSERT OR IGNORE` keyed by
`event_id` — idempotent, duplicates impossible. Failures keep the
event with exponential backoff (`2^n`, capped 60s, `next_retry_at`);
nothing is ever dropped by a failed sync. Bounded batches, no tight
loops, and it runs after a run completes so recovery is never blocked.
`sync_started/completed/failed` lifecycle rows are stored as synced
(they describe sync itself). Endpoints: `POST /api/offline/sync`,
`GET /api/offline/status` (auto-syncs), `POST /api/offline/connectivity`
(`{"online": true|false|null}` demo override).

## 7. Idempotency & retry

Stable `event_id` primary keys on both tables; re-syncing is a no-op;
backoff via `next_retry_at`; `retry_count` is visible for audit.

## 8. Security boundaries

Allowlist untouched; offline policy output asserted ⊆ allowlist in
tests; no shell/subprocess/eval; Gemini never called while offline
(asserted); secrets scrubbed before SQLite writes (tested); `.env`
untracked; `data/*.db` untracked.

## 9. Demo instructions (disconnect → operate → reconnect → sync)

1. Start backend + frontend; dashboard shows **ONLINE**, 0 pending.
2. Disconnect Wi-Fi (or press **Simulate offline**).
3. Submit "The payment service is returning HTTP 503 after the latest
   deployment." → workflow runs fully offline: Offline Policy →
   Health Check → Restart → Verification → **VERIFIED**; events show
   **PENDING** (4+ on one incident run).
4. Stay offline ≥ 1 minute; submit more incidents — all stay operational
   and queued.
5. Reconnect (or **Simulate online**/**Auto detect**) → status poll
   shows **SYNCING** then `N/N events synced`, queue 0 pending.
6. Evidence chain shows incident → OFFLINE → policy → checks →
   persistence → restore → sync → VERIFIED.

## 10. Tests

`tests/test_offline.py` (18 tests): connectivity states/transitions/
cooldown, policy mapping + allowlist invariance + no-Gemini, store
CRUD/persistence/scrub/idempotency, sync skip/publish/backoff/dup-proof,
offline E2E without Gemini, reconnect auto-sync, a **60-second outage
with a simulated clock** (operate at t=0/35/70s, all VERIFIED and
pending, then reconnect → all synced exactly once), endpoint behavior.
