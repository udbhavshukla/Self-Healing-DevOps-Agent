import { buildRecoveryAttempts } from "../labels";
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
      <section id="recovery" className="panel">
        <h2>Recovery</h2>
        <p className="muted">No recovery actions — service stayed healthy.</p>
      </section>
    );
  }
  const attempts = buildRecoveryAttempts(approvals, executions);
  return (
    <section id="recovery" className="panel">
      <h2>Recovery history</h2>
      {attempts.map((attempt) => (
        <div key={attempt.index} className="attempt-card">
          <div className="attempt-title">
            Recovery Attempt {attempt.index}
          </div>
          <div className="attempt-rows">
            <div>
              <span className="muted">Action: </span>
              <span className="nowrap">{attempt.action}</span>
            </div>
            <div>
              <span className="muted">Result: </span>
              <span
                className={attempt.result === "Recovered" ? "pass" : "fail"}
              >
                {attempt.result}
              </span>
            </div>
            <div>
              <span className="muted">Health: </span>
              <span>{attempt.health}</span>
            </div>
          </div>
        </div>
      ))}
      {cycles.length > 0 && (
        <p className="muted">
          Failed cycles: {cycles.length} (limit{" "}
          {String(cycles[cycles.length - 1]["max_attempts"] ?? "?")})
        </p>
      )}
      {status.final_result?.recovered_via !== undefined &&
        status.final_result?.recovered_via !== null && (
          <p>
            <span className="muted">Recovered via: </span>
            <span className="task-id">{status.final_result.recovered_via}</span>
          </p>
        )}
    </section>
  );
}
