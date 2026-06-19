import React, { useEffect, useState } from "react";
import { apiFetch } from "../../services/api";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

/**
 * Header system-status indicators. Single source of truth: GET /api/system/status.
 *
 *   Admin → CONNECTION (Schwab auth) + DATA (source · freshness · run · integrity)
 *   User  → STATUS (plain-language roll-up)
 *
 * The backend decides which axes to return based on the caller's role and computes
 * every color/tooltip/clickable, so this component just renders dots.
 *
 * Props:
 *   onRefresh — called when an admin clicks a clickable (red) DATA dot → REFRESH DATA.
 */
function Dot({ label, axis, onClick }) {
  if (!axis) return null;
  const clickable = axis.clickable && onClick;
  return (
    <div
      title={axis.tooltip}
      onClick={clickable ? onClick : undefined}
      style={{ color: axis.color, cursor: clickable ? "pointer" : "default" }}
    >
      ● {label}
    </div>
  );
}

export default function SystemStatus({ onRefresh }) {
  const [sys, setSys] = useState(null);

  useEffect(() => {
    let active = true;
    apiFetch(`/api/system/status`)
      .then((r) => (r && r.ok ? r.json() : null))
      .then((d) => { if (active && d) setSys(d); })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  if (!sys) return null;

  // Admin view — backend included the detailed axes.
  if (sys.connection && sys.data) {
    return (
      <>
        <Dot
          label="CONNECTION"
          axis={sys.connection}
          onClick={() => { window.location.href = `${API_BASE}/api/auth/schwab/login`; }}
        />
        <Dot label="DATA" axis={sys.data} onClick={onRefresh} />
      </>
    );
  }

  // Regular user — roll-up only.
  return <Dot label="STATUS" axis={sys.status} />;
}
