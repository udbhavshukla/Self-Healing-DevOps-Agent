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
  /** Level 2: present when the workflow started from a user incident. */
  ai_analysis?: AIAnalysis | null;
  /** Level 2: evidence chain built from real workflow data. */
  evidence?: EvidenceChain | null;
}

export interface AIAnalysis {
  available: boolean;
  source: string;
  diagnosis: string | null;
  recommended_action: string | null;
  reason: string | null;
  confidence: number | null;
  model: string;
  error: string | null;
  rejected_action: string | null;
}

export interface EvidenceCheck {
  step_id: string | null;
  action: string | null;
  attempt: number | null;
  success: boolean | null;
  http_status: number | null;
  health_status: string | null;
}

export interface EvidenceRecovery {
  attempt: number;
  action: string | null;
  step_id: string | null;
  executed: boolean;
  execution_success: boolean | null;
  recovered: boolean | null;
  health_status: string | null;
}

export interface EvidenceVerification {
  step_id: string | null;
  passed: boolean | null;
  reason: string | null;
}

export interface EvidenceChain {
  task_id: string;
  recorded_at: string | null;
  incident: { text: string; service_name: string } | null;
  ai_analysis: AIAnalysis | null;
  before: EvidenceCheck | null;
  recovery: EvidenceRecovery[];
  after: EvidenceCheck | null;
  verification: EvidenceVerification[];
  final: {
    status: string;
    outcome: string;
    error: string | null;
    recovered_via: string | null;
  };
}

export type ScenarioName = "normal" | "injected-failure" | "persistent-failure";

export interface StartWorkflowRequest {
  task_id?: string;
  task_type?: string;
  service_name?: string;
  scenario?: ScenarioName;
  incident?: string;
}

export interface OfflineSummary {
  connectivity: "online" | "offline";
  pending: number;
  synced: number;
  failed: number;
  last_sync: {
    attempted: boolean;
    synced: number;
    failed: number;
    skipped_offline: boolean;
  } | null;
}

export interface SyncResult {
  connectivity: "online" | "offline";
  sync: {
    attempted: boolean;
    synced: number;
    failed: number;
    skipped_offline: boolean;
  };
  pending: number;
  synced: number;
  failed: number;
}
