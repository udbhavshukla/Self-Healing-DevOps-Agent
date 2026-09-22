import { actionLabel } from "../labels";
import type { AIAnalysis } from "../types";

/**
 * Clearly separates AI-generated content from deterministic results:
 * the AI recommends; policy + executor + verifier decide and act.
 */
export default function AIAnalysisPanel({ ai }: { ai: AIAnalysis }) {
  const sourceLabel =
    ai.source === "offline_policy" ? "Local Offline Policy" : "Gemini";
  if (!ai.available && ai.rejected_action === null) {
    return (
      <section id="ai-analysis" className="panel ai-panel">
        <div className="card-head">
          <h2>AI Incident Analysis</h2>
          <span className="status-badge tone-neutral">NO SIGNAL</span>
        </div>
        <p>
          <strong>AI analysis unavailable.</strong>
        </p>
        {ai.error !== null && <p className="error-text">{ai.error}</p>}
        <p className="muted">
          Continuing with the deterministic recovery policy. No AI response
          was fabricated.
        </p>
      </section>
    );
  }
  if (ai.rejected_action !== null) {
    return (
      <section id="ai-analysis" className="panel ai-panel">
        <div className="card-head">
          <h2>AI Incident Analysis</h2>
          <span className="status-badge tone-bad">ADVISORY ONLY</span>
        </div>
        <p>
          <strong>AI recommendation rejected by allowlist validation.</strong>
        </p>
        <dl className="facts">
          <div>
            <dt>Rejected action</dt>
            <dd className="mono">{ai.rejected_action}</dd>
          </div>
          {ai.error !== null && (
            <div>
              <dt>Reason</dt>
              <dd>{ai.error}</dd>
            </div>
          )}
        </dl>
        <p className="muted">
          The suggested action was never executed. The deterministic policy
          remains in control.
        </p>
      </section>
    );
  }
  return (
    <section id="ai-analysis" className="panel ai-panel">
      <div className="card-head">
        <h2>AI Incident Analysis</h2>
        <span className="status-badge tone-info">ADVISORY ONLY</span>
      </div>
      <ol className="mini-flow" aria-label="How the recommendation is handled">
        <li>AI recommends</li>
        <li>Safety validation</li>
        <li>Controlled execution</li>
      </ol>
      <dl className="facts">
        <div>
          <dt>Diagnosis</dt>
          <dd>{ai.diagnosis ?? "—"}</dd>
        </div>
        <div>
          <dt>AI recommendation</dt>
          <dd>
            <span className="nowrap">
              {ai.recommended_action !== null
                ? actionLabel(ai.recommended_action)
                : "—"}
            </span>{" "}
            <span className="muted">(recommendation only — not executed by AI)</span>
          </dd>
        </div>
        <div>
          <dt>Reason</dt>
          <dd>{ai.reason ?? "—"}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>
            {ai.confidence !== null
              ? `${Math.round(ai.confidence * 100)}%`
              : "—"}
          </dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd className="muted">
            {sourceLabel}
            {ai.source !== "offline_policy" && ai.model
              ? ` (${ai.model})`
              : ""}
          </dd>
        </div>
        {ai.source === "offline_policy" && (
          <div>
            <dt>Status</dt>
            <dd>
              <strong>OFFLINE</strong>{" "}
              <span className="muted">
                — deterministic local policy advised; Gemini was not called.
              </span>
            </dd>
          </div>
        )}
      </dl>
      <p className="muted">
        AI recommendations are validated before execution.
      </p>
    </section>
  );
}
