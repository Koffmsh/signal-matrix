import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Scatter,
} from "recharts";
import { apiFetch } from "../../services/api";

const GREEN  = "#00e5a0";
const RED    = "#ff4d6d";
const AMBER  = "#f0b429";
const BLUE   = "#4e8fde";
const GREY   = "#8899aa";
const GRID   = "#1a2a3a";
const TEXT   = "#8899aa";
const LABEL  = "#c8d8e8";
const BG = "#0a1628";

const STATE_COLORS = {
  UPTREND_VALID:    GREEN,
  DOWNTREND_VALID:  RED,
  BREAK_OF_TRADE:   AMBER,
  BREAK_OF_TREND:   AMBER,
  BREAK_CONFIRMED:  RED,
  NO_STRUCTURE:     GREY,
};

const DIR_LABELS = {
  uptrend:   "Bullish",
  downtrend: "Bearish",
};

function fmt(v) {
  if (v == null) return "—";
  return typeof v === "number" ? v.toFixed(2) : v;
}

function fmtDate(d) {
  if (!d) return "";
  const parts = d.split("-");
  return `${parts[1]}/${parts[2]}`;
}

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div style={{
      background: "#0d1f33", border: "1px solid #1a2a3a",
      borderRadius: 6, padding: "8px 12px", fontSize: 11, maxWidth: 260,
    }}>
      <div style={{ color: LABEL, fontWeight: 700, marginBottom: 4 }}>{d.date}</div>
      <div style={{ color: LABEL }}>Close: {fmt(d.price)}</div>
      <div style={{ color: STATE_COLORS[d.state] || GREY, marginTop: 4 }}>
        {d.state}{d.d_extended ? " (D ext)" : ""}
      </div>
      {d.direction && (
        <div style={{ color: d.direction === "uptrend" ? GREEN : RED }}>
          {DIR_LABELS[d.direction] || d.direction}
        </div>
      )}
      {d.pivot_a != null && (
        <div style={{ color: TEXT, marginTop: 4, fontSize: 10 }}>
          A={fmt(d.pivot_a)} B={fmt(d.pivot_b)} C={fmt(d.pivot_c)} D={fmt(d.pivot_d)}
        </div>
      )}
      {d.break_level != null && (
        <div style={{ color: AMBER, fontSize: 10 }}>Break: {fmt(d.break_level)}</div>
      )}
    </div>
  );
}

// Pivot marker on the price line — circle + letter label
function PivotMarker({ cx, cy, color, label, r = 6 }) {
  if (cx == null || cy == null) return null;
  return (
    <g>
      <circle cx={cx} cy={cy} r={r} fill={color} stroke="#0a1628" strokeWidth={r < 6 ? 1 : 2} />
      <text x={cx} y={cy - 12} textAnchor="middle" fill={color} fontSize={11} fontWeight={800}>
        {label}
      </text>
    </g>
  );
}

export default function PivotDebug() {
  const [ticker, setTicker] = useState("SPY");
  const [timeframe, setTimeframe] = useState("trade");
  const [barWindow, setBarWindow] = useState(5);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tickers, setTickers] = useState([]);
  const [selectedBar, setSelectedBar] = useState(null);
  const tableRef = useRef(null);
  const defaultEnd = new Date().toISOString().slice(0, 10);
  const defaultStart = new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10);
  const startDateRef = useRef(defaultStart);
  const endDateRef = useRef(defaultEnd);
  const aLookbackRef = useRef("");

  // Load ticker list
  useEffect(() => {
    apiFetch("/api/tickers?active=true")
      .then(r => r.json())
      .then(list => setTickers(list.map(t => t.ticker).sort()))
      .catch(() => {});
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        ticker, timeframe, bar_window: barWindow,
        start_date: startDateRef.current, end_date: endDateRef.current,
      });
      if (aLookbackRef.current) params.set("a_lookback", aLookbackRef.current);
      const res = await apiFetch(`/api/debug/pivots?${params}`);
      const json = await res.json();
      if (json.error) { setError(json.error); setData(null); }
      else setData(json);
    } catch (e) {
      setError(e.message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [ticker, timeframe, barWindow]);

  // Auto-fetch on mount
  useEffect(() => { fetchData(); }, []); // eslint-disable-line

  // Merge trail into price data for chart
  const chartData = useMemo(() => {
    if (!data) return [];
    const trailMap = {};
    (data.trail || []).forEach(t => { trailMap[t.date] = t; });
    return (data.prices || []).map(p => ({
      date: p.date,
      price: p.price,
      ...trailMap[p.date],
    }));
  }, [data]);

  // Find state change rows for highlighting
  const stateChanges = useMemo(() => {
    if (!data?.trail) return new Set();
    const s = new Set();
    for (let i = 1; i < data.trail.length; i++) {
      if (data.trail[i].state !== data.trail[i - 1].state ||
          data.trail[i].direction !== data.trail[i - 1].direction ||
          data.trail[i].pivot_c !== data.trail[i - 1].pivot_c) {
        s.add(i);
      }
    }
    return s;
  }, [data]);

  // Last bar in view for showing current A/B/C/D reference lines
  const lastTrail = data?.trail?.[data.trail.length - 1];
  // Use selectedBar's pivots for reference lines if selected
  const refTrail = selectedBar != null ? data?.trail?.[selectedBar] : lastTrail;

  // Stamp pivot marker fields onto chartData based on refTrail's pivot dates
  const chartDataWithMarkers = useMemo(() => {
    if (!chartData.length || !refTrail) return chartData;
    const markers = {};
    if (refTrail.pivot_a_date && refTrail.pivot_a != null) markers[refTrail.pivot_a_date] = { markerA: refTrail.pivot_a };
    if (refTrail.pivot_b_date && refTrail.pivot_b != null) markers[refTrail.pivot_b_date] = { ...markers[refTrail.pivot_b_date], markerB: refTrail.pivot_b };
    if (refTrail.pivot_c_date && refTrail.pivot_c != null) markers[refTrail.pivot_c_date] = { ...markers[refTrail.pivot_c_date], markerC: refTrail.pivot_c };
    if (refTrail.pivot_d_date && refTrail.pivot_d != null) markers[refTrail.pivot_d_date] = { ...markers[refTrail.pivot_d_date], markerD: refTrail.pivot_d };
    // Always show white price dot on the selected/last bar
    if (refTrail.date && refTrail.price != null) {
      markers[refTrail.date] = { ...markers[refTrail.date], markerCurrent: refTrail.price };
    }
    if (!Object.keys(markers).length) return chartData;
    return chartData.map(d => markers[d.date] ? { ...d, ...markers[d.date] } : d);
  }, [chartData, refTrail]);

  // Background bands for structural state
  const stateBands = useMemo(() => {
    if (!chartData.length) return [];
    const bands = [];
    let cur = null;
    chartData.forEach((d, i) => {
      const st = d.state || "NO_STRUCTURE";
      if (!cur || cur.state !== st) {
        if (cur) cur.endDate = chartData[i - 1].date;
        cur = { state: st, startDate: d.date, startIdx: i };
        bands.push(cur);
      }
    });
    if (cur) cur.endDate = chartData[chartData.length - 1].date;
    return bands;
  }, [chartData]);

  const handleRowClick = (idx) => {
    setSelectedBar(idx === selectedBar ? null : idx);
  };

  const stepBar = useCallback((dir) => {
    if (!data?.trail?.length) return;
    const max = data.trail.length - 1;
    setSelectedBar(prev => {
      if (prev == null) return dir > 0 ? 0 : max;
      const next = prev + dir;
      if (next < 0) return 0;
      if (next > max) return max;
      return next;
    });
  }, [data]);

  // Auto-scroll table to selected row
  useEffect(() => {
    if (selectedBar == null || !tableRef.current) return;
    const row = tableRef.current.querySelector(`tbody tr:nth-child(${selectedBar + 1})`);
    if (row) row.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedBar]);

  // Keyboard arrow navigation
  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
      if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); stepBar(1); }
      if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); stepBar(-1); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [stepBar]);

  return (
    <div style={{ padding: "24px 32px", background: BG, minHeight: "100vh", color: LABEL }}>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <h1 style={{ fontSize: 18, fontWeight: 700, color: "#e8f4ff", letterSpacing: "0.06em", margin: 0 }}>
          PIVOT ENGINE DEBUG
        </h1>
        <div style={{ fontSize: 11, color: TEXT, letterSpacing: "0.05em", marginTop: 2 }}>
          Bar-by-bar pivot trail visualization
        </div>
      </div>

      {/* Controls */}
      <div style={{
        display: "flex", gap: 12, alignItems: "flex-end", marginBottom: 16,
        flexWrap: "wrap",
      }}>
        <div>
          <label style={lbl}>Ticker</label>
          <select value={ticker} onChange={e => setTicker(e.target.value)} style={sel}>
            {tickers.map(t => <option key={t} value={t}>{t}</option>)}
            {!tickers.includes(ticker) && <option value={ticker}>{ticker}</option>}
          </select>
        </div>
        <div>
          <label style={lbl}>Timeframe</label>
          <select value={timeframe} onChange={e => {
            setTimeframe(e.target.value);
            const defaults = { trade: 5, trend: 10, lt: 50 };
            setBarWindow(defaults[e.target.value] || 5);
            aLookbackRef.current = "";
          }} style={sel}>
            <option value="trade">Trade</option>
            <option value="trend">Trend</option>
            <option value="lt">Tail / LT</option>
          </select>
        </div>
        <div>
          <label style={lbl}>Bar Window</label>
          <input
            type="number" min={2} max={100} value={barWindow}
            onChange={e => setBarWindow(parseInt(e.target.value) || 5)}
            style={{ ...inp, width: 60 }}
          />
        </div>
        <div>
          <label style={lbl}>A Lookback</label>
          <input
            type="number" min={10} max={500} defaultValue={aLookbackRef.current}
            placeholder="def"
            onChange={e => { aLookbackRef.current = e.target.value ? parseInt(e.target.value) || "" : ""; }}
            style={{ ...inp, width: 60 }}
          />
        </div>
        <div>
          <label style={lbl}>Start Date</label>
          <input type="date" defaultValue={startDateRef.current} onChange={e => { startDateRef.current = e.target.value; }} style={inp} />
        </div>
        <div>
          <label style={lbl}>End Date</label>
          <input type="date" defaultValue={endDateRef.current} onChange={e => { endDateRef.current = e.target.value; }} style={inp} />
        </div>
        <button onClick={fetchData} disabled={loading} style={btn}>
          {loading ? "Loading..." : "RUN"}
        </button>
      </div>

      {error && <div style={{ color: RED, fontSize: 12, marginBottom: 12 }}>{error}</div>}

      {data && (
        <div style={{ fontSize: 10, color: TEXT, marginBottom: 8 }}>
          {data.total_history_bars} total bars · showing {data.prices?.length} bars
          ({data.start_date} → {data.end_date}) · bar_window={data.bar_window}
        </div>
      )}

      {/* Chart */}
      {chartData.length > 0 && (
        <div style={{
          background: "#0d1f33", borderRadius: 8, padding: "16px 8px 8px 8px",
          border: "1px solid #1a2a3a", marginBottom: 16,
        }}>
          <ResponsiveContainer width="100%" height={420}>
            <ComposedChart data={chartDataWithMarkers} margin={{ top: 20, right: 40, bottom: 10, left: 10 }}>
              <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
              <XAxis
                dataKey="date" tick={{ fill: TEXT, fontSize: 9 }}
                tickFormatter={fmtDate} interval={Math.max(1, Math.floor(chartData.length / 20))}
              />
              <YAxis
                tick={{ fill: TEXT, fontSize: 9 }} domain={["auto", "auto"]}
                tickFormatter={v => v.toFixed(0)}
              />
              <Tooltip content={<ChartTooltip />} />

              {/* State background bands via reference areas */}
              {stateBands.map((band, i) => {
                const color = STATE_COLORS[band.state] || GREY;
                return (
                  <ReferenceLine
                    key={`band-${i}`}
                    segment={[
                      { x: band.startDate, y: 0 },
                      { x: band.endDate, y: 0 },
                    ]}
                    stroke="none"
                  />
                );
              })}

              {/* Price line */}
              <Line
                type="monotone" dataKey="price" stroke={LABEL} strokeWidth={1.5}
                dot={false} isAnimationActive={false}
              />

              {/* Pivot dots on the price line */}
              <Scatter dataKey="markerA" fill={BLUE} isAnimationActive={false}
                shape={props => <PivotMarker {...props} color={BLUE} label="A" />} />
              <Scatter dataKey="markerB" fill={GREEN} isAnimationActive={false}
                shape={props => <PivotMarker {...props} color={GREEN} label="B" />} />
              <Scatter dataKey="markerC" fill={AMBER} isAnimationActive={false}
                shape={props => <PivotMarker {...props} color={AMBER} label="C" />} />
              <Scatter dataKey="markerD" fill={RED} isAnimationActive={false}
                shape={props => <PivotMarker {...props} color={RED} label="D" />} />
              <Scatter dataKey="markerCurrent" fill="#ffffff" isAnimationActive={false}
                shape={props => <PivotMarker {...props} color="#ffffff" label="" r={3} />} />

              {/* Pivot reference lines (from selected or last bar) */}
              {refTrail?.pivot_a != null && (
                <ReferenceLine y={refTrail.pivot_a} stroke={BLUE} strokeDasharray="6 3" strokeWidth={1}
                  label={{ value: `A ${fmt(refTrail.pivot_a)}`, fill: BLUE, fontSize: 10, position: "right" }} />
              )}
              {refTrail?.pivot_b != null && (
                <ReferenceLine y={refTrail.pivot_b} stroke={GREEN} strokeDasharray="6 3" strokeWidth={1}
                  label={{ value: `B ${fmt(refTrail.pivot_b)}`, fill: GREEN, fontSize: 10, position: "right" }} />
              )}
              {refTrail?.pivot_c != null && (
                <ReferenceLine y={refTrail.pivot_c} stroke={AMBER} strokeDasharray="6 3" strokeWidth={1}
                  label={{ value: `C ${fmt(refTrail.pivot_c)}`, fill: AMBER, fontSize: 10, position: "right" }} />
              )}
              {refTrail?.pivot_d != null && (
                <ReferenceLine y={refTrail.pivot_d} stroke={RED} strokeDasharray="4 4" strokeWidth={1}
                  label={{ value: `D ${fmt(refTrail.pivot_d)}`, fill: RED, fontSize: 10, position: "right" }} />
              )}
              {refTrail?.break_level != null && (
                <ReferenceLine y={refTrail.break_level} stroke={AMBER} strokeWidth={2} strokeDasharray="2 2"
                  label={{ value: `BRK ${fmt(refTrail.break_level)}`, fill: AMBER, fontSize: 10, position: "left" }} />
              )}
            </ComposedChart>
          </ResponsiveContainer>

          {/* Legend */}
          <div style={{ display: "flex", gap: 16, justifyContent: "center", marginTop: 4, fontSize: 10 }}>
            <span><span style={{ color: BLUE }}>━━</span> A</span>
            <span><span style={{ color: GREEN }}>━━</span> B</span>
            <span><span style={{ color: AMBER }}>━━</span> C / Break</span>
            <span><span style={{ color: RED }}>━━</span> D</span>
            {Object.entries(STATE_COLORS).map(([k, c]) => (
              <span key={k}><span style={{ color: c }}>●</span> {k.replace(/_/g, " ")}</span>
            ))}
          </div>
        </div>
      )}

      {/* Stepper */}
      {data?.trail?.length > 0 && (
        <div style={{
          display: "flex", alignItems: "center", gap: 12, marginBottom: 8,
        }}>
          <button onClick={() => stepBar(-1)} style={stepBtn} title="Previous bar (← arrow)">◀</button>
          <span style={{ fontSize: 12, color: LABEL, minWidth: 220, textAlign: "center" }}>
            {selectedBar != null && data.trail[selectedBar]
              ? `${data.trail[selectedBar].date}  ·  ${fmt(data.trail[selectedBar].price)}  ·  ${data.trail[selectedBar].state}`
              : "Click a row or use ◀ ▶ / arrow keys"}
          </span>
          <button onClick={() => stepBar(1)} style={stepBtn} title="Next bar (→ arrow)">▶</button>
        </div>
      )}

      {/* Trail table */}
      {data?.trail?.length > 0 && (
        <div style={{
          maxHeight: 400, overflowY: "auto", border: "1px solid #1a2a3a",
          borderRadius: 8, background: "#0d1f33",
        }} ref={tableRef}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
            <thead style={{ position: "sticky", top: 0, background: "#0d1f33", zIndex: 1 }}>
              <tr>
                {["Date", "Close", "Direction", "State", "A", "A Date", "B", "B Date",
                  "C", "C Date", "D", "D Date", "Break Lvl", "D Ext"].map(h => (
                  <th key={h} style={th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.trail.map((row, i) => {
                const isChange = stateChanges.has(i);
                const isSel = selectedBar === i;
                const dirColor = row.direction === "uptrend" ? GREEN :
                                 row.direction === "downtrend" ? RED : GREY;
                const stateColor = STATE_COLORS[row.state] || GREY;
                return (
                  <tr
                    key={i}
                    onClick={() => handleRowClick(i)}
                    style={{
                      cursor: "pointer",
                      background: isSel ? "#1e3a5f" : "transparent",
                      borderTop: isChange ? `1px solid ${stateColor}` : "none",
                    }}
                  >
                    <td style={td}>{row.date}</td>
                    <td style={{ ...td, color: LABEL }}>{fmt(row.price)}</td>
                    <td style={{ ...td, color: dirColor, fontWeight: 600 }}>
                      {DIR_LABELS[row.direction] || "—"}
                    </td>
                    <td style={{ ...td, color: stateColor, fontWeight: isChange ? 700 : 400 }}>
                      {row.state}
                    </td>
                    <td style={td}>{fmt(row.pivot_a)}</td>
                    <td style={{ ...td, fontSize: 9 }}>{fmtDate(row.pivot_a_date)}</td>
                    <td style={{ ...td, color: row.d_extended ? AMBER : GREY }}>{fmt(row.pivot_b)}</td>
                    <td style={{ ...td, fontSize: 9 }}>{fmtDate(row.pivot_b_date)}</td>
                    <td style={{ ...td, color: row.d_extended ? GREY : AMBER }}>{fmt(row.pivot_c)}</td>
                    <td style={{ ...td, fontSize: 9 }}>{fmtDate(row.pivot_c_date)}</td>
                    <td style={td}>{fmt(row.pivot_d)}</td>
                    <td style={{ ...td, fontSize: 9 }}>{fmtDate(row.pivot_d_date)}</td>
                    <td style={{ ...td, color: AMBER, fontWeight: 600 }}>{fmt(row.break_level)}</td>
                    <td style={{ ...td, color: row.d_extended ? AMBER : GREY }}>
                      {row.d_extended ? "YES" : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Selected bar detail */}
      {selectedBar != null && data?.trail?.[selectedBar] && (
        <div style={{
          marginTop: 12, padding: "12px 16px", background: "#1a2540",
          borderRadius: 8, border: "1px solid #1a3050", fontSize: 11,
        }}>
          <div style={{ color: "#e8f4ff", fontWeight: 700, marginBottom: 4 }}>
            Selected: {data.trail[selectedBar].date} — Close {fmt(data.trail[selectedBar].price)}
          </div>
          <div style={{ color: STATE_COLORS[data.trail[selectedBar].state], marginBottom: 2 }}>
            {data.trail[selectedBar].state}
            {data.trail[selectedBar].d_extended ? " (D Extended)" : ""}
          </div>
          <div style={{ color: TEXT }}>
            A={fmt(data.trail[selectedBar].pivot_a)} ({data.trail[selectedBar].pivot_a_date})
            {" · "}B={fmt(data.trail[selectedBar].pivot_b)} ({data.trail[selectedBar].pivot_b_date})
            {" · "}C={fmt(data.trail[selectedBar].pivot_c)} ({data.trail[selectedBar].pivot_c_date})
            {" · "}D={fmt(data.trail[selectedBar].pivot_d)} ({data.trail[selectedBar].pivot_d_date || "—"})
          </div>
          {data.trail[selectedBar].break_level != null && (
            <div style={{ color: AMBER }}>Break Level: {fmt(data.trail[selectedBar].break_level)}</div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────────
const lbl = { display: "block", fontSize: 9, color: TEXT, letterSpacing: "0.1em", fontWeight: 700, marginBottom: 2 };
const sel = {
  background: "#0d1f33", color: LABEL, border: "1px solid #1a2a3a",
  borderRadius: 4, padding: "4px 8px", fontSize: 12, outline: "none",
};
const inp = {
  background: "#0d1f33", color: LABEL, border: "1px solid #1a2a3a",
  borderRadius: 4, padding: "4px 8px", fontSize: 12, outline: "none",
  colorScheme: "dark",
};
const btn = {
  background: "#1a3050", color: LABEL, border: "1px solid #2a4060",
  borderRadius: 4, padding: "6px 20px", fontSize: 12, fontWeight: 700,
  cursor: "pointer", letterSpacing: "0.05em",
};
const th = {
  padding: "6px 8px", textAlign: "center", color: TEXT, fontSize: 9,
  fontWeight: 700, letterSpacing: "0.1em", borderBottom: "1px solid #1a2a3a",
};
const td = { padding: "4px 8px", textAlign: "center", color: GREY, fontSize: 11 };
const stepBtn = {
  background: "#1a3050", color: LABEL, border: "1px solid #2a4060",
  borderRadius: 4, padding: "4px 12px", fontSize: 14, fontWeight: 700,
  cursor: "pointer", lineHeight: 1,
};
