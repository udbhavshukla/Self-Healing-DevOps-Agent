import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export interface Session {
  user: string;
  loginAt: string;
  remember: boolean;
}

interface AuthContextValue {
  session: Session | null;
  login: (user: string, password: string, remember: boolean) => string | null;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const SESSION_KEY = "shda.session";
const REMEMBER_KEY = "shda.remember";

function loadSession(): Session | null {
  try {
    const raw =
      sessionStorage.getItem(SESSION_KEY) ?? localStorage.getItem(REMEMBER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Session;
    if (typeof parsed.user !== "string" || parsed.user === "") return null;
    return parsed;
  } catch {
    return null;
  }
}

function looksValidUser(user: string): boolean {
  const trimmed = user.trim();
  if (trimmed.length < 3) return false;
  // Accept a plain username or an email-style identifier for the demo.
  if (trimmed.includes("@")) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed);
  }
  return /^[A-Za-z0-9._-]+$/.test(trimmed);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(loadSession);

  const login = useCallback(
    (user: string, password: string, remember: boolean): string | null => {
      const name = user.trim();
      if (name === "" || password === "") {
        return "Enter your email/username and password to continue.";
      }
      if (!looksValidUser(name)) {
        return "Enter a valid username or email address.";
      }
      if (password.length < 4) {
        return "Password must be at least 4 characters for this prototype.";
      }
      // Prototype demo auth only: any valid-looking credential signs in.
      // No credential is sent anywhere; nothing leaves the browser.
      const next: Session = {
        user: name,
        loginAt: new Date().toISOString(),
        remember,
      };
      try {
        sessionStorage.removeItem(SESSION_KEY);
        localStorage.removeItem(REMEMBER_KEY);
        const raw = JSON.stringify(next);
        if (remember) {
          localStorage.setItem(REMEMBER_KEY, raw);
        } else {
          sessionStorage.setItem(SESSION_KEY, raw);
        }
      } catch {
        return "Browser storage is unavailable, so the session cannot persist.";
      }
      setSession(next);
      return null;
    },
    []
  );

  const logout = useCallback(() => {
    try {
      sessionStorage.removeItem(SESSION_KEY);
      localStorage.removeItem(REMEMBER_KEY);
    } catch {
      /* storage already unavailable */
    }
    setSession(null);
  }, []);

  const value = useMemo(
    () => ({ session, login, logout }),
    [session, login, logout]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
