/** Read-only helpers that extract display data from WorkflowStatus history. */
import type {
  ExecutionPayload,
  HistoryEvent,
  VerificationPayload,
  WorkflowStatus,
} from "./types";

function payloads<T>(history: HistoryEvent[], events: string[]): T[] {
  return history
    .filter((h) => events.includes(h.event))
    .map((h) => h.result as T)
    .filter((r) => typeof r === "object" && r !== null);
}

export function executions(status: WorkflowStatus): ExecutionPayload[] {
  return payloads<ExecutionPayload>(status.history, [
    "execution",
    "recovery_execution",
  ]);
}

export function verifications(status: WorkflowStatus): VerificationPayload[] {
  return payloads<VerificationPayload>(status.history, [
    "verification",
    "recovery_verification",
  ]);
}

export function latestExecution(
  status: WorkflowStatus
): ExecutionPayload | null {
  const all = executions(status);
  return all.length > 0 ? all[all.length - 1] : null;
}

export function latestVerification(
  status: WorkflowStatus
): VerificationPayload | null {
  const all = verifications(status);
  return all.length > 0 ? all[all.length - 1] : null;
}

export function recoveryApprovals(status: WorkflowStatus): HistoryEvent[] {
  return status.history.filter((h) => h.event === "recovery_approved");
}

export function recoveryExecutions(status: WorkflowStatus): ExecutionPayload[] {
  return payloads<ExecutionPayload>(status.history, ["recovery_execution"]);
}

export function recoveryCycles(status: WorkflowStatus): HistoryEvent[] {
  return status.history.filter((h) => h.event === "recovery_cycle_failed");
}

export function transitions(status: WorkflowStatus): HistoryEvent[] {
  return status.history.filter((h) => h.event === "state_transition");
}
