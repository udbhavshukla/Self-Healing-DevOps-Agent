import { useCallback, useEffect, useState } from "react";
import { checkHealth, startWorkflow } from "./api/client";
import FinalResult from "./components/FinalResult";
import HealthPanel from "./components/HealthPanel";
import RecoveryHistory from "./components/RecoveryHistory";
import StartWorkflowButton from "./components/StartWorkflowButton";
import StepPanel from "./components/StepPanel";
import VerificationPanel from "./components/VerificationPanel";
import WorkflowTimeline from "./components/WorkflowTimeline";
import { mockScenarios } from "./mock/scenarios";
import type { ScenarioName, WorkflowStatus } from "./types";

type Mode = "mock" | "live";

const SCENARIO_LABELS: Record<ScenarioName, string> = {
  normal: "Normal",
  "injected-failure": "Injected Failure",
  "persistent-failure": "Persistent Failure",
};

export default function App() {
  const [scenario, setScenario] = useState<ScenarioName>("normal");
  const [mode, setMode] = useState<Mode>("mock");
  const [liveStatus, setLiveStatus] = useState<WorkflowStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [backend, setBackend] = useState<"unknown" | "online" | "offline">(
    "unknown"
  );

  useEffect(() => {
    let cancelled = false;
    checkHealth()
      .then(() => {
        if (!cancelled) setBackend("online");
      })
      .catch(() => {
        if (!cancelled) setBackend("offline");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const displayed: WorkflowStatus | null =
    mode === "mock" ? mockScenarios[scenario] : liveStatus;

  const handleStart = useCallback(async () => {
    setRunning(true);
    setLiveError(null);
    try {
      const result = await startWorkflow({
        scenario,
        task_type: "service_recovery",
        service_name: "demo-service",
      });
      setLiveStatus(result);
      setMode("live");
    } catch (err) {
      setLiveError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }, [scenario]);

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Self-Healing DevOps Agent</h1>
          <p className="muted">
            Level 1 prototype dashboard — detect, recover, verify.
          </p>
        </div>
        <div className="sys-status">
          <span className="muted">Backend:</span>{" "}
          <strong className={backend === "online" ? "pass" : "fail"}>
            {backend === "unknown" ? "checking…" : backend}
          </strong>
        </div>
      </header>

      <section className="panel controls">
        <h2>Workflow control</h2>
        <div className="control-row">
          <label>
            Scenario{" "}
            <select
              value={scenario}
              onChange={(e) => setScenario(e.target.value as ScenarioName)}
            >
              {(Object.keys(SCENARIO_LABELS) as ScenarioName[]).map((key) => (
                <option key={key} value={key}>
                  {SCENARIO_LABELS[key]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Data source{" "}
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as Mode)}
            >
              <option value="mock">Mock data</option>
              <option value="live">Live API</option>
            </select>
          </label>
        </div>
        <StartWorkflowButton
          onStart={handleStart}
          running={running}
          disabledReason={
            backend === "offline"
              ? "Backend offline — start it with: uvicorn backend.api.app:app --reload"
              : undefined
          }
        />
        {liveError !== null && <p className="error-text">{liveError}</p>}
        {mode === "mock" && (
          <p className="muted">
            Showing static mock data for “{SCENARIO_LABELS[scenario]}”. Press
            Start Workflow to run the real backend and switch to live data.
          </p>
        )}
      </section>

      {displayed === null ? (
        <section className="panel">
          <h2>No workflow yet</h2>
          <p className="muted">
            Select the live data source and press Start Workflow.
          </p>
        </section>
      ) : (
        <>
          <div className="grid">
            <StepPanel status={displayed} />
            <HealthPanel status={displayed} />
            <VerificationPanel status={displayed} />
            <RecoveryHistory status={displayed} />
          </div>
          <FinalResult status={displayed} />
          <WorkflowTimeline history={displayed.history} />
        </>
      )}
    </div>
  );
}
