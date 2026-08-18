import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { fetchBondVolHistory } from "../../services/api";
import { GREEN, RED, GREY, LABEL, GRID } from "../../styles/tokens";

// ── Palette ──────────────────────────────────────────────────────────────────
const COLORS = {
  MOVE: "#c8d8e8",
};

// Threshold lines matching MOVE vol scorer (rule #61)
const MOVE_INVESTABLE = 85;
const MOVE_DANGER     = 120;

const LABELS = {
  MOVE: "MOVE",
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
  if (v == null) return GREY;
  if (v > 0) return RED;
  if (v < 0) return GREEN;
  return GREY;
}

// ── X-axis tick ───────────────────────────────────────────────────────────────
function XTick({ x, y, payload }) {
  if (!payload?.value) return null;
  const [yr] = payload.value.split("-");
  return (
    <text x={x} y={y + 12} textAnchor="middle" fontSize={10} fill={GREY}>
      {yr}
    </text>
  );
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const entries = payload.filter(p => p.value != null);
  return (
    <div style={{
      background: "#0d1f33", border: "1px solid #1a2a3a",
      borderRadius: 6, padding: "8px 12px", fontSize: 11,
    }}>
      <div style={{ color: LABEL, marginBottom: 6, fontWeight: 600 }}>{label}</div>
      {entries.map(p => (
        <div key={p.dataKey} style={{ color: COLORS[p.dataKey] ?? GREY, marginBottom: 2 }}>
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
    color: GREY,
    textAlign: "center",
    borderBottom: `1px solid ${GRID}`,
    whiteSpace: "nowrap",
  };
  const tdStyle = {
    padding: "5px 10px",
    fontSize: 11,
    textAlign: "center",
    fontVariantNumeric: "tabular-nums",
    fontFamily: "'Menlo', 'Consolas', monospace",
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
              <th key={c.label} style={thStyle} colSpan={2}>{c.label}</th>
            ))}
          </tr>
          <tr>
            <th style={{ ...thStyle, borderBottom: `2px solid ${GRID}` }} />
            {cols.map(c => (
              <th key={c.key} style={{ ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#8899aa", fontSize: 8 }}>
                vol
              </th>
            ))}
            {changeCols.map(c => (
              <React.Fragment key={c.dKey}>
                <th style={{ ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#8899aa", fontSize: 8 }}>{"Δ"} bps</th>
                <th style={{ ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#8899aa", fontSize: 8 }}>%{"Δ"}</th>
              </React.Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {tickers.map((tk, i) => {
            const s = stats[tk];
            const rowBg = i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)";
            return (
              <tr key={tk} style={{ background: rowBg }}>
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
                {cols.map(c => (
                  <td key={c.key} style={tdStyle}>
                    {s ? fmtVol(s[c.key]) : "—"}
                  </td>
                ))}
                {changeCols.map(c => (
                  <React.Fragment key={c.dKey}>
                    <td style={{ ...tdStyle, color: s ? deltaColor(s[c.dKey]) : GREY }}>
                      {s ? fmtBps(s[c.dKey]) : "—"}
                    </td>
                    <td style={{ ...tdStyle, color: s ? deltaColor(s[c.pKey]) : GREY }}>
                      {s ? fmtPct(s[c.pKey]) : "—"}
                    </td>
                  </React.Fragment>
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
function LegendDot({ color, label }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 16, height: 2, background: color, borderRadius: 1 }} />
      <span style={{ fontSize: 10, color: GREY, letterSpacing: "0.04em" }}>
        {label}
      </span>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function BondVolChart() {
  const [rawData,  setRawData]  = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(false);
  const [range,    setRange]    = useState("2y");

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    const res = await fetchBondVolHistory();
    if (!res || !res.dates?.length) {
      setError(true);
      setLoading(false);
      return;
    }
    setRawData(res);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const chartTickers = useMemo(() => {
    if (!rawData?.series) return [];
    return ["MOVE"].filter(tk => rawData.series[tk]?.length > 0);
  }, [rawData]);

  const statTickers = useMemo(() => {
    if (!rawData?.stats) return [];
    return ["MOVE"].filter(tk => rawData.stats[tk] != null);
  }, [rawData]);

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
            BOND VOL
          </h1>
          <span style={{ fontSize: 11, color: GREY, letterSpacing: "0.05em" }}>
            ICE BofA MOVE INDEX &mdash; TREASURY IMPLIED VOLATILITY
          </span>
          {rawData?.updated && (
            <span style={{ fontSize: 10, color: GREY, marginLeft: "auto" }}>
              EOD &middot; {rawData.updated}
            </span>
          )}
        </div>
      </div>

      {/* ── States ── */}
      {loading && (
        <div style={{ color: GREY, fontSize: 13, padding: "60px 0", textAlign: "center" }}>
          Loading...
        </div>
      )}
      {error && !loading && (
        <div style={{ color: RED, fontSize: 13, padding: "60px 0", textAlign: "center" }}>
          No data &mdash; run REFRESH DATA on the dashboard first to fetch MOVE.
        </div>
      )}

      {/* ── Chart + Table ── */}
      {!loading && !error && displayData.length > 0 && (
        <div>
          {/* Legend + Range toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 14, paddingLeft: 4, flexWrap: "wrap" }}>
            {chartTickers.map(tk => (
              <LegendDot key={tk} color={COLORS[tk]} label={LABELS[tk]} />
            ))}
            <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 9, color: GREY }}>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ width: 16, height: 0, borderTop: "1px dashed #00e5a0" }} />
                Investable ({MOVE_INVESTABLE})
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ width: 16, height: 0, borderTop: "1px dashed #ff4d6d" }} />
                Danger ({MOVE_DANGER})
              </span>
            </div>
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

                <YAxis
                  yAxisId="left"
                  orientation="left"
                  tickFormatter={v => `${v}`}
                  tick={{ fontSize: 10, fill: GREY }}
                  tickLine={false}
                  axisLine={false}
                  domain={[0, "auto"]}
                  width={36}
                />

                <Tooltip content={<ChartTooltip />} />

                {/* Threshold reference lines */}
                <ReferenceLine
                  yAxisId="left"
                  y={MOVE_INVESTABLE}
                  stroke="#00e5a0"
                  strokeDasharray="4 4"
                  strokeWidth={1}
                  strokeOpacity={0.5}
                />
                <ReferenceLine
                  yAxisId="left"
                  y={MOVE_DANGER}
                  stroke="#ff4d6d"
                  strokeDasharray="4 4"
                  strokeWidth={1}
                  strokeOpacity={0.5}
                />

                {chartTickers.map(tk => (
                  <Line
                    key={tk}
                    yAxisId="left"
                    dataKey={tk}
                    stroke={COLORS[tk]}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Stats table */}
          <StatsTable stats={rawData?.stats ?? {}} tickers={statTickers} />

          {/* Context note */}
          <div style={{
            marginTop: 16, padding: "12px 16px",
            border: `1px solid ${GRID}`, borderRadius: 6,
            background: "#07111f", fontSize: 10, color: GREY,
            lineHeight: 1.6, letterSpacing: "0.03em",
          }}>
            <span style={{ color: LABEL, fontWeight: 600 }}>MOVE</span> (Merrill Lynch Option Volatility Estimate)
            measures Treasury implied volatility across maturities.
            Thresholds: <span style={{ color: GREEN }}>Investable &lt; {MOVE_INVESTABLE}</span>
            {" · "}Choppy {MOVE_INVESTABLE}–{MOVE_DANGER}
            {" · "}<span style={{ color: RED }}>Danger &ge; {MOVE_DANGER}</span>
          </div>
        </div>
      )}
    </div>
  );
}
