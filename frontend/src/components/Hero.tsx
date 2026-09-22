import { latestVerification } from "../selectors";
import type { OfflineSummary, WorkflowStatus } from "../types";
import { MetricCard } from "./ui";

/** System overview: only real data, neutral placeholders when idle. */
export default function Hero({
  displayed,
  offline,
  incident,
}: {
  displayed: WorkflowStatus | null;
  offline: OfflineSummary | null;
  incident: string;
}) {
  const verification =
    displayed !== null ? latestVerification(displayed) : null;
  const pending = offline?.pending ?? 0;

  return (
    <section id="overview" className="hero">
      <div className="hero-text">
        <p className="card-eyebrow">Self-healing operations</p>
        <h2>Monitor, diagnose, recover and verify incidents automatically.</h2>
      </div>
      <div className="metric-row">
        <MetricCard
          label="System status"
          value={displayed ? displayed.status : "—"}
          tone={
            displayed?.status === "VERIFIED"
              ? "ok"
              : displayed?.status === "ESCALATED" ||
                  displayed?.status === "FAILED"
                ? "bad"
                : displayed
                  ? "warn"
                  : "neutral"
          }
          sub={
            displayed
              ? `Attempt ${displayed.attempt}`
              : "No workflow run yet"
          }
        />
        <MetricCard
          label="Current incident"
          value={
            incident.trim() !== ""
              ? incident.trim().slice(0, 60) +
                (incident.trim().length > 60 ? "…" : "")
              : (displayed?.evidence?.incident?.text.slice(0, 60) ?? "—")
          }
          sub={displayed ? `Task ${displayed.task_id}` : "Awaiting input"}
        />
        <MetricCard
          label="Connectivity"
          value={offline ? offline.connectivity.toUpperCase() : "…"}
          tone={
            offline === null
              ? "neutral"
              : offline.connectivity === "online"
                ? "ok"
                : "warn"
          }
          sub={
            pending > 0 ? `${pending} event(s) pending` : "Queue clear"
          }
        />
        <MetricCard
          label="Verification"
          value={
            verification
              ? verification.passed
                ? "PASSED"
                : "FAILED"
              : "—"
          }
          tone={
            verification
              ? verification.passed
                ? "ok"
                : "bad"
              : "neutral"
          }
          sub="Independent of AI"
        />
        <MetricCard
          label="Offline events"
          value={offline ? String(pending) : "…"}
          tone={pending > 0 ? "warn" : "ok"}
          sub={
            offline
              ? `${offline.synced} synced · ${offline.failed} failed`
              : "Loading queue state"
          }
        />
      </div>
    </section>
  );
}
