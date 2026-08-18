import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { fetchYieldCurveHistory } from "../../services/api";
import { GREEN, RED, GREY, LABEL, GRID } from "../../styles/tokens";

// ── Palette ──────────────────────────────────────────────────────────────────
const COLORS = {
  TWO:    "#c8d8e8",   // lightest — 2Y yield
  TNX:    "#8899aa",   // grey — 10Y yield (matches NazVol)
  SPREAD: "#4e8fde",   // blue — 2-10 spread
};

const LABELS = {
  TWO:    "2Y Yield",
  TNX:    "10Y Yield",
  SPREAD: "2-10 Spread",
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

function fmtYield(v) {
  if (v == null) return "—";
  return v.toFixed(2) + "%";
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

function spreadDeltaColor(v) {
  if (v == null) return GREY;
  if (v > 0) return GREEN;
  if (v < 0) return RED;
  return GREY;
}

// ── X-axis tick ─────────────────────────────────────────────────────────────
function XTick({ x, y, payload }) {
  if (!payload?.value) return null;
  const [yr] = payload.value.split("-");
  return (
    <text x={x} y={y + 12} textAnchor="middle" fontSize={10} fill={GREY}>
      {yr}
    </text>
  );
}

// ── Tooltip ─────────────────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const entries = payload.filter(p => p.value != null);
  return (
    <div style={{
      background: "#0d1f33", border: "1px solid #1a2a3a",
      borderRadius: 6, padding: "8px 12px", fontSize: 11,
    }}>
      <div style={{ color: LABEL, marginBottom: 6, fontWeight: 600 }}>{label}</div>
      {entries.map(p => {
        const isSp = p.dataKey === "SPREAD";
        const val = isSp
          ? `${(p.value * 100).toFixed(0)} bps`
          : `${p.value.toFixed(2)}%`;
        return (
          <div key={p.dataKey} style={{ color: COLORS[p.dataKey] ?? GREY, marginBottom: 2 }}>
            {LABELS[p.dataKey] ?? p.dataKey}: {val}
          </div>
        );
      })}
    </div>
  );
}

// ── Stats table ─────────────────────────────────────────────────────────────
function StatsTable({ stats, tickers }) {
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

  const thStyle = {
    padding: "6px 10px", fontSize: 9, fontWeight: 700,
    letterSpacing: "0.1em", color: GREY, textAlign: "center",
    borderBottom: `1px solid ${GRID}`, whiteSpace: "nowrap",
  };
  const tdStyle = {
    padding: "5px 10px", fontSize: 11, textAlign: "center",
    fontVariantNumeric: "tabular-nums",
    fontFamily: "'Menlo', 'Consolas', monospace",
    color: LABEL,
    borderBottom: `1px solid ${GRID}`,
  };

  return (
    <div style={{
      border: `1px solid ${GRID}`, borderRadius: 6,
      background: "#07111f", overflowX: "auto", marginTop: 20,
    }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ ...thStyle, textAlign: "left", width: 100 }}>Series</th>
            {cols.map(c => <th key={c.key} style={thStyle}>{c.label}</th>)}
            {changeCols.map(c => (
              <th key={c.label} style={thStyle} colSpan={2}>{c.label}</th>
            ))}
          </tr>
          <tr>
            <th style={{ ...thStyle, borderBottom: `2px solid ${GRID}` }} />
            {cols.map(c => (
              <th key={c.key} style={{ ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#8899aa", fontSize: 8 }}>
                yield
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
            const isSp = tk === "SPREAD";
            const rowBg = i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)";
            const dColorFn = isSp ? spreadDeltaColor : deltaColor;
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
                    {s ? (isSp ? fmtBps(s[c.key]) : fmtYield(s[c.key])) : "—"}
                  </td>
                ))}
                {changeCols.map(c => (
                  <React.Fragment key={c.dKey}>
                    <td style={{ ...tdStyle, color: s ? dColorFn(s[c.dKey]) : GREY }}>
                      {s ? fmtBps(s[c.dKey]) : "—"}
                    </td>
                    <td style={{ ...tdStyle, color: s ? dColorFn(s[c.pKey]) : GREY }}>
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

// ── Legend dot ───────────────────────────────────────────────────────────────
function LegendDot({ color, label, dashed }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{
        width: 16, height: 0,
        borderTop: dashed ? `2px dashed ${color}` : `2px solid ${color}`,
      }} />
      <span style={{ fontSize: 10, color: GREY, letterSpacing: "0.04em" }}>
        {label}
      </span>
    </div>
  );
}

// ── Main component ──────────────────────────────────────────────────────────
export default function YieldCurveChart() {
  const [rawData,  setRawData]  = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(false);
  const [range,    setRange]    = useState("2y");

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    const res = await fetchYieldCurveHistory();
    if (!res || !res.dates?.length) {
      setError(true);
      setLoading(false);
      return;
    }
    setRawData(res);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const yieldTickers = useMemo(() => {
    if (!rawData?.series) return [];
    return ["TWO", "TNX"].filter(tk => rawData.series[tk]?.length > 0);
  }, [rawData]);

  const hasSpread = useMemo(() => {
    return rawData?.series?.SPREAD?.length > 0;
  }, [rawData]);

  const statTickers = useMemo(() => {
    if (!rawData?.stats) return [];
    return ["TWO", "TNX", "SPREAD"].filter(tk => rawData.stats[tk] != null);
  }, [rawData]);

  const allRows = useMemo(() => {
    if (!rawData) return [];
    return rawData.dates.map((d, i) => {
      const row = { date: d };
      ["TWO", "TNX", "SPREAD"].forEach(tk => {
        row[tk] = rawData.series[tk]?.[i] ?? null;
      });
      return row;
    });
  }, [rawData]);

  const displayData = useMemo(() => {
    if (range === "max" || allRows.length === 0) return allRows;
    const cutoff = new Date();
    cutoff.setFullYear(cutoff.getFullYear() - 2);
    const cutoffStr = cutoff.toISOString().slice(0, 10);
    return allRows.filter(r => r.date >= cutoffStr);
  }, [allRows, range]);

  const janTicks = useMemo(() => getJanTicks(displayData.map(r => r.date)), [displayData]);

  const spreadLast = rawData?.stats?.SPREAD?.last;
  const isInverted = spreadLast != null && spreadLast < 0;

  return (
    <div style={{
      minHeight: "100vh", background: "#060e1a",
      padding: "28px 164px", boxSizing: "border-box",
    }}>
      {/* ── Header ── */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
          <h1 style={{
            margin: 0, fontSize: 18, fontWeight: 700,
            letterSpacing: "0.06em", color: "#e8f4ff",
          }}>
            YIELD CURVE
          </h1>
          <span style={{ fontSize: 11, color: GREY, letterSpacing: "0.05em" }}>
            2-YEAR &middot; 10-YEAR TREASURY YIELDS &amp; SPREAD
          </span>
          {spreadLast != null && (
            <span style={{
              fontSize: 12, fontWeight: 700, letterSpacing: "0.05em",
              color: isInverted ? RED : GREEN, marginLeft: 8,
            }}>
              {isInverted ? "INVERTED" : "NORMAL"} &middot; {(spreadLast * 100).toFixed(0)} bps
            </span>
          )}
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
          No data &mdash; run REFRESH DATA on the dashboard first.
        </div>
      )}

      {/* ── Chart + Table ── */}
      {!loading && !error && displayData.length > 0 && (
        <div>
          {/* Legend + Range toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 14, paddingLeft: 4, flexWrap: "wrap" }}>
            {yieldTickers.map(tk => (
              <LegendDot key={tk} color={COLORS[tk]} label={LABELS[tk]} />
            ))}
            {hasSpread && (
              <LegendDot color={COLORS.SPREAD} label={LABELS.SPREAD} />
            )}
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

                {/* Left axis — yield % */}
                <YAxis
                  yAxisId="left"
                  orientation="left"
                  tickFormatter={v => `${v}%`}
                  tick={{ fontSize: 10, fill: GREY }}
                  tickLine={false}
                  axisLine={false}
                  domain={["auto", "auto"]}
                  width={46}
                />

                {/* Right axis — spread (percentage points) */}
                {hasSpread && (
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    tickFormatter={v => `${(v * 100).toFixed(0)}`}
                    tick={{ fontSize: 10, fill: COLORS.SPREAD }}
                    tickLine={false}
                    axisLine={false}
                    domain={["dataMin", "dataMax"]}
                    width={36}
                    label={{
                      value: "bps",
                      position: "top",
                      offset: -4,
                      style: { fontSize: 8, fill: COLORS.SPREAD, letterSpacing: "0.1em" },
                    }}
                  />
                )}

                <Tooltip content={<ChartTooltip />} />

                {/* Zero line for spread */}
                {hasSpread && (
                  <ReferenceLine
                    yAxisId="right"
                    y={0}
                    stroke={GREY}
                    strokeDasharray="4 4"
                    strokeWidth={1}
                    strokeOpacity={0.5}
                  />
                )}

                {/* Yield lines */}
                {yieldTickers.map(tk => (
                  <Line
                    key={tk}
                    yAxisId="left"
                    dataKey={tk}
                    stroke={COLORS[tk]}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls={true}
                  />
                ))}

                {/* Spread area — filled below zero (inversion) */}
                {hasSpread && (
                  <Area
                    yAxisId="right"
                    dataKey="SPREAD"
                    stroke={COLORS.SPREAD}
                    strokeWidth={1.5}
                    fill={COLORS.SPREAD}
                    fillOpacity={0.08}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls={true}
                  />
                )}
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
            The <span style={{ color: LABEL, fontWeight: 600 }}>2-10 Spread</span> (10Y minus 2Y yield)
            is the market&rsquo;s primary curve shape signal.
            {" "}<span style={{ color: GREEN }}>Positive</span> = normal (long-term rates above short-term).
            {" "}<span style={{ color: RED }}>Negative</span> = inverted &mdash; historically precedes recessions
            and signals tight monetary policy.
          </div>
        </div>
      )}
    </div>
  );
}
