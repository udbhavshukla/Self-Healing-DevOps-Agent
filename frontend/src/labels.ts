/**
 * Pure presentation helpers. UI shows human-readable labels while the
 * original technical values (actions, event names, ids) are preserved
 * internally and passed through untouched.
 */
import type {
  ExecutionPayload,
  HistoryEvent,
  WorkflowStatus,
} from "./types";

const ACTION_LABELS: Record<string, string> = {
  health_check: "Health Check",
  restart_service: "Restart Service",
  restart: "Restart Service",
  inject_failure: "Inject Failure",
  deploy: "Deploy",
};

const EVENT_LABELS: Record<string, string> = {
  task_received: "Task Received",
  plan_created: "Plan Created",
  planning_failed: "Planning Failed",
  executing: "Execute",
  execution: "Execute",
  verification: "Verify",
  step_passed: "Step Passed",
  verification_failed: "Verify Failed",
  recovery_approved: "Recovery Approved",
  recovery_execution: "Recover",
  recovery_verification: "Verify Recovery",
  fresh_health_check_scheduled: "Verify Again",
  recovery_cycle_failed: "Recovery Cycle Failed",
  workflow_verified: "Verified",
  workflow_verified_after_recovery: "Verified After Recovery",
  workflow_escalated: "Escalated",
  workflow_failed: "Failed",
  internal_error: "Internal Error",
  state_transition: "State Change",
  executor_error: "Executor Error",
  verifier_error: "Verifier Error",
  unapproved_action: "Unapproved Action",
  executor_identity_mismatch: "Identity Mismatch",
  inconsistent_verification: "Inconsistent Verification",
};

export function humanize(value: string): string {
  return value
    .split("_")
    .map((word) =>
      word.length > 0 ? word[0].toUpperCase() + word.slice(1) : word
    )
    .join(" ");
}

/** health_check -> "Health Check". Unknown actions are humanized, never hidden. */
export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? humanize(action);
}

/** task_received -> "Task Received". Unknown events are humanized, never hidden. */
export function eventLabel(event: string): string {
  return EVENT_LABELS[event] ?? humanize(event);
}

/** healthy -> "Healthy", unhealthy -> "Unhealthy". */
export function healthDisplay(value: unknown): string {
  if (value === "healthy") return "Healthy";
  if (value === "unhealthy") return "Unhealthy";
  if (value === null || value === undefined) return "—";
  return String(value);
}

/** Normalizes a recovered flag for display. */
export function recoveredDisplay(
  value: unknown
): "Recovered" | "Failed" | "Unknown" {
  if (value === true) return "Recovered";
  if (value === false) return "Failed";
  return "Unknown";
}

export interface RecoveryAttemptView {
  index: number;
  action: string;
  stepId: string;
  result: "Recovered" | "Failed" | "Unknown";
  health: string;
}

/** Pairs each approved recovery action with its execution result. */
export function buildRecoveryAttempts(
  approvals: HistoryEvent[],
  executions: ExecutionPayload[]
): RecoveryAttemptView[] {
  return approvals.map((approval, i) => {
    const exec = executions[i];
    const action = String(
      approval["action"] ?? exec?.action ?? "restart_service"
    );
    return {
      index: i + 1,
      action: actionLabel(action),
      stepId: String(approval["step_id"] ?? exec?.step_id ?? "—"),
      result: recoveredDisplay(exec?.result?.["recovered"]),
      health: healthDisplay(exec?.result?.["health_status"]),
    };
  });
}

export type FinalSummary =
  | {
      kind: "verified";
      title: string;
      subtitle: string;
      recoveredVia: string | null;
    }
  | { kind: "terminal"; title: string; subtitle: string }
  | { kind: "pending"; title: string; subtitle: string };

/** Headline summary for the Final Result panel. Never assumes details exist. */
export function finalSummary(status: WorkflowStatus): FinalSummary {
  if (status.status === "VERIFIED" && status.final_result !== null) {
    const reason = status.final_result.reason;
    return {
      kind: "verified",
      title: "Verified",
      subtitle:
        reason === "healthy" || reason === null || reason === undefined
          ? "Service healthy"
          : reason,
      recoveredVia: status.final_result.recovered_via ?? null,
    };
  }
  if (status.status === "FAILED" || status.status === "ESCALATED") {
    return {
      kind: "terminal",
      title: status.status === "ESCALATED" ? "Escalated" : "Failed",
      subtitle: status.error ?? "Workflow did not verify.",
    };
  }
  return {
    kind: "pending",
    title: "In progress",
    subtitle: "Workflow has not reached a terminal state yet.",
  };
}
