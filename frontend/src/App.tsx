import { useCallback, useEffect, useState } from "react";
import {
  checkHealth,
  getOfflineStatus,
  setConnectivity,
  startWorkflow,
  triggerSync,
} from "./api/client";
import { useAuth } from "./auth";
import AIAnalysisPanel from "./components/AIAnalysisPanel";
import ArchitectureDiagram from "./components/ArchitectureDiagram";
import EvidencePanel from "./components/EvidencePanel";
import FinalResult from "./components/FinalResult";
import HealthPanel from "./components/HealthPanel";
import Hero from "./components/Hero";
import LoginPage from "./components/LoginPage";
import OfflinePanel from "./components/OfflinePanel";
import RecoveryHistory from "./components/RecoveryHistory";
import SafetyBoundary from "./components/SafetyBoundary";
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

const NAV = [
  { href: "#overview", label: "Overview" },
  { href: "#incident", label: "Incident Response" },
  { href: "#recovery", label: "Recovery" },
  { href: "#verification", label: "Verification" },
  { href: "#evidence", label: "Evidence" },
  { href: "#offline", label: "Offline Resilience" },
  { href: "#activity", label: "System Activity" },
];

function Logo({ size = 30 }: { size?: number }) {
  return (
    <span className="logo-mark" aria-hidden="true">
      <svg viewBox="0 0 48 48" width={size} height={size}>
        <circle cx="24" cy="24" r="21" fill="none" stroke="#22d3ee" strokeWidth="3" />
        <path
          d="M24 13v11l8 5"
          fill="none"
          stroke="#22d3ee"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <circle cx="24" cy="24" r="3.5" fill="#22d3ee" />
      </svg>
    </span>
  );
}

export default function App() {
  const { session, logout } = useAuth();
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
  const [navOpen, setNavOpen] = useState(false);

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
    if (!session) return;
    refreshOffline();
    const timer = setInterval(refreshOffline, 10000);
    return () => clearInterval(timer);
  }, [refreshOffline, session]);

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

  if (!session) {
    return <LoginPage />;
  }

  const charCount = incident.length;

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <button
            type="button"
            className="nav-toggle"
            onClick={() => setNavOpen((v) => !v)}
            aria-expanded={navOpen}
            aria-label="Toggle navigation"
          >
            ☰
          </button>
          <Logo />
          <div>
            <h1>Self-Healing DevOps Agent</h1>
            <p className="muted">Operations Console</p>
          </div>
        </div>
        <div className="sys-status">
          <span className="status-chip">
            <span className="muted">Backend</span>{" "}
            <strong className={backend === "online" ? "pass" : "fail"}>
              {backend === "unknown" ? "…" : backend.toUpperCase()}
            </strong>
          </span>
          <span className="status-chip">
            <span className="muted">Connectivity</span>{" "}
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
          </span>
          <span className="user-chip" title={`Signed in ${session.loginAt}`}>
            {session.user}
          </span>
          <button type="button" className="ghost-button" onClick={logout}>
            Logout
          </button>
        </div>
      </header>

      <div className="shell">
        <nav className={navOpen ? "sidebar open" : "sidebar"} aria-label="Sections">
          {NAV.map((item) => (
            <a key={item.href} href={item.href} onClick={() => setNavOpen(false)}>
              {item.label}
            </a>
          ))}
        </nav>

        <main className="main">
          <Hero displayed={displayed} offline={offline} incident={incident} />

          <section id="incident" className="panel controls">
            <h2>Create Incident</h2>
            <p className="muted">
              Describe the production issue in natural language.
            </p>
            <textarea
              className="incident-input"
              rows={3}
              placeholder="Example: The payment service is returning HTTP 503 errors after the latest deployment."
              value={incident}
              onChange={(e) => setIncident(e.target.value)}
              maxLength={1000}
            />
            <div className="incident-meta">
              <span className="muted">{charCount}/1000</span>
            </div>
            <div className="start-row">
              <button
                type="button"
                className="start-button"
                onClick={handleIncidentStart}
                disabled={running || incident.trim() === ""}
              >
                {running ? "Analyzing incident…" : "Analyze & Start Workflow"}
              </button>
            </div>
          </section>

          <section className="panel controls">
            <h2>Demo scenario</h2>
            <p className="muted">
              Deterministic demo cases. Data source controls whether panels
              below show mock or live results.
            </p>
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
              <SafetyBoundary />
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
              <ArchitectureDiagram />
              <WorkflowTimeline history={displayed.history} />
            </>
          )}
        </main>
      </div>
    </div>
  );
}
