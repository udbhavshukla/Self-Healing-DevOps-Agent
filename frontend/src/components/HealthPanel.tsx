import { latestExecution } from "../selectors";
import type { WorkflowStatus } from "../types";

export default function HealthPanel({ status }: { status: WorkflowStatus }) {
  const exec = latestExecution(status);
  if (!exec) {
    return (
      <section className="panel">
        <h2>Health</h2>
        <p className="muted">No executions recorded yet.</p>
      </section>
    );
  }
  const result = exec.result as Record<string, unknown>;
  const httpStatus = result["http_status"];
  const healthStatus = result["health_status"];
  return (
    <section className="panel">
      <h2>Health (latest execution)</h2>
      <dl className="facts">
        <div>
          <dt>HTTP status</dt>
          <dd className="mono">{String(httpStatus ?? "—")}</dd>
        </div>
        <div>
          <dt>Health status</dt>
          <dd>{String(healthStatus ?? "—")}</dd>
        </div>
        <div>
          <dt>Tool success</dt>
          <dd>{exec.success ? "true" : "false"}</dd>
        </div>
        <div>
          <dt>Action</dt>
          <dd className="mono">
            {exec.action} (step {exec.step_id}, attempt {exec.attempt})
          </dd>
        </div>
        {exec.error !== null && (
          <div>
            <dt>Error</dt>
            <dd className="error-text">{exec.error}</dd>
          </div>
        )}
      </dl>
    </section>
  );
}
