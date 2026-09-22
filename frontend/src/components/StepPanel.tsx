import type { WorkflowStatus } from "../types";
import StateBadge from "./StateBadge";

export default function StepPanel({ status }: { status: WorkflowStatus }) {
  return (
    <section id="status" className="panel">
      <h2>Current status</h2>
      <dl className="facts">
        <div>
          <dt>Task ID</dt>
          <dd className="task-id">{status.task_id}</dd>
        </div>
        <div>
          <dt>Current state</dt>
          <dd>
            <StateBadge state={status.status} />
          </dd>
        </div>
        <div>
          <dt>Current step</dt>
          <dd className="task-id">{status.current_step ?? "—"}</dd>
        </div>
        <div>
          <dt>Attempt count</dt>
          <dd>{status.attempt}</dd>
        </div>
      </dl>
    </section>
  );
}
