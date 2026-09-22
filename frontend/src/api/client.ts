/** All HTTP communication lives here. Components never call fetch directly. */
import type { StartWorkflowRequest, WorkflowStatus } from "../types";

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as Record<string, unknown>).detail)
        : response.statusText;
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return (await response.json()) as T;
}

export async function startWorkflow(
  request: StartWorkflowRequest
): Promise<WorkflowStatus> {
  const response = await fetch("/api/workflows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return handle<WorkflowStatus>(response);
}

export async function getWorkflow(taskId: string): Promise<WorkflowStatus> {
  const response = await fetch(
    `/api/workflows/${encodeURIComponent(taskId)}`
  );
  return handle<WorkflowStatus>(response);
}

export async function checkHealth(): Promise<{ status: string }> {
  const response = await fetch("/api/health");
  return handle<{ status: string }>(response);
}
