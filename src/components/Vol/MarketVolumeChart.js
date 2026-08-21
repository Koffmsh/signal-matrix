import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";
import { fetchMarketVolumeHistory } from "../../services/api";
import { GREEN, RED, GREY, LABEL, GRID } from "../../styles/tokens";

// ── Palette ──────────────────────────────────────────────────────────────────
const COLORS = {
  UVOL: GREEN,
  DVOL: RED,
  AD:   "#4e8fde",
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

function fmtK(v) {
  if (v == null) return "—";
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(0) + "K";
  return v.toLocaleString();
}

function fmtPctCell(v) {
  if (v == null) return "—";
  return (v > 0 ? "+" : "") + v.toFixed(0) + "%";
}

function pctColor(v) {
  if (v == null) return GREY;
  return v < 0 ? RED : v > 0 ? GREEN : LABEL;
}

// ── X-axis tick ──────────────────────────────────────────────────────────────
function XTick({ x, y, payload }) {
  if (!payload?.value) return null;
  const [yr] = payload.value.split("-");
  return (
    <text x={x} y={y + 12} textAnchor="middle" fontSize={10} fill={GREY}>
      {yr}
    </text>
  );
}

// ── Volume Chart Tooltip ─────────────────────────────────────────────────────
function VolTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const uvol = payload.find(p => p.dataKey === "UVOL");
  const dvol = payload.find(p => p.dataKey === "DVOL");
  const uv = uvol?.value ?? 0;
  const dv = dvol?.value ?? 0;
  const total = uv + dv;
  const ratio = total > 0 ? (uv / dv).toFixed(2) : "—";
  return (
    <div style={{
      background: "#0d1f33", border: "1px solid #1a2a3a",
      borderRadius: 6, padding: "8px 12px", fontSize: 11,
    }}>
      <div style={{ color: LABEL, marginBottom: 6, fontWeight: 600 }}>{label}</div>
      <div style={{ color: GREEN, marginBottom: 2 }}>Up Vol: {fmtK(uv)}</div>
      <div style={{ color: RED, marginBottom: 2 }}>Down Vol: {fmtK(dv)}</div>
      <div style={{ color: GREY, marginBottom: 2 }}>Total: {fmtK(total)}</div>
      <div style={{ color: LABEL }}>Up/Down: {ratio}</div>
    </div>
  );
}

// ── A/D Line Tooltip ─────────────────────────────────────────────────────────
function ADTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const ad = payload.find(p => p.dataKey === "ad");
  const daily = payload.find(p => p.dataKey === "daily_add");
  return (
    <div style={{
      background: "#0d1f33", border: "1px solid #1a2a3a",
      borderRadius: 6, padding: "8px 12px", fontSize: 11,
    }}>
      <div style={{ color: LABEL, marginBottom: 6, fontWeight: 600 }}>{label}</div>
      {ad && <div style={{ color: COLORS.AD, marginBottom: 2 }}>Cumulative A/D: {fmtK(ad.value)}</div>}
      {daily && <div style={{ color: daily.value >= 0 ? GREEN : RED }}>Daily A/D: {daily.value >= 0 ? "+" : ""}{daily.value?.toFixed(0)}</div>}
    </div>
  );
}

// ── Hedgeye-style Volume Table ───────────────────────────────────────────────
function VolumeTable({ volumeTable }) {
  if (!volumeTable || Object.keys(volumeTable).length === 0) return null;

  const tickers = ["TVOL", "UVOL", "DVOL"].filter(t => volumeTable[t]);
  const cols = [
    { key: "prior_day", label: "Prior Day" },
    { key: "avg_1m",    label: "1M Ave" },
    { key: "avg_3m",    label: "3M Ave" },
    { key: "avg_1y",    label: "1Y Ave" },
  ];

  const thStyle = {
    padding: "8px 16px",
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: "0.1em",
    color: GREY,
    textAlign: "center",
    borderBottom: `1px solid ${GRID}`,
    whiteSpace: "nowrap",
  };
  const tdStyle = {
    padding: "8px 16px",
    fontSize: 14,
    textAlign: "center",
    fontWeight: 700,
    fontVariantNumeric: "tabular-nums",
    fontFamily: "'Menlo', 'Consolas', monospace",
    borderBottom: `1px solid ${GRID}`,
  };

  return (
    <div style={{
      border: `1px solid ${GRID}`,
      borderRadius: 6,
      background: "#07111f",
      overflowX: "auto",
      marginBottom: 28,
    }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ ...thStyle, textAlign: "left", width: 200, borderRight: `1px solid ${GRID}` }}>
              INDEX / SECURITY
            </th>
            <th colSpan={4} style={{
              ...thStyle,
              background: "#111c2e",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.08em",
              color: LABEL,
            }}>
              VOLUME vs.
            </th>
          </tr>
          <tr>
            <th style={{ ...thStyle, borderBottom: `2px solid ${GRID}`, borderRight: `1px solid ${GRID}` }} />
            {cols.map(c => (
              <th key={c.key} style={{ ...thStyle, borderBottom: `2px solid ${GRID}` }}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tickers.map((tk, i) => {
            const row = volumeTable[tk];
            const rowBg = i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)";
            return (
              <tr key={tk} style={{ background: rowBg }}>
                <td style={{
                  ...tdStyle,
                  textAlign: "left",
                  fontSize: 11,
                  fontWeight: 600,
                  color: LABEL,
                  borderRight: `1px solid ${GRID}`,
                }}>
                  {row.label}
                </td>
                {cols.map(c => (
                  <td key={c.key} style={{ ...tdStyle, color: pctColor(row[c.key]) }}>
                    {fmtPctCell(row[c.key])}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Breadth Stats Table ──────────────────────────────────────────────────────
function BreadthTable({ breadthTable }) {
  if (!breadthTable || Object.keys(breadthTable).length === 0) return null;

  const thStyle = {
    padding: "6px 10px",
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: "0.1em",
    color: GREY,
    textAlign: "center",
    borderBottom: `1px solid ${GRID}`,
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

  const add = breadthTable["ADD"];
  const advn = breadthTable["ADVN"];
  const decn = breadthTable["DECN"];

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
            <th style={{ ...thStyle, textAlign: "left", width: 140 }}>Metric</th>
            <th style={thStyle}>Value</th>
            <th style={thStyle}>% Share</th>
            <th style={thStyle}>A/D Ratio</th>
          </tr>
        </thead>
        <tbody>
          {advn && (
            <tr>
              <td style={{ ...tdStyle, textAlign: "left", fontWeight: 600, color: GREEN }}>
                Advancing Issues
              </td>
              <td style={{ ...tdStyle, color: GREEN }}>{advn.last?.toLocaleString()}</td>
              <td style={{ ...tdStyle, color: GREEN }}>{advn.pct != null ? advn.pct + "%" : "—"}</td>
              <td rowSpan={2} style={{ ...tdStyle, fontSize: 14, fontWeight: 700, color: add?.ratio >= 1 ? GREEN : RED }}>
                {add?.ratio != null ? add.ratio.toFixed(2) : "—"}
              </td>
            </tr>
          )}
          {decn && (
            <tr style={{ background: "rgba(255,255,255,0.015)" }}>
              <td style={{ ...tdStyle, textAlign: "left", fontWeight: 600, color: RED }}>
                Declining Issues
              </td>
              <td style={{ ...tdStyle, color: RED }}>{decn.last?.toLocaleString()}</td>
              <td style={{ ...tdStyle, color: RED }}>{decn.pct != null ? decn.pct + "%" : "—"}</td>
            </tr>
          )}
          {add && (
            <tr>
              <td style={{ ...tdStyle, textAlign: "left", fontWeight: 600 }}>Net A/D</td>
              <td style={{ ...tdStyle, color: add.last >= 0 ? GREEN : RED, fontWeight: 700 }}>
                {add.last >= 0 ? "+" : ""}{add.last?.toLocaleString()}
              </td>
              <td style={tdStyle}>—</td>
              <td style={tdStyle}>—</td>
            </tr>
          )}
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

// ── Range Toggle ─────────────────────────────────────────────────────────────
function RangeToggle({ range, setRange }) {
  return (
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
            border: `1px solid ${range === r ? GREEN : "#1a2a3a"}`,
            borderRadius: 3,
            color: range === r ? GREEN : GREY,
            cursor: "pointer",
            fontFamily: "inherit",
          }}
        >
          {r === "2y" ? "2Y" : "MAX"}
        </button>
      ))}
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
export default function MarketVolumeChart() {
  const [rawData,  setRawData]  = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(false);
  const [range,    setRange]    = useState("2y");

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    const res = await fetchMarketVolumeHistory();
    if (!res || (!res.volume_table && !res.ad_cumulative_dates?.length)) {
      setError(true);
      setLoading(false);
      return;
    }
    setRawData(res);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  // Build up/down volume chart data
  const volChartData = useMemo(() => {
    if (!rawData?.volume?.UVOL || !rawData?.volume?.DVOL) return [];
    const uv = rawData.volume.UVOL;
    const dv = rawData.volume.DVOL;
    // Use union of dates (they should be aligned)
    const dates = uv.dates.length >= dv.dates.length ? uv.dates : dv.dates;
    const uvMap = {};
    uv.dates.forEach((d, i) => { uvMap[d] = uv.closes[i]; });
    const dvMap = {};
    dv.dates.forEach((d, i) => { dvMap[d] = dv.closes[i]; });
    return dates.map(d => ({
      date: d,
      UVOL: uvMap[d] ?? null,
      DVOL: dvMap[d] ?? null,
    }));
  }, [rawData]);

  // Build A/D cumulative chart data
  const adChartData = useMemo(() => {
    if (!rawData?.ad_cumulative_dates?.length) return [];
    const addSeries = rawData.breadth?.ADD;
    return rawData.ad_cumulative_dates.map((d, i) => ({
      date: d,
      ad: rawData.ad_cumulative[i],
      daily_add: addSeries?.closes?.[i] ?? null,
    }));
  }, [rawData]);

  // Filter by range
  const filterByRange = useCallback((data) => {
    if (range === "max" || data.length === 0) return data;
    const cutoff = new Date();
    cutoff.setFullYear(cutoff.getFullYear() - 2);
    const cutoffStr = cutoff.toISOString().slice(0, 10);
    return data.filter(r => r.date >= cutoffStr);
  }, [range]);

  const displayVolData = useMemo(() => filterByRange(volChartData), [volChartData, filterByRange]);
  const displayAdData  = useMemo(() => filterByRange(adChartData), [adChartData, filterByRange]);

  const volJanTicks = useMemo(() => getJanTicks(displayVolData.map(r => r.date)), [displayVolData]);
  const adJanTicks  = useMemo(() => getJanTicks(displayAdData.map(r => r.date)), [displayAdData]);

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
            MKT VOLUME
          </h1>
          <span style={{ fontSize: 11, color: GREY, letterSpacing: "0.05em" }}>
            NYSE MARKET VOLUME &amp; BREADTH
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
          No data &mdash; run REFRESH DATA on the dashboard first to bootstrap NYSE breadth data.
        </div>
      )}

      {/* ── Content ── */}
      {!loading && !error && rawData && (
        <div>
          {/* Section A: Hedgeye-style volume table */}
          <VolumeTable volumeTable={rawData.volume_table} />

          {/* Section B: Up/Down Volume Chart */}
          {displayVolData.length > 0 && (
            <>
              <div style={{
                display: "flex", alignItems: "center", gap: 16,
                marginBottom: 10, marginTop: 8,
              }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: LABEL, letterSpacing: "0.04em" }}>
                  UP / DOWN VOLUME
                </span>
                <LegendDot color={GREEN} label="Up Volume" />
                <LegendDot color={RED} label="Down Volume" />
                <RangeToggle range={range} setRange={setRange} />
              </div>
              <div style={{
                border: `1px solid ${GRID}`,
                borderRadius: 6,
                padding: "16px 0 8px 0",
                background: "#07111f",
              }}>
                <ResponsiveContainer width="100%" height={320}>
                  <ComposedChart data={displayVolData} margin={{ top: 8, right: 56, left: 0, bottom: 8 }}>
                    <CartesianGrid vertical={false} stroke={GRID} strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      ticks={volJanTicks}
                      tick={<XTick />}
                      tickLine={false}
                      axisLine={{ stroke: GRID }}
                      interval={0}
                    />
                    <YAxis
                      orientation="left"
                      tickFormatter={fmtK}
                      tick={{ fontSize: 10, fill: GREY }}
                      tickLine={false}
                      axisLine={false}
                      width={60}
                    />
                    <Tooltip content={<VolTooltip />} />
                    <Area
                      dataKey="UVOL"
                      stroke={GREEN}
                      fill={GREEN}
                      fillOpacity={0.15}
                      strokeWidth={1.5}
                      dot={false}
                      isAnimationActive={false}
                      connectNulls={false}
                    />
                    <Area
                      dataKey="DVOL"
                      stroke={RED}
                      fill={RED}
                      fillOpacity={0.15}
                      strokeWidth={1.5}
                      dot={false}
                      isAnimationActive={false}
                      connectNulls={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </>
          )}

          {/* Section C: Cumulative A/D Line */}
          {displayAdData.length > 0 && (
            <>
              <div style={{
                display: "flex", alignItems: "center", gap: 16,
                marginBottom: 10, marginTop: 28,
              }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: LABEL, letterSpacing: "0.04em" }}>
                  ADVANCE / DECLINE LINE
                </span>
                <LegendDot color={COLORS.AD} label="Cumulative A/D" />
              </div>
              <div style={{
                border: `1px solid ${GRID}`,
                borderRadius: 6,
                padding: "16px 0 8px 0",
                background: "#07111f",
              }}>
                <ResponsiveContainer width="100%" height={320}>
                  <ComposedChart data={displayAdData} margin={{ top: 8, right: 56, left: 0, bottom: 8 }}>
                    <CartesianGrid vertical={false} stroke={GRID} strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      ticks={adJanTicks}
                      tick={<XTick />}
                      tickLine={false}
                      axisLine={{ stroke: GRID }}
                      interval={0}
                    />
                    <YAxis
                      orientation="left"
                      tickFormatter={fmtK}
                      tick={{ fontSize: 10, fill: GREY }}
                      tickLine={false}
                      axisLine={false}
                      width={60}
                    />
                    <Tooltip content={<ADTooltip />} />
                    <Line
                      dataKey="ad"
                      stroke={COLORS.AD}
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                      connectNulls={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </>
          )}

          {/* Section D: Breadth Stats Table */}
          <BreadthTable breadthTable={rawData.breadth_table} />

          {/* Context note */}
          <div style={{
            marginTop: 16, padding: "12px 16px",
            border: `1px solid ${GRID}`, borderRadius: 6,
            background: "#07111f", fontSize: 10, color: GREY,
            lineHeight: 1.6, letterSpacing: "0.03em",
          }}>
            <span style={{ color: LABEL, fontWeight: 600 }}>NYSE Market Breadth</span> tracks
            total volume and advancing/declining issues on the New York Stock Exchange.
            {" "}<span style={{ color: GREEN }}>Up Volume</span> = volume on advancing stocks.
            {" "}<span style={{ color: RED }}>Down Volume</span> = volume on declining stocks.
            {" "}The <span style={{ color: COLORS.AD }}>Cumulative A/D Line</span> is the running
            sum of daily net advancing minus declining issues &mdash; a divergence from price
            signals weakening breadth.
          </div>
        </div>
      )}
    </div>
  );
}
