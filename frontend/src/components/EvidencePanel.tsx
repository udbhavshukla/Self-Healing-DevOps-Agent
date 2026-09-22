import { actionLabel, healthDisplay } from "../labels";
import type { EvidenceChain } from "../types";

function checkText(
  http: number | null | undefined,
  health: string | null | undefined
): string {
  return `HTTP ${http ?? "?"}, ${healthDisplay(health ?? null)}`;
}

export default function EvidencePanel({
  evidence,
}: {
  evidence: EvidenceChain;
}) {
  const items: Array<{ title: string; body: string }> = [];
  items.push({
    title: "Initial health check",
    body: checkText(
      evidence.before?.http_status ?? null,
      evidence.before?.health_status ?? null
    ),
  });
  if (evidence.verification.length > 0) {
    const first = evidence.verification[0];
    items.push({
      title: `Verification ${first.passed ? "passed" : "failed"}`,
      body: first.reason ?? "No reason recorded.",
    });
  }
  for (const rec of evidence.recovery) {
    items.push({
      title: `Recovery action — ${actionLabel(rec.action ?? "restart")} (attempt ${rec.attempt})`,
      body: `Execution: ${
        rec.executed && rec.execution_success ? "SUCCESS" : "NOT SUCCESSFUL"
      }${
        rec.recovered === true
          ? " · service recovered"
          : rec.recovered === false
            ? " · service still down"
            : ""
      }`,
    });
  }
  if (evidence.after !== null && evidence.recovery.length > 0) {
    items.push({
      title: "Fresh health check",
      body: checkText(
        evidence.after.http_status,
        evidence.after.health_status
      ),
    });
  }
  if (evidence.verification.length > 1) {
    const last = evidence.verification[evidence.verification.length - 1];
    items.push({
      title: `Verification ${last.passed ? "passed" : "failed"}`,
      body: last.reason ?? "No reason recorded.",
    });
  }
  items.push({
    title: `Final result — ${evidence.final.status}`,
    body: evidence.final.error ?? "Workflow verified successfully.",
  });

  return (
    <section id="evidence" className="panel wide">
      <h2>
        Evidence chain
        <span className="muted"> — audit trail, derived from recorded history</span>
      </h2>
      <ol className="evidence-chain">
        {items.map((item, i) => (
          <li key={i} className="evidence-item">
            <details open={i === 0}>
              <summary>
                <span className="evidence-num">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="evidence-title">{item.title}</span>
              </summary>
              <p className="evidence-body">{item.body}</p>
            </details>
          </li>
        ))}
      </ol>
      <details className="json-details">
        <summary>Raw evidence JSON</summary>
        <pre className="json">{JSON.stringify(evidence, null, 2)}</pre>
      </details>
    </section>
  );
}
