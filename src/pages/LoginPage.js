import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { A } from "./authStyles";

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState(null);
  const [busy, setBusy]         = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const result = await login(email.trim(), password);
    setBusy(false);
    if (result.ok) {
      navigate("/");
    } else {
      setError(result.error || "Login failed");
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
        <div style={A.pageTitle}>SIGN IN</div>

        <label style={A.label}>EMAIL</label>
        <input
          type="email"
          autoComplete="email"
          autoFocus
          value={email}
          onChange={e => setEmail(e.target.value)}
          style={A.input}
          required
        />

        <label style={A.label}>PASSWORD</label>
        <input
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          style={A.input}
          required
        />

        {error && <div style={A.error}>{error}</div>}

        <button
          type="submit"
          disabled={busy}
          style={{ ...A.button, ...(busy ? A.buttonDisabled : {}) }}
        >
          {busy ? "SIGNING IN…" : "SIGN IN"}
        </button>

        <div style={A.linkRow}>
          <Link to="/forgot-password" style={A.link}>Forgot password?</Link>
          <span>
            Don't have an account?{" "}
            <Link to="/register" style={A.link}>Register</Link>
          </span>
        </div>
      </form>
    </div>
  );
}
