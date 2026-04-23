import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

const QUAD_COLORS = { 1: "#00e5a0", 2: "#a3c940", 3: "#f0b429", 4: "#ff4d6d" };

const COUNTRIES = [
  "United States", "Japan", "China", "Eurozone",
  "Germany", "France", "United Kingdom", "Spain",
  "Mexico", "Turkey", "UAE", "South Korea",
  "India", "Brazil", "Canada", "Australia",
];

const COUNTRY_CODE = {
  "United States": "US", "Japan": "JP", "China": "CN", "Eurozone": "EU",
  "Germany": "DE", "France": "FR", "United Kingdom": "GB", "Spain": "ES",
  "Mexico": "MX", "Turkey": "TR", "UAE": "AE", "South Korea": "KR",
  "India": "IN", "Brazil": "BR", "Canada": "CA", "Australia": "AU",
};

const mono = { fontFamily: "'IBM Plex Mono', 'Courier New', monospace" };

// ── helpers ──────────────────────────────────────────────────────────────────

function getNTMMonths() {
  const now = new Date();
  // Use local date as ET approximation (admin is in ET timezone)
  const months = [];
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
    const year = d.getFullYear();
    const month = d.getMonth(); // 0-indexed
    const key = `${year}-${String(month + 1).padStart(2, "0")}`;
    const label = d.toLocaleString("en-US", { month: "short" }) + " " + year;
    const qNum = Math.floor(month / 3) + 1;
    const qLabel = `Q${qNum} ${year}`;
    months.push({ key, label, qLabel });
  }
  return months;
}

function getNTMQuarters() {
  const now = new Date();
  const quarters = [];
  const currentQ = Math.floor(now.getMonth() / 3); // 0-indexed
  for (let i = 0; i < 4; i++) {
    let q = currentQ + i;
    let year = now.getFullYear();
    while (q >= 4) { q -= 4; year += 1; }
    const key = `${year}-Q${q + 1}`;
    const label = `Q${q + 1} ${year}`;
    quarters.push({ key, label });
  }
  return quarters;
}

// ── sub-components ────────────────────────────────────────────────────────────

function QuadBtn({ n, selected, onSelect, disabled }) {
  const active = selected === n;
  return (
    <button
      onClick={() => !disabled && onSelect(n)}
      style={{
        ...mono,
        background:    active ? `${QUAD_COLORS[n]}55` : "transparent",
        border:        `1px solid ${active ? QUAD_COLORS[n] : "#1a2e45"}`,
        color:         active ? "#ffffff" : "#8899aa",
        padding:       "3px 10px",
        fontSize:      "10px",
        fontWeight:    active ? "700" : "400",
        borderRadius:  "2px",
        cursor:        disabled ? "default" : "pointer",
        letterSpacing: "0.05em",
        minWidth:      "30px",
      }}
    >
      Q{n}
    </button>
  );
}

function SaveDot({ status }) {
  if (!status) return null;
  if (status === "saving") return <span style={{ fontSize: "9px", color: "#8899aa" }}>…</span>;
  if (status === "ok")     return <span style={{ fontSize: "10px", color: "#00e5a0", fontWeight: "700" }}>✓</span>;
  return <span style={{ fontSize: "9px", color: "#ff4d6d" }} title={status}>✗</span>;
}

// ── Section 1: US Monthly ─────────────────────────────────────────────────────

function MonthRow({ month, initialQuad, initialProb }) {
  const [quad,       setQuad]       = useState(initialQuad  ?? null);
  const [prob,       setProb]       = useState(initialProb  != null ? Math.round(initialProb * 100).toString() : "");
  const [saveStatus, setSaveStatus] = useState(null);

  const save = useCallback((q, p) => {
    if (!q) return;
    const probVal = parseFloat(p);
    if (isNaN(probVal) || probVal < 0 || probVal > 100) return;
    setSaveStatus("saving");
    fetch(`${API_BASE}/api/quad/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        country:        "US",
        forecast_month: month.key,
        quad:           q,
        probability:    probVal / 100,
        quad_type:      "monthly",
      }),
    })
      .then(r => { if (!r.ok) return r.json().then(e => { throw new Error(e.detail || r.status); }); return r.json(); })
      .then(() => {
        setSaveStatus("ok");
        setTimeout(() => setSaveStatus(null), 2000);
      })
      .catch(e => setSaveStatus(e.message || "error"));
  }, [month.key]);

  const handleQuadSelect = (n) => {
    setQuad(n);
    save(n, prob || "50");
    if (!prob) setProb("50");
  };

  const handleProbBlur = () => {
    if (!quad) return;
    save(quad, prob);
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "10px", padding: "5px 0", borderBottom: "1px solid #0d1a2a" }}>
      <div style={{ width: "70px", fontSize: "10px", color: "#c8d8e8" }}>{month.label}</div>
      <div style={{ display: "flex", gap: "4px" }}>
        {[1, 2, 3, 4].map(n => (
          <QuadBtn key={n} n={n} selected={quad} onSelect={handleQuadSelect} />
        ))}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
        <input
          type="number" min="0" max="100"
          value={prob}
          onChange={e => setProb(e.target.value)}
          onBlur={handleProbBlur}
          placeholder="—"
          style={{
            ...mono,
            width: "46px",
            background: "#080e18",
            border: "1px solid #1a2e45",
            color: "#c8d8e8",
            padding: "3px 6px",
            fontSize: "10px",
            borderRadius: "2px",
            textAlign: "right",
            outline: "none",
          }}
        />
        <span style={{ fontSize: "10px", color: "#8899aa" }}>%</span>
      </div>
      <SaveDot status={saveStatus} />
    </div>
  );
}

// ── Section 2: Country Quarterly ──────────────────────────────────────────────

function CountryRow({ country, quarters, initialData }) {
  const code = COUNTRY_CODE[country] || country.slice(0, 3).toUpperCase();
  const [quads,      setQuads]      = useState(() => {
    const init = {};
    quarters.forEach(q => { init[q.key] = null; });
    (initialData || []).forEach(r => { init[r.forecast_month] = r.quad; });
    return init;
  });
  const [statuses,   setStatuses]   = useState({});

  const handleSelect = (quarterKey, n) => {
    setQuads(prev => ({ ...prev, [quarterKey]: n }));
    setStatuses(prev => ({ ...prev, [quarterKey]: "saving" }));
    fetch(`${API_BASE}/api/quad/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        country:        code,
        forecast_month: quarterKey,
        quad:           n,
        probability:    1.0,
        quad_type:      "quarterly",
      }),
    })
      .then(r => { if (!r.ok) return r.json().then(e => { throw new Error(e.detail || r.status); }); return r.json(); })
      .then(() => {
        setStatuses(prev => ({ ...prev, [quarterKey]: "ok" }));
        setTimeout(() => setStatuses(prev => ({ ...prev, [quarterKey]: null })), 2000);
      })
      .catch(e => setStatuses(prev => ({ ...prev, [quarterKey]: e.message || "error" })));
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0", borderBottom: "1px solid #0d1a2a" }}>
      <div style={{ width: "130px", fontSize: "10px", color: "#c8d8e8", padding: "6px 0", flexShrink: 0 }}>
        {country}
      </div>
      {quarters.map(q => (
        <div key={q.key} style={{ width: "160px", display: "flex", gap: "3px", padding: "4px 8px", flexShrink: 0 }}>
          {[1, 2, 3, 4].map(n => (
            <QuadBtn key={n} n={n} selected={quads[q.key]} onSelect={(v) => handleSelect(q.key, v)} />
          ))}
          <SaveDot status={statuses[q.key]} />
        </div>
      ))}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function QuadSetup() {
  const ntmMonths   = getNTMMonths();
  const ntmQuarters = getNTMQuarters();

  const [monthlyData,   setMonthlyData]   = useState([]);  // [{forecast_month, quad, probability}]
  const [quarterlyData, setQuarterlyData] = useState([]);  // [{country, forecast_month, quad}]
  const [loading,       setLoading]       = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/quad/settings?country=US&type=monthly`).then(r => r.json()),
      fetch(`${API_BASE}/api/quad/settings?country=ALL&type=quarterly`).then(r => r.json()),
    ])
      .then(([monthly, quarterly]) => {
        setMonthlyData(monthly);
        setQuarterlyData(quarterly);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Index monthly data by forecast_month for quick lookup
  const monthlyIndex = {};
  monthlyData.forEach(r => { monthlyIndex[r.forecast_month] = r; });

  // Index quarterly data by country_code + forecast_month
  const quarterlyIndex = {};
  quarterlyData.forEach(r => {
    if (!quarterlyIndex[r.country]) quarterlyIndex[r.country] = [];
    quarterlyIndex[r.country].push(r);
  });

  // Group months by quarter label for section headers
  const qGroups = [];
  ntmMonths.forEach(m => {
    const last = qGroups[qGroups.length - 1];
    if (!last || last.label !== m.qLabel) {
      qGroups.push({ label: m.qLabel, months: [m] });
    } else {
      last.months.push(m);
    }
  });

  const sectionHeader = (txt) => (
    <div style={{ fontSize: "10px", fontWeight: "700", letterSpacing: "0.2em", color: "#00e5a0", marginBottom: "12px", marginTop: "28px" }}>
      {txt}
    </div>
  );

  const qGroupHeader = (label) => (
    <div style={{ fontSize: "9px", color: "#c8d8e8", letterSpacing: "0.15em", margin: "14px 0 4px" }}>
      {label}
    </div>
  );

  if (loading) {
    return (
      <div style={{ ...mono, padding: "32px", color: "#8899aa", fontSize: "10px" }}>LOADING…</div>
    );
  }

  return (
    <div style={{ ...mono, padding: "32px", maxWidth: "900px", color: "#c8d8e8" }}>

      {/* ── Section 1: US Monthly ── */}
      {sectionHeader("US — MONTHLY QUADS  NTM")}
      <div style={{ fontSize: "10px", color: "#8899aa", marginBottom: "16px" }}>
        Current month + 11 forward · Auto-saves on selection or probability blur
      </div>

      {/* Column headers */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px", paddingBottom: "6px", borderBottom: "1px solid #1a2e45", marginBottom: "4px" }}>
        <div style={{ width: "70px", fontSize: "9px", color: "#c8d8e8", letterSpacing: "0.12em" }}>MONTH</div>
        <div style={{ width: "196px", fontSize: "9px", color: "#c8d8e8", letterSpacing: "0.12em" }}>QUAD</div>
        <div style={{ fontSize: "9px", color: "#c8d8e8", letterSpacing: "0.12em" }}>PROB</div>
      </div>

      {qGroups.map(group => (
        <div key={group.label}>
          {qGroupHeader(group.label)}
          {group.months.map(month => (
            <MonthRow
              key={month.key}
              month={month}
              initialQuad={monthlyIndex[month.key]?.quad ?? null}
              initialProb={monthlyIndex[month.key]?.probability ?? null}
            />
          ))}
        </div>
      ))}

      {/* ── Section 2: Country Quarterly ── */}
      <div style={{ borderTop: "1px solid #1a2e45", marginTop: "32px" }} />
      {sectionHeader("COUNTRY QUADS — QUARTERLY")}
      <div style={{ fontSize: "10px", color: "#8899aa", marginBottom: "16px" }}>
        Dominant macro regime per country · Auto-saves on selection
      </div>

      {/* Quarter column headers */}
      <div style={{ display: "flex", alignItems: "center", borderBottom: "1px solid #1a2e45", paddingBottom: "6px", marginBottom: "4px" }}>
        <div style={{ width: "130px", fontSize: "9px", color: "#c8d8e8", letterSpacing: "0.12em" }}>COUNTRY</div>
        {ntmQuarters.map(q => (
          <div key={q.key} style={{ width: "160px", fontSize: "9px", color: "#c8d8e8", letterSpacing: "0.12em", padding: "0 8px" }}>
            {q.label}
          </div>
        ))}
      </div>

      {COUNTRIES.map(country => {
        const code = COUNTRY_CODE[country] || country.slice(0, 3).toUpperCase();
        return (
          <CountryRow
            key={country}
            country={country}
            quarters={ntmQuarters}
            initialData={quarterlyIndex[code] || []}
          />
        );
      })}

    </div>
  );
}
