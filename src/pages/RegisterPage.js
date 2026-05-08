import { useState } from "react";
import { Link } from "react-router-dom";
import { A } from "./authStyles";

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

export default function RegisterPage() {
  const [email, setEmail]               = useState("");
  const [displayName, setDisplayName]   = useState("");
  const [password, setPassword]         = useState("");
  const [confirm, setConfirm]           = useState("");
  const [error, setError]               = useState(null);
  const [busy, setBusy]                 = useState(false);
  const [success, setSuccess]           = useState(false);

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

    setBusy(true);
    try {
      const res = await fetch(`${API_URL}/api/auth/register`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({
          email:        email.trim(),
          display_name: displayName.trim() || null,
          password,
        }),
      });
      if (res.ok) {
        setSuccess(true);
      } else {
        let detail = "Registration failed";
        try {
          const err = await res.json();
          // FastAPI uses `detail`; slowapi uses `error`. Read both.
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

  if (success) {
    return (
      <div style={A.page}>
        <div style={A.card}>
          <div style={A.brand}>
            <div style={A.brandBar} />
            <div>
              <div style={A.brandTitle}>SIGNAL MATRIX</div>
              <div style={A.brandSub}>MULTI-TIMEFRAME · PROBABILISTIC</div>
            </div>
          </div>
          <div style={A.pageTitle}>REGISTRATION RECEIVED</div>
          <div style={A.success}>
            Your account is pending approval. You'll be notified when activated.
          </div>
          <div style={A.linkRow}>
            <Link to="/login" style={A.link}>Back to login</Link>
          </div>
        </div>
      </div>
    );
  }

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
        <div style={A.pageTitle}>CREATE ACCOUNT</div>

        <label style={A.label}>EMAIL</label>
        <input type="email" autoComplete="email" autoFocus value={email}
          onChange={e => setEmail(e.target.value)} style={A.input} required />

        <label style={A.label}>DISPLAY NAME (OPTIONAL)</label>
        <input type="text" autoComplete="name" value={displayName}
          onChange={e => setDisplayName(e.target.value)} style={A.input} />

        <label style={A.label}>PASSWORD (12+ CHARACTERS)</label>
        <input type="password" autoComplete="new-password" value={password}
          onChange={e => setPassword(e.target.value)} style={A.input} required minLength={12} />

        <label style={A.label}>CONFIRM PASSWORD</label>
        <input type="password" autoComplete="new-password" value={confirm}
          onChange={e => setConfirm(e.target.value)} style={A.input} required />

        {error && <div style={A.error}>{error}</div>}

        <button type="submit" disabled={busy}
          style={{ ...A.button, ...(busy ? A.buttonDisabled : {}) }}>
          {busy ? "CREATING…" : "CREATE ACCOUNT"}
        </button>

        <div style={A.linkRow}>
          <span>
            Already have an account?{" "}
            <Link to="/login" style={A.link}>Sign in</Link>
          </span>
        </div>
      </form>
    </div>
  );
}
