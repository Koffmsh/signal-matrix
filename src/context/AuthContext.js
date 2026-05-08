import { createContext, useContext, useState, useEffect } from "react";

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser]               = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  useEffect(() => {
    checkSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // NOTE: this function uses raw fetch, NOT apiFetch.
  // /api/auth/check returns 200 with {authenticated: false} when not logged in,
  // so the apiFetch 401-redirect would never fire here — but if we ever switch
  // to 401, using apiFetch would create an infinite redirect loop. Keep raw fetch.
  const checkSession = async () => {
    try {
      const res  = await fetch(`${API_URL}/api/auth/check`, { credentials: "include" });
      const data = await res.json();
      setUser(data.authenticated ? data : null);
    } catch {
      setUser(null);
    } finally {
      setAuthLoading(false);
    }
  };

  const login = async (email, password) => {
    const res = await fetch(`${API_URL}/api/auth/login`, {
      method:      "POST",
      credentials: "include",
      headers:     { "Content-Type": "application/json" },
      body:        JSON.stringify({ email, password }),
    });
    if (res.ok) {
      const data = await res.json();
      setUser({ email: data.email, role: data.role, display_name: data.display_name });
      return { ok: true };
    }
    let detail = "Login failed";
    try {
      const err = await res.json();
      // FastAPI uses `detail`; slowapi uses `error`. Read both.
      detail = err.detail || err.error || detail;
    } catch { /* ignore */ }
    return { ok: false, error: detail };
  };

  const logout = async () => {
    try {
      await fetch(`${API_URL}/api/auth/logout`, { method: "POST", credentials: "include" });
    } catch { /* ignore */ }
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, authLoading, login, logout, checkSession }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
