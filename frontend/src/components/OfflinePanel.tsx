import type { OfflineSummary } from "../types";

interface Props {
  offline: OfflineSummary | null;
  syncing: boolean;
  onSimulate: (online: boolean | null) => void;
  onSyncNow: () => void;
}

export default function OfflinePanel({
  offline,
  syncing,
  onSimulate,
  onSyncNow,
}: Props) {
  if (offline === null) {
    return (
      <section className="panel">
        <h2>Offline resilience</h2>
        <p className="muted">Connectivity state loading…</p>
      </section>
    );
  }
  const isOnline = offline.connectivity === "online";
  const last = offline.last_sync;
  const syncText = syncing
    ? "SYNCING…"
    : last === null || !last.attempted
      ? offline.pending > 0
        ? "Waiting for connectivity"
        : "Idle — nothing queued"
      : last.failed > 0
        ? `${last.synced} synced, ${last.failed} failed (kept for retry)`
        : `${last.synced}/${last.synced + offline.pending} events synced`;
  return (
    <section className="panel">
      <h2>Offline resilience</h2>
      <dl className="facts">
        <div>
          <dt>Connectivity</dt>
          <dd>
            <strong className={isOnline ? "pass" : "fail"}>
              {isOnline ? "ONLINE" : "OFFLINE"}
            </strong>
          </dd>
        </div>
        <div>
          <dt>Critical workflow</dt>
          <dd>
            <span className="pass">OPERATIONAL</span>{" "}
            <span className="muted">(local recovery needs no internet)</span>
          </dd>
        </div>
        <div>
          <dt>Offline events</dt>
          <dd>
            {offline.pending} pending · {offline.synced} synced ·{" "}
            {offline.failed} failed
          </dd>
        </div>
        <div>
          <dt>Synchronization</dt>
          <dd>{syncText}</dd>
        </div>
      </dl>
      <div className="button-row">
        <button type="button" onClick={() => onSimulate(false)}>
          Simulate offline
        </button>
        <button type="button" onClick={() => onSimulate(true)}>
          Simulate online
        </button>
        <button type="button" onClick={() => onSimulate(null)}>
          Auto detect
        </button>
        <button type="button" onClick={onSyncNow} disabled={syncing}>
          Sync now
        </button>
      </div>
      <p className="muted">
        Real Wi-Fi disconnects are detected automatically; the simulate
        buttons only force the state for demos.
      </p>
    </section>
  );
}
