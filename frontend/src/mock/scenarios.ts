/**
 * Static mock WorkflowStatus payloads for UI development only.
 * Same shape as the real backend (see backend/api/app.py serialize_status).
 * No workflow logic here — components just render the given object.
 */
import type { ScenarioName, WorkflowStatus } from "../types";

function base(taskId: string, status: WorkflowStatus["status"]) {
  return { task_id: taskId, status };
}

export const mockNormal: WorkflowStatus = {
  ...base("mock-normal-001", "VERIFIED"),
  current_step: "mock-normal-001-step-1",
  attempt: 1,
  history: [
    { event: "task_received", task_type: "service_recovery", parameters: { service_name: "demo-service" } },
    {
      event: "plan_created",
      steps: [{ step_id: "mock-normal-001-step-1", action: "health_check", order: 1 }],
    },
    { event: "state_transition", from: "PLANNED", to: "EXECUTING" },
    { event: "executing", step_id: "mock-normal-001-step-1", action: "health_check", attempt: 1 },
    {
      event: "execution",
      result: {
        task_id: "mock-normal-001",
        step_id: "mock-normal-001-step-1",
        action: "health_check",
        attempt: 1,
        success: true,
        result: { http_status: 200, health_status: "healthy" },
        error: null,
      },
    },
    { event: "state_transition", from: "EXECUTING", to: "VERIFYING" },
    {
      event: "verification",
      result: {
        task_id: "mock-normal-001",
        step_id: "mock-normal-001-step-1",
        passed: true,
        reason: "healthy",
        evidence: { http_status: 200, health_status: "healthy" },
      },
    },
    { event: "state_transition", from: "VERIFYING", to: "VERIFIED" },
    { event: "workflow_verified" },
  ],
  final_result: {
    step_id: "mock-normal-001-step-1",
    action: "health_check",
    execution: { http_status: 200, health_status: "healthy" },
    evidence: { http_status: 200, health_status: "healthy" },
    reason: "healthy",
  },
  error: null,
};

export const mockInjectedFailure: WorkflowStatus = {
  ...base("mock-healed-001", "VERIFIED"),
  current_step: "mock-healed-001-verify-1",
  attempt: 3,
  history: [
    { event: "task_received", task_type: "service_recovery", parameters: { service_name: "demo-service" } },
    {
      event: "plan_created",
      steps: [{ step_id: "mock-healed-001-step-1", action: "health_check", order: 1 }],
    },
    { event: "state_transition", from: "PLANNED", to: "EXECUTING" },
    { event: "executing", step_id: "mock-healed-001-step-1", action: "health_check", attempt: 1 },
    {
      event: "execution",
      result: {
        task_id: "mock-healed-001",
        step_id: "mock-healed-001-step-1",
        action: "health_check",
        attempt: 1,
        success: true,
        result: { http_status: 503, health_status: "unhealthy" },
        error: null,
      },
    },
    { event: "state_transition", from: "EXECUTING", to: "VERIFYING" },
    {
      event: "verification",
      result: {
        task_id: "mock-healed-001",
        step_id: "mock-healed-001-step-1",
        passed: false,
        reason: "service unhealthy",
        evidence: { http_status: 503, health_status: "unhealthy" },
      },
    },
    { event: "state_transition", from: "VERIFYING", to: "RECOVERING" },
    { event: "verification_failed", step_id: "mock-healed-001-step-1", reason: "service unhealthy", recovery_attempts: 0 },
    { event: "recovery_approved", action: "restart_service", step_id: "mock-healed-001-recovery-1", recovery_attempts: 0 },
    { event: "state_transition", from: "RECOVERING", to: "EXECUTING" },
    {
      event: "recovery_execution",
      result: {
        task_id: "mock-healed-001",
        step_id: "mock-healed-001-recovery-1",
        action: "restart_service",
        attempt: 2,
        success: true,
        result: { action: "restart", recovered: true, health_status: "healthy" },
        error: null,
      },
    },
    { event: "fresh_health_check_scheduled", step_id: "mock-healed-001-verify-1" },
    { event: "state_transition", from: "VERIFYING", to: "RECOVERING" },
    { event: "state_transition", from: "RECOVERING", to: "EXECUTING" },
    {
      event: "execution",
      result: {
        task_id: "mock-healed-001",
        step_id: "mock-healed-001-verify-1",
        action: "health_check",
        attempt: 3,
        success: true,
        result: { http_status: 200, health_status: "healthy" },
        error: null,
      },
    },
    { event: "state_transition", from: "EXECUTING", to: "VERIFYING" },
    {
      event: "verification",
      result: {
        task_id: "mock-healed-001",
        step_id: "mock-healed-001-verify-1",
        passed: true,
        reason: "healthy",
        evidence: { http_status: 200, health_status: "healthy" },
      },
    },
    { event: "state_transition", from: "VERIFYING", to: "VERIFIED" },
    { event: "workflow_verified_after_recovery" },
  ],
  final_result: {
    step_id: "mock-healed-001-verify-1",
    action: "health_check",
    execution: { http_status: 200, health_status: "healthy" },
    evidence: { http_status: 200, health_status: "healthy" },
    reason: "healthy",
    recovered_via: "mock-healed-001-recovery-1",
  },
  error: null,
};

export const mockPersistentFailure: WorkflowStatus = {
  ...base("mock-escalated-001", "ESCALATED"),
  current_step: "mock-escalated-001-verify-3",
  attempt: 7,
  history: [
    { event: "task_received", task_type: "service_recovery", parameters: { service_name: "demo-service" } },
    {
      event: "plan_created",
      steps: [{ step_id: "mock-escalated-001-step-1", action: "health_check", order: 1 }],
    },
    { event: "state_transition", from: "PLANNED", to: "EXECUTING" },
    { event: "executing", step_id: "mock-escalated-001-step-1", action: "health_check", attempt: 1 },
    {
      event: "execution",
      result: {
        task_id: "mock-escalated-001",
        step_id: "mock-escalated-001-step-1",
        action: "health_check",
        attempt: 1,
        success: true,
        result: { http_status: 503, health_status: "unhealthy" },
        error: null,
      },
    },
    { event: "state_transition", from: "EXECUTING", to: "VERIFYING" },
    {
      event: "verification",
      result: {
        task_id: "mock-escalated-001",
        step_id: "mock-escalated-001-step-1",
        passed: false,
        reason: "service unhealthy",
        evidence: { http_status: 503, health_status: "unhealthy" },
      },
    },
    { event: "state_transition", from: "VERIFYING", to: "RECOVERING" },
    { event: "verification_failed", step_id: "mock-escalated-001-step-1", reason: "service unhealthy", recovery_attempts: 0 },
    { event: "recovery_approved", action: "restart_service", step_id: "mock-escalated-001-recovery-1", recovery_attempts: 0 },
    {
      event: "recovery_execution",
      result: {
        task_id: "mock-escalated-001",
        step_id: "mock-escalated-001-recovery-1",
        action: "restart_service",
        attempt: 2,
        success: true,
        result: { action: "restart", recovered: false, health_status: "unhealthy" },
        error: null,
      },
    },
    { event: "fresh_health_check_scheduled", step_id: "mock-escalated-001-verify-1" },
    {
      event: "execution",
      result: {
        task_id: "mock-escalated-001",
        step_id: "mock-escalated-001-verify-1",
        action: "health_check",
        attempt: 3,
        success: true,
        result: { http_status: 503, health_status: "unhealthy" },
        error: null,
      },
    },
    { event: "recovery_cycle_failed", recovery_attempts: 1, max_attempts: 3 },
    { event: "recovery_cycle_failed", recovery_attempts: 2, max_attempts: 3 },
    { event: "recovery_cycle_failed", recovery_attempts: 3, max_attempts: 3 },
    { event: "state_transition", from: "RECOVERING", to: "ESCALATED" },
    { event: "workflow_escalated", error: "Recovery exhausted after 3 attempt(s); escalating." },
  ],
  final_result: null,
  error: "Recovery exhausted after 3 attempt(s); escalating.",
};

export const mockScenarios: Record<ScenarioName, WorkflowStatus> = {
  normal: mockNormal,
  "injected-failure": mockInjectedFailure,
  "persistent-failure": mockPersistentFailure,
};
