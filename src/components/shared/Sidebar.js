import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

// ── Inline SVG icons ──────────────────────────────────────────────────────────
function GridIcon({ color }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="1" y="1" width="6" height="6" rx="1" fill={color} />
      <rect x="9" y="1" width="6" height="6" rx="1" fill={color} />
      <rect x="1" y="9" width="6" height="6" rx="1" fill={color} />
      <rect x="9" y="9" width="6" height="6" rx="1" fill={color} />
    </svg>
  );
}

// ── Nav item definitions ──────────────────────────────────────────────────────
const NAV_ITEMS = [
  {
    label: "SIGNAL MATRIX",
    path: "/",
    exact: true,
    icon: (color) => <GridIcon color={color} />,
  },
  // future dashboards:
  // { label: "QUAD TRACKER", path: "/quad", exact: false, icon: (color) => <QuadIcon color={color} /> },
];

// ── Sidebar ───────────────────────────────────────────────────────────────────
export default function Sidebar() {
  const [expanded, setExpanded] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  function isActive(item) {
    if (item.exact) return location.pathname === item.path;
    return location.pathname.startsWith(item.path);
  }

  return (
    <div
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
      style={{
        width: expanded ? 180 : 48,
        minHeight: "100vh",
        background: "#060e1a",
        borderRight: "1px solid #1a2a3a",
        display: "flex",
        flexDirection: "column",
        transition: "width 200ms ease",
        overflow: "hidden",
        flexShrink: 0,
        position: "sticky",
        top: 0,
      }}
    >
      {/* Logo mark */}
      <div
        style={{
          height: 48,
          display: "flex",
          alignItems: "center",
          paddingLeft: 14,
          borderBottom: "1px solid #1a2a3a",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: 4,
            height: 20,
            background: "linear-gradient(180deg, #00e5a0, #0077ff)",
            borderRadius: 2,
            flexShrink: 0,
          }}
        />
        {expanded && (
          <span
            style={{
              marginLeft: 10,
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: "0.2em",
              color: "#e8f4ff",
              whiteSpace: "nowrap",
            }}
          >
            SIGNAL MATRIX
          </span>
        )}
      </div>

      {/* Nav items */}
      <div style={{ flex: 1, paddingTop: 8 }}>
        {NAV_ITEMS.map((item) => {
          const active = isActive(item);
          const iconColor = active ? "#00e5a0" : "#8899aa";
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              title={expanded ? undefined : item.label}
              style={{
                display: "flex",
                alignItems: "center",
                width: "100%",
                padding: "10px 0 10px 14px",
                background: active ? "rgba(0,229,160,0.07)" : "transparent",
                border: "none",
                borderLeft: active ? "3px solid #00e5a0" : "3px solid transparent",
                cursor: "pointer",
                gap: 10,
                boxSizing: "border-box",
              }}
            >
              <span style={{ flexShrink: 0, display: "flex", alignItems: "center" }}>
                {item.icon(iconColor)}
              </span>
              {expanded && (
                <span
                  style={{
                    fontSize: 9,
                    fontWeight: 700,
                    letterSpacing: "0.15em",
                    color: active ? "#00e5a0" : "#8899aa",
                    whiteSpace: "nowrap",
                  }}
                >
                  {item.label}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Bottom spacer — future: settings gear */}
      <div style={{ height: 48, borderTop: "1px solid #1a2a3a" }} />
    </div>
  );
}
