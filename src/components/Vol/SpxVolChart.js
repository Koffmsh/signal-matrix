import { useEffect, useState, useCallback, useMemo } from "react";
import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { fetchSpxVolHistory } from "../../services/api";

const GREEN  = "#00e5a0";
const RED    = "#ff4d6d";
const BLUE   = "#4e8fde";
const ORANGE = "#e07b3a";
const GRID   = "#1a2a3a";
const TEXT   = "#8899aa";
const LABEL  = "#c8d8e8";

// ── Custom bar: green if positive, red if negative ────────────────────────────
function PctBar(props) {
  const { x, y, width, height, value } = props;
  if (value == null || height === 0) return null;
  const fill = value >= 0 ? GREEN : RED;
  const yPos = value >= 0 ? y : y + height;
  return <rect x={x} y={yPos} width={width} height={Math.abs(height)} fill={fill} opacity={0.75} />;
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const hv30 = payload.find(p => p.dataKey === "hv30");
  const hv90 = payload.find(p => p.dataKey === "hv90");
  const pct  = payload.find(p => p.dataKey === "pct_change");
  return (
    <div style={{
      background: "#0d1f33", border: "1px solid #1a2a3a",
      borderRadius: 6, padding: "8px 12px", fontSize: 11,
    }}>
      <div style={{ color: LABEL, marginBottom: 6, fontWeight: 600 }}>{label}</div>
      {hv30?.value != null && (
        <div style={{ color: BLUE, marginBottom: 2 }}>HV30: {hv30.value.toFixed(1)}%</div>
      )}
      {hv90?.value != null && (
        <div style={{ color: ORANGE, marginBottom: 2 }}>HV90: {hv90.value.toFixed(1)}%</div>
      )}
      {pct?.value != null && (
        <div style={{ color: pct.value >= 0 ? GREEN : RED }}>
          SPX: {pct.value >= 0 ? "+" : ""}{pct.value.toFixed(2)}%
        </div>
      )}
    </div>
  );
}

// ── X-axis tick — only renders for Jan dates (passed via explicit ticks prop) ─
function XTick({ x, y, payload }) {
  if (!payload?.value) return null;
  const [yr] = payload.value.split("-");
  return (
    <text x={x} y={y + 12} textAnchor="middle" fontSize={10} fill={TEXT}>
      {yr}
    </text>
  );
}

// ── Compute Jan-1 tick dates from data array ──────────────────────────────────
function getJanTicks(dates) {
  const seen = new Set();
  return dates.filter(d => {
    const [yr, mo] = d.split("-");
    if (mo === "01" && !seen.has(yr)) { seen.add(yr); return true; }
    return false;
  });
}

// ── Main component ────────────────────────────────────────────────────────────
export default function SpxVolChart() {
  const [data,    setData]    = useState([]);
  const [updated, setUpdated] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(false);
  const [range,   setRange]   = useState("2y");

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    const res = await fetchSpxVolHistory();
    if (!res || !res.dates?.length) {
      setError(true);
      setLoading(false);
      return;
    }
    const rows = res.dates.map((d, i) => ({
      date:       d,
      hv30:       res.hv30[i],
      hv90:       res.hv90[i],
      pct_change: res.pct_change[i],
    }));
    setData(rows);
    setUpdated(res.updated);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  // ── Filter data to selected range ──────────────────────────────────────────
  const displayData = useMemo(() => {
    if (range === "max" || data.length === 0) return data;
    const cutoff = new Date();
    cutoff.setFullYear(cutoff.getFullYear() - 2);
    const cutoffStr = cutoff.toISOString().slice(0, 10);
    return data.filter(d => d.date >= cutoffStr);
  }, [data, range]);

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
            SPX VOL
          </h1>
          <span style={{ fontSize: 11, color: TEXT, letterSpacing: "0.05em" }}>
            REALIZED VOLATILITY · 1 MONTH vs 3 MONTH
          </span>
          {updated && (
            <span style={{ fontSize: 10, color: TEXT, marginLeft: "auto" }}>
              EOD · {updated}
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
          No data — run REFRESH DATA on the dashboard first.
        </div>
      )}

      {/* ── Chart area ── */}
      {!loading && !error && displayData.length > 0 && (
        <div>

          {/* Legend + Range toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: 24, marginBottom: 14, paddingLeft: 4 }}>
            <LegendDot color={BLUE}   label="HV30 — 1 Month Realized" />
            <LegendDot color={ORANGE} label="HV90 — 3 Month Realized" />
            <LegendDot color={GREEN}  label="SPX Daily % Change" square />
            {/* Range toggle */}
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

          {/* Bordered chart */}
          <div style={{
            border: "1px solid #1a2a3a",
            borderRadius: 6,
            padding: "16px 0 8px 0",
            background: "#07111f",
          }}>
            <ResponsiveContainer width="100%" height={380}>
              <ComposedChart data={displayData} margin={{ top: 8, right: 48, left: 0, bottom: 8 }}>
                <CartesianGrid vertical={false} stroke={GRID} strokeDasharray="3 3" />

                <XAxis
                  dataKey="date"
                  ticks={getJanTicks(displayData.map(d => d.date))}
                  tick={<XTick />}
                  tickLine={false}
                  axisLine={{ stroke: GRID }}
                  interval={0}
                />

                {/* Left axis — HV % */}
                <YAxis
                  yAxisId="hv"
                  orientation="left"
                  tickFormatter={v => `${v}%`}
                  tick={{ fontSize: 10, fill: TEXT }}
                  tickLine={false}
                  axisLine={false}
                  domain={[0, "auto"]}
                  width={40}
                />

                {/* Right axis — daily pct change */}
                <YAxis
                  yAxisId="pct"
                  orientation="right"
                  tickFormatter={v => `${v > 0 ? "+" : ""}${v}%`}
                  tick={{ fontSize: 10, fill: TEXT }}
                  tickLine={false}
                  axisLine={false}
                  domain={([dataMin, dataMax]) => {
                    const bound = Math.ceil(Math.max(Math.abs(dataMin), Math.abs(dataMax)) * 10) / 10;
                    return [-bound, bound];
                  }}
                  width={48}
                />

                <Tooltip content={<ChartTooltip />} />

                {/* Daily % change bars — behind the lines */}
                <Bar
                  yAxisId="pct"
                  dataKey="pct_change"
                  shape={<PctBar />}
                  isAnimationActive={false}
                  maxBarSize={4}
                >
                  {displayData.map((entry, i) => (
                    <Cell key={i} fill={entry.pct_change >= 0 ? GREEN : RED} />
                  ))}
                </Bar>

                {/* HV90 — orange, drawn before HV30 so HV30 sits on top */}
                <Line
                  yAxisId="hv"
                  dataKey="hv90"
                  stroke={ORANGE}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />

                {/* HV30 — blue */}
                <Line
                  yAxisId="hv"
                  dataKey="hv30"
                  stroke={BLUE}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

        </div>
      )}
    </div>
  );
}

function LegendDot({ color, label, square }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      {square
        ? <div style={{ width: 10, height: 10, background: color, opacity: 0.75, borderRadius: 1 }} />
        : <div style={{ width: 16, height: 2, background: color, borderRadius: 1 }} />
      }
      <span style={{ fontSize: 10, color: TEXT, letterSpacing: "0.04em" }}>{label}</span>
    </div>
  );
}
