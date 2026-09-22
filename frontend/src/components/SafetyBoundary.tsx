const STEPS = [
  "AI Recommendation",
  "Schema Validation",
  "Allowlist Gate",
  "Deterministic Executor",
  "Independent Verifier",
];

/**
 * Static architecture explainer (not live data): the core differentiator.
 * AI can recommend actions, but cannot directly execute them.
 */
export default function SafetyBoundary() {
  return (
    <section id="safety" className="panel">
      <h2>AI Safety Boundary</h2>
      <ol className="safety-flow">
        {STEPS.map((step, i) => (
          <li key={step}>
            <span className="safety-node">
              {i === 0 && (
                <span className="shield" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="14" height="14">
                    <path
                      d="M12 2l8 3v6c0 5-3.5 9.3-8 11-4.5-1.7-8-6-8-11V5l8-3z"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    />
                  </svg>
                </span>
              )}
              {step}
            </span>
            {i < STEPS.length - 1 && (
              <span className="flow-arrow" aria-hidden="true">
                ↓
              </span>
            )}
          </li>
        ))}
      </ol>
      <p className="muted">
        AI can recommend actions, but cannot directly execute them. Every
        recommendation passes schema validation and an allowlist gate before
        the deterministic executor runs it — and the verifier judges the
        observed result, never the AI response.
      </p>
    </section>
  );
}
