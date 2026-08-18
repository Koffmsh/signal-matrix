import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";
import { fetchCorrelations } from "../../services/api";
import { LABEL, GREEN, RED, AMBER } from "../../styles/tokens";

const GRID  = "#1a2a3a";
const TEXT  = "#8899aa";

const WINDOWS = ["15D", "30D", "90D", "120D", "180D"];

function corrColor(v) {
  if (v == null) return TEXT;
  const abs = Math.abs(v);
  if (abs >= 0.70) return v > 0 ? GREEN : RED;
  if (abs >= 0.50) return v > 0 ? "#66eebb" : "#ff8da6";
  return LABEL;
}

function corrCellColor(v) {
  if (v == null) return LABEL;
  const abs = Math.abs(v);
  if (abs >= 0.50) return "#0a1628";
  return LABEL;
}

function corrCellWeight(v) {
  if (v == null) return 400;
  return Math.abs(v) >= 0.50 ? 700 : 400;
}

function corrBg(v) {
  if (v == null) return "transparent";
  const abs = Math.abs(v);
  if (abs >= 0.70) return v > 0 ? GREEN : RED;
  if (abs >= 0.50) return v > 0 ? "#66eebb" : "#ff8da6";
  return "transparent";
}

function fmtCorr(v) {
  if (v == null) return "—";
  return v.toFixed(2);
}

function fmtPct(v) {
  if (v == null) return "—";
  return v + "%";
}

const Q_COLORS = { 1: "#007a55", 2: "#00e5a0", 3: "#f0b429", 4: "#ff4d6d" };

function quadTooltip(dxy) {
  const align = dxy.quad_alignment;
  const score = dxy.quad_score;
  const genericSectors = ["Index", "Broad Market", "Equities"];
  const sectorLabel = dxy.sector && !genericSectors.includes(dxy.sector)
    ? dxy.sector : dxy.asset_class || "this asset class";

  if (align === "Neutral" || !align)
    return `No strong historical edge for ${sectorLabel} in the current macro environment.`;

  const structDir = dxy.trade_dir !== "Neutral" ? dxy.trade_dir
                  : dxy.trend_dir !== "Neutral" ? dxy.trend_dir : null;
  const isBestForSector = align === "Best"
    || (align === "Aligned" && structDir === "Bullish")
    || (align === "Misaligned" && structDir === "Bearish");
  const envLine = isBestForSector
    ? `${sectorLabel} historically perform well in the current macro environment.`
    : `${sectorLabel} historically perform poorly in the current macro environment.`;

  let structLine = "";
  if (score > 0) structLine = " The macro environment supports current price structure.";
  else if (score < 0 && structDir) structLine = ` Currently working against ${structDir.toLowerCase()} price structure.`;
  else if (score === 0 && !structDir) structLine = " No directional structure to align with yet.";
  else if (score === 0 && structDir) structLine = ` Currently working against ${structDir.toLowerCase()} price structure.`;
  return envLine + structLine;
}

function DxySection({ dxy, navigate }) {
  const chartData = (dxy.chart_dates || []).map((d, i) => ({
    date: d,
    close: dxy.chart_closes?.[i] ?? null,
  }));

  const vp = dxy.viewpoint || "Neutral";
  const conv = dxy.conviction;
  const trendDir = dxy.trend_dir || "Neutral";
  const quadNum = dxy.quad;
  const qColor = Q_COLORS[quadNum] || TEXT;

  return (
    <div style={{
      marginTop: 24, border: `1px solid ${GRID}`, borderRadius: 6,
      background: "#07111f", padding: "16px 20px",
    }}>
      {/* Header row */}
      <div style={{
        display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap",
        marginBottom: 14,
      }}>
        <span
          onClick={() => navigate("/security/DXY")}
          style={{
            fontSize: 15, fontWeight: 700, letterSpacing: "0.06em",
            color: "#e8f4ff", cursor: "pointer",
          }}
          onMouseEnter={e => { e.target.style.color = "#2196F3"; e.target.style.textDecoration = "underline"; }}
          onMouseLeave={e => { e.target.style.color = "#e8f4ff"; e.target.style.textDecoration = "none"; }}
        >
          $DXY — US DOLLAR INDEX
        </span>

        <span style={{ fontSize: 14, fontWeight: 600, color: LABEL }}>
          {dxy.close != null ? dxy.close.toFixed(2) : "—"}
        </span>

        {/* Viewpoint */}
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ fontSize: 9, fontWeight: 700, color: TEXT, letterSpacing: "0.1em" }}>VIEWPOINT</span>
          <span style={{ fontSize: 12, fontWeight: 700, color: viewpointColor(vp) }}>{vp}</span>
        </span>

        {/* Trend */}
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ fontSize: 9, fontWeight: 700, color: TEXT, letterSpacing: "0.1em" }}>TREND</span>
          <span style={{ fontSize: 12, fontWeight: 700, color: viewpointColor(trendDir) }}>{trendDir}</span>
        </span>

        {/* Conviction */}
        {conv != null && conv >= 45 && (
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ fontSize: 9, fontWeight: 700, color: TEXT, letterSpacing: "0.1em" }}>CONVICTION</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: viewpointColor(vp) }}>{Math.round(conv)}%</span>
          </span>
        )}

        {/* Quad */}
        {quadNum && (
          <span style={{ display: "flex", alignItems: "center", gap: 5 }} title={quadTooltip(dxy)}>
            <span style={{ fontSize: 9, fontWeight: 700, color: TEXT, letterSpacing: "0.1em" }}>QUAD</span>
            <span style={{
              fontSize: 10, fontWeight: 700, color: "#fff",
              background: qColor + "55", border: `1px solid ${qColor}`,
              borderRadius: 3, padding: "1px 6px",
            }}>
              Q{quadNum}
            </span>
            <span style={{ fontSize: 14, color: TEXT, cursor: "help" }}>&#9432;</span>
          </span>
        )}

        {/* Security link */}
        <span
          onClick={() => navigate("/security/DXY")}
          style={{
            fontSize: 10, fontWeight: 600, color: "#4e8fde",
            cursor: "pointer", letterSpacing: "0.05em",
          }}
          onMouseEnter={e => { e.target.style.color = "#2196F3"; e.target.style.textDecoration = "underline"; }}
          onMouseLeave={e => { e.target.style.color = "#4e8fde"; e.target.style.textDecoration = "none"; }}
        >
          VIEW DETAIL →
        </span>
      </div>

      {/* Chart */}
      {chartData.length > 0 && (
        <div style={{ height: 200 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
              <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} yAxisId="left" />
              <XAxis
                dataKey="date" tick={{ fontSize: 9, fill: TEXT }}
                tickLine={false} axisLine={{ stroke: GRID }}
                tickFormatter={d => {
                  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
                  return months[parseInt(d.slice(5, 7), 10) - 1] + " " + d.slice(2, 4);
                }}
                interval={Math.max(1, Math.floor(chartData.length / 10))}
              />
              <YAxis
                yAxisId="left"
                domain={[d => Math.floor(d - 0.5), d => Math.ceil(d + 0.5)]}
                tick={{ fontSize: 9, fill: TEXT }}
                tickLine={false} axisLine={false} width={42}
              />
              <YAxis
                yAxisId="right" orientation="right"
                domain={[d => Math.floor(d - 0.5), d => Math.ceil(d + 0.5)]}
                tick={{ fontSize: 9, fill: TEXT }}
                tickLine={false} axisLine={false} width={42}
              />
              <Tooltip
                contentStyle={{
                  background: "#0c1a2e", border: `1px solid ${GRID}`,
                  borderRadius: 4, fontSize: 11, color: LABEL,
                }}
                formatter={v => [v?.toFixed(2), "DXY"]}
                labelFormatter={l => l}
              />
              <Area
                yAxisId="left"
                type="monotone" dataKey="close" fill="#4e8fde" fillOpacity={0.08}
                stroke="none" connectNulls
                tooltipType="none"
              />
              <Line
                yAxisId="left"
                type="monotone" dataKey="close" stroke="#c8d8e8" strokeWidth={1.5}
                dot={false} connectNulls name="DXY"
              />
              <Line
                yAxisId="right"
                type="monotone" dataKey="close" stroke="transparent" strokeWidth={0}
                dot={false} connectNulls
                tooltipType="none" legendType="none"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}


function viewpointColor(vp) {
  if (vp === "Bullish") return GREEN;
  if (vp === "Bearish") return RED;
  return TEXT;
}

export default function KeyCorrelations() {
  const navigate = useNavigate();
  const cachedLive = sessionStorage.getItem("correlationsLive");
  const [snapshots, setSnapshots] = useState({ eod: null, live: cachedLive ? JSON.parse(cachedLive) : null });
  const [active, setActive] = useState(cachedLive ? "live" : "eod");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    const res = await fetchCorrelations();
    if (!res || !res.rows?.length) {
      setError(true);
      setLoading(false);
      return;
    }
    setSnapshots(prev => ({ ...prev, eod: res }));
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleLive = async () => {
    setRefreshing(true);
    try {
      const res = await fetchCorrelations(true);
      if (res && res.rows?.length) {
        setSnapshots(prev => ({ ...prev, live: res }));
        setActive("live");
        sessionStorage.setItem("correlationsLive", JSON.stringify(res));
      }
    } catch (e) {
      console.warn("Live fetch failed", e);
    } finally {
      setRefreshing(false);
    }
  };

  const data = snapshots[active] || snapshots.eod;

  const nowET = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" }));
  const dayOfWeek = nowET.getDay();
  const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5;
  const pastEOD = isWeekday && nowET.getHours() >= 16;
  const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
  const liveDisabled = pastEOD || isWeekend;

  const thStyle = {
    padding: "6px 10px", fontSize: 9, fontWeight: 700,
    letterSpacing: "0.1em", color: TEXT, textAlign: "center",
    borderBottom: `1px solid ${GRID}`, whiteSpace: "nowrap",
  };
  const tdStyle = {
    padding: "5px 10px", fontSize: 11, textAlign: "center",
    fontVariantNumeric: "tabular-nums", color: LABEL,
    borderBottom: `1px solid ${GRID}`,
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: "#060e1a",
      padding: "28px 164px",
      boxSizing: "border-box",
    }}>

      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
          <h1 style={{
            margin: 0, fontSize: 18, fontWeight: 700,
            letterSpacing: "0.06em", color: "#e8f4ff",
          }}>
            KEY $USD CORRELATIONS
          </h1>
          <span style={{ fontSize: 11, color: TEXT, letterSpacing: "0.05em" }}>
            ROLLING CORRELATIONS vs {data?.base ?? "DXY"}
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 10, flexWrap: "wrap", gap: 12 }}>
          {data?.updated && (
            <span style={{ fontSize: 10, color: TEXT }}>
              {active === "live" && data.refreshed_at ? `Live · ${data.refreshed_at}` : `EOD · ${data.updated}`}
            </span>
          )}
          {!data?.updated && <div />}

          <div style={{ display: "flex", gap: 6 }}>
            {[
              { key: "eod",  label: "EOD" },
              { key: "live", label: "LIVE" },
            ].map(({ key, label }) => {
              const available = !!snapshots[key];
              const isActive = active === key;
              const disabled = key === "live" && (refreshing || liveDisabled);
              const eodDateTag = key === "eod" && snapshots.eod?.updated
                ? (() => { const parts = snapshots.eod.updated.split(" ")[0].split("/"); return ` ${parseInt(parts[0])}/${parseInt(parts[1])}`; })()
                : "";
              return (
                <button
                  key={key}
                  onClick={() => {
                    if (disabled) return;
                    if (key === "live") {
                      handleLive();
                    } else {
                      setActive(key);
                    }
                  }}
                  disabled={disabled}
                  style={{
                    padding: "4px 12px",
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: "0.1em",
                    borderRadius: 4,
                    border: `1px solid ${isActive ? GREEN : GRID}`,
                    background: isActive ? "rgba(0, 229, 160, 0.1)" : "transparent",
                    color: isActive ? GREEN : available ? TEXT : "#556677",
                    cursor: disabled ? "default" : (key === "live" && refreshing) ? "wait" : "pointer",
                    transition: "all 150ms ease",
                  }}
                >
                  {key === "live" && refreshing ? "⟳ FETCHING..." : label}
                  {key === "eod" && available && <span style={{ opacity: 0.7, marginLeft: 4 }}>{eodDateTag}</span>}
                  {key === "live" && snapshots.live?.refreshed_at && <span style={{ opacity: 0.7, marginLeft: 4 }}>{snapshots.live.refreshed_at}</span>}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* States */}
      {loading && (
        <div style={{ color: TEXT, fontSize: 13, padding: "60px 0", textAlign: "center" }}>
          Loading...
        </div>
      )}
      {error && !loading && (
        <div style={{ color: RED, fontSize: 13, padding: "60px 0", textAlign: "center" }}>
          No data &mdash; confirm DXY and correlation tickers have price history.
        </div>
      )}

      {/* Correlation Table */}
      {!loading && !error && data && (
        <div>
          <div style={{
            border: `1px solid ${GRID}`, borderRadius: 6,
            background: "#07111f", overflowX: "auto",
          }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ ...thStyle, textAlign: "left", width: 140 }}>METRIC</th>
                  {WINDOWS.map(w => (
                    <th key={w} style={thStyle}>{w}</th>
                  ))}
                  <th style={{ ...thStyle, borderLeft: `2px solid ${GRID}`, width: "10%" }}>High</th>
                  <th style={{ ...thStyle, width: "10%" }}>Low</th>
                  <th style={{ ...thStyle, width: "10%" }}>% Time Pos</th>
                  <th style={{ ...thStyle, width: "10%" }}>% Time Neg</th>
                </tr>
                <tr>
                  <th style={{ ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#8899aa", fontSize: 9 }} />
                  <th colSpan={WINDOWS.length} style={{
                    ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#8899aa", fontSize: 9,
                    textAlign: "center", fontStyle: "italic",
                  }}>
                    *Days = Trading Days
                  </th>
                  <th colSpan={4} style={{
                    ...thStyle, borderBottom: `2px solid ${GRID}`, borderLeft: `2px solid ${GRID}`,
                    color: "#8899aa", fontSize: 9, textAlign: "center",
                  }}>
                    52-Wk Rolling 30D Correlation
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row, i) => {
                  const d = row.data;
                  const rowBg = i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)";
                  return (
                    <tr key={row.ticker} style={{ background: rowBg }}>
                      <td style={{ ...tdStyle, textAlign: "left", fontWeight: 600 }}>
                        {row.label}
                      </td>
                      {WINDOWS.map(w => {
                        const v = d?.[w] ?? null;
                        return (
                          <td key={w} style={{
                            ...tdStyle,
                            color: corrCellColor(v),
                            background: corrBg(v),
                            fontWeight: corrCellWeight(v),
                          }}>
                            {fmtCorr(v)}
                          </td>
                        );
                      })}
                      <td style={{
                        ...tdStyle, borderLeft: `2px solid ${GRID}`,
                        color: corrColor(d?.rolling_high), fontWeight: 700,
                      }}>
                        {fmtCorr(d?.rolling_high)}
                      </td>
                      <td style={{
                        ...tdStyle,
                        color: corrColor(d?.rolling_low), fontWeight: 700,
                      }}>
                        {fmtCorr(d?.rolling_low)}
                      </td>
                      <td style={{ ...tdStyle, fontStyle: "italic" }}>
                        {fmtPct(d?.time_pos)}
                      </td>
                      <td style={{ ...tdStyle, fontStyle: "italic" }}>
                        {fmtPct(d?.time_neg)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Context note */}
          <div style={{
            marginTop: 16, padding: "12px 16px",
            border: `1px solid ${GRID}`, borderRadius: 6,
            background: "#07111f", fontSize: 10, color: TEXT,
            lineHeight: 1.6, letterSpacing: "0.03em",
          }}>
            <span style={{ color: LABEL, fontWeight: 600 }}>Key $USD Correlations</span> show
            rolling Pearson price-level correlations vs the US Dollar Index across multiple timeframes.
            {" "}
            <span style={{ color: GREEN }}>Green</span> = strong positive correlation (moves with DXY);
            {" "}<span style={{ color: RED }}>Red</span> = strong negative correlation (moves inversely to DXY).
            {" "}The 52-week rolling 30D window computes the 30-day correlation every trading day for the past year —
            High/Low shows the range, % Time Pos/Neg shows how often the relationship was positive vs negative.
          </div>

          {/* DXY Chart Section */}
          {data.dxy && <DxySection dxy={data.dxy} navigate={navigate} />}
        </div>
      )}
    </div>
  );
}
