import type { WorkflowState } from "../types";

const CLASS_BY_STATE: Record<WorkflowState, string> = {
  PLANNED: "badge planned",
  EXECUTING: "badge executing",
  VERIFYING: "badge verifying",
  RECOVERING: "badge recovering",
  VERIFIED: "badge verified",
  FAILED: "badge failed",
  ESCALATED: "badge escalated",
};

export default function StateBadge({ state }: { state: WorkflowState }) {
  return <span className={CLASS_BY_STATE[state]}>{state}</span>;
}
