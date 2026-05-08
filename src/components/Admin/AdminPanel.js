import { Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import TickerList from "./TickerList";
import QuadSetup from "./QuadSetup";
import UserList from "./UserList";
import { useAuth } from "../../context/AuthContext";

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
  { label: "USERS",      path: "users"   },
];

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
            onClick={() => navigate(`/admin/${tab.path}`)}
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
  const navigate    = useNavigate();
  const { logout }  = useAuth();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

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
        <div style={{ display: "flex", gap: "8px" }}>
          <button style={S.backBtn} onClick={() => navigate("/")}>← DASHBOARD</button>
          <button style={S.backBtn} onClick={handleLogout}>LOGOUT</button>
        </div>
      </div>

      {/* Tab nav */}
      <TabNav />

      {/* Tab content */}
      <Routes>
        <Route path="tickers" element={<TickerList />} />
        <Route path="quad"    element={<QuadSetup />} />
        <Route path="users"   element={<UserList />} />
        <Route path="*"       element={<Navigate to="tickers" replace />} />
      </Routes>
    </div>
  );
}
