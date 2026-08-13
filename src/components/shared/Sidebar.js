import { useState, useEffect, useRef } from "react";
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
      <circle cx="8" cy="8" r="6.5" stroke={color} strokeWidth="1.2" fill="none" opacity="0.4" />
      <path d="M8 8 L8 1.5 A6.5 6.5 0 0 1 13.6 4.75 Z" fill={color} opacity="0.9" />
      <path d="M8 8 L13.6 4.75 A6.5 6.5 0 0 1 13.6 11.25 Z" fill={color} opacity="0.5" />
      <path d="M8 8 L13.6 11.25 A6.5 6.5 0 0 1 2.4 11.25 Z" fill={color} opacity="0.7" />
      <path d="M8 8 L2.4 11.25 A6.5 6.5 0 0 1 8 1.5 Z" fill={color} opacity="0.35" />
    </svg>
  );
}

function SecurityIcon({ color }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="3" width="12" height="10" rx="1.5" stroke={color} strokeWidth="1.2" fill="none" />
      <polyline points="3,8 6,5 9,9 12,4 14,6" stroke={color} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <line x1="2" y1="13" x2="14" y2="13" stroke={color} strokeWidth="1" opacity="0.4" />
    </svg>
  );
}

function MacroIcon({ color }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M2,13 L2,3 L8,8 L14,3 L14,13" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <line x1="1" y1="15" x2="15" y2="15" stroke={color} strokeWidth="1" opacity="0.4" />
    </svg>
  );
}

function ChevronIcon({ color, open }) {
  return (
    <svg
      width="8" height="8" viewBox="0 0 8 8" fill="none"
      style={{
        transition: "transform 150ms ease",
        transform: open ? "rotate(90deg)" : "rotate(0deg)",
      }}
    >
      <polyline points="2,1 6,4 2,7" stroke={color} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" fill="none" />
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
    label: "SECURITY",
    path: "/security",
    exact: false,
    icon: (color) => <SecurityIcon color={color} />,
  },
  {
    label: "VOL",
    path: "/vol",
    exact: false,
    icon: (color) => <VolIcon color={color} />,
    children: [
      { label: "SPX VOL",   path: "/vol",       exact: true },
      { label: "MACRO VOL", path: "/vol/macro",  exact: true },
      { label: "BOND VOL",  path: "/vol/bond",   exact: true },
      { label: "HY CREDIT", path: "/vol/hy-credit", exact: true },
    ],
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
  {
    label: "MACRO",
    path: "/macro",
    exact: false,
    icon: (color) => <MacroIcon color={color} />,
    children: [
      { label: "YIELD CURVE", path: "/macro/yield-curve", exact: true },
      { label: "KEY CORRELATIONS", path: "/macro/correlations", exact: true },
    ],
  },
];

// Collect all parent paths that have children for generic expand/collapse
const _PARENTS_WITH_CHILDREN = NAV_ITEMS.filter(i => i.children).map(i => i.path);

function _initOpenMenus() {
  const p = window.location.pathname;
  const open = {};
  _PARENTS_WITH_CHILDREN.forEach(pp => {
    open[pp] = p.startsWith(pp);
  });
  return open;
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
export default function Sidebar({ locked = false, onToggleLock }) {
  const [hovered, setHovered] = useState(false);
  const [openMenus, setOpenMenus] = useState(_initOpenMenus);
  const location = useLocation();
  const navigate = useNavigate();
  const prevPath = useRef(location.pathname);

  const expanded = locked || hovered;

  // Auto-open parent when navigating INTO one of its child routes
  useEffect(() => {
    const prev = prevPath.current;
    _PARENTS_WITH_CHILDREN.forEach(pp => {
      const wasIn = prev.startsWith(pp);
      const isIn  = location.pathname.startsWith(pp);
      if (isIn && !wasIn) {
        setOpenMenus(m => ({ ...m, [pp]: true }));
      }
    });
    prevPath.current = location.pathname;
  }, [location.pathname]);

  function isActive(item) {
    if (item.exact) return location.pathname === item.path;
    return location.pathname.startsWith(item.path);
  }

  function handleParentClick(item) {
    if (item.children) {
      if (!expanded) {
        navigate(item.children[0].path);
      } else {
        setOpenMenus(m => ({ ...m, [item.path]: !m[item.path] }));
      }
    } else {
      navigate(item.path);
    }
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
          const hasChildren = !!item.children;
          const showChildren = hasChildren && expanded && openMenus[item.path];
          return (
            <div key={item.path}>
              <button
                onClick={() => handleParentClick(item)}
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
                    flex: 1,
                    textAlign: "left",
                  }}
                >
                  {item.label}
                </span>
                {hasChildren && expanded && (
                  <span style={{
                    flexShrink: 0, display: "flex", alignItems: "center",
                    marginRight: 12,
                    opacity: expanded ? 1 : 0,
                    transition: "opacity 150ms ease",
                  }}>
                    <ChevronIcon color={active ? "#00e5a0" : "#8899aa"} open={showChildren} />
                  </span>
                )}
              </button>
              {/* Children */}
              {hasChildren && showChildren && (
                <div style={{
                  overflow: "hidden",
                  transition: "max-height 200ms ease",
                  maxHeight: showChildren ? 200 : 0,
                }}>
                  {item.children.map(child => {
                    const childActive = isActive(child);
                    return (
                      <button
                        key={child.path}
                        onClick={() => navigate(child.path)}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          width: "100%",
                          padding: "7px 0 7px 41px",
                          background: childActive ? "rgba(0,229,160,0.05)" : "transparent",
                          border: "none",
                          borderLeft: childActive ? "3px solid #00e5a0" : "3px solid transparent",
                          cursor: "pointer",
                          boxSizing: "border-box",
                        }}
                      >
                        <span style={{
                          fontSize: 8,
                          fontWeight: 600,
                          letterSpacing: "0.12em",
                          color: childActive ? "#00e5a0" : "#667788",
                          whiteSpace: "nowrap",
                        }}>
                          {child.label}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
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
