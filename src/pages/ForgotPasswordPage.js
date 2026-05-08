import { useState } from "react";
import { Link } from "react-router-dom";
import { A } from "./authStyles";

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

export default function ForgotPasswordPage() {
  const [email, setEmail]   = useState("");
  const [busy, setBusy]     = useState(false);
  const [sent, setSent]     = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      // Backend always returns 200 — enumeration-resistant
      await fetch(`${API_URL}/api/auth/forgot-password`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ email: email.trim() }),
      });
    } catch { /* ignore — show success either way */ }
    setBusy(false);
    setSent(true);
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
        <div style={A.pageTitle}>RESET PASSWORD</div>

        {sent ? (
          <>
            <div style={A.success}>
              If that email is registered to an active account, a password reset link has been sent. The link expires in 15 minutes.
            </div>
            <div style={A.linkRow}>
              <Link to="/login" style={A.link}>Back to login</Link>
            </div>
          </>
        ) : (
          <>
            <label style={A.label}>EMAIL</label>
            <input type="email" autoComplete="email" autoFocus value={email}
              onChange={e => setEmail(e.target.value)} style={A.input} required />

            <button type="submit" disabled={busy}
              style={{ ...A.button, ...(busy ? A.buttonDisabled : {}) }}>
              {busy ? "SENDING…" : "SEND RESET LINK"}
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
