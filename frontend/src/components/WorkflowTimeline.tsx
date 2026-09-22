import { actionLabel, eventLabel } from "../labels";
import type { HistoryEvent } from "../types";

/** Friendly primary label; original technical names kept as muted detail. */
function detail(event: HistoryEvent): string | null {
  const parts: string[] = [];
  const action = event["action"];
  if (action !== undefined) parts.push(`action: ${String(action)}`);
  const step = event["step_id"];
  if (step !== undefined) parts.push(`step: ${String(step)}`);
  const from = event["from"];
  const to = event["to"];
  if (from !== undefined || to !== undefined) {
    parts.push(`${String(from ?? "?")} → ${String(to ?? "?")}`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

export default function WorkflowTimeline({
  history,
}: {
  history: HistoryEvent[];
}) {
  if (history.length === 0) {
    return (
      <section className="panel">
        <h2>Timeline</h2>
        <p className="muted">No history recorded.</p>
      </section>
    );
  }
  return (
    <section className="panel wide">
      <h2>Workflow timeline ({history.length} events)</h2>
      <ol className="timeline">
        {history.map((event, i) => {
          const extra = detail(event);
          return (
            <li key={i} className="timeline-item">
              <span className="timeline-label">
                {eventLabel(event.event)}
                {event.event === "executing" &&
                  event["action"] !== undefined &&
                  ` — ${actionLabel(String(event["action"]))}`}
              </span>
              {extra !== null && (
                <span className="timeline-tech">{extra}</span>
              )}
              <span className="timeline-tech muted-id">{event.event}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
