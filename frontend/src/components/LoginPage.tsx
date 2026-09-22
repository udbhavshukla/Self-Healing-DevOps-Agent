import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";

const FLOW = ["Incident", "AI Analysis", "Safety Gate", "Recovery", "Verification"];

export default function LoginPage() {
  const { login } = useAuth();
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    // Small async beat so the loading state is perceptible; auth itself
    // is synchronous local validation (prototype only).
    setTimeout(() => {
      const failure = login(user, password, remember);
      if (failure) setError(failure);
      setBusy(false);
    }, 350);
  };

  return (
    <div className="login-page">
      <div className="login-bg" aria-hidden="true">
        <span className="node n1" />
        <span className="node n2" />
        <span className="node n3" />
        <span className="node n4" />
        <span className="node n5" />
        <span className="grid-overlay" />
      </div>

      <div className="login-split">
        <section className="login-brand">
          <div className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 48 48" width="44" height="44">
              <circle cx="24" cy="24" r="21" fill="none" stroke="#22d3ee" strokeWidth="2.5" />
              <path
                d="M24 13v11l8 5"
                fill="none"
                stroke="#22d3ee"
                strokeWidth="2.5"
                strokeLinecap="round"
              />
              <circle cx="24" cy="24" r="3.5" fill="#22d3ee" />
            </svg>
          </div>
          <p className="brand-eyebrow">Self-Healing DevOps Agent</p>
          <h1>
            Autonomous incident response
            <span> with controlled AI.</span>
          </h1>
          <p className="brand-sub">
            The agent detects unhealthy services, proposes a recovery under a
            strict allowlist, executes it deterministically, and proves the
            outcome with independent verification and evidence.
          </p>
          <ol className="brand-flow">
            {FLOW.map((step, i) => (
              <li key={step}>
                <span className="flow-dot">{i + 1}</span>
                <span>{step}</span>
                {i < FLOW.length - 1 && <span className="flow-arrow">↓</span>}
              </li>
            ))}
          </ol>
        </section>

        <section className="login-card-wrap">
          <form className="login-card" onSubmit={submit} noValidate>
            <div className="brand-mark small" aria-hidden="true">
              <svg viewBox="0 0 48 48" width="32" height="32">
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
            </div>
            <h2>Welcome back</h2>
            <p className="muted">Sign in to open the operations console.</p>

            <label className="field">
              <span>Email or username</span>
              <input
                type="text"
                autoComplete="username"
                placeholder="sre-operator@example.com"
                value={user}
                onChange={(e) => setUser(e.target.value)}
                disabled={busy}
              />
            </label>

            <label className="field">
              <span>Password</span>
              <div className="password-row">
                <input
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={busy}
                />
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-pressed={showPassword}
                  disabled={busy}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
            </label>

            <label className="remember">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                disabled={busy}
              />
              Remember me
            </label>

            {error !== null && (
              <p className="error-text" role="alert">
                {error}
              </p>
            )}

            <button type="submit" className="start-button login-submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign In"}
            </button>

            <p className="muted proto-note">
              Prototype environment — demo sign-in only, no real authentication.
            </p>
          </form>
        </section>
      </div>
    </div>
  );
}
