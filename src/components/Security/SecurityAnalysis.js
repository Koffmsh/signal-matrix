import { useEffect, useState, useMemo, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ReferenceArea,
} from "recharts";
import { apiFetch } from "../../services/api";

import { GREEN, RED, AMBER, GREY, LABEL, BG, CARD, BORDER, GRID, FONT_SANS, FONT_MONO } from "../../styles/tokens";
const MONO = FONT_MONO;

function vpColor(vp) {
  if (vp === "Bullish") return GREEN;
  if (vp === "Bearish") return RED;
  return GREY;
}

function pillarLabel(name, raw, data) {
  if (raw == null) return "—";
  switch (name) {
    case "STRUCTURE": {
      if (raw >= 40) return data?.viewpoint || "Neutral";
      if (raw >= 30) {
        const dir = data?.trend?.direction;
        return dir && dir !== "Neutral" ? `Leaning ${dir}` : "Neutral";
      }
      return "Neutral";
    }
    case "VOLUME":     return data.obv_direction || "Neutral";
    case "VOLATILITY": return null;
    case "QUAD": {
      const align = data?.quad_alignment;
      if (align === "Best") return "Best";
      if (align === "Worst") return "Worst";
      return raw > 0 ? "Aligned" : raw < 0 ? "Misaligned" : "Neutral";
    }
    default:           return "—";
  }
}

function pillarColor(name, raw, data) {
  if (raw == null) return GREY;
  switch (name) {
    case "STRUCTURE":      return raw >= 40 ? GREEN : raw >= 30 ? AMBER : GREY;
    case "VOLUME":     return raw >= 10 ? GREEN : raw >= 5 ? AMBER : GREY;
    case "VOLATILITY": return raw >= 10 ? GREEN : raw >= 5 ? AMBER : GREY;
    case "QUAD": {
      if (raw > 0) return GREEN;
      if (raw < 0) return RED;
      const align = data?.quad_alignment;
      if (align === "Best") return GREEN;
      if (align === "Worst") return RED;
      return GREY;
    }
    default:           return GREY;
  }
}

function pillarDetail(name, data) {
  if (!data) return "";
  switch (name) {
    case "STRUCTURE": {
      const trd = data.trend?.direction || "Neutral";
      const drift = data.drift_dir || "Neutral";
      const td = data.trade?.direction || "Neutral";
      if (trd === "Neutral") return "Trend has not confirmed a direction.";
      const parts = [`Trend is ${trd}`];
      if (drift === trd) parts.push("Drift confirms");
      else parts.push("Drift not confirming");
      if (td === trd) parts.push("Trade aligned");
      return parts.join(", ") + ".";
    }
    case "VOLUME": {
      const dir = data.obv_direction || "Neutral";
      if (dir === "Bullish" || dir === "Bearish") return `Volume is ${dir.toLowerCase()} — both volume signals aligned.`;
      if (dir === "Leaning Bullish" || dir === "Leaning Bearish") return `Volume is ${dir.toLowerCase()} — one volume signal directional.`;
      return "Volume is neutral — no directional bias.";
    }
    case "VOLATILITY": {
      const volVal = data.vix_close != null ? data.vix_close.toFixed(1) : null;
      const regime = data.vix_regime || "—";
      const idx = data.vol_index || "VIX";
      if (!volVal) return "Volatility data unavailable.";
      if (regime === "N/A") return `No vol index applies — full credit (+15).`;
      if (["Investable", "Investable+", "Tradable", "Calm"].includes(regime)) return `${idx} at ${volVal} — low volatility supports positioning.`;
      if (regime === "Choppy") return `${idx} at ${volVal} — choppy conditions, proceed with caution.`;
      if (regime === "Danger") return `${idx} at ${volVal} — extreme volatility, risk is elevated.`;
      return `${idx} at ${volVal}.`;
    }
    case "QUAD": {
      const align = data.quad_alignment;
      const score = data.quad_score;
      const genericSectors = ["Index", "Broad Market", "Equities"];
      const sectorLabel = data.sector && !genericSectors.includes(data.sector)
        ? data.sector : data.asset_class || "this asset class";

      if (align === "Neutral")
        return `No strong historical edge for ${sectorLabel} in the current macro environment.`;

      const structDir = data.trend?.direction !== "Neutral" ? data.trend?.direction
                      : (data.drift_dir && data.drift_dir !== "Neutral") ? data.drift_dir : null;
      // "Best"/"Worst" = raw macro stance (no structure). "Aligned"/"Misaligned" = relative to structure.
      // Aligned+Bullish or Misaligned+Bearish → quad is Best for sector → "perform well"
      // Aligned+Bearish or Misaligned+Bullish → quad is Worst for sector → "perform poorly"
      const isBestForSector = align === "Best"
        || (align === "Aligned" && structDir === "Bullish")
        || (align === "Misaligned" && structDir === "Bearish");
      const envLine = isBestForSector
        ? `${sectorLabel} historically perform well in the current macro environment.`
        : `${sectorLabel} historically perform poorly in the current macro environment.`;

      let structLine = "";
      if (score > 0) {
        structLine = " The macro environment supports current price structure.";
      } else if (score < 0 && structDir) {
        structLine = ` Currently working against ${structDir.toLowerCase()} price structure.`;
      } else if (score === 0 && !structDir) {
        structLine = " No directional structure to align with yet.";
      } else if (score === 0 && structDir) {
        structLine = ` Currently working against ${structDir.toLowerCase()} price structure.`;
      }
      return envLine + structLine;
    }
    default: return "";
  }
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const close = payload.find(p => p.dataKey === "close");
  return (
    <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 4, padding: "8px 12px", fontSize: 11, fontFamily: MONO }}>
      <div style={{ color: LABEL, marginBottom: 4 }}>{label}</div>
      {close && <div style={{ color: "#e8f4ff" }}>Close: ${Number(close.value).toFixed(2)}</div>}
    </div>
  );
}

function PriceBubble({ viewBox, value, color, textColor, yOffset }) {
  const w = value.length * 6.0 + 4;
  const h = 16;
  const rx = (viewBox?.x ?? 0) + (viewBox?.width ?? 0) + 8;
  const ry = (viewBox?.y ?? 0) - h / 2 + (yOffset || 0);
  return (
    <g>
      <rect x={rx} y={ry} width={w} height={h} rx={3} fill={color} />
      <text x={rx + w / 2} y={ry + h / 2} textAnchor="middle" dominantBaseline="central" fill={textColor || "#fff"} fontSize={9} fontFamily="monospace" fontWeight={600}>
        {value}
      </text>
    </g>
  );
}

function XTick({ x, y, payload }) {
  const val = payload?.value || "";
  const parts = val.split("-");
  const display = parts.length >= 2 ? `${parts[1]}/${parts[2]?.slice(0,2) || ""}` : val;
  return (
    <text x={x} y={y + 14} textAnchor="middle" fill={GREY} fontSize={9} fontFamily="monospace">
      {display}
    </text>
  );
}

const DATE_RANGES = [
  { label: "5D",  val: 5 },
  { label: "1M",  val: 21 },
  { label: "6M",  val: 126 },
  { label: "YTD", val: -1 },
  { label: "1Y",  val: 252 },
  { label: "5Y",  val: 1260 },
  { label: "MAX", val: 0 },
];

const BLOCK1_TABS = ["AI ANALYSIS", "RISK RANGE", "PROFILE"];

const CONTENT_TABS = ["METRICS", "ANALYSIS", "FINANCIALS", "NEWS"];

const THUMBNAILS = [
  { title: "Vol Risk Premium", desc: "IV30 vs HV30 spread — cheap or expensive options" },
  { title: "Signal History",   desc: "Conviction over time from daily snapshots" },
  { title: "Correlation (vs SPX)", desc: "Rolling 60-day correlation to S&P 500" },
];

export default function SecurityAnalysis({ defaultTicker }) {
  const params = useParams();
  const ticker = params.ticker || defaultTicker || "SPY";
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [navInput, setNavInput] = useState("");
  const [tickerList, setTickerList] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [dateRange, setDateRange] = useState(252);
  const [showRR, setShowRR] = useState(true);
  const [showMA20, setShowMA20] = useState(false);
  const [block1Tab, setBlock1Tab] = useState("AI ANALYSIS");
  const [contentTab, setContentTab] = useState("METRICS");
  const [aiSummary, setAiSummary] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    apiFetch("/api/tickers?active=true").then(r => r.json()).then(d => setTickerList(d)).catch(() => {});
  }, []);

  const filteredTickers = useMemo(() => {
    if (!navInput.trim()) return [];
    const q = navInput.trim().toLowerCase();
    return tickerList.filter(t =>
      t.ticker.toLowerCase().includes(q) || (t.description || "").toLowerCase().includes(q)
    ).slice(0, 10);
  }, [navInput, tickerList]);

  const fetchDetail = useCallback(async (sym) => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/security/${encodeURIComponent(sym)}/detail`);
      if (!res.ok) {
        if (res.status === 404) { setError("Ticker not found"); setLoading(false); return; }
        throw new Error(`HTTP ${res.status}`);
      }
      const json = await res.json();
      setData(json);
      localStorage.setItem("lastSecurityTicker", sym);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ticker) {
      fetchDetail(ticker);
      setAiSummary(null);
      setAiLoading(true);
      apiFetch(`/api/security/${encodeURIComponent(ticker)}/summary`)
        .then(r => r.json())
        .then(d => { if (d.headline) setAiSummary(d); })
        .catch(() => {})
        .finally(() => setAiLoading(false));
      window.scrollTo(0, 0);
    }
  }, [ticker, fetchDetail]);

  const handleNav = (e) => {
    e.preventDefault();
    const s = navInput.trim().toUpperCase();
    if (s && tickerList.some(t => t.ticker === s)) {
      navigate(`/security/${encodeURIComponent(s)}`); setNavInput(""); setShowDropdown(false);
    }
  };

  const chartData = useMemo(() => {
    if (!data?.price_history) return [];
    const { dates, closes } = data.price_history;
    const len = Math.min(dates.length, closes.length);
    let start = 0;
    if (dateRange === -1) {
      const year = new Date().getFullYear();
      const ytdStart = `${year}-01-01`;
      start = dates.findIndex(d => d >= ytdStart);
      if (start < 0) start = 0;
    } else if (dateRange > 0) {
      start = Math.max(0, len - dateRange);
    }
    const result = [];
    for (let i = start; i < len; i++) {
      let ma20 = null;
      if (i >= 19) {
        let sum = 0;
        for (let j = i - 19; j <= i; j++) sum += closes[j];
        ma20 = sum / 20;
      }
      result.push({ date: dates[i], close: closes[i], ma20 });
    }
    return result;
  }, [data, dateRange]);

  const pillars = useMemo(() => {
    if (!data) return [];
    return [
      { name: "STRUCTURE",   raw: data.structural_score },
      { name: "VOLUME",     raw: data.volume_score },
      { name: "VOLATILITY", raw: data.vix_score },
      { name: "QUAD",       raw: data.quad_score },
    ].map(p => ({
      ...p,
      score: p.raw,
      label: p.name === "VOLATILITY" ? (() => {
        if (!data.vix_regime || data.vix_regime === "N/A") return "Full Credit";
        if (["Investable", "Tradable", "Calm"].includes(data.vix_regime)) {
          const lean = data.trade?.direction !== "Neutral" ? data.trade?.direction
                     : data.trend?.direction !== "Neutral" ? data.trend?.direction : "Neutral";
          return lean === "Bearish" ? "Tradable" : data.vix_regime === "Tradable" ? "Tradable" : "Investable";
        }
        return data.vix_regime;
      })() : pillarLabel(p.name, p.raw, data),
      color: pillarColor(p.name, p.raw, data),
      detail: pillarDetail(p.name, data),
    }));
  }, [data]);

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", background: BG, color: GREY, padding: "32px 40px" }}>
        <style>{`
          @keyframes shimmer { 0% { opacity: 0.3; } 50% { opacity: 0.6; } 100% { opacity: 0.3; } }
          .skel { background: #1a2a3a; borderRadius: 3; animation: shimmer 1.5s ease-in-out infinite; }
        `}</style>
        <div style={{ display: "flex", gap: 20, marginBottom: 20 }}>
          <div style={{ flex: 1 }}>
            <div className="skel" style={{ width: 120, height: 20, borderRadius: 3, marginBottom: 12 }} />
            <div className="skel" style={{ width: 240, height: 14, borderRadius: 3, marginBottom: 8 }} />
            <div className="skel" style={{ width: "100%", height: 160, borderRadius: 4, marginTop: 16 }} />
          </div>
          <div style={{ width: 340 }}>
            <div className="skel" style={{ width: "100%", height: 60, borderRadius: 4, marginBottom: 12 }} />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {[1,2,3,4].map(i => <div key={i} className="skel" style={{ height: 90, borderRadius: 4 }} />)}
            </div>
          </div>
        </div>
        <div className="skel" style={{ width: "100%", height: 300, borderRadius: 4 }} />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{ minHeight: "100vh", background: BG, color: GREY, padding: "32px 40px" }}>
        <Link to="/" style={{ color: GREY, textDecoration: "none", fontSize: 11, letterSpacing: "0.1em" }}>← DASHBOARD</Link>
        <div style={{ marginTop: 24, fontSize: 14, color: RED }}>{error || "No data available"}</div>
      </div>
    );
  }

  const changePct = data.change_pct;
  const changeColor = changePct > 0 ? GREEN : changePct < 0 ? RED : GREY;
  const lrr = data.trade?.lrr;
  const hrr = data.trade?.hrr;

  return (
    <div style={{ minHeight: "100vh", background: BG, color: "#e8f4ff", fontFamily: "-apple-system, 'Segoe UI', sans-serif", padding: "24px 32px" }}>
      <style>{`
        .sa-tab-scroll::-webkit-scrollbar { width: 4px; }
        .sa-tab-scroll::-webkit-scrollbar-track { background: transparent; }
        .sa-tab-scroll::-webkit-scrollbar-thumb { background: #445566; border-radius: 2px; }
        .sa-tab-scroll::-webkit-scrollbar-thumb:hover { background: #667788; }
        .sa-tab-scroll { scrollbar-width: thin; scrollbar-color: #445566 transparent; }
      `}</style>

      {/* ═══════════ TOP BAR ═══════════ */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <Link to="/" style={{ color: GREY, textDecoration: "none", fontSize: 11, letterSpacing: "0.1em" }}>← DASHBOARD</Link>
        <div style={{ position: "relative" }}>
          <form onSubmit={handleNav} style={{ display: "flex" }}>
            <input
              value={navInput}
              onChange={e => { setNavInput(e.target.value); setShowDropdown(true); }}
              onFocus={() => setShowDropdown(true)}
              onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
              placeholder="Search ticker / name..."
              style={{
                background: CARD, border: `1px solid ${BORDER}`, borderRadius: 3,
                color: "#c8d8e8", fontSize: 11, padding: "6px 12px", outline: "none",
                width: 180, fontFamily: "inherit",
              }}
            />
          </form>
          {showDropdown && filteredTickers.length > 0 && (
            <div style={{
              position: "absolute", top: "100%", left: 0, width: 280, marginTop: 2,
              background: CARD, border: `1px solid ${BORDER}`, borderRadius: 3,
              zIndex: 200, maxHeight: 300, overflowY: "auto",
            }}>
              {filteredTickers.map(t => (
                <div
                  key={t.ticker}
                  onMouseDown={() => { navigate(`/security/${encodeURIComponent(t.ticker)}`); setNavInput(""); setShowDropdown(false); }}
                  style={{
                    padding: "6px 12px", cursor: "pointer", display: "flex", gap: 8, alignItems: "baseline",
                    fontSize: 11, fontFamily: "inherit",
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = "#1a2e45"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                  <span style={{ color: "#e8f4ff", fontWeight: 700, minWidth: 50 }}>{t.ticker}</span>
                  <span style={{ color: GREY, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.description}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ fontSize: 11, color: GREY }}>
          {data.updated_at ? (() => {
            try {
              const d = new Date(data.updated_at.replace(" ", "T"));
              return d.toLocaleString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true }) + " ET";
            } catch { return data.updated_at; }
          })() : ""}
        </div>
      </div>

      {/* ═══════════ TWO-COLUMN LAYOUT ═══════════ */}
      <div style={{ display: "flex", gap: 20, marginBottom: 20, flexWrap: "wrap" }}>

        {/* ── Block 1: Stock Details + Tabs ── */}
        <div style={{ flex: 1, minWidth: 340, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 8, padding: "20px 24px", display: "flex", flexDirection: "column" }}>
          {/* Ticker badge + description + Viewpoint/Conviction right-justified */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 22 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <span style={{
                display: "inline-block", padding: "5px 14px", borderRadius: 4,
                border: `1px solid ${GREEN}`, fontSize: 20, fontWeight: 700,
                color: GREEN, letterSpacing: "0.08em",
              }}>{data.ticker}</span>
              <span style={{ fontSize: 18, color: LABEL }}>{data.description}</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 11, letterSpacing: "0.12em", color: GREY, marginBottom: 8 }}>VIEWPOINT</div>
                <span style={{
                  display: "inline-block", padding: "3px 10px", borderRadius: 3, fontSize: 11, fontWeight: 700,
                  letterSpacing: "0.1em", color: "#fff",
                  background: vpColor(data.viewpoint),
                }}>
                  {data.viewpoint?.toUpperCase() || "NEUTRAL"}
                </span>
              </div>
              {data.trend?.structural_state === "BREAK_OF_TREND" && (
                <div style={{ textAlign: "center" }}
                  title={data.trend?.direction === "Bullish"
                    ? "Break of Trend Support — watching for confirmation"
                    : "Break of Trend Resistance — watching for confirmation"}>
                  <div style={{ fontSize: 11, letterSpacing: "0.12em", color: GREY, marginBottom: 8 }}>TREND</div>
                  <span style={{
                    display: "inline-block", padding: "3px 10px", borderRadius: 3, fontSize: 11, fontWeight: 700,
                    letterSpacing: "0.1em", color: "#fff", background: "#f0b429", cursor: "help",
                  }}>⚠ BREAK</span>
                </div>
              )}
              <div style={{ textAlign: "center" }}
                title={data.conviction == null
                  ? "No score — conviction below 45%"
                  : undefined}>
                <div style={{ fontSize: 11, letterSpacing: "0.12em", color: GREY, marginBottom: 8 }}>CONVICTION</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: data.conviction != null ? vpColor(data.viewpoint) : GREY, fontFamily: MONO }}>
                  {data.conviction != null ? `${data.conviction}%` : "—"}
                </div>
              </div>
            </div>
          </div>

          {/* Price row: Last Price, Change */}
          <div style={{ display: "flex", alignItems: "baseline", gap: 20, marginBottom: 16, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 10, letterSpacing: "0.12em", color: GREY, marginBottom: 2 }}>LAST PRICE</div>
              <div style={{ fontSize: 18, fontWeight: 600, fontFamily: MONO }}>{data.close?.toFixed(2)}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, letterSpacing: "0.12em", color: GREY, marginBottom: 2 }}>CHANGE</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: changeColor, fontFamily: MONO }}>
                {data.close != null && data.prev_close != null ? `${(data.close - data.prev_close) >= 0 ? "+" : ""}${(data.close - data.prev_close).toFixed(2)}` : "—"}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, letterSpacing: "0.12em", color: GREY, marginBottom: 2 }}>CHANGE %</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: changeColor, fontFamily: MONO }}>
                {changePct != null ? `${changePct > 0 ? "+" : ""}${changePct.toFixed(2)}%` : "—"}
              </div>
            </div>
          </div>

          {/* Vol metrics row */}
          <div style={{ display: "flex", gap: 24, marginBottom: 24, flexWrap: "wrap", fontSize: 12 }}>
            <div>
              <div style={{ fontSize: 10, letterSpacing: "0.1em", color: GREY, marginBottom: 6 }}>IV30</div>
              <div style={{ fontWeight: 700, color: LABEL, fontFamily: MONO }}>{data.iv30 != null ? `${(data.iv30 * 100).toFixed(2)}%` : "—"}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, letterSpacing: "0.1em", color: GREY, marginBottom: 6 }}>HV30</div>
              <div style={{ fontWeight: 700, color: LABEL, fontFamily: MONO }}>{data.hv30 != null ? `${(data.hv30 * 100).toFixed(2)}%` : "—"}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, letterSpacing: "0.1em", color: GREY, marginBottom: 6 }}>IV RANK</div>
              <div style={{ fontWeight: 700, color: LABEL, fontFamily: MONO }}>{data.iv_rank != null ? `${data.iv_rank.toFixed(2)}%` : "—"}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, letterSpacing: "0.1em", color: GREY, marginBottom: 6 }}>VRP</div>
              <div style={{ fontWeight: 700, color: data.vrp != null ? (data.vrp < 0 ? GREEN : data.vrp > 0 ? RED : LABEL) : GREY, fontFamily: MONO }}>
                {data.vrp != null ? `${(data.vrp * 100).toFixed(2)}%` : "—"}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, letterSpacing: "0.1em", color: GREY, marginBottom: 6 }}>VOLATILITY REGIME</div>
              {(() => {
                const vrpPct = data.vrp != null ? data.vrp * 100 : null;
                const ivr = data.iv_rank;
                let regime = "—", regimeColor = GREY;
                if (vrpPct != null && ivr != null) {
                  if (ivr > 80 && vrpPct < -15)      { regime = "Falling Knife"; regimeColor = RED; }
                  else if (ivr > 50 && vrpPct < -10)  { regime = "Gamma Trap"; regimeColor = AMBER; }
                  else if (ivr > 50 && vrpPct > 5)    { regime = "Yield Harvest"; regimeColor = GREEN; }
                  else if (ivr < 30 && vrpPct > 5)    { regime = "Upside Panic"; regimeColor = AMBER; }
                  else if (ivr < 20 && vrpPct > -2 && vrpPct < 5) { regime = "Quiet Accumulation"; regimeColor = "#66eebb"; }
                  else                                 { regime = "Neutral"; regimeColor = GREY; }
                }
                const regimeTooltips = {
                  "Falling Knife": "IV is historically elevated and realized vol exceeds implied — options are cheap relative to actual moves. Avoid selling premium; consider long vol or protective puts.",
                  "Gamma Trap": "Elevated IV with realized vol running hot — hedging demand is high and dealers are short gamma. Expect amplified moves; tread carefully with directional bets.",
                  "Yield Harvest": "High IV but realized vol is contained — options are overpriced. Favorable for selling premium (covered calls, credit spreads).",
                  "Upside Panic": "Low IV but realized vol is elevated — the market is moving more than options imply. Cheap options relative to actual movement; consider long vol strategies.",
                  "Quiet Accumulation": "Low IV and low realized vol — calm conditions. Good environment for building positions; options are fairly priced. Breakout setups may be forming.",
                  "Neutral": "No strong IV/HV skew — options are fairly priced relative to realized movement.",
                };
                const tip = regimeTooltips[regime] || "";
                return <div style={{ fontWeight: 700, color: regimeColor, cursor: tip ? "help" : "default" }} title={tip}>{regime}</div>;
              })()}
            </div>
          </div>

          {/* Block 1 tab navigation */}
          <div style={{ display: "flex", gap: 0, borderBottom: `1px solid ${BORDER}`, marginBottom: 16 }}>
            {BLOCK1_TABS.map(tab => (
              <button
                key={tab}
                onClick={() => setBlock1Tab(tab)}
                style={{
                  padding: "8px 16px", fontSize: 11, letterSpacing: "0.12em", fontWeight: 600,
                  color: block1Tab === tab ? GREEN : GREY,
                  cursor: "pointer",
                  background: "none", border: "none",
                  borderBottom: `2px solid ${block1Tab === tab ? GREEN : "transparent"}`,
                }}
              >{tab}</button>
            ))}
          </div>

          {/* Block 1 tab content */}
          <div className="sa-tab-scroll" style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
            {block1Tab === "AI ANALYSIS" && (
              <div>
                {aiLoading ? (
                  <div style={{ fontSize: 12, color: GREY }}>Analyzing...</div>
                ) : aiSummary ? (
                  <>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "#e8f4ff", marginBottom: 12 }}>
                      {aiSummary.headline}
                    </div>
                    <ul style={{ margin: 0, paddingLeft: 16, lineHeight: 1.8 }}>
                      {aiSummary.bullets.map((b, i) => (
                        <li key={i} style={{ fontSize: 12, color: LABEL, marginBottom: 4 }}>{b}</li>
                      ))}
                    </ul>
                    <div style={{ marginTop: 12, fontSize: 10, color: GREY }}>
                      Generated {aiSummary.summary_date}
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize: 12, color: GREY }}>Summary not available.</div>
                )}
              </div>
            )}
            {block1Tab === "RISK RANGE" && (
              <div>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontVariantNumeric: "tabular-nums" }}>
                  <thead>
                    <tr>
                      {["Timeframe", "Direction", "State", "LRR", "HRR", "Level"].map(h => (
                        <th key={h} style={{ textAlign: "left", padding: "8px 8px", color: GREY, borderBottom: `1px solid ${BORDER}`, fontSize: 11, letterSpacing: "0.1em" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { tf: "Trade", d: data.trade },
                      { tf: "Trend", d: data.trend },
                      { tf: "Tail",  d: data.lt },
                    ].map(({ tf, d }) => {
                      const isTrendBreak = tf === "Trend" && d?.structural_state === "BREAK_OF_TREND";
                      const dirClr = isTrendBreak ? "#f0b429" : (d ? vpColor(d.direction) : GREY);
                      const breakTip = isTrendBreak
                        ? (d.direction === "Bullish" ? "Break of Trend Support — watching for confirmation" : "Break of Trend Resistance — watching for confirmation")
                        : null;
                      return (
                      <tr key={tf}>
                        <td style={{ padding: "8px 8px", color: LABEL }}>{tf}</td>
                        <td style={{ padding: "8px 8px", color: dirClr, fontWeight: 600 }}>
                          {d?.direction || "—"}
                          {isTrendBreak && <span title={breakTip} style={{ cursor: "help" }}> ⚠</span>}
                        </td>
                        <td style={{ padding: "8px 8px", color: isTrendBreak ? "#f0b429" : GREY, fontSize: 10 }}>{d?.structural_state?.replace(/_/g, " ") || "—"}</td>
                        <td style={{ padding: "8px 8px", color: dirClr }}>{d?.lrr != null ? `$${d.lrr.toFixed(2)}` : "—"}</td>
                        <td style={{ padding: "8px 8px", color: dirClr }}>{d?.hrr != null ? `$${d.hrr.toFixed(2)}` : "—"}</td>
                        <td style={{ padding: "8px 8px", color: dirClr }}>
                          {tf === "Trade"
                            ? (d?.d_extended && d?.pivot_b != null ? `$${d.pivot_b.toFixed(2)}`
                              : d?.pivot_c != null ? `$${d.pivot_c.toFixed(2)}` : "—")
                            : d?.lrr != null ? `$${d.lrr.toFixed(2)}` : "—"}
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {block1Tab === "PROFILE" && (
              <div style={{ padding: "4px 0" }}>
                {data.profile_summary && (
                  <div style={{ fontSize: 12, color: LABEL, lineHeight: 1.7, marginBottom: 16 }}>
                    {data.profile_summary}
                  </div>
                )}
                <div style={{ display: "flex", gap: 24, flexWrap: "wrap", fontSize: 11 }}>
                  <div><span style={{ color: GREY }}>Asset Class: </span><span style={{ color: LABEL }}>{data.asset_class}</span></div>
                  <div><span style={{ color: GREY }}>Sector: </span><span style={{ color: LABEL }}>{data.sector}</span></div>
                </div>
                {data.viewpoint_since && data.viewpoint !== "Neutral" && (
                  <div style={{ marginTop: 10, fontSize: 11 }}>
                    <span style={{ color: GREY }}>Aligned since: </span>
                    <span style={{ color: LABEL }}>{data.viewpoint_since}</span>
                  </div>
                )}
                {!data.profile_summary && (
                  <div style={{ marginTop: 12, fontSize: 11, color: GREY }}>Profile description not yet available.</div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ── Block 2: Signal Score — 2×2 pillar grid ── */}
        <div style={{ flex: "0 1 auto", minWidth: 340, maxWidth: 480, padding: "20px 24px" }}>
          <div style={{ fontSize: 12, letterSpacing: "0.2em", color: GREEN, marginBottom: 14, fontWeight: 700 }}>SIGNAL SCORE</div>

          {data.alert && (
            <div style={{
              background: "#2a1a00", border: `1px solid ${AMBER}`, borderRadius: 6,
              padding: "8px 14px", marginBottom: 12, fontSize: 11, color: AMBER,
              fontWeight: 700, letterSpacing: "0.1em", textAlign: "center",
            }}>
              ⚡ HIGH CONVICTION ALERT — {data.conviction}%
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {pillars.map(p => (
              <div key={p.name} style={{
                background: CARD, border: `1px solid ${BORDER}`, borderRadius: 6,
                borderTop: `3px solid ${p.color}`, padding: "18px 14px", textAlign: "center",
              }}>
                <div>
                  <div style={{ fontSize: 36, fontWeight: 700, color: p.color, marginBottom: 6, lineHeight: 1, fontFamily: MONO }}>
                    {p.score != null ? p.score : "—"}
                  </div>
                  <div style={{ fontSize: 14, color: p.color, letterSpacing: "0.08em", fontWeight: 600, marginBottom: 10 }}>{p.label}</div>
                  <div style={{ fontSize: 11, letterSpacing: "0.15em", color: GREY, marginBottom: 10 }}>{p.name}</div>
                  <div style={{ fontSize: 11, color: "#a8b8c8", lineHeight: 1.6 }}>{p.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ═══════════ PRICE & RISK RANGE CHART ═══════════ */}
      <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 8, padding: "20px 24px", marginBottom: 20 }}>
        <div style={{ fontSize: 12, letterSpacing: "0.2em", color: GREEN, marginBottom: 14, fontWeight: 700 }}>PRICE & RISK RANGE</div>

        {/* Chart controls: toggle left, date ranges right */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div style={{ display: "flex", gap: 16 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: LABEL, cursor: "pointer" }}>
              <input
                type="checkbox" checked={showRR} onChange={e => setShowRR(e.target.checked)}
                style={{ accentColor: GREEN, width: 14, height: 14 }}
              />
              Risk Range
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: LABEL, cursor: "pointer" }}>
              <input
                type="checkbox" checked={showMA20} onChange={e => setShowMA20(e.target.checked)}
                style={{ accentColor: "#4e8fde", width: 14, height: 14 }}
              />
              MA20
            </label>
          </div>
          <div style={{ display: "flex", gap: 4 }}>
            {DATE_RANGES.map(r => (
              <button
                key={r.label}
                onClick={() => setDateRange(r.val)}
                style={{
                  background: dateRange === r.val ? "#162840" : "transparent",
                  border: `1px solid ${dateRange === r.val ? GREEN : BORDER}`,
                  borderRadius: 4, color: dateRange === r.val ? GREEN : GREY,
                  fontSize: 10, fontWeight: 600, letterSpacing: "0.06em",
                  padding: "4px 8px", cursor: "pointer",
                  minWidth: 32, textAlign: "center",
                }}
              >{r.label}</button>
            ))}
          </div>
        </div>

        <ResponsiveContainer width="100%" height={400}>
          <ComposedChart data={chartData} margin={{ top: 20, right: 55, bottom: 10, left: 10 }}>
            <CartesianGrid stroke="#3a4f65" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" tick={<XTick />} axisLine={{ stroke: GRID }} tickLine={false} interval="preserveStartEnd" minTickGap={60} />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fill: GREY, fontSize: 10, fontFamily: MONO }}
              axisLine={false} tickLine={false}
              tickFormatter={v => `$${v}`}
              width={65}
            />
            <Tooltip content={<ChartTooltip />} />

            {showRR && lrr != null && hrr != null && (
              <ReferenceArea y1={lrr} y2={hrr} fill={GREEN} fillOpacity={0.06} />
            )}

            {showRR && lrr != null && (
              <ReferenceLine y={lrr} stroke={GREEN} strokeDasharray="6 4" strokeWidth={1.5} label={<PriceBubble value={`$${lrr.toFixed(2)}`} color={GREEN} />} />
            )}
            {showRR && hrr != null && (
              <ReferenceLine y={hrr} stroke={RED} strokeDasharray="6 4" strokeWidth={1.5} label={<PriceBubble value={`$${hrr.toFixed(2)}`} color={RED} />} />
            )}
            {data.close != null && (() => {
              let yOff = 0;
              if (showRR && chartData.length > 0) {
                const prices = chartData.map(d => d.close).filter(Boolean);
                const yMin = Math.min(...prices, lrr || Infinity, hrr || -Infinity);
                const yMax = Math.max(...prices, lrr || -Infinity, hrr || Infinity);
                const range = yMax - yMin || 1;
                const pxPerUnit = 360 / range;
                if (hrr != null) {
                  const gapPx = Math.abs(data.close - hrr) * pxPerUnit;
                  if (gapPx < 18) yOff = 18 - gapPx;
                }
                if (lrr != null) {
                  const gapPx = Math.abs(data.close - lrr) * pxPerUnit;
                  if (gapPx < 18 && (yOff === 0 || data.close > lrr)) yOff = -(18 - gapPx);
                }
              }
              return (
                <ReferenceLine y={data.close} stroke="transparent" label={<PriceBubble value={`$${data.close.toFixed(2)}`} color="#ffffff" textColor="#0a1628" yOffset={yOff} />} />
              );
            })()}

            <Line type="linear" dataKey="close" stroke="#e8f4ff" strokeWidth={1.5} dot={false} activeDot={{ r: 3, fill: "#e8f4ff" }} />
            {showMA20 && (
              <Line type="linear" dataKey="ma20" stroke="#4e8fde" strokeWidth={1.2} dot={false} activeDot={false} connectNulls />
            )}
          </ComposedChart>
        </ResponsiveContainer>

        {/* Legend below chart */}
        <div style={{ display: "flex", gap: 20, marginTop: 10, fontSize: 11 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 20, height: 2, background: "#e8f4ff", display: "inline-block" }} />
            <span style={{ color: LABEL }}>Price</span>
          </span>
          {showMA20 && (
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 20, height: 2, background: "#4e8fde", display: "inline-block" }} />
              <span style={{ color: LABEL }}>MA20</span>
            </span>
          )}
          {showRR && (
            <>
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 20, height: 0, display: "inline-block", borderTop: `2px dashed ${GREEN}` }} />
                <span style={{ color: LABEL }}>LRR (Buy/Add)</span>
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 20, height: 0, display: "inline-block", borderTop: `2px dashed ${RED}` }} />
                <span style={{ color: LABEL }}>HRR (Sell/Reduce)</span>
              </span>
            </>
          )}
        </div>
      </div>

      {/* ═══════════ CONTENT TABS ═══════════ */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", gap: 0, borderBottom: `1px solid ${BORDER}`, marginBottom: 20 }}>
          {CONTENT_TABS.map(tab => (
            <button
              key={tab}
              onClick={() => setContentTab(tab)}
              style={{
                padding: "10px 20px", fontSize: 11, letterSpacing: "0.12em", fontWeight: 600,
                color: contentTab === tab ? GREEN : GREY,
                cursor: "pointer",
                background: "none", border: "none",
                borderBottom: `2px solid ${contentTab === tab ? GREEN : "transparent"}`,
              }}
            >{tab}</button>
          ))}
        </div>

        {contentTab === "METRICS" && (
          <div style={{ textAlign: "center", padding: "32px 20px", color: GREY, fontSize: 11, letterSpacing: "0.1em" }}>
            METRICS — KEY RATIOS, PERFORMANCE, FUNDAMENTALS (COMING SOON)
          </div>
        )}
        {contentTab === "ANALYSIS" && (
          <div style={{ textAlign: "center", padding: "32px 20px", color: GREY, fontSize: 11, letterSpacing: "0.1em" }}>
            ANALYSIS — DEEP DIVE REPORTS (COMING SOON)
          </div>
        )}
        {contentTab === "FINANCIALS" && (
          <div style={{ textAlign: "center", padding: "32px 20px", color: GREY, fontSize: 11, letterSpacing: "0.1em" }}>
            FINANCIALS — EARNINGS, REVENUE, MARGINS (COMING SOON)
          </div>
        )}
        {contentTab === "NEWS" && (
          <div style={{ textAlign: "center", padding: "32px 20px", color: GREY, fontSize: 11, letterSpacing: "0.1em" }}>
            NEWS — RECENT HEADLINES & SENTIMENT (COMING SOON)
          </div>
        )}
      </div>

      {/* ═══════════ THUMBNAIL GRID ═══════════ */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {THUMBNAILS.map(t => (
          <div key={t.title} style={{
            background: CARD, border: `1px solid ${BORDER}`, borderRadius: 8,
            padding: "16px 18px", cursor: "default",
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#e8f4ff", marginBottom: 6 }}>{t.title}</div>
            <div style={{ fontSize: 11, color: GREY, lineHeight: 1.5 }}>{t.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
