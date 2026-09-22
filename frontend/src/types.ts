/** TypeScript mirrors of backend/workflow/models.py + states.py.
 *  Only fields the backend actually provides. Nullable fields stay nullable.
 */

export type WorkflowState =
  | "PLANNED"
  | "EXECUTING"
  | "VERIFYING"
  | "RECOVERING"
  | "VERIFIED"
  | "FAILED"
  | "ESCALATED";

export interface HistoryEvent {
  event: string;
  [key: string]: unknown;
}

export interface ExecutionPayload {
  task_id: string;
  step_id: string;
  action: string;
  attempt: number;
  success: boolean;
  result: Record<string, unknown>;
  error: string | null;
}

export interface VerificationPayload {
  task_id: string;
  step_id: string;
  passed: boolean;
  reason: string | null;
  evidence: Record<string, unknown>;
}

export interface FinalResult {
  step_id: string;
  action: string;
  execution: Record<string, unknown>;
  evidence: Record<string, unknown>;
  reason: string | null;
  recovered_via?: string;
}

export interface WorkflowStatus {
  task_id: string;
  status: WorkflowState;
  current_step: string | null;
  attempt: number;
  history: HistoryEvent[];
  final_result: FinalResult | null;
  error: string | null;
}

export type ScenarioName = "normal" | "injected-failure" | "persistent-failure";

export interface StartWorkflowRequest {
  task_id?: string;
  task_type?: string;
  service_name?: string;
  scenario: ScenarioName;
}
