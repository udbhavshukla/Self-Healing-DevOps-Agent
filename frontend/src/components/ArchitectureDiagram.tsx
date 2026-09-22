const NODES = [
  "Incident",
  "AI / Offline Policy",
  "Safety Gate",
  "Orchestrator",
  "Allowlisted Executor",
  "Health Check",
  "Verifier",
  "Verified / Escalated",
  "Evidence Store",
  "Synchronization",
];

/** Compact static systems-architecture diagram (pure CSS, no libraries). */
export default function ArchitectureDiagram() {
  return (
    <section id="architecture" className="panel">
      <h2>System architecture</h2>
      <ol className="arch-flow">
        {NODES.map((node, i) => (
          <li key={node}>
            <span className="arch-node">{node}</span>
            {i < NODES.length - 1 && (
              <span className="flow-arrow" aria-hidden="true">
                ↓
              </span>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
