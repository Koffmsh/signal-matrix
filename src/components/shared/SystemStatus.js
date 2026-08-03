import React, { useEffect, useState, useCallback } from "react";
import { apiFetch } from "../../services/api";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";
const POLL_INTERVAL_MS = 60_000;

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

export default function SystemStatus({ onRefresh, onNewSignals }) {
  const [sys, setSys] = useState(null);

  const fetchStatus = useCallback(() => {
    return apiFetch(`/api/system/status`)
      .then((r) => (r && r.ok ? r.json() : null))
      .then((d) => {
        if (d) setSys(d);
        return d;
      })
      .catch(() => null);
  }, []);

  useEffect(() => {
    let active = true;
    fetchStatus();
    const id = setInterval(() => {
      if (active) fetchStatus();
    }, POLL_INTERVAL_MS);
    return () => { active = false; clearInterval(id); };
  }, [fetchStatus]);

  useEffect(() => {
    if (sys?.last_signals_calculated_at && onNewSignals) {
      onNewSignals(sys.last_signals_calculated_at);
    }
  }, [sys?.last_signals_calculated_at, onNewSignals]);

  if (!sys) return null;

  if (sys.connection && sys.data) {
    return (
      <>
        {sys.db_env && (
          <div
            title={sys.db_env.tooltip}
            style={{
              color: sys.db_env.color,
              border: `1px solid ${sys.db_env.color}`,
              background: sys.db_env.color + "22",
              borderRadius: 4,
              padding: "1px 7px",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: 0.5,
            }}
          >
            DB: {sys.db_env.label}
          </div>
        )}
        <Dot
          label="CONNECTION"
          axis={sys.connection}
          onClick={() => { window.location.href = `${API_BASE}/api/auth/schwab/login`; }}
        />
        <Dot label="DATA" axis={sys.data} onClick={onRefresh} />
      </>
    );
  }

  return <Dot label="STATUS" axis={sys.status} />;
}
