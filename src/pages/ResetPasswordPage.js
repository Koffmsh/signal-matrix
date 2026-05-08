import { useState } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { A } from "./authStyles";

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate       = useNavigate();
  const token          = searchParams.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm]   = useState("");
  const [error, setError]       = useState(null);
  const [busy, setBusy]         = useState(false);
  const [done, setDone]         = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);

    if (password.length < 12) {
      setError("Password must be at least 12 characters");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    if (!token) {
      setError("Reset link is missing its token. Please request a new link.");
      return;
    }

    setBusy(true);
    try {
      const res = await fetch(`${API_URL}/api/auth/reset-password`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ token, new_password: password }),
      });
      if (res.ok) {
        setDone(true);
        setTimeout(() => navigate("/login"), 2000);
      } else {
        let detail = "This reset link is invalid or has expired.";
        try {
          const err = await res.json();
          detail = err.detail || err.error || detail;
        } catch { /* ignore */ }
        setError(detail);
      }
    } catch (err) {
      setError("Network error — please try again");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={A.page}>
      <form style={A.card} onSubmit={submit}>
        <div style={A.brand}>
          <div style={A.brandBar} />
          <div>
            <div style={A.brandTitle}>SIGNAL MATRIX</div>
            <div style={A.brandSub}>MULTI-TIMEFRAME · PROBABILISTIC</div>
          </div>
        </div>
        <div style={A.pageTitle}>SET NEW PASSWORD</div>

        {done ? (
          <>
            <div style={A.success}>Password updated. Redirecting to login…</div>
          </>
        ) : (
          <>
            <label style={A.label}>NEW PASSWORD (12+ CHARACTERS)</label>
            <input type="password" autoComplete="new-password" autoFocus value={password}
              onChange={e => setPassword(e.target.value)} style={A.input} required minLength={12} />

            <label style={A.label}>CONFIRM PASSWORD</label>
            <input type="password" autoComplete="new-password" value={confirm}
              onChange={e => setConfirm(e.target.value)} style={A.input} required />

            {error && <div style={A.error}>{error}</div>}

            <button type="submit" disabled={busy}
              style={{ ...A.button, ...(busy ? A.buttonDisabled : {}) }}>
              {busy ? "RESETTING…" : "RESET PASSWORD"}
            </button>

            <div style={A.linkRow}>
              <Link to="/login" style={A.link}>Back to login</Link>
            </div>
          </>
        )}
      </form>
    </div>
  );
}
