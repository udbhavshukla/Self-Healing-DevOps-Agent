import { useCallback, useEffect, useState } from "react";
import {
  checkHealth,
  getOfflineStatus,
  setConnectivity,
  startWorkflow,
  triggerSync,
} from "./api/client";
import AIAnalysisPanel from "./components/AIAnalysisPanel";
import EvidencePanel from "./components/EvidencePanel";
import FinalResult from "./components/FinalResult";
import HealthPanel from "./components/HealthPanel";
import OfflinePanel from "./components/OfflinePanel";
import RecoveryHistory from "./components/RecoveryHistory";
import StartWorkflowButton from "./components/StartWorkflowButton";
import StepPanel from "./components/StepPanel";
import VerificationPanel from "./components/VerificationPanel";
import WorkflowTimeline from "./components/WorkflowTimeline";
import { mockScenarios } from "./mock/scenarios";
import type {
  OfflineSummary,
  ScenarioName,
  WorkflowStatus,
} from "./types";

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
  const [incident, setIncident] = useState("");
  const [backend, setBackend] = useState<"unknown" | "online" | "offline">(
    "unknown"
  );
  const [offline, setOffline] = useState<OfflineSummary | null>(null);
  const [syncing, setSyncing] = useState(false);

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

  const refreshOffline = useCallback(async () => {
    try {
      const status = await getOfflineStatus();
      setOffline(status);
    } catch {
      /* backend unreachable: keep last known state */
    }
  }, []);

  useEffect(() => {
    refreshOffline();
    const timer = setInterval(refreshOffline, 10000);
    return () => clearInterval(timer);
  }, [refreshOffline]);

  const handleSimulate = useCallback(
    async (online: boolean | null) => {
      try {
        setOffline(await setConnectivity(online));
      } catch (err) {
        setLiveError(err instanceof Error ? err.message : String(err));
      }
    },
    []
  );

  const handleSyncNow = useCallback(async () => {
    setSyncing(true);
    try {
      await triggerSync();
      await refreshOffline();
    } catch (err) {
      setLiveError(err instanceof Error ? err.message : String(err));
    } finally {
      setSyncing(false);
    }
  }, [refreshOffline]);

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
      await refreshOffline();
    } catch (err) {
      setLiveError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }, [scenario, refreshOffline]);

  const handleIncidentStart = useCallback(async () => {
    const text = incident.trim();
    if (text === "") {
      setLiveError("Please describe the incident first.");
      return;
    }
    setRunning(true);
    setLiveError(null);
    try {
      const result = await startWorkflow({
        incident: text,
        task_type: "service_recovery",
        service_name: "demo-service",
      });
      setLiveStatus(result);
      setMode("live");
      await refreshOffline();
    } catch (err) {
      setLiveError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }, [incident, refreshOffline]);

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
          </strong>{" "}
          <span className="muted">Connectivity:</span>{" "}
          <strong
            className={
              offline === null || offline.connectivity === "online"
                ? "pass"
                : "fail"
            }
          >
            {offline === null
              ? "…"
              : offline.connectivity.toUpperCase()}
          </strong>
          {offline !== null && offline.pending > 0 && (
            <span className="muted"> ({offline.pending} pending)</span>
          )}
        </div>
      </header>

      <section className="panel controls">
        <h2>Demo scenario (Level 1)</h2>
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

      <section className="panel controls">
        <h2>User incident (Level 2)</h2>
        <p className="muted">
          Describe a real incident instead of using a demo scenario — e.g.
          “The payment service is returning HTTP 503 after the latest
          deployment.” The AI analyzes it; the deterministic workflow still
          decides and acts.
        </p>
        <textarea
          className="incident-input"
          rows={3}
          placeholder="Describe the incident..."
          value={incident}
          onChange={(e) => setIncident(e.target.value)}
        />
        <div className="start-row">
          <button
            type="button"
            className="start-button"
            onClick={handleIncidentStart}
            disabled={running}
          >
            {running ? "Running…" : "Analyze & Start Workflow"}
          </button>
        </div>
      </section>

      <OfflinePanel
        offline={offline}
        syncing={syncing}
        onSimulate={handleSimulate}
        onSyncNow={handleSyncNow}
      />

      {displayed === null ? (
        <section className="panel">
          <h2>No workflow yet</h2>
          <p className="muted">
            Select the live data source and press Start Workflow.
          </p>
        </section>
      ) : (
        <>
          {displayed.ai_analysis !== undefined &&
            displayed.ai_analysis !== null && (
              <AIAnalysisPanel ai={displayed.ai_analysis} />
            )}
          <div className="grid">
            <StepPanel status={displayed} />
            <HealthPanel status={displayed} />
            <VerificationPanel status={displayed} />
            <RecoveryHistory status={displayed} />
          </div>
          <FinalResult status={displayed} />
          {displayed.evidence !== undefined &&
            displayed.evidence !== null && (
              <EvidencePanel evidence={displayed.evidence} />
            )}
          <WorkflowTimeline history={displayed.history} />
        </>
      )}
    </div>
  );
}
