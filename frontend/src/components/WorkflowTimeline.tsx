import type { HistoryEvent } from "../types";

function describe(event: HistoryEvent, index: number): string {
  const from = event["from"];
  const to = event["to"];
  if (event.event === "state_transition") {
    return `#${index} state: ${String(from)} → ${String(to)}`;
  }
  const step = event["step_id"];
  const action = event["action"];
  const extra =
    step !== undefined || action !== undefined
      ? ` — ${[action, step].filter((v) => v !== undefined).map(String).join(" / ")}`
      : "";
  return `#${index} ${event.event}${extra}`;
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
        {history.map((event, i) => (
          <li key={i} className="timeline-item">
            <code>{describe(event, i + 1)}</code>
          </li>
        ))}
      </ol>
    </section>
  );
}
