import { useState, useEffect, useRef } from "react";

const API = "http://localhost:8000/api/tickers";

// ── Field mapping: API (snake_case) ↔ local state (camelCase) ────────────────
const fromApi = (r) => ({
  ticker:       r.ticker        || "",
  description:  r.description   || "",
  assetClass:   r.asset_class   || "Domestic Equities",
  sector:       r.sector        || "",
  tier:         r.tier          ?? 1,
  parentTicker: r.parent_ticker || "",
  active:       r.active        ?? true,
  displayOrder: r.display_order ?? 999,
});

const toApi = (row) => ({
  ticker:        row.ticker,
  description:   row.description,
  asset_class:   row.assetClass,
  sector:        row.sector,
  tier:          Number(row.tier),
  parent_ticker: row.parentTicker || null,
  active:        row.active,
  display_order: Number(row.displayOrder),
});

// ── Constants ─────────────────────────────────────────────────────────────────
const ASSET_CLASSES = [
  "Domestic Equities",
  "Domestic Fixed Income",
  "Commodities",
  "Foreign Exchange",
  "International Equities",
  "Digital Assets",
];

const BLANK_TICKER = {
  ticker: "",
  description: "",
  assetClass: "Domestic Equities",
  sector: "",
  tier: 1,
  parentTicker: "",
  active: true,
  displayOrder: 999,
  _isNew: true,  // local-only flag — not sent to API
};

// ── Styles ────────────────────────────────────────────────────────────────────
const S = {
  page:      { background: "#070d14", minHeight: "100vh", fontFamily: "'IBM Plex Mono', 'Courier New', monospace", color: "#c8d8e8" },
  header:    { background: "linear-gradient(90deg, #0a1628 0%, #0d1f3c 100%)", borderBottom: "1px solid #1a3050", padding: "16px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" },
  badge:     { background: "#0d2a45", border: "1px solid #0077ff", borderRadius: "2px", padding: "2px 10px", fontSize: "10px", color: "#0099ff", letterSpacing: "0.15em", marginLeft: "12px" },
  backBtn:   { background: "none", border: "1px solid #1a2e45", borderRadius: "2px", color: "#8899aa", padding: "5px 14px", fontSize: "10px", cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.08em" },
  addBtn:    { background: "#001a2e", border: "1px solid #0077ff", borderRadius: "2px", color: "#0099ff", padding: "6px 16px", fontSize: "10px", cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.08em" },
  saveBtn:   { background: "#001a0e", border: "1px solid #00e5a0", borderRadius: "2px", color: "#00e5a0", padding: "6px 16px", fontSize: "10px", cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.08em" },
  deactBtn:  { background: "#1a0005", border: "1px solid #ff4d6d", borderRadius: "2px", color: "#ff4d6d", padding: "3px 10px", fontSize: "9px", cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.05em" },
  reactBtn:  { background: "#001a0e", border: "1px solid #00e5a0", borderRadius: "2px", color: "#00e5a0", padding: "3px 10px", fontSize: "9px", cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.05em" },
  th:        { padding: "10px 8px", textAlign: "left", fontSize: "10px", letterSpacing: "0.08em", color: "#8899aa", borderBottom: "1px solid #1a2535", whiteSpace: "nowrap", userSelect: "none" },
  input:     { background: "#0a1828", border: "1px solid #0077ff", borderRadius: "2px", color: "#e8f4ff", padding: "3px 6px", fontSize: "11px", fontFamily: "inherit", outline: "none", width: "100%" },
  select:    { background: "#0a1828", border: "1px solid #0077ff", borderRadius: "2px", color: "#e8f4ff", padding: "3px 6px", fontSize: "10px", fontFamily: "inherit", outline: "none", width: "100%", cursor: "pointer" },
  cellText:  { padding: "8px", fontSize: "11px", cursor: "text", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "180px" },
  toast:     { position: "fixed", bottom: "24px", left: "50%", transform: "translateX(-50%)", background: "#001a0e", border: "1px solid #00e5a0", borderRadius: "3px", padding: "8px 20px", fontSize: "11px", color: "#00e5a0", letterSpacing: "0.05em", zIndex: 200 },
};

// ── Password Gate ─────────────────────────────────────────────────────────────
function PasswordGate({ onSuccess }) {
  const [pw, setPw] = useState("");
  const [error, setError] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const attempt = () => {
    const envPw = process.env.REACT_APP_ADMIN_PASSWORD;
    if (!envPw) {
      setError(true);
      return;
    }
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
        {error && <div style={{ fontSize: "10px", color: "#ff4d6d", marginBottom: "10px", letterSpacing: "0.05em" }}>
          {!process.env.REACT_APP_ADMIN_PASSWORD ? "REACT_APP_ADMIN_PASSWORD not set in .env" : "Incorrect password"}
        </div>}
        <button onClick={attempt} style={{ ...S.saveBtn, width: "100%", padding: "8px", fontSize: "11px" }}>
          ENTER
        </button>
      </div>
    </div>
  );
}

// ── Inline editable cell ──────────────────────────────────────────────────────
function EditCell({ value, onChange, onCommit, type = "text", options = null, disabled = false }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef(null);

  useEffect(() => { if (editing) inputRef.current?.focus(); }, [editing]);
  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);

  const commit = () => {
    setEditing(false);
    if (draft !== value) onCommit(draft);
  };

  if (disabled) {
    return <td style={{ ...S.cellText, color: "#c8d8e8", cursor: "default" }}>{value || "—"}</td>;
  }

  if (editing) {
    if (options) {
      return (
        <td style={{ padding: "4px 6px" }}>
          <select
            ref={inputRef}
            value={draft}
            onChange={e => { setDraft(e.target.value); }}
            onBlur={() => { commit(); }}
            style={S.select}
          >
            {options.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        </td>
      );
    }
    return (
      <td style={{ padding: "4px 6px" }}>
        <input
          ref={inputRef}
          type={type}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={e => { if (e.key === "Enter") commit(); if (e.key === "Escape") { setEditing(false); setDraft(value); } }}
          style={S.input}
        />
      </td>
    );
  }

  return (
    <td
      style={{ ...S.cellText, color: "#c8d8e8" }}
      onClick={() => { setDraft(value); setEditing(true); }}
      title="Click to edit"
    >
      {value !== undefined && value !== "" ? String(value) : <span style={{ color: "#3a4a5a" }}>—</span>}
    </td>
  );
}

// ── Main AdminPanel ───────────────────────────────────────────────────────────
export default function AdminPanel() {
  const [authed, setAuthed] = useState(false);
  const [rows, setRows] = useState([]);
  const [hoveredRow, setHoveredRow] = useState(null);
  const [toast, setToast] = useState(null);
  const [filter, setFilter] = useState("all"); // all | active | inactive

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2000);
  };

  // Load from API on auth
  const loadFromApi = () => {
    fetch(API)  // fetch all — no active filter, admin sees everything
      .then(r => r.json())
      .then(data => setRows(data.map(fromApi)))
      .catch(() => showToast("Failed to load tickers"));
  };

  useEffect(() => {
    if (authed) loadFromApi();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authed]);

  const updateField = async (idx, field, value) => {
    // Update local state first for instant UI feedback
    const updated = rows.map((r, i) => i === idx ? { ...r, [field]: value } : r);
    setRows(updated);
    const row = updated[idx];

    if (row._isNew) {
      // New row — only POST once the ticker symbol is committed
      if (field === "ticker" && value) {
        try {
          const res = await fetch(API, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(toApi(row)),
          });
          if (res.status === 409) {
            showToast(`${value} already exists`);
            setRows(rows); // revert
            return;
          }
          if (!res.ok) throw new Error();
          // Clear _isNew flag — row is now persisted
          setRows(prev => prev.map((r, i) => i === idx ? { ...r, _isNew: false } : r));
          showToast("Added");
        } catch {
          showToast("Error saving ticker");
        }
      }
      // Other fields on new row: update local state only, wait for ticker symbol
      return;
    }

    // Existing row — PUT to API
    try {
      const res = await fetch(`${API}/${row.ticker}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(toApi(row)),
      });
      if (!res.ok) throw new Error();
      showToast("Saved");
    } catch {
      showToast("Error saving");
    }
  };

  const addRow = () => {
    const maxOrder = rows.filter(r => !r._isNew).reduce((m, r) => Math.max(m, r.displayOrder || 0), 0);
    setRows(prev => [...prev, { ...BLANK_TICKER, displayOrder: maxOrder + 1 }]);
  };

  const deactivate = async (idx) => {
    const row = rows[idx];
    if (row._isNew) {
      // Just remove from local state — not in DB yet
      setRows(prev => prev.filter((_, i) => i !== idx));
      return;
    }
    try {
      const res = await fetch(`${API}/${row.ticker}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      setRows(prev => prev.map((r, i) => i === idx ? { ...r, active: false } : r));
      showToast("Deactivated");
    } catch {
      showToast("Error deactivating");
    }
  };

  const reactivate = async (idx) => {
    const row = rows[idx];
    try {
      const res = await fetch(`${API}/${row.ticker}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...toApi(row), active: true }),
      });
      if (!res.ok) throw new Error();
      setRows(prev => prev.map((r, i) => i === idx ? { ...r, active: true } : r));
      showToast("Reactivated");
    } catch {
      showToast("Error reactivating");
    }
  };

  const tier1Tickers = rows.filter(r => r.tier === 1 && r.ticker && !r._isNew).map(r => r.ticker);

  const visibleRows = rows
    .map((r, originalIdx) => ({ ...r, originalIdx }))
    .filter(r => {
      if (filter === "active") return r.active;
      if (filter === "inactive") return !r.active;
      return true;
    })
    .sort((a, b) => {
      if (a._isNew) return 1;
      if (b._isNew) return -1;
      return (a.displayOrder || 999) - (b.displayOrder || 999) || (a.ticker || "").localeCompare(b.ticker || "");
    });

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
            <div style={{ fontSize: "9px", color: "#8899aa", letterSpacing: "0.2em" }}>TICKER MANAGEMENT</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <span style={{ fontSize: "10px", color: "#667788" }}>{rows.filter(r => r.active && !r._isNew).length} active · {rows.filter(r => !r.active).length} inactive · {rows.filter(r => !r._isNew).length} total</span>
          <button style={S.addBtn} onClick={addRow}>+ ADD TICKER</button>
          <button style={S.backBtn} onClick={() => window.location.href = "/"}>← DASHBOARD</button>
        </div>
      </div>

      {/* Filter bar */}
      <div style={{ background: "#0a1422", borderBottom: "1px solid #131f2e", padding: "10px 24px", display: "flex", gap: "6px", alignItems: "center" }}>
        {[["all", "ALL"], ["active", "ACTIVE"], ["inactive", "INACTIVE"]].map(([val, label]) => (
          <button
            key={val}
            onClick={() => setFilter(val)}
            style={{ background: filter === val ? "#0d2a45" : "transparent", border: `1px solid ${filter === val ? "#0077ff" : "#1a2e45"}`, color: filter === val ? "#0099ff" : "#8899aa", padding: "4px 12px", fontSize: "10px", borderRadius: "2px", cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.05em" }}
          >{label}</button>
        ))}
        <span style={{ marginLeft: "auto", fontSize: "10px", color: "#667788" }}>{visibleRows.length} showing · Click any cell to edit · Tab/Enter to confirm</span>
      </div>

      {/* Table */}
      <div style={{ overflowX: "auto", padding: "0 24px 40px" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", marginTop: "8px" }}>
          <thead>
            <tr style={{ background: "#0a1220" }}>
              <th style={S.th}>STATUS</th>
              <th style={S.th}>TICKER</th>
              <th style={S.th}>DESCRIPTION</th>
              <th style={S.th}>ASSET CLASS</th>
              <th style={S.th}>SECTOR</th>
              <th style={S.th}>TIER</th>
              <th style={S.th}>PARENT</th>
              <th style={S.th}>ORDER</th>
              <th style={S.th}></th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => {
              const idx = row.originalIdx;
              const isHovered = hoveredRow === idx;
              const isInactive = !row.active;

              return (
                <tr
                  key={`${row.ticker}-${idx}`}
                  onMouseEnter={() => setHoveredRow(idx)}
                  onMouseLeave={() => setHoveredRow(null)}
                  style={{
                    background: isHovered ? "#0d1a28" : isInactive ? "#07090e" : row._isNew ? "#071020" : idx % 2 === 0 ? "#080e18" : "#090f1a",
                    borderLeft: row._isNew ? "2px solid #0077ff" : "2px solid transparent",
                    opacity: isInactive ? 0.45 : 1,
                    transition: "background 0.15s, opacity 0.2s",
                  }}
                >
                  {/* Status dot */}
                  <td style={{ padding: "8px 12px", textAlign: "center" }}>
                    <span
                      style={{ fontSize: "14px", color: row._isNew ? "#0077ff" : row.active ? "#00e5a0" : "#3a4a5a" }}
                      title={row._isNew ? "New — enter ticker to save" : row.active ? "Active" : "Inactive"}
                    >●</span>
                  </td>

                  {/* Ticker — editable only on new rows */}
                  <EditCell
                    value={row.ticker}
                    disabled={!row._isNew}
                    onCommit={v => updateField(idx, "ticker", v.toUpperCase().trim())}
                  />

                  {/* Description */}
                  <EditCell
                    value={row.description}
                    onCommit={v => updateField(idx, "description", v)}
                  />

                  {/* Asset Class — dropdown */}
                  <EditCell
                    value={row.assetClass}
                    options={ASSET_CLASSES}
                    onCommit={v => updateField(idx, "assetClass", v)}
                  />

                  {/* Sector */}
                  <EditCell
                    value={row.sector}
                    onCommit={v => updateField(idx, "sector", v)}
                  />

                  {/* Tier — dropdown */}
                  <EditCell
                    value={String(row.tier)}
                    options={["1", "2"]}
                    onCommit={v => updateField(idx, "tier", Number(v))}
                  />

                  {/* Parent ticker — only editable when tier 2 */}
                  <EditCell
                    value={row.parentTicker || ""}
                    options={row.tier === 2 ? ["", ...tier1Tickers] : undefined}
                    onCommit={v => updateField(idx, "parentTicker", v)}
                    disabled={row.tier !== 2}
                  />

                  {/* Display order */}
                  <EditCell
                    value={String(row.displayOrder || "")}
                    type="number"
                    onCommit={v => updateField(idx, "displayOrder", Number(v))}
                  />

                  {/* Deactivate / Reactivate — show on hover */}
                  <td style={{ padding: "8px", textAlign: "right", minWidth: "100px" }}>
                    {isHovered && (
                      row._isNew
                        ? <button style={S.deactBtn} onClick={() => deactivate(idx)}>REMOVE</button>
                        : row.active
                        ? <button style={S.deactBtn} onClick={() => deactivate(idx)}>DEACTIVATE</button>
                        : <button style={S.reactBtn} onClick={() => reactivate(idx)}>REACTIVATE</button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Toast */}
      {toast && <div style={S.toast}>{toast}</div>}
    </div>
  );
}
