import { actionLabel, healthDisplay } from "../labels";
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
          <dd>{healthDisplay(healthStatus)}</dd>
        </div>
        <div>
          <dt>Tool success</dt>
          <dd className="nowrap">{exec.success ? "true" : "false"}</dd>
        </div>
        <div>
          <dt>Action</dt>
          <dd>
            <span className="nowrap">{actionLabel(exec.action)}</span>{" "}
            <span className="muted">
              (step <span className="task-id">{exec.step_id}</span>, attempt{" "}
              {exec.attempt})
            </span>
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
