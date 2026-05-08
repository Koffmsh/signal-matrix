import { useState, useEffect } from "react";
import { apiFetch } from "../../services/api";
import { useAuth } from "../../context/AuthContext";

const ET_FORMAT = (iso) => {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      timeZone:   "America/New_York",
      month:      "2-digit",
      day:        "2-digit",
      year:       "2-digit",
      hour:       "2-digit",
      minute:     "2-digit",
      hour12:     false,
    }).replace(",", "");
  } catch { return "—"; }
};

const ET_DATE = (iso) => {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      timeZone: "America/New_York",
      month:    "2-digit",
      day:      "2-digit",
      year:     "2-digit",
    });
  } catch { return "—"; }
};

const STATUS_STYLE = {
  active:   { background: "rgba(0, 229, 160, 0.12)",  color: "#00e5a0", border: "1px solid #00e5a0" },
  pending:  { background: "rgba(240, 180, 41, 0.12)", color: "#f0b429", border: "1px solid #f0b429" },
  disabled: { background: "rgba(136, 153, 170, 0.10)", color: "#8899aa", border: "1px solid #445566" },
};

const baseBtn = {
  background: "transparent",
  border:     "1px solid #1a2e45",
  borderRadius: "2px",
  color:      "#c8d8e8",
  padding:    "4px 10px",
  fontSize:   "10px",
  cursor:     "pointer",
  fontFamily: "inherit",
  letterSpacing: "0.08em",
};

export default function UserList() {
  const { user: currentUser } = useAuth();
  const [users, setUsers]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast]     = useState(null);
  const [resetTarget, setResetTarget] = useState(null);
  const [resetPw, setResetPw]         = useState("");
  const [resetErr, setResetErr]       = useState(null);
  const [resetBusy, setResetBusy]     = useState(false);

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(null), 2200); };

  const load = () => {
    apiFetch(`/api/users`)
      .then(r => r ? r.json() : null)
      .then(data => { if (data) setUsers(data); })
      .catch(() => showToast("Failed to load users"))
      .finally(() => setLoading(false));
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const patch = async (userId, payload) => {
    try {
      const res = await apiFetch(`/api/users/${userId}`, { method: "PATCH", body: JSON.stringify(payload) });
      if (!res) return false;
      if (!res.ok) {
        let detail = "Update failed";
        try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
        showToast(detail);
        return false;
      }
      showToast("Saved");
      load();
      return true;
    } catch {
      showToast("Network error");
      return false;
    }
  };

  const submitReset = async () => {
    if (!resetTarget) return;
    setResetErr(null);
    if (resetPw.length < 12) { setResetErr("Password must be at least 12 characters"); return; }
    setResetBusy(true);
    try {
      const res = await apiFetch(`/api/users/${resetTarget.id}/reset-password`, {
        method: "POST",
        body:   JSON.stringify({ new_password: resetPw }),
      });
      if (!res) return;
      if (!res.ok) {
        let detail = "Reset failed";
        try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
        setResetErr(detail);
      } else {
        setResetTarget(null);
        setResetPw("");
        showToast(`Password reset for ${resetTarget.email}`);
      }
    } finally { setResetBusy(false); }
  };

  const isSelf = (u) => currentUser && currentUser.email === u.email;

  return (
    <div style={{ padding: "20px 24px", color: "#c8d8e8", fontFamily: "'IBM Plex Mono', 'Courier New', monospace" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "14px" }}>
        <div style={{ fontSize: "11px", color: "#8899aa", letterSpacing: "0.12em" }}>
          {loading ? "LOADING…" : `${users.length} USERS`}
        </div>
        <button onClick={load} style={baseBtn}>↻ REFRESH</button>
      </div>

      <div style={{ overflow: "auto", border: "1px solid #1a2535", borderRadius: "3px" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}>
          <thead>
            <tr style={{ background: "#080f1a", borderBottom: "1px solid #1a2535" }}>
              {["EMAIL","DISPLAY NAME","ROLE","STATUS","LAST LOGIN","REGISTERED","ACTIONS"].map(h => (
                <th key={h} style={{ textAlign: "left", padding: "8px 12px", color: "#c8d8e8", fontWeight: 600, letterSpacing: "0.08em", fontSize: "10px" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map(u => {
              const self    = isSelf(u);
              const stStyle = STATUS_STYLE[u.status] || STATUS_STYLE.disabled;
              return (
                <tr key={u.id} style={{ borderBottom: "1px solid #0d1a2a" }}>
                  <td style={{ padding: "8px 12px" }}>{u.email} {self && <span style={{ color: "#8899aa", fontSize: "9px" }}>(you)</span>}</td>
                  <td style={{ padding: "8px 12px", color: u.display_name ? "#c8d8e8" : "#445566" }}>{u.display_name || "—"}</td>
                  <td style={{ padding: "8px 12px" }}>
                    <select
                      value={u.role}
                      disabled={self}
                      onChange={e => patch(u.id, { role: e.target.value })}
                      style={{
                        background: "#080e18",
                        color:      self ? "#445566" : "#c8d8e8",
                        border:     "1px solid #1a2e45",
                        borderRadius: "2px",
                        padding:    "3px 6px",
                        fontSize:   "10px",
                        fontFamily: "inherit",
                        outline:    "none",
                        cursor:     self ? "not-allowed" : "pointer",
                      }}
                    >
                      <option value="admin">Admin</option>
                      <option value="viewer">Viewer</option>
                    </select>
                  </td>
                  <td style={{ padding: "8px 12px" }}>
                    <span style={{
                      ...stStyle,
                      borderRadius: "2px",
                      padding: "2px 8px",
                      fontSize: "9px",
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                    }}>{u.status}</span>
                  </td>
                  <td style={{ padding: "8px 12px", color: u.last_login ? "#c8d8e8" : "#445566" }}>{u.last_login ? ET_FORMAT(u.last_login) : "Never"}</td>
                  <td style={{ padding: "8px 12px" }}>{ET_DATE(u.created_at)}</td>
                  <td style={{ padding: "8px 12px" }}>
                    <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                      {(u.status === "pending" || u.status === "disabled") && (
                        <button onClick={() => patch(u.id, { status: "active" })}
                          style={{ ...baseBtn, color: "#00e5a0", borderColor: "#00e5a0" }}>
                          ACTIVATE
                        </button>
                      )}
                      {u.status === "active" && !self && (
                        <button onClick={() => patch(u.id, { status: "disabled" })}
                          style={{ ...baseBtn, color: "#ff4d6d", borderColor: "#ff4d6d" }}>
                          DISABLE
                        </button>
                      )}
                      <button onClick={() => { setResetTarget(u); setResetPw(""); setResetErr(null); }}
                        style={baseBtn}>
                        RESET PW
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {!loading && users.length === 0 && (
              <tr><td colSpan="7" style={{ padding: "40px", textAlign: "center", color: "#8899aa" }}>No users.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {toast && (
        <div style={{
          position: "fixed", bottom: "30px", left: "50%", transform: "translateX(-50%)",
          background: "#0e1424", border: "1px solid #1a3050", borderRadius: "3px",
          color: "#c8d8e8", padding: "10px 18px", fontSize: "11px",
          letterSpacing: "0.08em", zIndex: 1000,
        }}>{toast}</div>
      )}

      {/* Reset password modal */}
      {resetTarget && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1100,
        }} onClick={() => !resetBusy && setResetTarget(null)}>
          <div onClick={e => e.stopPropagation()} style={{
            background: "#0e1424", border: "1px solid #1d2638", borderRadius: "4px",
            padding: "28px 32px", minWidth: "380px", maxWidth: "440px",
          }}>
            <div style={{ fontSize: "11px", color: "#00e5a0", letterSpacing: "0.12em", marginBottom: "12px" }}>
              RESET PASSWORD — {resetTarget.email}
            </div>
            <div style={{ fontSize: "10px", color: "#8899aa", marginBottom: "14px" }}>
              Set a new password directly (12+ characters). The user can log in immediately with this new password. Communicate the new password to them out of band.
            </div>
            <input
              type="password"
              autoFocus
              value={resetPw}
              onChange={e => setResetPw(e.target.value)}
              placeholder="New password (12+ characters)"
              style={{
                width: "100%", boxSizing: "border-box",
                background: "#070d18", border: "1px solid #1d2638", borderRadius: "3px",
                color: "#e8f4ff", padding: "10px 12px", fontSize: "12px",
                fontFamily: "inherit", outline: "none",
              }}
              onKeyDown={e => e.key === "Enter" && submitReset()}
            />
            {resetErr && <div style={{ color: "#ff4d6d", fontSize: "10px", marginTop: "8px" }}>{resetErr}</div>}
            <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end", marginTop: "18px" }}>
              <button onClick={() => setResetTarget(null)} disabled={resetBusy} style={baseBtn}>CANCEL</button>
              <button onClick={submitReset} disabled={resetBusy}
                style={{ ...baseBtn, color: "#00e5a0", borderColor: "#00e5a0", opacity: resetBusy ? 0.5 : 1 }}>
                {resetBusy ? "SAVING…" : "RESET"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
