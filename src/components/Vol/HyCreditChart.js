import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { fetchHyCreditHistory } from "../../services/api";

// ── Palette ──────────────────────────────────────────────────────────────────
const COLORS = {
  OAS: "#4e8fde",
  HYG: "#c8d8e8",
};

const GRID    = "#1a2a3a";
const TEXT    = "#8899aa";
const LABEL   = "#c8d8e8";
const GREEN   = "#00e5a0";
const RED     = "#ff4d6d";
const BLUE    = "#4e8fde";

const LABELS = {
  OAS: "HY OAS",
  HYG: "HYG",
};

// OAS regime thresholds (bps)
const OAS_TIGHT  = 300;
const OAS_STRESS = 500;

// ── Helpers ──────────────────────────────────────────────────────────────────
function getJanTicks(dates) {
  const seen = new Set();
  return dates.filter(d => {
    const [yr, mo] = d.split("-");
    if (mo === "01" && !seen.has(yr)) { seen.add(yr); return true; }
    return false;
  });
}

function fmtBps(v) {
  if (v == null) return "—";
  return Math.round(v) + " bps";
}

function fmtPrice(v) {
  if (v == null) return "—";
  return "$" + v.toFixed(2);
}

function fmtDeltaBps(v) {
  if (v == null) return "—";
  const bps = Math.round(v);
  return (bps > 0 ? "+" : "") + bps + " bps";
}

function fmtDeltaPrice(v) {
  if (v == null) return "—";
  return (v > 0 ? "+" : "") + v.toFixed(2);
}

function fmtPct(v) {
  if (v == null) return "—";
  return (v > 0 ? "+" : "") + v.toFixed(1) + "%";
}

function oasDeltaColor(v) {
  if (v == null) return TEXT;
  if (v > 0) return RED;
  if (v < 0) return GREEN;
  return TEXT;
}

function priceDeltaColor(v) {
  if (v == null) return TEXT;
  if (v > 0) return GREEN;
  if (v < 0) return RED;
  return TEXT;
}

function getOasRegime(oas) {
  if (oas == null) return { label: "—", color: TEXT };
  if (oas < OAS_TIGHT) return { label: "TIGHT", color: GREEN };
  if (oas < OAS_STRESS) return { label: "NORMAL", color: "#f0b429" };
  return { label: "STRESS", color: RED };
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
  const entries = payload.filter(p => p.value != null);
  return (
    <div style={{
      background: "#0d1f33", border: "1px solid #1a2a3a",
      borderRadius: 6, padding: "8px 12px", fontSize: 11,
    }}>
      <div style={{ color: LABEL, marginBottom: 6, fontWeight: 600 }}>{label}</div>
      {entries.map(p => (
        <div key={p.dataKey} style={{ color: COLORS[p.dataKey] ?? TEXT, marginBottom: 2 }}>
          {LABELS[p.dataKey] ?? p.dataKey}:{" "}
          {p.dataKey === "OAS" ? fmtBps(p.value) : fmtPrice(p.value)}
        </div>
      ))}
    </div>
  );
}

// ── Stats table ───────────────────────────────────────────────────────────────
function StatsTable({ stats }) {
  const cols = [
    { key: "last",  label: "Last" },
    { key: "day1",  label: "Prior Day" },
    { key: "wk1",   label: "1 Wk Ago" },
    { key: "mo1",   label: "1 Mo Ago" },
    { key: "mo3",   label: "3 Mo Ago" },
  ];
  const changeCols = [
    { dKey: "dod_delta", pKey: "dod_pct", label: "DoD" },
    { dKey: "wow_delta", pKey: "wow_pct", label: "WoW" },
    { dKey: "mom_delta", pKey: "mom_pct", label: "MoM" },
  ];

  const tickers = ["OAS", "HYG"].filter(tk => stats[tk] != null);

  const thStyle = {
    padding: "6px 10px", fontSize: 9, fontWeight: 700,
    letterSpacing: "0.1em", color: TEXT, textAlign: "right",
    borderBottom: `1px solid ${GRID}`, whiteSpace: "nowrap",
  };
  const tdStyle = {
    padding: "5px 10px", fontSize: 11, textAlign: "right",
    fontVariantNumeric: "tabular-nums", color: LABEL,
    borderBottom: `1px solid ${GRID}`,
  };

  const fmtVal = (tk, v) => tk === "OAS" ? fmtBps(v) : fmtPrice(v);
  const fmtDelta = (tk, v) => tk === "OAS" ? fmtDeltaBps(v) : fmtDeltaPrice(v);
  const dColor = (tk, v) => tk === "OAS" ? oasDeltaColor(v) : priceDeltaColor(v);

  return (
    <div style={{
      border: `1px solid ${GRID}`, borderRadius: 6,
      background: "#07111f", overflowX: "auto", marginTop: 20,
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
              <th key={c.key} style={{ ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#445566", fontSize: 8 }}>
                level
              </th>
            ))}
            {changeCols.map(c => (
              <React.Fragment key={c.dKey}>
                <th style={{ ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#445566", fontSize: 8 }}>{"Δ"}</th>
                <th style={{ ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#445566", fontSize: 8 }}>%{"Δ"}</th>
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
                    {s ? fmtVal(tk, s[c.key]) : "—"}
                  </td>
                ))}
                {changeCols.map(c => (
                  <React.Fragment key={c.dKey}>
                    <td style={{ ...tdStyle, color: s ? dColor(tk, s[c.dKey]) : TEXT }}>
                      {s ? fmtDelta(tk, s[c.dKey]) : "—"}
                    </td>
                    <td style={{ ...tdStyle, color: s ? dColor(tk, s[c.pKey]) : TEXT }}>
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
      <span style={{ fontSize: 10, color: TEXT, letterSpacing: "0.04em" }}>
        {label}
      </span>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function HyCreditChart() {
  const [rawData,  setRawData]  = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(false);
  const [range,    setRange]    = useState("2y");

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    const res = await fetchHyCreditHistory();
    if (!res || !res.dates?.length) {
      setError(true);
      setLoading(false);
      return;
    }
    setRawData(res);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const hasOAS = rawData?.series?.OAS?.length > 0;
  const hasHYG = rawData?.series?.HYG?.length > 0;

  const allRows = useMemo(() => {
    if (!rawData) return [];
    return rawData.dates.map((d, i) => {
      const row = { date: d };
      if (hasOAS) row.OAS = rawData.series.OAS[i] ?? null;
      if (hasHYG) row.HYG = rawData.series.HYG[i] ?? null;
      return row;
    });
  }, [rawData, hasOAS, hasHYG]);

  const displayData = useMemo(() => {
    if (range === "max" || allRows.length === 0) return allRows;
    const cutoff = new Date();
    cutoff.setFullYear(cutoff.getFullYear() - 2);
    const cutoffStr = cutoff.toISOString().slice(0, 10);
    return allRows.filter(r => r.date >= cutoffStr);
  }, [allRows, range]);

  const janTicks = useMemo(() => getJanTicks(displayData.map(r => r.date)), [displayData]);

  const currentOAS = rawData?.stats?.OAS?.last;
  const regime = getOasRegime(currentOAS);

  return (
    <div style={{
      minHeight: "100vh",
      background: "#060e1a",
      padding: "28px 164px",
      boxSizing: "border-box",
    }}>

      {/* ── Header ── */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
          <h1 style={{
            margin: 0, fontSize: 18, fontWeight: 700,
            letterSpacing: "0.06em", color: "#e8f4ff",
          }}>
            HY CREDIT
          </h1>
          <span style={{ fontSize: 11, color: TEXT, letterSpacing: "0.05em" }}>
            HIGH YIELD OPTION-ADJUSTED SPREAD + HYG
          </span>
          {currentOAS != null && (
            <span style={{
              fontSize: 12, fontWeight: 700,
              color: regime.color,
              letterSpacing: "0.06em",
            }}>
              {regime.label} &middot; {Math.round(currentOAS)} bps
            </span>
          )}
          {rawData?.updated && (
            <span style={{ fontSize: 10, color: TEXT, marginLeft: "auto" }}>
              EOD &middot; {rawData.updated}
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
          No data &mdash; confirm FRED_API_KEY is set and HYG has price data.
        </div>
      )}

      {/* ── Chart + Table ── */}
      {!loading && !error && displayData.length > 0 && (
        <div>
          {/* Legend + Range toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 14, paddingLeft: 4, flexWrap: "wrap" }}>
            {hasOAS && <LegendDot color={COLORS.OAS} label="HY OAS (bps)" />}
            {hasHYG && <LegendDot color={COLORS.HYG} label="HYG ($)" />}
            <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 9, color: TEXT }}>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ width: 16, height: 0, borderTop: "1px dashed #00e5a0" }} />
                Tight ({OAS_TIGHT})
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ width: 16, height: 0, borderTop: "1px dashed #ff4d6d" }} />
                Stress ({OAS_STRESS})
              </span>
            </div>
            <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
              {["2y", "max"].map(r => (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  style={{
                    padding: "3px 10px", fontSize: 9, fontWeight: 700,
                    letterSpacing: "0.1em",
                    background: range === r ? "rgba(0,229,160,0.12)" : "transparent",
                    border: `1px solid ${range === r ? "#00e5a0" : "#1a2a3a"}`,
                    borderRadius: 3,
                    color: range === r ? "#00e5a0" : "#8899aa",
                    cursor: "pointer", fontFamily: "inherit",
                  }}
                >
                  {r === "2y" ? "2Y" : "MAX"}
                </button>
              ))}
            </div>
          </div>

          {/* Chart */}
          <div style={{
            border: `1px solid ${GRID}`, borderRadius: 6,
            padding: "16px 0 8px 0", background: "#07111f",
          }}>
            <ResponsiveContainer width="100%" height={480}>
              <ComposedChart data={displayData} margin={{ top: 8, right: 56, left: 0, bottom: 8 }}>
                <CartesianGrid stroke={GRID} strokeDasharray="3 3" />

                <XAxis
                  dataKey="date"
                  ticks={janTicks}
                  tick={<XTick />}
                  tickLine={false}
                  axisLine={{ stroke: GRID }}
                  interval={0}
                />

                {/* Left axis — OAS (bps) */}
                {hasOAS && (
                  <YAxis
                    yAxisId="left"
                    orientation="left"
                    tickFormatter={v => `${Math.round(v)}`}
                    tick={{ fontSize: 10, fill: COLORS.OAS }}
                    tickLine={false}
                    axisLine={false}
                    domain={["auto", "auto"]}
                    width={44}
                  />
                )}

                {/* Right axis — HYG ($) */}
                {hasHYG && (
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    tickFormatter={v => `$${v}`}
                    tick={{ fontSize: 10, fill: COLORS.HYG }}
                    tickLine={false}
                    axisLine={false}
                    domain={["auto", "auto"]}
                    width={50}
                  />
                )}

                <Tooltip content={<ChartTooltip />} />

                {/* Threshold reference lines on OAS axis */}
                {hasOAS && (
                  <ReferenceLine
                    yAxisId="left"
                    y={OAS_TIGHT}
                    stroke="#00e5a0"
                    strokeDasharray="4 4"
                    strokeWidth={1}
                    strokeOpacity={0.5}
                  />
                )}
                {hasOAS && (
                  <ReferenceLine
                    yAxisId="left"
                    y={OAS_STRESS}
                    stroke="#ff4d6d"
                    strokeDasharray="4 4"
                    strokeWidth={1}
                    strokeOpacity={0.5}
                  />
                )}

                {/* OAS line */}
                {hasOAS && (
                  <Line
                    yAxisId="left"
                    dataKey="OAS"
                    stroke={COLORS.OAS}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls={true}
                  />
                )}

                {/* HYG line */}
                {hasHYG && (
                  <Line
                    yAxisId={hasOAS ? "right" : "left"}
                    dataKey="HYG"
                    stroke={COLORS.HYG}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls={true}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Stats table */}
          <StatsTable stats={rawData?.stats ?? {}} />

          {/* Context note */}
          <div style={{
            marginTop: 16, padding: "12px 16px",
            border: `1px solid ${GRID}`, borderRadius: 6,
            background: "#07111f", fontSize: 10, color: TEXT,
            lineHeight: 1.6, letterSpacing: "0.03em",
          }}>
            <span style={{ color: LABEL, fontWeight: 600 }}>HY OAS</span> (ICE BofA US High Yield Option-Adjusted Spread)
            measures the credit spread investors demand above Treasuries for holding junk bonds.
            Widening = risk aversion / credit stress; tightening = risk appetite / benign conditions.
            {" "}
            <span style={{ color: LABEL, fontWeight: 600 }}>HYG</span> tracks the iBoxx $ Liquid High Yield Index
            — moves inversely to OAS (spreads widen → HYG drops).
            {" "}Thresholds: <span style={{ color: GREEN }}>Tight &lt; {OAS_TIGHT} bps</span>
            {" · "}Normal {OAS_TIGHT}–{OAS_STRESS} bps
            {" · "}<span style={{ color: RED }}>Stress &ge; {OAS_STRESS} bps</span>
            {" · "}Source: FRED ({_FRED_HY_OAS}).
          </div>
        </div>
      )}
    </div>
  );
}

const _FRED_HY_OAS = "BAMLH0A0HYM2";
