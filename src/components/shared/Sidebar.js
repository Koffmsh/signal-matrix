import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

const HEADER_HEIGHT = 48;

// ── Inline SVG icons ──────────────────────────────────────────────────────────
function VolIcon({ color }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <polyline points="1,12 4,7 7,9 10,4 13,6 15,3" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <line x1="1" y1="14" x2="15" y2="14" stroke={color} strokeWidth="1" opacity="0.4" />
    </svg>
  );
}

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

function ImpactIcon({ color }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="1" y="9" width="3" height="6" rx="0.5" fill={color} opacity="0.5" />
      <rect x="5" y="6" width="3" height="9" rx="0.5" fill={color} opacity="0.7" />
      <rect x="9" y="3" width="3" height="12" rx="0.5" fill={color} />
      <rect x="13" y="7" width="3" height="8" rx="0.5" fill={color} opacity="0.4" />
    </svg>
  );
}

function SectorIcon({ color }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      {/* Pie wedges representing sectors */}
      <circle cx="8" cy="8" r="6.5" stroke={color} strokeWidth="1.2" fill="none" opacity="0.4" />
      {/* Top wedge */}
      <path d="M8 8 L8 1.5 A6.5 6.5 0 0 1 13.6 4.75 Z" fill={color} opacity="0.9" />
      {/* Right wedge */}
      <path d="M8 8 L13.6 4.75 A6.5 6.5 0 0 1 13.6 11.25 Z" fill={color} opacity="0.5" />
      {/* Bottom wedge */}
      <path d="M8 8 L13.6 11.25 A6.5 6.5 0 0 1 2.4 11.25 Z" fill={color} opacity="0.7" />
      {/* Left wedge */}
      <path d="M8 8 L2.4 11.25 A6.5 6.5 0 0 1 8 1.5 Z" fill={color} opacity="0.35" />
    </svg>
  );
}

function MacroVolIcon({ color }) {
  // Multiple rising vol lines — cross-asset feel
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <polyline points="1,13 4,9 7,11 10,6 13,8 15,5" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <polyline points="1,11 4,7 7,9 10,4 13,6 15,3" stroke={color} strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" fill="none" opacity="0.5" />
    </svg>
  );
}

function LockIcon({ locked, color }) {
  return locked ? (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <rect x="2" y="6" width="10" height="7" rx="1.5" fill={color} opacity="0.9" />
      <path d="M4 6V4.5a3 3 0 0 1 6 0V6" stroke={color} strokeWidth="1.5" strokeLinecap="round" fill="none" />
      <circle cx="7" cy="9.5" r="1" fill="#060e1a" />
    </svg>
  ) : (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <rect x="2" y="6" width="10" height="7" rx="1.5" fill={color} opacity="0.4" />
      <path d="M4 6V4.5a3 3 0 0 1 6 0V3" stroke={color} strokeWidth="1.5" strokeLinecap="round" fill="none" />
      <circle cx="7" cy="9.5" r="1" fill="#060e1a" />
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
  {
    label: "SPX VOL",
    path: "/vol",
    exact: true,
    icon: (color) => <VolIcon color={color} />,
  },
  {
    label: "MACRO VOL",
    path: "/vol/macro",
    exact: true,
    icon: (color) => <MacroVolIcon color={color} />,
  },
  {
    label: "SPX IMPACT",
    path: "/spx-impact",
    exact: true,
    icon: (color) => <ImpactIcon color={color} />,
  },
  {
    label: "SECTOR PERF",
    path: "/sector",
    exact: true,
    icon: (color) => <SectorIcon color={color} />,
  },
];

// ── Sidebar ───────────────────────────────────────────────────────────────────
export default function Sidebar({ locked = false, onToggleLock }) {
  const [hovered, setHovered] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const expanded = locked || hovered;

  function isActive(item) {
    if (item.exact) return location.pathname === item.path;
    return location.pathname.startsWith(item.path);
  }

  return (
    <div
      onMouseEnter={() => !locked && setHovered(true)}
      onMouseLeave={() => !locked && setHovered(false)}
      style={{
        width: expanded ? 180 : 48,
        height: `calc(100vh - ${HEADER_HEIGHT}px)`,
        background: "#060e1a",
        borderRight: "1px solid #1a2a3a",
        display: "flex",
        flexDirection: "column",
        transition: "width 200ms ease",
        overflow: "hidden",
        position: "fixed",
        top: HEADER_HEIGHT,
        left: 0,
        zIndex: 100,
        willChange: "width",
      }}
    >
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
              <span
                style={{
                  fontSize: 9,
                  fontWeight: 700,
                  letterSpacing: "0.15em",
                  color: active ? "#00e5a0" : "#8899aa",
                  whiteSpace: "nowrap",
                  opacity: expanded ? 1 : 0,
                  transition: "opacity 150ms ease",
                  pointerEvents: "none",
                }}
              >
                {item.label}
              </span>
            </button>
          );
        })}
      </div>

      {/* Lock toggle — bottom, no text label, tooltip = action */}
      <div style={{ borderTop: "1px solid #1a2a3a", flexShrink: 0 }}>
        <button
          onClick={onToggleLock}
          title={locked ? "Collapse Sidebar" : "Expand Sidebar"}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "100%",
            padding: "12px 0",
            background: "transparent",
            border: "none",
            cursor: "pointer",
            boxSizing: "border-box",
          }}
        >
          <LockIcon locked={locked} color={locked ? "#00e5a0" : "#8899aa"} />
        </button>
      </div>
    </div>
  );
}
