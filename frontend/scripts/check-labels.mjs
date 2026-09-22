/**
 * Lightweight checks for frontend/src/labels.ts (presentation logic only).
 * No test framework: compiles labels.ts with esbuild (already a Vite
 * dependency) and runs plain node:assert checks.
 *
 * Run: npm run check:labels  (from frontend/)
 */
import { strict as assert } from "node:assert";
import { unlinkSync } from "node:fs";
import { buildSync } from "esbuild";

const outPath = new URL("./.labels.check.cjs", import.meta.url);
buildSync({
  entryPoints: [new URL("../src/labels.ts", import.meta.url).pathname],
  outfile: outPath.pathname,
  format: "cjs",
  platform: "node",
  logLevel: "silent",
});

let labels;
try {
  labels = await import(outPath.href);
} finally {
  try {
    unlinkSync(outPath);
  } catch {
    /* temp file already gone */
  }
}

// Human-readable action labels (technical values preserved elsewhere).
assert.equal(labels.actionLabel("health_check"), "Health Check");
assert.equal(labels.actionLabel("restart_service"), "Restart Service");
assert.equal(labels.actionLabel("restart"), "Restart Service");
assert.equal(labels.actionLabel("inject_failure"), "Inject Failure");
assert.equal(labels.actionLabel("deploy"), "Deploy");
assert.equal(labels.actionLabel("some_future_action"), "Some Future Action");

// Friendly event labels with original names never hidden (fallback).
assert.equal(labels.eventLabel("task_received"), "Task Received");
assert.equal(labels.eventLabel("fresh_health_check_scheduled"), "Verify Again");
assert.equal(
  labels.eventLabel("workflow_verified_after_recovery"),
  "Verified After Recovery"
);

// VERIFIED summary rendering.
const verified = labels.finalSummary({
  task_id: "t-1",
  status: "VERIFIED",
  current_step: "t-1-step-1",
  attempt: 1,
  history: [],
  final_result: {
    step_id: "t-1-step-1",
    action: "health_check",
    execution: { http_status: 200, health_status: "healthy" },
    evidence: {},
    reason: "healthy",
  },
  error: null,
});
assert.equal(verified.kind, "verified");
assert.equal(verified.title, "Verified");
assert.equal(verified.subtitle, "Service healthy");

// ESCALATED summary rendering (no final_result assumed).
const escalated = labels.finalSummary({
  task_id: "t-2",
  status: "ESCALATED",
  current_step: "t-2-verify-3",
  attempt: 7,
  history: [],
  final_result: null,
  error: "Recovery exhausted after 3 attempt(s); escalating.",
});
assert.equal(escalated.kind, "terminal");
assert.equal(escalated.title, "Escalated");
assert.equal(
  escalated.subtitle,
  "Recovery exhausted after 3 attempt(s); escalating."
);

// Recovery history rendering: attempts pair approvals with executions.
const attempts = labels.buildRecoveryAttempts(
  [
    { event: "recovery_approved", action: "restart_service", step_id: "t-recovery-1" },
    { event: "recovery_approved", action: "restart_service", step_id: "t-recovery-2" },
  ],
  [
    {
      task_id: "t",
      step_id: "t-recovery-1",
      action: "restart_service",
      attempt: 2,
      success: true,
      result: { recovered: false, health_status: "unhealthy" },
      error: null,
    },
    {
      task_id: "t",
      step_id: "t-recovery-2",
      action: "restart_service",
      attempt: 4,
      success: true,
      result: { recovered: true, health_status: "healthy" },
      error: null,
    },
  ]
);
assert.equal(attempts.length, 2);
assert.deepEqual(attempts[0], {
  index: 1,
  action: "Restart Service",
  stepId: "t-recovery-1",
  result: "Failed",
  health: "Unhealthy",
});
assert.deepEqual(attempts[1], {
  index: 2,
  action: "Restart Service",
  stepId: "t-recovery-2",
  result: "Recovered",
  health: "Healthy",
});

console.log("labels checks passed");
