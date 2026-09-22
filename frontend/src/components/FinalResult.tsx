import type { WorkflowStatus } from "../types";

export default function FinalResult({ status }: { status: WorkflowStatus }) {
  if (status.status === "VERIFIED" && status.final_result !== null) {
    const final = status.final_result;
    return (
      <section className="panel">
        <h2>Final result</h2>
        <dl className="facts">
          <div>
            <dt>Step</dt>
            <dd className="mono">{final.step_id}</dd>
          </div>
          <div>
            <dt>Action</dt>
            <dd className="mono">{final.action}</dd>
          </div>
          <div>
            <dt>Reason</dt>
            <dd>{final.reason ?? "—"}</dd>
          </div>
          {final.recovered_via !== undefined && (
            <div>
              <dt>Recovered via</dt>
              <dd className="mono">{final.recovered_via}</dd>
            </div>
          )}
          <div>
            <dt>Execution</dt>
            <dd>
              <pre className="json">
                {JSON.stringify(final.execution, null, 2)}
              </pre>
            </dd>
          </div>
        </dl>
      </section>
    );
  }
  if (status.status === "FAILED" || status.status === "ESCALATED") {
    return (
      <section className="panel">
        <h2>Final result</h2>
        <p className="error-text">{status.error ?? "Workflow did not verify."}</p>
        <p className="muted">
          No final result is available in state {status.status}.
        </p>
      </section>
    );
  }
  return (
    <section className="panel">
      <h2>Final result</h2>
      <p className="muted">Workflow has not reached a terminal state yet.</p>
    </section>
  );
}
