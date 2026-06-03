import { useEffect, useState, useCallback, useMemo } from "react";
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";
import { fetchMacroVolHistory } from "../../services/api";

// ── Palette ──────────────────────────────────────────────────────────────────
const COLORS = {
  VIX:  "#c8d8e8",   // light grey-white — most important, stands out on dark bg
  VXN:  "#8899aa",   // medium grey
  RVX:  "#5577aa",   // slate blue-grey
  GVZ:  "#e07b3a",   // orange
  OVX:  "#4e8fde",   // blue (right axis)
};

const GRID    = "#1a2a3a";
const TEXT    = "#8899aa";
const LABEL   = "#c8d8e8";
const GREEN   = "#00e5a0";
const RED     = "#ff4d6d";
const AMBER   = "#f0b429";

// Preferred order — tickers with no data are filtered out automatically at render time
const CHART_TICKER_ORDER = ["VIX", "VXN", "RVX", "GVZ", "OVX"];
const STAT_TICKER_ORDER  = ["VIX", "VXN", "RVX", "GVZ", "OVX"];

const LABELS = {
  VIX:  "VIX",
  VXN:  "NazVol",
  RVX:  "RVX",
  GVZ:  "GVZ",
  OVX:  "OVX (RHS)",
};

// ── Helpers ──────────────────────────────────────────────────────────────────
function getJanTicks(dates) {
  const seen = new Set();
  return dates.filter(d => {
    const [yr, mo] = d.split("-");
    if (mo === "01" && !seen.has(yr)) { seen.add(yr); return true; }
    return false;
  });
}

function fmtVol(v) {
  if (v == null) return "—";
  return v.toFixed(2);
}

function fmtBps(v) {
  if (v == null) return "—";
  const bps = Math.round(v * 100);
  return (bps > 0 ? "+" : "") + bps + " bps";
}

function fmtPct(v) {
  if (v == null) return "—";
  return (v > 0 ? "+" : "") + v.toFixed(1) + "%";
}

function deltaColor(v) {
  if (v == null) return TEXT;
  if (v > 0) return RED;    // vol up = bad
  if (v < 0) return GREEN;  // vol down = good
  return TEXT;
}

// ── X-axis tick ───────────────────────────────────────────────────────────────
function XTick({ x, y, payload }) {
  if (!payload?.value) return null;
  const [yr] = payload.value.split("-");
  return (
    <text x={x} y={y + 12} textAnchor="middle" fontSize={10} fill={TEXT}>
      {yr}
    </text>
  );
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  // Show all series present in payload, in order
  const entries = payload.filter(p => p.value != null);
  return (
    <div style={{
      background: "#0d1f33", border: "1px solid #1a2a3a",
      borderRadius: 6, padding: "8px 12px", fontSize: 11,
    }}>
      <div style={{ color: LABEL, marginBottom: 6, fontWeight: 600 }}>{label}</div>
      {entries.map(p => (
        <div key={p.dataKey} style={{ color: COLORS[p.dataKey] ?? TEXT, marginBottom: 2 }}>
          {LABELS[p.dataKey] ?? p.dataKey}: {p.value.toFixed(2)}
        </div>
      ))}
    </div>
  );
}

// ── Stats table ───────────────────────────────────────────────────────────────
function StatsTable({ stats, tickers }) {
  const cols = [
    { key: "last",      label: "Last" },
    { key: "day1",      label: "Prior Day" },
    { key: "wk1",       label: "1 Wk Ago" },
    { key: "mo1",       label: "1 Mo Ago" },
    { key: "mo3",       label: "3 Mo Ago" },
  ];
  const changeCols = [
    { dKey: "dod_delta", pKey: "dod_pct", label: "DoD" },
    { dKey: "wow_delta", pKey: "wow_pct", label: "WoW" },
    { dKey: "mom_delta", pKey: "mom_pct", label: "MoM" },
  ];

  const thStyle = {
    padding: "6px 10px",
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: "0.1em",
    color: TEXT,
    textAlign: "right",
    borderBottom: `1px solid ${GRID}`,
    whiteSpace: "nowrap",
  };
  const tdStyle = {
    padding: "5px 10px",
    fontSize: 11,
    textAlign: "right",
    fontVariantNumeric: "tabular-nums",
    color: LABEL,
    borderBottom: `1px solid ${GRID}`,
  };

  return (
    <div style={{
      border: `1px solid ${GRID}`,
      borderRadius: 6,
      background: "#07111f",
      overflowX: "auto",
      marginTop: 20,
    }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ ...thStyle, textAlign: "left", width: 80 }}>Series</th>
            {cols.map(c => <th key={c.key} style={thStyle}>{c.label}</th>)}
            {changeCols.map(c => (
              <>
                <th key={c.label}     style={thStyle}>{c.label}</th>
                <th key={c.label+"_"} style={thStyle} />
              </>
            ))}
          </tr>
          <tr>
            <th style={{ ...thStyle, borderBottom: `2px solid ${GRID}` }} />
            {cols.map(c => (
              <th key={c.key} style={{ ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#445566", fontSize: 8 }}>
                {c.key === "last" ? "vol" : "vol"}
              </th>
            ))}
            {changeCols.map(c => (
              <>
                <th key={c.dKey} style={{ ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#445566", fontSize: 8 }}>Δ bps</th>
                <th key={c.pKey} style={{ ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#445566", fontSize: 8 }}>%Δ</th>
              </>
            ))}
          </tr>
        </thead>
        <tbody>
          {tickers.map((tk, i) => {
            const s = stats[tk];
            const rowBg = i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)";
            return (
              <tr key={tk} style={{ background: rowBg }}>
                {/* Series name */}
                <td style={{ ...tdStyle, textAlign: "left" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <div style={{
                      width: 10, height: 2,
                      background: COLORS[tk] ?? "#8899aa",
                      borderRadius: 1, flexShrink: 0,
                    }} />
                    <span style={{ color: COLORS[tk] ?? LABEL, fontWeight: 600 }}>
                      {LABELS[tk]}
                    </span>
                  </div>
                </td>
                {/* Price columns */}
                {cols.map(c => (
                  <td key={c.key} style={tdStyle}>
                    {s ? fmtVol(s[c.key]) : "—"}
                  </td>
                ))}
                {/* Change columns */}
                {changeCols.map(c => (
                  <>
                    <td key={c.dKey} style={{ ...tdStyle, color: s ? deltaColor(s[c.dKey]) : TEXT }}>
                      {s ? fmtBps(s[c.dKey]) : "—"}
                    </td>
                    <td key={c.pKey} style={{ ...tdStyle, color: s ? deltaColor(s[c.pKey]) : TEXT }}>
                      {s ? fmtPct(s[c.pKey]) : "—"}
                    </td>
                  </>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Legend dot ────────────────────────────────────────────────────────────────
function LegendDot({ color, label, rightAxis }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 16, height: 2, background: color, borderRadius: 1 }} />
      <span style={{ fontSize: 10, color: TEXT, letterSpacing: "0.04em" }}>
        {label}{rightAxis && <span style={{ color: AMBER, marginLeft: 3 }}>▶</span>}
      </span>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function MacroVolChart() {
  const [rawData,  setRawData]  = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(false);
  const [range,    setRange]    = useState("2y");

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    const res = await fetchMacroVolHistory();
    if (!res || !res.dates?.length) {
      setError(true);
      setLoading(false);
      return;
    }
    setRawData(res);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  // Derive which tickers actually have data from the API response
  const chartTickers = useMemo(() => {
    if (!rawData?.series) return [];
    return CHART_TICKER_ORDER.filter(tk => rawData.series[tk]?.length > 0);
  }, [rawData]);

  const statTickers = useMemo(() => {
    if (!rawData?.stats) return [];
    return STAT_TICKER_ORDER.filter(tk => rawData.stats[tk] != null);
  }, [rawData]);

  // Build flat chart rows from {dates, series}
  const allRows = useMemo(() => {
    if (!rawData) return [];
    return rawData.dates.map((d, i) => {
      const row = { date: d };
      chartTickers.forEach(tk => {
        row[tk] = rawData.series[tk]?.[i] ?? null;
      });
      return row;
    });
  }, [rawData, chartTickers]);

  const displayData = useMemo(() => {
    if (range === "max" || allRows.length === 0) return allRows;
    const cutoff = new Date();
    cutoff.setFullYear(cutoff.getFullYear() - 2);
    const cutoffStr = cutoff.toISOString().slice(0, 10);
    return allRows.filter(r => r.date >= cutoffStr);
  }, [allRows, range]);

  const janTicks = useMemo(() => getJanTicks(displayData.map(r => r.date)), [displayData]);

  return (
    <div style={{
      minHeight: "100vh",
      background: "#060e1a",
      padding: "28px 164px",
      boxSizing: "border-box",
    }}>

      {/* ── Header ── */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 16 }}>
          <h1 style={{
            margin: 0, fontSize: 18, fontWeight: 700,
            letterSpacing: "0.06em", color: "#e8f4ff",
          }}>
            MACRO VOL
          </h1>
          <span style={{ fontSize: 11, color: TEXT, letterSpacing: "0.05em" }}>
            CROSS-ASSET IMPLIED VOLATILITY
          </span>
          {rawData?.updated && (
            <span style={{ fontSize: 10, color: TEXT, marginLeft: "auto" }}>
              EOD · {rawData.updated}
            </span>
          )}
        </div>
      </div>

      {/* ── States ── */}
      {loading && (
        <div style={{ color: TEXT, fontSize: 13, padding: "60px 0", textAlign: "center" }}>
          Loading...
        </div>
      )}
      {error && !loading && (
        <div style={{ color: RED, fontSize: 13, padding: "60px 0", textAlign: "center" }}>
          No data — run REFRESH DATA on the dashboard first to fetch these tickers.
        </div>
      )}

      {/* ── Chart + Table ── */}
      {!loading && !error && displayData.length > 0 && (
        <div>
          {/* Legend + Range toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 14, paddingLeft: 4, flexWrap: "wrap" }}>
            {chartTickers.map(tk => (
              <LegendDot
                key={tk}
                color={COLORS[tk]}
                label={LABELS[tk]}
                rightAxis={tk === "OVX"}
              />
            ))}
            <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
              {["2y", "max"].map(r => (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  style={{
                    padding: "3px 10px",
                    fontSize: 9,
                    fontWeight: 700,
                    letterSpacing: "0.1em",
                    background: range === r ? "rgba(0,229,160,0.12)" : "transparent",
                    border: `1px solid ${range === r ? "#00e5a0" : "#1a2a3a"}`,
                    borderRadius: 3,
                    color: range === r ? "#00e5a0" : "#8899aa",
                    cursor: "pointer",
                    fontFamily: "inherit",
                  }}
                >
                  {r === "2y" ? "2Y" : "MAX"}
                </button>
              ))}
            </div>
          </div>

          {/* OVX right-axis note */}
          <div style={{ fontSize: 9, color: AMBER, marginBottom: 8, paddingLeft: 4, letterSpacing: "0.06em" }}>
            ▶ OVX plotted on right axis (crude oil vol — higher scale)
          </div>

          {/* Chart */}
          <div style={{
            border: `1px solid ${GRID}`,
            borderRadius: 6,
            padding: "16px 0 8px 0",
            background: "#07111f",
          }}>
            <ResponsiveContainer width="100%" height={380}>
              <ComposedChart data={displayData} margin={{ top: 8, right: 56, left: 0, bottom: 8 }}>
                <CartesianGrid vertical={false} stroke={GRID} strokeDasharray="3 3" />

                <XAxis
                  dataKey="date"
                  ticks={janTicks}
                  tick={<XTick />}
                  tickLine={false}
                  axisLine={{ stroke: GRID }}
                  interval={0}
                />

                {/* Left axis — VIX / VXN / RVX / GVZ */}
                <YAxis
                  yAxisId="left"
                  orientation="left"
                  tickFormatter={v => `${v}`}
                  tick={{ fontSize: 10, fill: TEXT }}
                  tickLine={false}
                  axisLine={false}
                  domain={[0, "auto"]}
                  width={36}
                />

                {/* Right axis — OVX */}
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tickFormatter={v => `${v}`}
                  tick={{ fontSize: 10, fill: COLORS.OVX }}
                  tickLine={false}
                  axisLine={false}
                  domain={[0, "auto"]}
                  width={44}
                />

                <Tooltip content={<ChartTooltip />} />

                {/* Left-axis lines */}
                {chartTickers.filter(tk => tk !== "OVX").map(tk => (
                  <Line
                    key={tk}
                    yAxisId="left"
                    dataKey={tk}
                    stroke={COLORS[tk]}
                    strokeWidth={tk === "VIX" ? 2 : 1.5}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                ))}

                {/* OVX — right axis, slightly thicker (only if data present) */}
                {chartTickers.includes("OVX") && (
                  <Line
                    yAxisId="right"
                    dataKey="OVX"
                    stroke={COLORS.OVX}
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Stats table */}
          <StatsTable stats={rawData?.stats ?? {}} tickers={statTickers} />

        </div>
      )}
    </div>
  );
}
