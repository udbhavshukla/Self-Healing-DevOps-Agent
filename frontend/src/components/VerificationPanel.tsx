import { latestVerification } from "../selectors";
import type { WorkflowStatus } from "../types";

export default function VerificationPanel({
  status,
}: {
  status: WorkflowStatus;
}) {
  const verification = latestVerification(status);
  if (!verification) {
    return (
      <section className="panel">
        <h2>Verification</h2>
        <p className="muted">No verification recorded yet (Member 3 pending).</p>
      </section>
    );
  }
  return (
    <section className="panel">
      <h2>Verification (latest)</h2>
      <dl className="facts">
        <div>
          <dt>Result</dt>
          <dd>
            <span className={verification.passed ? "pass" : "fail"}>
              {verification.passed ? "PASSED" : "FAILED"}
            </span>
          </dd>
        </div>
        <div>
          <dt>Reason</dt>
          <dd>{verification.reason ?? "—"}</dd>
        </div>
        <div>
          <dt>Step</dt>
          <dd className="task-id">{verification.step_id}</dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>
            <details className="json-details" open>
              <summary>Show evidence</summary>
              <pre className="json">
                {JSON.stringify(verification.evidence, null, 2)}
              </pre>
            </details>
          </dd>
        </div>
      </dl>
    </section>
  );
}
