import { finalSummary } from "../labels";
import type { WorkflowStatus } from "../types";

export default function FinalResult({ status }: { status: WorkflowStatus }) {
  const summary = finalSummary(status);
  if (summary.kind === "verified") {
    return (
      <section className="panel">
        <h2>Final result</h2>
        <div className="result-banner verified">
          <strong>Status: {summary.title}</strong>
          <span>Result: {summary.subtitle}</span>
          {summary.recoveredVia !== null && (
            <span>
              Recovered via:{" "}
              <span className="task-id">{summary.recoveredVia}</span>
            </span>
          )}
        </div>
        {status.final_result !== null && (
          <details className="json-details">
            <summary>Execution details</summary>
            <pre className="json">
              {JSON.stringify(status.final_result.execution, null, 2)}
            </pre>
          </details>
        )}
      </section>
    );
  }
  if (summary.kind === "terminal") {
    return (
      <section className="panel">
        <h2>Final result</h2>
        <div className="result-banner terminal">
          <strong>Status: {summary.title}</strong>
          <span>Result: {summary.subtitle}</span>
        </div>
        <p className="muted">
          No final result is available in state {status.status}.
        </p>
      </section>
    );
  }
  return (
    <section className="panel">
      <h2>Final result</h2>
      <p className="muted">{summary.subtitle}</p>
    </section>
  );
}
