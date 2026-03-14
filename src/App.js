import { useState, useMemo } from "react";
import { fetchBatchMarketData } from "./services/api";
import tickersData from "./data/tickers";
import AdminPanel from "./components/Admin/AdminPanel";

// ── Storage helpers ──────────────────────────────────────────────────────────
export function loadTickers() {
  try {
    const stored = localStorage.getItem("sm_tickers");
    if (stored) return JSON.parse(stored);
  } catch (e) {}
  return tickersData;
}

export function saveTickers(data) {
  try {
    localStorage.setItem("sm_tickers", JSON.stringify(data));
  } catch (e) {}
}

// ── Routing ──────────────────────────────────────────────────────────────────
export default function App() {
  if (window.location.pathname === "/admin") return <AdminPanel />;
  return <Dashboard />;
}

// ── Seeded RNG ───────────────────────────────────────────────────────────────
function seededRand(seed) {
  let s = seed;
  return () => {
    s = (s * 16807 + 0) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

// ── Sparkline (pure SVG) ─────────────────────────────────────────────────────
function Sparkline({ prices, color }) {
  const W = 80, H = 28, pad = 2;
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const pts = prices.map((p, i) => {
    const x = pad + (i / (prices.length - 1)) * (W - pad * 2);
    const y = H - pad - ((p - min) / range) * (H - pad * 2);
    return `${x},${y}`;
  });
  return (
    <svg width={W} height={H} style={{ display: "block" }}>
      <polyline
        points={pts.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ── Mock data ────────────────────────────────────────────────────────────────
function generateMockData(ticker) {
  const seed = ticker.ticker.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  const r = seededRand(seed);
  const directions = ["Bullish", "Bearish", "Neutral"];
  const volSignals = ["Confirming", "Diverging", "Neutral"];

  const close = +(50 + r() * 450).toFixed(2);
  const tradeDir = directions[Math.floor(r() * 3)];
  const trendDir = directions[Math.floor(r() * 3)];
  const ltDir = directions[Math.floor(r() * 3)];
  const aligned = tradeDir === trendDir && tradeDir !== "Neutral";
  const viewpoint = aligned ? tradeDir : directions[Math.floor(r() * 3)];
  const conviction = aligned ? Math.floor(55 + r() * 45) : Math.floor(20 + r() * 45);
  const spread = close * (0.03 + r() * 0.08);
  const tradeLRR = +(close - spread * (0.4 + r() * 0.4)).toFixed(2);
  const tradeHRR = +(close + spread * (0.6 + r() * 0.6)).toFixed(2);
  const trendLRR = +(close * (0.82 + r() * 0.1)).toFixed(2);
  const ltLRR = +(close * (0.65 + r() * 0.15)).toFixed(2);
  const hurstTrade = +(0.45 + r() * 0.35).toFixed(2);
  const relIV = Math.floor(15 + r() * 80);
  const volSignal = volSignals[Math.floor(r() * 3)];
  const isAlert = aligned && conviction > 75;

  // Sparkline — 60 points, last anchors to close
  const sr = seededRand(seed + 9999);
  const sparkPrices = (() => {
    const pts = [];
    let v = close * (0.88 + sr() * 0.08);
    for (let i = 0; i < 59; i++) {
      v = v * (0.992 + sr() * 0.016);
      pts.push(+v.toFixed(2));
    }
    pts.push(close);
    return pts;
  })();

  return {
    ...ticker,
    close, viewpoint, conviction, tradeDir, tradeLRR, tradeHRR,
    trendDir, trendLRR, ltDir, ltLRR, hurstTrade, relIV, volSignal,
    isAlert, sparkPrices, updated: "03/11/26 16:00",
  };
}

// ── Merge real data over mock ─────────────────────────────────────────────────
function mergeRealData(mockRow, realDataMap) {
  const real = realDataMap.get(mockRow.ticker);
  if (!real) return mockRow; // No real data — keep mock entirely

  return {
    ...mockRow,
    close:       real.close        ?? mockRow.close,
    sparkPrices: real.spark_prices?.length === 60
                   ? real.spark_prices
                   : mockRow.sparkPrices,
    relIV:       real.rel_iv       ?? mockRow.relIV,
    volume:      real.volume       ?? 0,
    ma20:        real.ma20         ?? null,
    ma50:        real.ma50         ?? null,
    ma100:       real.ma100        ?? null,
    updated:     real.updated      ?? mockRow.updated,
    dataSource:  "live",
  };
}

// ── Sort helpers ─────────────────────────────────────────────────────────────
const ASSET_CLASS_ORDER = [
  "Domestic Equities", "Domestic Fixed Income", "Commodities",
  "Foreign Exchange", "International Equities", "Digital Assets",
];
const SECTOR_ORDER = [
  "Index", "Broad Market", "Technology", "Communication Services",
  "Consumer Discretionary", "Consumer Staples", "Energy", "Financials",
  "Health Care", "Industrials", "Materials", "Real Estate", "Utilities", "Factor",
];

function defaultSort(a, b) {
  const ac = ASSET_CLASS_ORDER.indexOf(a.assetClass) - ASSET_CLASS_ORDER.indexOf(b.assetClass);
  if (ac !== 0) return ac;
  const sc = SECTOR_ORDER.indexOf(a.sector) - SECTOR_ORDER.indexOf(b.sector);
  if (sc !== 0) return sc;
  return a.ticker.localeCompare(b.ticker);
}

// ── Color helpers ────────────────────────────────────────────────────────────
const dirIcon   = (d)  => d === "Bullish" ? "▲" : d === "Bearish" ? "▼" : "—";
const dirColor  = (d)  => d === "Bullish" ? "#00e5a0" : d === "Bearish" ? "#ff4d6d" : "#8899aa";
const vpColor   = (v)  => v === "Bullish" ? "#00e5a0" : v === "Bearish" ? "#ff4d6d" : "#8899aa";
const convColor = (c)  => c >= 70 ? "#00e5a0" : c >= 50 ? "#f0b429" : "#8899aa";
const volColor  = (v)  => v === "Confirming" ? "#00e5a0" : v === "Diverging" ? "#ff4d6d" : "#8899aa";
const hurstColor= (h)  => h >= 0.6 ? "#00e5a0" : h >= 0.5 ? "#f0b429" : "#ff4d6d";
const ivColor   = (iv) => iv <= 30 ? "#00e5a0" : iv <= 60 ? "#f0b429" : "#ff4d6d";
const sparkColor= (v)  => v === "Bullish" ? "#00e5a0" : v === "Bearish" ? "#ff4d6d" : "#8899aa";

// ── Data ─────────────────────────────────────────────────────────────────────
const TICKERS = loadTickers();

const CLASSES    = ["All", "Domestic Equities", "Domestic Fixed Income", "Digital Assets", "Foreign Exchange", "International Equities", "Commodities"];
const VIEWPOINTS = ["All", "Bullish", "Bearish", "Neutral"];

// ── Dashboard ────────────────────────────────────────────────────────────────
function Dashboard() {
  const [classFilter, setClassFilter] = useState("All");
  const [vpFilter,    setVpFilter]    = useState("All");
  const [alignedOnly, setAlignedOnly] = useState(false);
  const [alertOnly,   setAlertOnly]   = useState(false);
  const [search,      setSearch]      = useState("");
  const [sortKey,     setSortKey]     = useState("default");
  const [sortDir,     setSortDir]     = useState(1);
  const [selected,    setSelected]    = useState(null);
  const [expandedTickers, setExpandedTickers] = useState(new Set());

  const [realDataMap,  setRealDataMap]  = useState(new Map());
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [dataError,    setDataError]    = useState(false);

  const handleRefresh = () => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    setDataError(false);
    fetchBatchMarketData()
      .then(map => {
        setRealDataMap(map);
        setIsRefreshing(false);
        if (map.size === 0) setDataError(true);
      })
      .catch(() => {
        setIsRefreshing(false);
        setDataError(true);
      });
  };

  // Merge real data over mock — reruns whenever realDataMap updates
  const ALL_DATA = useMemo(() =>
    TICKERS.filter(t => t.active).map(t =>
      mergeRealData(generateMockData(t), realDataMap)
    ),
    [realDataMap]
  );
  const DATA    = ALL_DATA.filter(t => t.tier === 1);
  const TIER2_DATA = ALL_DATA.filter(t => t.tier === 2);
  const TIER2_BY_PARENT = TIER2_DATA.reduce((acc, row) => {
    const p = row.parentTicker;
    if (!acc[p]) acc[p] = [];
    acc[p].push(row);
    return acc;
  }, {});

  const toggleExpand = (ticker, e) => {
    e.stopPropagation();
    setExpandedTickers(prev => {
      const next = new Set(prev);
      next.has(ticker) ? next.delete(ticker) : next.add(ticker);
      return next;
    });
  };

  const filtered = useMemo(() => {
    let d = ALL_DATA.filter(t => t.tier === 1);
    if (classFilter !== "All") d = d.filter(x => x.assetClass === classFilter);
    if (vpFilter !== "All")    d = d.filter(x => x.viewpoint === vpFilter);
    if (alignedOnly) d = d.filter(x => x.tradeDir === x.trendDir && x.tradeDir !== "Neutral");
    if (alertOnly)   d = d.filter(x => x.isAlert);
    if (search)      d = d.filter(x =>
      x.ticker.toLowerCase().includes(search.toLowerCase()) ||
      x.description.toLowerCase().includes(search.toLowerCase())
    );
    return [...d].sort((a, b) => {
      if (sortKey === "default") return defaultSort(a, b);
      const av = a[sortKey], bv = b[sortKey];
      return (typeof av === "string" ? av.localeCompare(bv) : av - bv) * sortDir;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classFilter, vpFilter, alignedOnly, alertOnly, search, sortKey, sortDir, ALL_DATA]);

  const bullish = DATA.filter(x => x.viewpoint === "Bullish").length;
  const bearish = DATA.filter(x => x.viewpoint === "Bearish").length;
  const alerts  = DATA.filter(x => x.isAlert).length;
  const aligned = DATA.filter(x => x.tradeDir === x.trendDir && x.tradeDir !== "Neutral").length;

  const handleSort = (key) => {
    if (sortKey === key) setSortDir(d => -d);
    else { setSortKey(key); setSortDir(1); }
  };

  const SortHdr = ({ label, k, align }) => (
    <th
      onClick={() => handleSort(k)}
      style={{
        cursor: "pointer", userSelect: "none", padding: "10px 8px",
        textAlign: align || "left", fontSize: "10px", letterSpacing: "0.08em",
        color: sortKey === k ? "#00e5a0" : "#8899aa",
        borderBottom: "1px solid #1a2535", whiteSpace: "nowrap",
      }}
    >
      {label} {sortKey === k ? (sortDir === 1 ? "↑" : "↓") : ""}
    </th>
  );

  const renderRow = (row, i, isTier2 = false) => {
    const isSelected  = selected === row.ticker;
    const isAligned   = row.tradeDir === row.trendDir && row.tradeDir !== "Neutral";
    const children    = TIER2_BY_PARENT[row.ticker] || [];
    const hasChildren = !isTier2 && children.length > 0;
    const isExpanded  = expandedTickers.has(row.ticker);
    const rowBg       = isTier2
      ? (isSelected ? "#0d1f35" : "#0a1018")
      : (isSelected ? "#0d1f35" : i % 2 === 0 ? "#080e18" : "#090f1a");

    return (
      <tr
        key={isTier2 ? `t2-${row.ticker}` : row.ticker}
        onClick={() => setSelected(isSelected ? null : row.ticker)}
        style={{ background: rowBg, borderLeft: isSelected ? "2px solid #0077ff" : "2px solid transparent", cursor: "pointer", transition: "background 0.15s" }}
        onMouseEnter={e => e.currentTarget.style.background = "#0d1a28"}
        onMouseLeave={e => e.currentTarget.style.background = rowBg}
      >
        <td style={{ padding: "9px 4px 9px 8px", width: "24px", textAlign: "center" }}>
          {hasChildren && (
            <span onClick={e => toggleExpand(row.ticker, e)} style={{ display: "inline-block", color: "#8899aa", fontSize: "13px", lineHeight: 1, cursor: "pointer", userSelect: "none", transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.3s" }}>›</span>
          )}
        </td>
        <td style={{ padding: "9px 8px", textAlign: "center" }}>{row.isAlert ? <span style={{ color: "#f0b429" }}>⚡</span> : ""}</td>
        <td style={{ padding: isTier2 ? "9px 8px 9px 24px" : "9px 8px", fontWeight: "700", color: isTier2 ? "#b0c4d8" : "#e8f4ff", letterSpacing: "0.05em" }}>{row.ticker}</td>
        <td style={{ padding: "9px 8px", color: isTier2 ? "#506070" : "#6688aa", maxWidth: "180px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.description}</td>
        <td style={{ padding: "9px 8px" }}>
          <span style={{ background: isTier2 ? "#0a1520" : "#0d1a2a", border: `1px solid ${isTier2 ? "#141e2e" : "#1a2e45"}`, borderRadius: "2px", padding: "2px 6px", fontSize: "9px", color: isTier2 ? "#667788" : "#8899aa", letterSpacing: "0.1em" }}>{row.assetClass}</span>
        </td>
        <td style={{ padding: "9px 8px" }}>
          <span style={{ background: isTier2 ? "#0a1520" : "#0d1a2a", border: `1px solid ${isTier2 ? "#141e2e" : "#1a2e45"}`, borderRadius: "2px", padding: "2px 6px", fontSize: "9px", color: isTier2 ? "#667788" : "#8899aa", letterSpacing: "0.1em" }}>{row.sector}</span>
        </td>
        <td style={{ padding: "9px 8px", color: isTier2 ? "#a0b0c0" : "#c8d8e8", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>${row.close.toFixed(2)}</td>
        <td style={{ padding: "6px 8px" }}>
          <Sparkline prices={row.sparkPrices} color={sparkColor(row.viewpoint)} />
        </td>
        <td style={{ padding: "9px 8px" }}>
          <span style={{ color: vpColor(row.viewpoint), fontWeight: "600", letterSpacing: "0.05em" }}>{row.viewpoint.toUpperCase()}</span>
          {isAligned && <span style={{ marginLeft: "4px", fontSize: "9px", color: "#0077ff" }}>●</span>}
        </td>
        <td style={{ padding: "9px 8px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <div style={{ width: "50px", height: "4px", background: "#1a2535", borderRadius: "2px", overflow: "hidden" }}>
              <div style={{ width: `${row.conviction}%`, height: "100%", background: convColor(row.conviction), borderRadius: "2px" }} />
            </div>
            <span style={{ color: convColor(row.conviction), fontVariantNumeric: "tabular-nums" }}>{row.conviction}%</span>
          </div>
        </td>
        <td style={{ padding: "9px 8px", color: dirColor(row.tradeDir), fontWeight: "600" }}>{dirIcon(row.tradeDir)} {row.tradeDir}</td>
        <td style={{ padding: "9px 8px", color: "#ff4d6d", fontVariantNumeric: "tabular-nums" }}>${row.tradeLRR.toFixed(2)}</td>
        <td style={{ padding: "9px 8px", color: "#00e5a0", fontVariantNumeric: "tabular-nums" }}>${row.tradeHRR.toFixed(2)}</td>
        <td style={{ padding: "9px 8px", color: dirColor(row.trendDir), fontWeight: "600" }}>{dirIcon(row.trendDir)} {row.trendDir}</td>
        <td style={{ padding: "9px 8px", color: "#ff8855", fontVariantNumeric: "tabular-nums" }}>${row.trendLRR.toFixed(2)}</td>
      </tr>
    );
  };

  return (
    <div style={{ background: "#070d14", minHeight: "100vh", fontFamily: "'IBM Plex Mono', 'Courier New', monospace", color: "#c8d8e8", padding: "0" }}>

      {/* Header */}
      <div style={{ background: "linear-gradient(90deg, #0a1628 0%, #0d1f3c 100%)", borderBottom: "1px solid #1a3050", padding: "16px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <div style={{ width: "8px", height: "36px", background: "linear-gradient(180deg, #00e5a0, #0077ff)", borderRadius: "2px" }} />
          <div>
            <div style={{ fontSize: "18px", fontWeight: "700", letterSpacing: "0.15em", color: "#e8f4ff" }}>SIGNAL MATRIX</div>
            <div style={{ fontSize: "10px", color: "#8899aa", letterSpacing: "0.2em" }}>MULTI-TIMEFRAME PROBABILISTIC DASHBOARD</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: "24px" }}>
          {[["BULLISH", bullish, "#00e5a0"], ["BEARISH", bearish, "#ff4d6d"], ["ALIGNED", aligned, "#0099ff"], ["ALERTS", alerts, "#f0b429"]].map(([label, val, color]) => (
            <div key={label} style={{ textAlign: "center" }}>
              <div style={{ fontSize: "20px", fontWeight: "700", color }}>{val}</div>
              <div style={{ fontSize: "9px", color: "#8899aa", letterSpacing: "0.15em" }}>{label}</div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "6px" }}>
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            style={{
              background: isRefreshing ? "transparent" : "#001a0f",
              border: `1px solid ${isRefreshing ? "#1a2535" : "#00e5a0"}`,
              color: isRefreshing ? "#445566" : "#00e5a0",
              padding: "5px 14px", fontSize: "10px", borderRadius: "2px",
              cursor: isRefreshing ? "default" : "pointer",
              fontFamily: "inherit", letterSpacing: "0.1em",
            }}
          >
            {isRefreshing ? "⟳ LOADING..." : "⟳ REFRESH DATA"}
          </button>
          <div style={{ textAlign: "right", fontSize: "10px", color: "#667788" }}>
            <div style={{ color: "#8899aa" }}>EOD · 03/11/26</div>
            <div style={{ color: "#00e5a0", marginTop: "2px" }}>● LIVE</div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div style={{ background: "#0a1422", borderBottom: "1px solid #131f2e", padding: "12px 24px", display: "flex", gap: "16px", alignItems: "center", flexWrap: "wrap" }}>
        <input
          placeholder="Search ticker / name..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ background: "#0d1a2a", border: "1px solid #1a2e45", borderRadius: "3px", color: "#c8d8e8", padding: "6px 12px", fontSize: "11px", fontFamily: "inherit", width: "180px", outline: "none" }}
        />
        <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
          {CLASSES.map(c => (
            <button key={c} onClick={() => setClassFilter(c)} style={{ background: classFilter === c ? "#0d2a45" : "transparent", border: `1px solid ${classFilter === c ? "#0077ff" : "#1a2e45"}`, color: classFilter === c ? "#0099ff" : "#8899aa", padding: "4px 10px", fontSize: "10px", borderRadius: "2px", cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.05em" }}>{c}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: "4px" }}>
          {VIEWPOINTS.map(v => (
            <button key={v} onClick={() => setVpFilter(v)} style={{ background: vpFilter === v ? "#1a1a0a" : "transparent", border: `1px solid ${vpFilter === v ? vpColor(v) : "#1a2e45"}`, color: vpFilter === v ? vpColor(v) : "#8899aa", padding: "4px 10px", fontSize: "10px", borderRadius: "2px", cursor: "pointer", fontFamily: "inherit" }}>{v}</button>
          ))}
        </div>
        <button onClick={() => setAlignedOnly(x => !x)} style={{ background: alignedOnly ? "#001a2e" : "transparent", border: `1px solid ${alignedOnly ? "#0077ff" : "#1a2e45"}`, color: alignedOnly ? "#0099ff" : "#8899aa", padding: "4px 12px", fontSize: "10px", borderRadius: "2px", cursor: "pointer", fontFamily: "inherit" }}>ALIGNED ONLY</button>
        <button onClick={() => setAlertOnly(x => !x)} style={{ background: alertOnly ? "#1a1400" : "transparent", border: `1px solid ${alertOnly ? "#f0b429" : "#1a2e45"}`, color: alertOnly ? "#f0b429" : "#8899aa", padding: "4px 12px", fontSize: "10px", borderRadius: "2px", cursor: "pointer", fontFamily: "inherit" }}>⚡ ALERTS</button>
        <div style={{ marginLeft: "auto", fontSize: "10px", color: "#667788" }}>{filtered.length} of {DATA.length} instruments</div>
      </div>

      {/* Data status banner */}
      {isRefreshing && (
        <div style={{ padding: "10px 24px", fontSize: "10px", color: "#8899aa", letterSpacing: "0.1em", borderBottom: "1px solid #131f2e" }}>
          ⟳ LOADING MARKET DATA...
        </div>
      )}
      {!isRefreshing && dataError && (
        <div style={{ padding: "10px 24px", fontSize: "10px", color: "#f0b429", letterSpacing: "0.1em", borderBottom: "1px solid #131f2e" }}>
          ⚠ LIVE DATA UNAVAILABLE — DISPLAYING MOCK DATA
        </div>
      )}

      {/* Table */}
      <div style={{ overflowX: "auto", padding: "0 24px 24px" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", marginTop: "8px" }}>
          <thead>
            <tr style={{ background: "#0a1220" }}>
              <th style={{ width: "24px", padding: "10px 4px 10px 8px", borderBottom: "1px solid #1a2535" }} />
              <SortHdr label="⚡"          k="isAlert" />
              <SortHdr label="TICKER"      k="ticker" />
              <SortHdr label="DESCRIPTION" k="description" />
              <SortHdr label="ASSET CLASS" k="assetClass" />
              <SortHdr label="SECTOR"      k="sector" />
              <SortHdr label="CLOSE"       k="close" align="right" />
              <th style={{ padding: "10px 8px", fontSize: "10px", letterSpacing: "0.08em", color: "#8899aa", borderBottom: "1px solid #1a2535", whiteSpace: "nowrap" }}>TREND</th>
              <SortHdr label="VIEWPOINT"   k="viewpoint" />
              <SortHdr label="CONVICTION"  k="conviction" />
              <SortHdr label="TRADE DIR"   k="tradeDir" />
              <SortHdr label="TRADE LRR"   k="tradeLRR" />
              <SortHdr label="TRADE HRR"   k="tradeHRR" />
              <SortHdr label="TREND DIR"   k="trendDir" />
              <SortHdr label="TREND LRR"   k="trendLRR" />
            </tr>
          </thead>
          <tbody>
            {filtered.flatMap((row, i) => {
              const children  = TIER2_BY_PARENT[row.ticker] || [];
              const isExpanded = expandedTickers.has(row.ticker);
              const t1 = renderRow(row, i, false);
              const t2 = (isExpanded && children.length > 0)
                ? children.map(child => renderRow(child, i, true))
                : [];
              return [t1, ...t2];
            })}
          </tbody>
        </table>
      </div>

      {/* Detail Panel */}
      {selected && (() => {
        const row = ALL_DATA.find(x => x.ticker === selected);
        if (!row) return null;
        return (
          <div style={{ position: "fixed", bottom: "0", right: "0", width: "360px", background: "#0a1422", border: "1px solid #1a3050", borderBottom: "none", borderRight: "none", padding: "20px", zIndex: 100 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px" }}>
              <div>
                <div style={{ fontSize: "22px", fontWeight: "700", color: "#e8f4ff", letterSpacing: "0.1em" }}>{row.ticker}</div>
                <div style={{ fontSize: "11px", color: "#8899aa" }}>{row.description}</div>
              </div>
              <button onClick={() => setSelected(null)} style={{ background: "none", border: "none", color: "#8899aa", cursor: "pointer", fontSize: "18px" }}>×</button>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              {[
                ["Close",      `$${row.close.toFixed(2)}`,            "#c8d8e8"],
                ["Viewpoint",  row.viewpoint,                          vpColor(row.viewpoint)],
                ["Conviction", `${row.conviction}%`,                   convColor(row.conviction)],
                ["LT Dir",     `${dirIcon(row.ltDir)} ${row.ltDir}`,   dirColor(row.ltDir)],
                ["LT LRR",     `$${row.ltLRR.toFixed(2)}`,            "#cc7744"],
                ["Trend LRR",  `$${row.trendLRR.toFixed(2)}`,         "#ff8855"],
                ["Hurst (T)",  row.hurstTrade,                         hurstColor(row.hurstTrade)],
                ["Rel IV%",    `${row.relIV}%`,                        ivColor(row.relIV)],
                ["Vol Signal", row.volSignal,                          volColor(row.volSignal)],
                ["Updated",    row.updated,                            "#667788"],
              ].map(([label, val, color]) => (
                <div key={label} style={{ background: "#080e18", border: "1px solid #131f2e", borderRadius: "3px", padding: "8px 10px" }}>
                  <div style={{ fontSize: "9px", color: "#99aabb", letterSpacing: "0.1em", marginBottom: "3px" }}>{label}</div>
                  <div style={{ fontSize: "13px", fontWeight: "600", color }}>{val}</div>
                </div>
              ))}
            </div>
            {row.isAlert && (
              <div style={{ marginTop: "12px", background: "#1a1200", border: "1px solid #f0b429", borderRadius: "3px", padding: "8px 12px", fontSize: "10px", color: "#f0b429", letterSpacing: "0.05em" }}>
                ⚡ HIGH CONVICTION ALERT — Trade & Trend aligned with {row.conviction}% conviction
              </div>
            )}
          </div>
        );
      })()}

      {/* Legend */}
      <div style={{ padding: "8px 24px 16px", display: "flex", gap: "20px", flexWrap: "wrap", borderTop: "1px solid #0d1a2a" }}>
        {[["● ALIGNED", "#0077ff"], ["▲ BULLISH", "#00e5a0"], ["▼ BEARISH", "#ff4d6d"], ["HURST >0.6 TRENDING", "#00e5a0"], ["HURST <0.5 MEAN-REV", "#ff4d6d"], ["IV LOW <30%", "#00e5a0"], ["IV HIGH >60%", "#ff4d6d"]].map(([label, color]) => (
          <span key={label} style={{ fontSize: "9px", color, letterSpacing: "0.08em" }}>{label}</span>
        ))}
      </div>
    </div>
  );
}
