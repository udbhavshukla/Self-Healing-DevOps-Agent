import {
  recoveryApprovals,
  recoveryCycles,
  recoveryExecutions,
} from "../selectors";
import type { WorkflowStatus } from "../types";

export default function RecoveryHistory({
  status,
}: {
  status: WorkflowStatus;
}) {
  const approvals = recoveryApprovals(status);
  const executions = recoveryExecutions(status);
  const cycles = recoveryCycles(status);
  if (approvals.length === 0 && cycles.length === 0) {
    return (
      <section className="panel">
        <h2>Recovery</h2>
        <p className="muted">No recovery actions — service stayed healthy.</p>
      </section>
    );
  }
  return (
    <section className="panel">
      <h2>Recovery history</h2>
      <dl className="facts">
        <div>
          <dt>Recovery attempts</dt>
          <dd>{approvals.length}</dd>
        </div>
        {approvals.map((approval, i) => (
          <div key={i}>
            <dt>Approved action</dt>
            <dd className="mono">
              {String(approval.action)} (step {String(approval.step_id)})
            </dd>
          </div>
        ))}
        {executions.map((exec, i) => (
          <div key={`exec-${i}`}>
            <dt>Recovery result</dt>
            <dd className="mono">
              recovered={String(exec.result["recovered"] ?? "?")},{" "}
              health={String(exec.result["health_status"] ?? "?")}
            </dd>
          </div>
        ))}
        {cycles.length > 0 && (
          <div>
            <dt>Failed cycles</dt>
            <dd>
              {cycles.length} (last:{" "}
              {String(
                cycles[cycles.length - 1]["recovery_attempts"] ?? "?"
              )}{" "}
              / {String(cycles[cycles.length - 1]["max_attempts"] ?? "?")})
            </dd>
          </div>
        )}
        {status.final_result?.recovered_via !== undefined &&
          status.final_result?.recovered_via !== null && (
            <div>
              <dt>Recovered via</dt>
              <dd className="mono">{status.final_result.recovered_via}</dd>
            </div>
          )}
      </dl>
    </section>
  );
}
