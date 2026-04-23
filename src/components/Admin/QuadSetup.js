import { useState, useEffect } from "react";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

const QUAD_COLORS = { 1: "#00e5a0", 2: "#a3c940", 3: "#f0b429", 4: "#ff4d6d" };
const QUAD_LABELS = {
  1: "Q1 — Goldilocks  (growth ↑, inflation ↓)",
  2: "Q2 — Reflation   (growth ↑, inflation ↑)",
  3: "Q3 — Stagflation (growth ↓, inflation ↑)",
  4: "Q4 — Deflation   (growth ↓, inflation ↓)",
};

const mono = { fontFamily: "'IBM Plex Mono', 'Courier New', monospace" };

function QuadButton({ n, selected, onSelect }) {
  const active = selected === n;
  return (
    <button
      onClick={() => onSelect(n)}
      style={{
        ...mono,
        background:  active ? `${QUAD_COLORS[n]}22` : "transparent",
        border:      `1px solid ${active ? QUAD_COLORS[n] : "#1a2e45"}`,
        color:       active ? QUAD_COLORS[n] : "#8899aa",
        padding:     "5px 14px",
        fontSize:    "11px",
        fontWeight:  active ? "700" : "400",
        borderRadius:"2px",
        cursor:      "pointer",
        letterSpacing: "0.06em",
      }}
    >
      Q{n}
    </button>
  );
}

export default function QuadSetup() {
  const [currentQuad, setCurrentQuad]   = useState(null);
  const [currentProb, setCurrentProb]   = useState("");
  const [nextQuad,    setNextQuad]      = useState(null);
  const [nextProb,    setNextProb]      = useState("");
  const [effDate,     setEffDate]       = useState("");
  const [notes,       setNotes]         = useState("");
  const [saving,      setSaving]        = useState(false);
  const [saveStatus,  setSaveStatus]    = useState(null);   // "ok" | "error" | null
  const [lastSaved,   setLastSaved]     = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/quad/settings`)
      .then(r => r.json())
      .then(data => {
        if (!data.current_quad) return;
        setLastSaved(data);
        setCurrentQuad(data.current_quad);
        setCurrentProb(Math.round((data.current_prob ?? 0) * 100).toString());
        setNextQuad(data.next_quad ?? null);
        setNextProb(data.next_prob != null ? Math.round(data.next_prob * 100).toString() : "");
        setEffDate(data.effective_date ?? "");
        setNotes(data.notes ?? "");
      })
      .catch(() => {});
  }, []);

  const handleSave = () => {
    if (!currentQuad || !currentProb || !effDate) return;
    setSaving(true);
    setSaveStatus(null);

    const body = {
      current_quad:   currentQuad,
      current_prob:   parseFloat(currentProb) / 100,
      next_quad:      nextQuad || null,
      next_prob:      nextProb ? parseFloat(nextProb) / 100 : null,
      effective_date: effDate,
      notes:          notes || null,
    };

    fetch(`${API_BASE}/api/quad/settings`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    })
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(data => {
        setLastSaved({ ...body, ...data });
        setSaveStatus("ok");
      })
      .catch(() => setSaveStatus("error"))
      .finally(() => setSaving(false));
  };

  const label = (txt) => (
    <div style={{ fontSize: "9px", color: "#8899aa", letterSpacing: "0.15em", marginBottom: "6px" }}>{txt}</div>
  );

  const dividerStyle = {
    borderTop: "1px solid #1a2e45",
    margin: "24px 0",
  };

  const inputStyle = {
    ...mono,
    background: "#080e18",
    border: "1px solid #1a2e45",
    color: "#c8d8e8",
    padding: "6px 10px",
    fontSize: "11px",
    borderRadius: "2px",
    outline: "none",
    width: "100%",
    boxSizing: "border-box",
  };

  return (
    <div style={{ ...mono, padding: "32px", maxWidth: "640px", color: "#c8d8e8" }}>
      <div style={{ fontSize: "10px", fontWeight: "700", letterSpacing: "0.2em", color: "#00e5a0", marginBottom: "4px" }}>
        QUAD SETTINGS
      </div>
      <div style={{ fontSize: "10px", color: "#8899aa", letterSpacing: "0.05em", marginBottom: "28px" }}>
        Define the active quadrant framework — drives conviction multipliers across all signals.
        Each save appends a new row; the most recent effective date is always active.
      </div>

      {/* Current Quad */}
      <div style={{ marginBottom: "20px" }}>
        {label("CURRENT QUAD")}
        <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
          {[1, 2, 3, 4].map(n => (
            <QuadButton key={n} n={n} selected={currentQuad} onSelect={setCurrentQuad} />
          ))}
          <div style={{ display: "flex", alignItems: "center", gap: "6px", marginLeft: "12px" }}>
            <input
              type="number" min="0" max="100" placeholder="58"
              value={currentProb}
              onChange={e => setCurrentProb(e.target.value)}
              style={{ ...inputStyle, width: "60px", textAlign: "right" }}
            />
            <span style={{ fontSize: "11px", color: "#8899aa" }}>%</span>
          </div>
        </div>
        {currentQuad && (
          <div style={{ marginTop: "8px", fontSize: "10px", color: QUAD_COLORS[currentQuad], letterSpacing: "0.05em" }}>
            {QUAD_LABELS[currentQuad]}
          </div>
        )}
      </div>

      {/* Next Quad */}
      <div style={{ marginBottom: "20px" }}>
        {label("NEXT QUAD  (optional — probability of transition)")}
        <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
          {[1, 2, 3, 4].map(n => (
            <QuadButton key={n} n={n} selected={nextQuad} onSelect={q => setNextQuad(q === nextQuad ? null : q)} />
          ))}
          <div style={{ display: "flex", alignItems: "center", gap: "6px", marginLeft: "12px" }}>
            <input
              type="number" min="0" max="100" placeholder="37"
              value={nextProb}
              onChange={e => setNextProb(e.target.value)}
              style={{ ...inputStyle, width: "60px", textAlign: "right" }}
              disabled={!nextQuad}
            />
            <span style={{ fontSize: "11px", color: nextQuad ? "#8899aa" : "#445566" }}>%</span>
          </div>
          {nextQuad && (
            <button
              onClick={() => { setNextQuad(null); setNextProb(""); }}
              style={{ ...mono, background: "transparent", border: "none", color: "#8899aa", cursor: "pointer", fontSize: "11px" }}
            >
              ✕ clear
            </button>
          )}
        </div>
      </div>

      {/* Effective Date */}
      <div style={{ marginBottom: "20px" }}>
        {label("EFFECTIVE DATE  (YYYY-MM-DD ET)")}
        <input
          type="text" placeholder="2026-04-23"
          value={effDate}
          onChange={e => setEffDate(e.target.value)}
          style={{ ...inputStyle, width: "160px" }}
        />
      </div>

      {/* Notes */}
      <div style={{ marginBottom: "24px" }}>
        {label("NOTES  (optional)")}
        <textarea
          placeholder="e.g. Tariff shock pushing growth expectations lower"
          value={notes}
          onChange={e => setNotes(e.target.value)}
          rows={3}
          style={{ ...inputStyle, resize: "vertical" }}
        />
      </div>

      {/* Save button */}
      <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
        <button
          onClick={handleSave}
          disabled={saving || !currentQuad || !currentProb || !effDate}
          style={{
            ...mono,
            background:    saving ? "transparent" : "#001a0f",
            border:        `1px solid ${saving ? "#1a2e45" : "#00e5a0"}`,
            color:         saving ? "#445566" : "#00e5a0",
            padding:       "7px 20px",
            fontSize:      "10px",
            fontWeight:    "700",
            letterSpacing: "0.15em",
            borderRadius:  "2px",
            cursor:        saving || !currentQuad || !currentProb || !effDate ? "default" : "pointer",
          }}
        >
          {saving ? "SAVING..." : "SAVE QUAD SETTINGS"}
        </button>
        {saveStatus === "ok"    && <span style={{ fontSize: "10px", color: "#00e5a0" }}>✓ Saved</span>}
        {saveStatus === "error" && <span style={{ fontSize: "10px", color: "#ff4d6d" }}>✗ Save failed</span>}
      </div>

      {/* Last saved confirmation */}
      {lastSaved && (
        <>
          <div style={dividerStyle} />
          <div style={{ fontSize: "10px", color: "#8899aa", letterSpacing: "0.05em" }}>
            <span style={{ color: "#445566" }}>Last saved: </span>
            <span style={{ color: QUAD_COLORS[lastSaved.current_quad] }}>Quad {lastSaved.current_quad}</span>
            <span style={{ color: "#667788" }}> · {Math.round((lastSaved.current_prob ?? 0) * 100)}%</span>
            {lastSaved.next_quad && (
              <>
                <span style={{ color: "#445566" }}> → </span>
                <span style={{ color: QUAD_COLORS[lastSaved.next_quad] }}>Quad {lastSaved.next_quad}</span>
                <span style={{ color: "#667788" }}> · {Math.round((lastSaved.next_prob ?? 0) * 100)}%</span>
              </>
            )}
            <span style={{ color: "#445566" }}> · effective </span>
            <span style={{ color: "#8899aa" }}>{lastSaved.effective_date}</span>
          </div>
        </>
      )}
    </div>
  );
}
