import { useState } from "react";
import { Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useRef, useEffect } from "react";
import TickerList from "./TickerList";
import QuadSetup from "./QuadSetup";

// ── Styles ────────────────────────────────────────────────────────────────────
const S = {
  page:    { background: "#070d14", minHeight: "100vh", fontFamily: "'IBM Plex Mono', 'Courier New', monospace", color: "#c8d8e8" },
  header:  { background: "linear-gradient(90deg, #0a1628 0%, #0d1f3c 100%)", borderBottom: "1px solid #1a3050", padding: "16px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" },
  badge:   { background: "#0d2a45", border: "1px solid #0077ff", borderRadius: "2px", padding: "2px 10px", fontSize: "10px", color: "#0099ff", letterSpacing: "0.15em", marginLeft: "12px" },
  backBtn: { background: "none", border: "1px solid #1a2e45", borderRadius: "2px", color: "#8899aa", padding: "5px 14px", fontSize: "10px", cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.08em" },
  input:   { background: "#0a1828", border: "1px solid #0077ff", borderRadius: "2px", color: "#e8f4ff", padding: "3px 6px", fontSize: "11px", fontFamily: "inherit", outline: "none", width: "100%" },
  saveBtn: { background: "#001a0e", border: "1px solid #00e5a0", borderRadius: "2px", color: "#00e5a0", padding: "6px 16px", fontSize: "10px", cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.08em" },
};

// ── Tab definitions ───────────────────────────────────────────────────────────
const TABS = [
  { label: "TICKERS",    path: "tickers" },
  { label: "QUAD SETUP", path: "quad"    },
];

// ── Password Gate ─────────────────────────────────────────────────────────────
function PasswordGate({ onSuccess }) {
  const [pw, setPw]       = useState("");
  const [error, setError] = useState(false);
  const inputRef          = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const attempt = () => {
    const envPw = process.env.REACT_APP_ADMIN_PASSWORD;
    if (!envPw)    { setError(true); return; }
    if (pw === envPw) {
      onSuccess();
    } else {
      setError(true);
      setPw("");
      setTimeout(() => setError(false), 1500);
    }
  };

  return (
    <div style={{ ...S.page, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "#0a1422", border: "1px solid #1a3050", borderRadius: "4px", padding: "40px 48px", textAlign: "center", minWidth: "320px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", justifyContent: "center", marginBottom: "28px" }}>
          <div style={{ width: "6px", height: "28px", background: "linear-gradient(180deg, #00e5a0, #0077ff)", borderRadius: "2px" }} />
          <div>
            <div style={{ fontSize: "15px", fontWeight: "700", letterSpacing: "0.15em", color: "#e8f4ff" }}>SIGNAL MATRIX</div>
            <div style={{ fontSize: "9px", color: "#8899aa", letterSpacing: "0.2em" }}>ADMIN ACCESS</div>
          </div>
        </div>
        <input
          ref={inputRef}
          type="password"
          value={pw}
          onChange={e => setPw(e.target.value)}
          onKeyDown={e => e.key === "Enter" && attempt()}
          placeholder="Enter password"
          style={{ ...S.input, marginBottom: "12px", padding: "8px 12px", fontSize: "13px", border: `1px solid ${error ? "#ff4d6d" : "#1a2e45"}`, transition: "border 0.2s" }}
        />
        {error && (
          <div style={{ fontSize: "10px", color: "#ff4d6d", marginBottom: "10px", letterSpacing: "0.05em" }}>
            {!process.env.REACT_APP_ADMIN_PASSWORD ? "REACT_APP_ADMIN_PASSWORD not set in .env" : "Incorrect password"}
          </div>
        )}
        <button onClick={attempt} style={{ ...S.saveBtn, width: "100%", padding: "8px", fontSize: "11px" }}>
          ENTER
        </button>
      </div>
    </div>
  );
}

// ── Tab nav ───────────────────────────────────────────────────────────────────
function TabNav() {
  const location = useLocation();
  const navigate  = useNavigate();
  const active    = TABS.find(t => location.pathname.endsWith(t.path))?.path || "tickers";

  return (
    <div style={{ background: "#080f1a", borderBottom: "1px solid #1a2535", padding: "0 24px", display: "flex", gap: "0" }}>
      {TABS.map(tab => {
        const isActive = active === tab.path;
        return (
          <button
            key={tab.path}
            onClick={() => navigate(tab.path)}
            style={{
              background: "transparent",
              border: "none",
              borderBottom: isActive ? "2px solid #00e5a0" : "2px solid transparent",
              color: isActive ? "#00e5a0" : "#8899aa",
              padding: "10px 20px",
              fontSize: "10px",
              fontWeight: isActive ? "700" : "400",
              letterSpacing: "0.12em",
              cursor: "pointer",
              fontFamily: "inherit",
              transition: "color 0.15s, border-color 0.15s",
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Admin shell ───────────────────────────────────────────────────────────────
export default function AdminPanel() {
  const [authed, setAuthed] = useState(false);
  const navigate             = useNavigate();

  if (!authed) return <PasswordGate onSuccess={() => setAuthed(true)} />;

  return (
    <div style={S.page}>
      {/* Header */}
      <div style={S.header}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <div style={{ width: "6px", height: "32px", background: "linear-gradient(180deg, #00e5a0, #0077ff)", borderRadius: "2px" }} />
          <div>
            <div style={{ display: "flex", alignItems: "center" }}>
              <span style={{ fontSize: "16px", fontWeight: "700", letterSpacing: "0.15em", color: "#e8f4ff" }}>SIGNAL MATRIX</span>
              <span style={S.badge}>ADMIN</span>
            </div>
            <div style={{ fontSize: "9px", color: "#8899aa", letterSpacing: "0.2em" }}>ADMINISTRATION</div>
          </div>
        </div>
        <button style={S.backBtn} onClick={() => navigate("/")}>← DASHBOARD</button>
      </div>

      {/* Tab nav */}
      <TabNav />

      {/* Tab content */}
      <Routes>
        <Route path="tickers" element={<TickerList />} />
        <Route path="quad"    element={<QuadSetup />} />
        <Route path="*"       element={<Navigate to="tickers" replace />} />
      </Routes>
    </div>
  );
}
