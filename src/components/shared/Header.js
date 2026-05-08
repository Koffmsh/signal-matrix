import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export default function Header() {
  const { user, logout } = useAuth();
  const navigate         = useNavigate();
  const [open, setOpen]  = useState(false);
  const wrapRef          = useRef(null);

  // Click outside to close
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const handleLogout = async () => {
    setOpen(false);
    await logout();
    navigate("/login");
  };

  const handleAdmin = () => {
    setOpen(false);
    navigate("/admin");
  };

  const initials = computeInitials(user);

  return (
    <div style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      height: 48,
      background: "#060e1a",
      borderBottom: "1px solid #1a2a3a",
      display: "flex",
      alignItems: "center",
      padding: "0 20px",
      zIndex: 200,
      boxSizing: "border-box",
    }}>
      {/* Brand */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, userSelect: "none" }}>
        <div style={{
          width: 4,
          height: 20,
          background: "linear-gradient(180deg, #00e5a0, #0077ff)",
          borderRadius: 2,
          flexShrink: 0,
        }} />
        <span style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: "0.2em",
          color: "#e8f4ff",
          whiteSpace: "nowrap",
        }}>
          SIGNAL MATRIX
        </span>
        <span style={{
          fontSize: 9,
          fontWeight: 500,
          letterSpacing: "0.1em",
          color: "#445566",
          marginLeft: 4,
          whiteSpace: "nowrap",
        }}>
          MULTI-TIMEFRAME · PROBABILISTIC
        </span>
      </div>

      {/* Right side — user menu */}
      <div ref={wrapRef} style={{ marginLeft: "auto", position: "relative" }}>
        <div
          onClick={() => setOpen(o => !o)}
          title={user ? `${user.display_name || user.email} (${user.role})` : "Account"}
          style={{
            width: 30,
            height: 30,
            borderRadius: "50%",
            background: open ? "#13243d" : "#0d1f33",
            border: `1px solid ${open ? "#00e5a0" : "#1a2a3a"}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            color: "#c8d8e8",
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.05em",
            userSelect: "none",
            transition: "border-color 0.15s, background 0.15s",
          }}
        >
          {user ? initials : (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="4.5" r="2.5" stroke="#8899aa" strokeWidth="1.2" />
              <path d="M1.5 13c0-2.8 2.46-4.5 5.5-4.5s5.5 1.7 5.5 4.5" stroke="#8899aa" strokeWidth="1.2" strokeLinecap="round" />
            </svg>
          )}
        </div>

        {open && user && (
          <div style={{
            position:     "absolute",
            top:          38,
            right:        0,
            minWidth:     250,
            background:   "#0a1422",
            border:       "1px solid #1a3050",
            borderRadius: 6,
            boxShadow:    "0 12px 32px rgba(0,0,0,0.55)",
            padding:      "6px 0",
            zIndex:       300,
            fontFamily:   "'IBM Plex Mono', 'Courier New', monospace",
          }}>
            {/* "Signed in as" header */}
            <div style={{ padding: "12px 16px 10px" }}>
              <div style={{
                fontSize: 9,
                color: "#8899aa",
                letterSpacing: "0.15em",
                marginBottom: 4,
              }}>
                SIGNED IN AS
              </div>
              <div style={{
                fontSize: 12,
                color: "#e8f4ff",
                fontWeight: 600,
                wordBreak: "break-all",
                lineHeight: 1.3,
                marginBottom: 6,
              }}>
                {user.email}
              </div>
              <div style={{
                display: "inline-block",
                fontSize: 8,
                letterSpacing: "0.18em",
                padding: "2px 8px",
                borderRadius: 2,
                background: user.role === "admin" ? "rgba(0, 229, 160, 0.12)" : "rgba(136, 153, 170, 0.12)",
                color:      user.role === "admin" ? "#00e5a0" : "#8899aa",
                border:     `1px solid ${user.role === "admin" ? "#00e5a0" : "#445566"}`,
              }}>
                {user.role.toUpperCase()}
              </div>
            </div>

            <div style={{ height: 1, background: "#14233a", margin: "4px 0" }} />

            {/* Menu items */}
            {user.role === "admin" && (
              <MenuItem onClick={handleAdmin} icon={<MenuShield />}>ADMIN PANEL</MenuItem>
            )}
            <MenuItem onClick={handleLogout} icon={<MenuLogout />} danger>SIGN OUT</MenuItem>
          </div>
        )}
      </div>
    </div>
  );
}

function MenuItem({ children, onClick, icon, danger }) {
  const [hover, setHover] = useState(false);
  const color = danger ? "#ff4d6d" : (hover ? "#00e5a0" : "#c8d8e8");
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        padding: "10px 16px",
        fontSize: 11,
        letterSpacing: "0.12em",
        color,
        cursor: "pointer",
        background: hover ? "rgba(0,229,160,0.05)" : "transparent",
        display: "flex",
        alignItems: "center",
        gap: 12,
        userSelect: "none",
        transition: "background 0.1s, color 0.1s",
      }}
    >
      <span style={{ display: "flex", alignItems: "center", width: 16, color }}>{icon}</span>
      {children}
    </div>
  );
}

// Derive 1-2 letter initials. Priority:
//   1. display_name with a space → first letter of first 2 words ("Shannon Koffman" → "SK")
//   2. email local part with `.` or `_` separator → letters of first 2 segments ("shannon.koffman@..." → "SK")
//   3. fallback to first letter of display_name or email
function computeInitials(user) {
  if (!user) return "?";
  const name = (user.display_name || "").trim();
  if (name.includes(" ")) {
    const parts = name.split(/\s+/).filter(Boolean);
    return (parts[0][0] + (parts[1]?.[0] || "")).toUpperCase();
  }
  const local = (user.email || "").split("@")[0];
  const segs  = local.split(/[._-]/).filter(Boolean);
  if (segs.length >= 2) {
    return (segs[0][0] + segs[1][0]).toUpperCase();
  }
  return (name || local || "?").charAt(0).toUpperCase();
}

function MenuShield() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M8 1.5 2.5 4v4c0 3.3 2.4 6.2 5.5 7 3.1-.8 5.5-3.7 5.5-7V4L8 1.5Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" fill="none" />
      <path d="m5.5 8 1.7 1.8L10.5 6.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  );
}

function MenuLogout() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M6.5 2.5h-3a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <path d="M10 5.5 13 8l-3 2.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <line x1="13" y1="8" x2="6.5" y2="8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
