import { actionLabel, healthDisplay } from "../labels";
import type { EvidenceChain } from "../types";

export default function EvidencePanel({
  evidence,
}: {
  evidence: EvidenceChain;
}) {
  let step = 0;
  const next = () => {
    step += 1;
    return step;
  };
  return (
    <section className="panel wide">
      <h2>Evidence of {evidence.final.status === "VERIFIED" ? "recovery" : "what happened"}</h2>
      <ol className="evidence-list">
        <li>
          {next()}. Initial health check —{" "}
          {evidence.before !== null
            ? `HTTP ${evidence.before.http_status ?? "?"}, ${healthDisplay(
                evidence.before.health_status
              )}`
            : "no data"}
        </li>
        {evidence.verification.length > 0 && (
          <li>
            {next()}. Verification —{" "}
            {evidence.verification[0].passed ? "PASSED" : "FAILED"}
            {evidence.verification[0].reason
              ? ` (${evidence.verification[0].reason})`
              : ""}
          </li>
        )}
        {evidence.recovery.map((rec) => (
          <li key={rec.attempt}>
            {next()}. Recovery action — {actionLabel(rec.action ?? "restart")}{" "}
            (attempt {rec.attempt}): execution{" "}
            {rec.executed && rec.execution_success ? "SUCCESS" : "NOT SUCCESSFUL"}
            {rec.recovered === true
              ? ", service recovered"
              : rec.recovered === false
                ? ", service still down"
                : ""}
          </li>
        ))}
        {evidence.after !== null &&
          evidence.after !== undefined &&
          evidence.recovery.length > 0 && (
            <li>
              {next()}. Fresh health check —{" "}
              {`HTTP ${evidence.after.http_status ?? "?"}, ${healthDisplay(
                evidence.after.health_status
              )}`}
            </li>
          )}
        {evidence.verification.length > 1 && (
          <li>
            {next()}. Verification —{" "}
            {evidence.verification[evidence.verification.length - 1].passed
              ? "PASSED"
              : "FAILED"}
          </li>
        )}
        <li>
          {next()}. Final result — {evidence.final.status}
          {evidence.final.error ? `: ${evidence.final.error}` : ""}
        </li>
      </ol>
      <details className="json-details">
        <summary>Raw evidence JSON</summary>
        <pre className="json">{JSON.stringify(evidence, null, 2)}</pre>
      </details>
    </section>
  );
}
