import { useState, useMemo, useEffect, useRef } from "react";
import { fetchBatchMarketData } from "./services/api";
import AdminPanel from "./components/Admin/AdminPanel";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

// ── API field mapping: snake_case → camelCase ─────────────────────────────────
function tickerFromApi(r) {
  return {
    ticker:       r.ticker        || "",
    description:  r.description   || "",
    assetClass:   r.asset_class   || "",
    sector:       r.sector        || "",
    tier:         r.tier          ?? 1,
    parentTicker: r.parent_ticker || null,
    active:       r.active        ?? true,
    displayOrder: r.display_order ?? 999,
  };
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
  const hurstTrend = +(0.45 + r() * 0.35).toFixed(2);
  const hurstLt    = +(0.45 + r() * 0.35).toFixed(2);
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
    trendDir, trendLRR, ltDir, ltLRR,
    hurstTrade, hurstTrend, hurstLt,
    relIV, volSignal, isAlert, sparkPrices, updated: "03/11/26 16:00",
    tradeWarn: false, trendWarn: false,
    tradeLrrWarn: false, tradeHrrWarn: false,
    trendLrrWarn: false, trendHrrWarn: false,
    ltLrrWarn: false, ltHrrWarn: false,
    trendHRR: null, ltHRR: null,
    tradeState: null, trendState: null, ltState: null,
    tradeC: null, tradeB: null,
    trendC: null, trendB: null,
    ltC: null, ltB: null,
  };
}

// ── Merge real data over mock ─────────────────────────────────────────────────
function mergeRealData(mockRow, realDataMap) {
  const real = realDataMap.get(mockRow.ticker);
  if (!real) return mockRow;

  return {
    ...mockRow,
    close:       real.close        ?? mockRow.close,
    sparkPrices: real.spark_prices?.length === 60
                   ? real.spark_prices
                   : mockRow.sparkPrices,
    relIV:       real.rel_iv       ?? mockRow.relIV,
    ivSource:    real.iv_source    ?? null,
    volume:      real.volume       ?? 0,
    ma20:        real.ma20         ?? null,
    ma50:        real.ma50         ?? null,
    ma100:       real.ma100        ?? null,
    updated:     real.updated      ?? mockRow.updated,
    dataSource:  "live",
  };
}

// ── Merge signal data over row ────────────────────────────────────────────────
function mergeSignalData(row, signalMap) {
  const sig = signalMap.get(row.ticker);
  if (!sig) return row;

  return {
    ...row,
    viewpoint:  sig.viewpoint  ?? row.viewpoint,
    conviction: sig.conviction ?? null,       // null = blank (Neutral) — never fall back to mock
    volSignal:  sig.vol_signal ?? row.volSignal,
    isAlert:    sig.alert      ?? row.isAlert,
    tradeDir:   sig.trade?.direction         ?? row.tradeDir,
    tradeLRR:   sig.trade?.lrr               ?? null,
    tradeHRR:   sig.trade?.hrr               ?? null,
    tradeWarn:  sig.trade?.warning           ?? false,
    tradeState: sig.trade?.structural_state  ?? null,
    trendDir:   sig.trend?.direction         ?? row.trendDir,
    trendLRR:   sig.trend?.lrr               ?? null,
    trendHRR:   sig.trend?.hrr               ?? null,
    trendWarn:  sig.trend?.warning           ?? false,
    trendState: sig.trend?.structural_state  ?? null,
    ltDir:      sig.lt?.direction            ?? row.ltDir,
    ltLRR:      sig.lt?.lrr                  ?? null,
    ltHRR:      sig.lt?.hrr                  ?? null,
    ltState:    sig.lt?.structural_state     ?? null,
    hurstTrade: sig.trade?.h_value           ?? row.hurstTrade,
    hurstTrend:   sig.trend?.h_value           ?? row.hurstTrend,
    hurstLt:      sig.lt?.h_value              ?? row.hurstLt,
    tradeLrrWarn:     sig.trade?.lrr_warn          ?? false,
    tradeHrrWarn:     sig.trade?.hrr_warn          ?? false,
    trendLrrWarn:     sig.trend?.lrr_warn          ?? false,
    trendHrrWarn:     sig.trend?.hrr_warn          ?? false,
    ltLrrWarn:        sig.lt?.lrr_warn             ?? false,
    ltHrrWarn:        sig.lt?.hrr_warn             ?? false,
    tradeLrrExtended: sig.trade?.lrr_extended      ?? false,
    tradeHrrExtended: sig.trade?.hrr_extended      ?? false,
    trendLrrExtended: sig.trend?.lrr_extended      ?? false,
    trendHrrExtended: sig.trend?.hrr_extended      ?? false,
    tradeC:       sig.trade?.pivot_c           ?? null,
    tradeB:       sig.trade?.pivot_b           ?? null,
    trendC:       sig.trend?.pivot_c           ?? null,
    trendB:       sig.trend?.pivot_b           ?? null,
    ltC:           sig.lt?.pivot_c              ?? null,
    ltB:           sig.lt?.pivot_b              ?? null,
    viewpointSince: sig.viewpoint_since         ?? null,
    obvDirection:   sig.obv_direction           ?? "Neutral",
    obvConfirming:  sig.obv_confirming          ?? false,
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
const dirIcon    = (d)  => d === "Bullish" ? "▲" : d === "Bearish" ? "▼" : "—";
const dirColor   = (d)  => d === "Bullish" ? "#00e5a0" : d === "Bearish" ? "#ff4d6d" : "#8899aa";
const vpColor    = (v)  => v === "Bullish" ? "#00e5a0" : v === "Bearish" ? "#ff4d6d" : "#8899aa";
const convColor  = (c)  => c >= 70 ? "#00e5a0" : c >= 50 ? "#f0b429" : "#8899aa";
const volColor   = (v)  => v === "Confirming" ? "#00e5a0" : v === "Diverging" ? "#ff4d6d" : "#8899aa";
const hurstColor = (h)  => h == null ? "#8899aa" : h >= 0.6 ? "#00e5a0" : h >= 0.5 ? "#f0b429" : "#ff4d6d";
const ivColor    = (iv) => iv <= 30 ? "#00e5a0" : iv <= 60 ? "#f0b429" : "#ff4d6d";
const sparkColor = (v)  => v === "Bullish" ? "#00e5a0" : v === "Bearish" ? "#ff4d6d" : "#8899aa";
const dirRangeColor = (dir, isWarn) => isWarn ? "#f0b429" : dirColor(dir);
const fmtWarnPrice = (v) => v != null
  ? `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  : null;
const warnTip = (dir, which, cVal, bVal) => {
  const c = fmtWarnPrice(cVal);
  const b = fmtWarnPrice(bVal);
  if (dir === "Bullish")
    return which === "lrr"
      ? `LRR is below C${c ? ` (${c})` : ""} — approaching trade invalidation level`
      : `HRR is below B${b ? ` (${b})` : ""} — target doesn't reach prior swing high`;
  if (dir === "Bearish")
    return which === "hrr"
      ? `HRR is above C${c ? ` (${c})` : ""} — approaching trade invalidation level`
      : `LRR is above B${b ? ` (${b})` : ""} — target doesn't reach prior swing low`;
  return "Warning threshold breached";
};
const stateColor = (s)  =>
  !s                    ? "#8899aa" :
  s.includes("VALID")   ? "#00e5a0" :
  s === "EXTENDED"      ? "#00e5a0" :
  s.includes("WARN")    ? "#f0b429" :
  s.includes("BREAK")   ? "#ff4d6d" : "#8899aa";

// ── Multi-select dropdown ─────────────────────────────────────────────────────
function MultiSelectDropdown({ label, options, selected, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const toggle = (val) => {
    const next = new Set(selected);
    next.has(val) ? next.delete(val) : next.add(val);
    onChange(next);
  };

  const count = selected.size;
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(x => !x)}
        style={{
          background: count > 0 ? "#0d2a45" : "transparent",
          border: `1px solid ${count > 0 ? "#0077ff" : "#1a2e45"}`,
          color: count > 0 ? "#0099ff" : "#8899aa",
          padding: "4px 10px", fontSize: "10px", borderRadius: "2px",
          cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.05em",
          display: "flex", alignItems: "center", gap: "6px",
        }}
      >
        {label}
        {count > 0 && (
          <span style={{ background: "#0077ff", color: "#fff", borderRadius: "8px", padding: "0 5px", fontSize: "9px", fontWeight: "700" }}>{count}</span>
        )}
        <span style={{ fontSize: "8px", opacity: 0.7 }}>{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 4px)", left: 0, zIndex: 200,
          background: "#0d1a2a", border: "1px solid #1a3050", borderRadius: "3px",
          minWidth: "200px", maxHeight: "260px", overflowY: "auto",
          boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
        }}>
          {options.map(opt => (
            <label
              key={opt}
              style={{
                display: "flex", alignItems: "center", gap: "8px",
                padding: "6px 12px", cursor: "pointer", userSelect: "none",
                color: selected.has(opt) ? "#00e5a0" : "#8899aa",
                fontSize: "10px", letterSpacing: "0.05em",
                borderBottom: "1px solid #131f2e",
              }}
            >
              <input
                type="checkbox"
                checked={selected.has(opt)}
                onChange={() => toggle(opt)}
                style={{ accentColor: "#00e5a0", width: "12px", height: "12px" }}
              />
              {opt}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Data ─────────────────────────────────────────────────────────────────────
const CLASSES    = ["All", "Domestic Equities", "Domestic Fixed Income", "Digital Assets", "Foreign Exchange", "International Equities", "Commodities"];
const VIEWPOINTS = ["All", "Bullish", "Bearish", "Neutral"];

// ── Dashboard ────────────────────────────────────────────────────────────────
function Dashboard() {
  const [classFilter,  setClassFilter]  = useState(new Set());
  const [sectorFilter, setSectorFilter] = useState(new Set());
  const [vpFilter,     setVpFilter]     = useState("All");
  const [alignedOnly, setAlignedOnly] = useState(false);
  const [alertOnly,   setAlertOnly]   = useState(false);
  const [search,      setSearch]      = useState("");
  const [sortKey,     setSortKey]     = useState("default");
  const [sortDir,     setSortDir]     = useState(1);
  const [selected,    setSelected]    = useState(null);
  const [expandedTickers, setExpandedTickers] = useState(new Set());

  const [tickerUniverse,  setTickerUniverse]  = useState([]);
  const [realDataMap,     setRealDataMap]     = useState(new Map());
  const [batchDataSource, setBatchDataSource] = useState(null);
  const [signalMap,       setSignalMap]       = useState(new Map());
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isRefreshing,    setIsRefreshing]    = useState(false);
  const [dataError,       setDataError]       = useState(false);
  const [isCalculating,      setIsCalculating]      = useState(false);
  const [calcStatus,         setCalcStatus]         = useState(null);
  const [signalsCalculatedAt, setSignalsCalculatedAt] = useState(null);
  const [schedulerStatus, setSchedulerStatus] = useState(null);
  const [schwabStatus,    setSchwabStatus]    = useState(null);

  // Load ticker universe from DB on page load
  useEffect(() => {
    fetch(`${API_BASE}/api/tickers?active=true`)
      .then(r => r.json())
      .then(data => setTickerUniverse(data.map(tickerFromApi)))
      .catch(() => {});
  }, []);

  // Load market data from cache on page load (instant when cache is warm)
  useEffect(() => {
    fetchBatchMarketData()
      .then(({ map, dataSource }) => {
        setRealDataMap(map);
        setBatchDataSource(dataSource);
        if (map.size === 0) setDataError(true);
      })
      .catch(() => setDataError(true))
      .finally(() => setIsInitialLoading(false));
  }, []);

  // Load stored signals on page load (no recalculation)
  useEffect(() => {
    fetch(`${API_BASE}/api/signals/stored`)
      .then(r => r.json())
      .then(data => {
        const m = new Map();
        (data.results || []).forEach(r => m.set(r.ticker, r));
        setSignalMap(m);
        if (data.calculated_at) setSignalsCalculatedAt(data.calculated_at);
      })
      .catch(() => {});
  }, []);

  // Load scheduler status on page load (no polling)
  useEffect(() => {
    fetch(`${API_BASE}/api/scheduler/status`)
      .then(r => r.json())
      .then(data => setSchedulerStatus(data))
      .catch(() => {});
  }, []);

  // Load Schwab auth status on page load
  useEffect(() => {
    fetch(`${API_BASE}/api/auth/schwab/status`)
      .then(r => r.json())
      .then(data => setSchwabStatus(data))
      .catch(() => {});
  }, []);

  const handleCalculateSignals = () => {
    if (isCalculating) return;
    setIsCalculating(true);
    setCalcStatus(null);
    fetch(`${API_BASE}/api/signals/calculate`)
      .then(r => r.json())
      .then(outputData => {
        const m = new Map();
        (outputData.results || []).forEach(r => m.set(r.ticker, r));
        setSignalMap(m);
        setSignalsCalculatedAt(outputData.calculated_at || new Date().toISOString());
        setIsCalculating(false);
        setCalcStatus("ok");
      })
      .catch(() => {
        setIsCalculating(false);
        setCalcStatus("error");
      });
  };

  const handleRefresh = () => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    setDataError(false);
    fetchBatchMarketData()
      .then(({ map, dataSource }) => {
        setRealDataMap(map);
        setBatchDataSource(dataSource);
        setIsRefreshing(false);
        if (map.size === 0) setDataError(true);
      })
      .catch(() => {
        setIsRefreshing(false);
        setDataError(true);
      });
  };

  // Three-step pipeline: mock → price → signals
  const ALL_DATA = useMemo(() =>
    tickerUniverse.filter(t => t.active).map(t => {
      const mockRow  = generateMockData(t);
      const priceRow = mergeRealData(mockRow, realDataMap);
      const sigRow   = mergeSignalData(priceRow, signalMap);
      // ENTRY v1.7 — proximity-based (prox > 0.85), range-normalized via HRR–LRR (STD20 scaled)
      const _band   = (sigRow.tradeLRR != null && sigRow.tradeHRR != null && sigRow.tradeHRR > sigRow.tradeLRR)
        ? sigRow.tradeHRR - sigRow.tradeLRR : null;
      const proxBull = _band != null ? Math.max(0, Math.min(1, 1 - (sigRow.close - sigRow.tradeLRR) / _band)) : null;
      const proxBear = _band != null ? Math.max(0, Math.min(1, (sigRow.close - sigRow.tradeLRR) / _band)) : null;
      const isBuy  = sigRow.viewpoint === "Bullish" && sigRow.tradeDir === "Bullish" && sigRow.trendDir === "Bullish" &&
        proxBull != null && proxBull > 0.85;
      const isSell = sigRow.viewpoint === "Bearish" && sigRow.tradeDir === "Bearish" && sigRow.trendDir === "Bearish" &&
        proxBear != null && proxBear > 0.85;
      return { ...sigRow, entrySignal: isBuy ? "BUY" : isSell ? "SELL" : null };
    }),
    [tickerUniverse, realDataMap, signalMap]
  );
  const DATA    = ALL_DATA.filter(t => t.tier === 1);
  const TIER2_DATA = ALL_DATA.filter(t => t.tier === 2);
  const TIER2_BY_PARENT = TIER2_DATA.reduce((acc, row) => {
    const p = row.parentTicker;
    if (!acc[p]) acc[p] = [];
    acc[p].push(row);
    return acc;
  }, {});

  const availableClasses = useMemo(() =>
    [...new Set(tickerUniverse.filter(t => t.tier === 1 && t.active).map(t => t.assetClass).filter(Boolean))]
      .sort((a, b) => ASSET_CLASS_ORDER.indexOf(a) - ASSET_CLASS_ORDER.indexOf(b)),
    [tickerUniverse]
  );
  const availableSectors = useMemo(() =>
    [...new Set(tickerUniverse.filter(t => t.tier === 1 && t.active).map(t => t.sector).filter(Boolean))]
      .sort((a, b) => SECTOR_ORDER.indexOf(a) - SECTOR_ORDER.indexOf(b)),
    [tickerUniverse]
  );

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
    if (classFilter.size > 0)  d = d.filter(x => classFilter.has(x.assetClass));
    if (sectorFilter.size > 0) d = d.filter(x => sectorFilter.has(x.sector));
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
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return (typeof av === "string" ? av.localeCompare(bv) : av - bv) * sortDir;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classFilter, sectorFilter, vpFilter, alignedOnly, alertOnly, search, sortKey, sortDir, ALL_DATA]);

  const bullish = DATA.filter(x => x.viewpoint === "Bullish").length;
  const bearish = DATA.filter(x => x.viewpoint === "Bearish").length;
  const alerts  = DATA.filter(x => x.isAlert).length;
  const aligned = DATA.filter(x => x.tradeDir === x.trendDir && x.tradeDir !== "Neutral").length;
  const entries = DATA.filter(x => x.entrySignal != null).length;

  const handleSort = (key) => {
    if (sortKey === key) setSortDir(d => -d);
    else { setSortKey(key); setSortDir(1); }
  };

  // Change 2 — title prop for tooltip support
  const SortHdr = ({ label, k, align, title }) => (
    <th
      onClick={() => handleSort(k)}
      title={title}
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

    // Tightened badge style for asset class / sector
    const badgeStyle = {
      background: isTier2 ? "#0a1520" : "#0d1a2a",
      border: `1px solid ${isTier2 ? "#141e2e" : "#1a2e45"}`,
      borderRadius: "2px", padding: "1px 4px",
      fontSize: "8px", color: isTier2 ? "#667788" : "#8899aa",
      letterSpacing: "0.08em", display: "inline-block",
      maxWidth: "110px", overflow: "hidden",
      textOverflow: "ellipsis", whiteSpace: "nowrap",
    };

    return (
      <tr
        key={isTier2 ? `t2-${row.ticker}` : row.ticker}
        onClick={() => setSelected(isSelected ? null : row.ticker)}
        style={{ background: rowBg, borderLeft: isSelected ? "2px solid #0077ff" : "2px solid transparent", cursor: "pointer", transition: "background 0.15s" }}
        onMouseEnter={e => e.currentTarget.style.background = "#0d1a28"}
        onMouseLeave={e => e.currentTarget.style.background = rowBg}
      >
        {/* Expand chevron */}
        <td style={{ padding: "9px 4px 9px 8px", width: "24px", textAlign: "center" }}>
          {hasChildren && (
            <span onClick={e => toggleExpand(row.ticker, e)} style={{ display: "inline-block", color: "#8899aa", fontSize: "13px", lineHeight: 1, cursor: "pointer", userSelect: "none", transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.3s" }}>›</span>
          )}
        </td>
        {/* Alert */}
        <td style={{ padding: "9px 8px", textAlign: "center" }}>{row.isAlert ? <span style={{ color: "#f0b429" }}>⚡</span> : ""}</td>
        {/* Ticker */}
        <td style={{ padding: isTier2 ? "9px 8px 9px 24px" : "9px 8px", fontWeight: "700", color: isTier2 ? "#b0c4d8" : "#e8f4ff", letterSpacing: "0.05em" }}>{row.ticker}</td>
        {/* Description */}
        <td style={{ padding: "9px 8px", color: isTier2 ? "#506070" : "#6688aa", maxWidth: "180px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.description}</td>
        {/* Close */}
        <td style={{ padding: "9px 8px", color: isTier2 ? "#a0b0c0" : "#c8d8e8", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>${row.close.toFixed(2)}</td>
        {/* Sparkline */}
        <td style={{ padding: "6px 8px" }}>
          <Sparkline prices={row.sparkPrices} color={sparkColor(row.viewpoint)} />
        </td>
        {/* Viewpoint */}
        <td style={{ padding: "9px 8px" }}>
          <span style={{ color: vpColor(row.viewpoint), fontWeight: "600", letterSpacing: "0.05em" }}>{row.viewpoint.toUpperCase()}</span>
          {isAligned && <span style={{ marginLeft: "4px", fontSize: "9px", color: "#0077ff" }}>●</span>}
        </td>
        {/* Conviction */}
        <td style={{ padding: "9px 8px" }}>
          {row.conviction !== null && row.conviction !== undefined ? (
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <div style={{ width: "50px", height: "4px", background: "#1a2535", borderRadius: "2px", overflow: "hidden" }}>
                <div style={{ width: `${row.conviction}%`, height: "100%", background: convColor(row.conviction), borderRadius: "2px" }} />
              </div>
              <span style={{ color: convColor(row.conviction), fontVariantNumeric: "tabular-nums" }}>{row.conviction}%</span>
            </div>
          ) : (
            <span style={{ color: "#8899aa" }}>—</span>
          )}
        </td>
        {/* ENTRY */}
        <td style={{ padding: "9px 8px", textAlign: "center" }}>
          {row.entrySignal === "BUY"  && <span style={{ color: "#00e5a0", fontWeight: "700", fontSize: "10px", letterSpacing: "0.05em" }}>▲ BUY</span>}
          {row.entrySignal === "SELL" && <span style={{ color: "#ff4d6d", fontWeight: "700", fontSize: "10px", letterSpacing: "0.05em" }}>▼ SELL</span>}
        </td>
        {/* Trade Dir */}
        <td style={{ padding: "9px 8px", color: dirColor(row.tradeDir), fontWeight: "600" }}>{dirIcon(row.tradeDir)} {row.tradeDir}</td>
        {/* Trade LRR */}
        <td style={{ padding: "9px 8px", color: dirRangeColor(row.tradeDir, row.tradeLrrWarn), fontVariantNumeric: "tabular-nums" }}>
          {row.tradeLRR != null ? `$${row.tradeLRR.toFixed(2)}` : "—"}
          {row.tradeLrrWarn && <span title={warnTip(row.tradeDir, "lrr", row.tradeC, row.tradeB)} style={{ cursor: "help" }}> ⚠</span>}
          {row.tradeLrrExtended && <span title="Price has closed below LRR — extended beyond target range, do not chase" style={{ cursor: "help" }}> ↓</span>}
        </td>
        {/* Trade HRR */}
        <td style={{ padding: "9px 8px", color: dirRangeColor(row.tradeDir, row.tradeHrrWarn), fontVariantNumeric: "tabular-nums" }}>
          {row.tradeHRR != null ? `$${row.tradeHRR.toFixed(2)}` : "—"}
          {row.tradeHrrWarn && <span title={warnTip(row.tradeDir, "hrr", row.tradeC, row.tradeB)} style={{ cursor: "help" }}> ⚠</span>}
          {row.tradeHrrExtended && <span title="Price has closed above HRR — extended beyond target range, do not chase" style={{ cursor: "help" }}> ↑</span>}
        </td>
        {/* Trend Dir */}
        <td style={{ padding: "9px 8px", color: dirColor(row.trendDir), fontWeight: "600" }}>{dirIcon(row.trendDir)} {row.trendDir}</td>
        {/* Trend Level — MA100 floor (Bullish) or ceiling (Bearish); blank when Neutral */}
        <td style={{ padding: "9px 8px", color: dirRangeColor(row.trendDir, row.trendLrrWarn), fontVariantNumeric: "tabular-nums" }}>
          {row.trendLRR != null ? `$${row.trendLRR.toFixed(2)}` : "—"}
          {row.trendLrrWarn && <span title={warnTip(row.trendDir, "lrr", row.trendC, row.trendB)} style={{ cursor: "help" }}> ⚠</span>}
        </td>
        {/* Asset Class — moved to far right, tightened */}
        <td style={{ padding: "9px 6px", maxWidth: "120px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          <span style={badgeStyle}>{row.assetClass}</span>
        </td>
        {/* Sector — moved to far right, tightened */}
        <td style={{ padding: "9px 6px", maxWidth: "100px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          <span style={badgeStyle}>{row.sector}</span>
        </td>
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
        {/* VIX Gauge */}
        {(() => {
          const vix = realDataMap.get("VIX")?.close;
          if (vix == null) return null;
          const color = vix < 20 ? "#00e5a0" : vix < 30 ? "#f0b429" : "#ff4d6d";
          const label = vix < 20 ? "INVESTABLE" : vix < 30 ? "CHOPPY" : "DANGER";
          return (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "4px" }}>
              <div style={{ fontSize: "9px", color: "#8899aa", letterSpacing: "0.15em" }}>VIX REGIME</div>
              <div style={{ display: "flex", alignItems: "baseline", gap: "6px" }}>
                <span style={{ fontSize: "20px", fontWeight: "700", color, fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>{vix.toFixed(2)}</span>
                <span style={{ fontSize: "9px", color, letterSpacing: "0.1em" }}>{label}</span>
              </div>
              <div style={{ position: "relative", width: "160px", height: "6px" }}>
                <div style={{ position: "absolute", inset: 0, display: "flex", borderRadius: "3px", overflow: "hidden" }}>
                  <div style={{ width: "30.6%", height: "100%", background: "#00e5a0", opacity: 0.55 }} />
                  <div style={{ width: "27.8%", height: "100%", background: "#f0b429", opacity: 0.55 }} />
                  <div style={{ width: "41.6%", height: "100%", background: "#ff4d6d", opacity: 0.55 }} />
                </div>
                <div style={{ position: "absolute", left: `${Math.min(Math.max((vix - 9) / 36, 0), 1) * 100}%`, top: "-4px", bottom: "-4px", width: "3px", background: color, transform: "translateX(-1px)", borderRadius: "1px", boxShadow: `0 0 6px ${color}, 0 0 2px #fff` }} />
              </div>
              <div style={{ position: "relative", width: "160px", height: "10px" }}>
                <span style={{ position: "absolute", left: 0, fontSize: "11px", color: "#8899aa" }}>9</span>
                <span style={{ position: "absolute", left: "30.6%", fontSize: "11px", color: "#8899aa", transform: "translateX(-50%)" }}>20</span>
                <span style={{ position: "absolute", left: "58.3%", fontSize: "11px", color: "#8899aa", transform: "translateX(-50%)" }}>30</span>
                <span style={{ position: "absolute", right: 0, fontSize: "11px", color: "#8899aa" }}>45+</span>
              </div>
            </div>
          );
        })()}
        <div style={{ display: "flex", gap: "24px" }}>
          {[["BULLISH", bullish, "#00e5a0"], ["BEARISH", bearish, "#ff4d6d"], ["ALIGNED", aligned, "#0099ff"], ["ALERTS", alerts, "#f0b429"], ["ENTRY", entries, "#e8f4ff"]].map(([label, val, color]) => (
            <div key={label} style={{ textAlign: "center" }}>
              <div style={{ fontSize: "20px", fontWeight: "700", color }}>{val}</div>
              <div style={{ fontSize: "9px", color: "#8899aa", letterSpacing: "0.15em" }}>{label}</div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "6px" }}>
          {(() => {
            // Freshness checks — compare dates in ET
            const todayET = new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" }); // YYYY-MM-DD
            const firstUpdated = realDataMap.size > 0 ? realDataMap.values().next().value?.updated : null;
            // updated format: "MM/DD/YY HH:MM" — extract date
            const dataDateET = firstUpdated
              ? (() => { const [d] = firstUpdated.split(" "); const [m, day, y] = d.split("/"); return `20${y}-${m.padStart(2,"0")}-${day.padStart(2,"0")}`; })()
              : null;
            // Only amber after 4:15 PM ET on a weekday — before then, yesterday's close IS the freshest data
            const etNow      = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" }));
            const etHour     = etNow.getHours();
            const etMinute   = etNow.getMinutes();
            const etDay      = etNow.getDay(); // 0=Sun, 6=Sat
            const isWeekday  = etDay >= 1 && etDay <= 5;
            const pastCutoff = etHour > 16 || (etHour === 16 && etMinute >= 15);
            const dataStale  = realDataMap.size > 0 && dataDateET !== todayET && isWeekday && pastCutoff;
            // signals stale if calculated before today's data — compare full timestamps
            // signalsCalculatedAt is UTC ISO ("2026-03-27 01:16:32"), firstUpdated is ET "MM/DD/YY HH:MM"
            const calcDateObj = signalsCalculatedAt
              ? new Date(signalsCalculatedAt.replace(" ", "T") + "Z") : null;
            const calcDateET = calcDateObj
              ? calcDateObj.toLocaleDateString("en-CA", { timeZone: "America/New_York" }) : null;
            const calcTimeET = calcDateObj
              ? calcDateObj.toLocaleTimeString("en-GB", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }) : null;
            const dataTimeStr = firstUpdated ? firstUpdated.split(" ")[1] : null; // "HH:MM"
            const sigsStale = calcDateET && dataDateET
              ? calcDateET < dataDateET                                          // signals from a prior day
                || (calcDateET === dataDateET && calcTimeET && dataTimeStr && calcTimeET < dataTimeStr) // same day, signals older than data
              : false;

            const calcColor  = (isCalculating || isInitialLoading) ? "#445566" : calcStatus === "error" ? "#ff4d6d" : sigsStale ? "#f0b429" : "#0099ff";
            const calcBg     = (isCalculating || isInitialLoading) ? "transparent" : sigsStale ? "#1a1200" : "#00101a";
            const refreshColor = (isRefreshing || isInitialLoading) ? "#445566" : dataStale ? "#f0b429" : "#00e5a0";
            const refreshBg    = (isRefreshing || isInitialLoading) ? "transparent" : dataStale ? "#1a1000" : "#001a0f";

            return (
              <div style={{ display: "flex", gap: "8px" }}>
                <button
                  onClick={handleCalculateSignals}
                  disabled={isCalculating || isInitialLoading}
                  style={{
                    background: calcBg,
                    border: `1px solid ${(isCalculating || isInitialLoading) ? "#1a2535" : calcColor}`,
                    color: calcColor,
                    padding: "5px 14px", fontSize: "10px", borderRadius: "2px",
                    cursor: (isCalculating || isInitialLoading) ? "default" : "pointer",
                    fontFamily: "inherit", letterSpacing: "0.1em",
                  }}
                >
                  {isCalculating ? "⟳ CALCULATING..." : "⟳ CALCULATE SIGNALS"}
                </button>
                <button
                  onClick={handleRefresh}
                  disabled={isRefreshing || isInitialLoading}
                  style={{
                    background: refreshBg,
                    border: `1px solid ${(isRefreshing || isInitialLoading) ? "#1a2535" : refreshColor}`,
                    color: refreshColor,
                    padding: "5px 14px", fontSize: "10px", borderRadius: "2px",
                    cursor: (isRefreshing || isInitialLoading) ? "default" : "pointer",
                    fontFamily: "inherit", letterSpacing: "0.1em",
                  }}
                >
                  {(isRefreshing || isInitialLoading) ? "⟳ LOADING..." : "⟳ REFRESH DATA"}
                </button>
              </div>
            );
          })()}
          <div style={{ textAlign: "right", fontSize: "10px", color: "#667788" }}>
            {realDataMap.size > 0 && (() => {
              const ts = realDataMap.values().next().value?.updated;
              return ts ? <div style={{ color: "#8899aa" }}>EOD · {ts}</div> : null;
            })()}
            <div style={{ display: "flex", gap: "10px", alignItems: "center", justifyContent: "flex-end", marginTop: "2px" }}>
              {schedulerStatus && (() => {
                const done  = schedulerStatus.today_complete;
                const fail  = schedulerStatus.last_run_status === "failure";
                const color = done ? "#00e5a0" : fail ? "#ff4d6d" : "#f0b429";
                const label = done ? "● SCHED" : fail ? "● SCHED" : "● SCHED";
                const tip   = done
                  ? `EOD run complete · ${schedulerStatus.last_run_time || ""}`
                  : fail
                  ? `Last run failed — check scheduler_log`
                  : `Scheduled · next run ${schedulerStatus.next_run_time || "4:15 PM ET"}`;
                return <div title={tip} style={{ color, cursor: "default" }}>{label}</div>;
              })()}
              {schwabStatus && (() => {
                const state      = schwabStatus.state;
                const isYahooFallback = schwabStatus.connected && batchDataSource === "yahoo_fallback";

                const color = state === "connected" ? "#00e5a0"
                            : state === "aging"     ? "#f0b429"
                            : "#ff4d6d";
                // ◐ when connected but data came from Yahoo fallback
                const icon  = isYahooFallback ? "◐" : "●";

                const tip   = isYahooFallback
                            ? "Schwab token stale — click to re-authenticate"
                            : state === "connected" ? `Schwab connected · token age ${schwabStatus.age_days ?? 0}d`
                            : state === "aging"     ? `Schwab token aging (${schwabStatus.age_days}d) — re-auth soon`
                            : state === "expired"   ? "Schwab token expired — click to re-authenticate"
                            : "Schwab not connected — click to authenticate";
                const clickable = !schwabStatus.connected || isYahooFallback;
                return (
                  <div
                    title={tip}
                    style={{ color, cursor: clickable ? "pointer" : "default" }}
                    onClick={clickable ? () => { window.location.href = `${API_BASE}/api/auth/schwab/login`; } : undefined}
                  >
                    {icon} SCHWAB
                  </div>
                );
              })()}
            </div>
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
        <MultiSelectDropdown label="ASSET CLASS" options={availableClasses} selected={classFilter} onChange={setClassFilter} />
        <MultiSelectDropdown label="SECTOR" options={availableSectors} selected={sectorFilter} onChange={setSectorFilter} />
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
      {(isRefreshing || isInitialLoading) && (
        <div style={{ padding: "18px 24px", fontSize: "13px", color: "#f0b429", letterSpacing: "0.12em", borderBottom: "1px solid #131f2e", textAlign: "center" }}>
          ⟳ LOADING MARKET DATA...
        </div>
      )}
      {!isRefreshing && !isInitialLoading && dataError && (
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
              {/* Change 2 — tooltip on alert header */}
              <SortHdr label="⚡" k="isAlert"
                title="High conviction alert — Trend H>0.55, conviction ≥70%, viewpoint Bullish or Bearish" />
              <SortHdr label="TICKER"      k="ticker" />
              <SortHdr label="DESCRIPTION" k="description" />
              {/* Change 1 — CLOSE / TREND before signal columns; ASSET CLASS / SECTOR at far right */}
              <SortHdr label="CLOSE"       k="close" align="right" />
              <th style={{ padding: "10px 8px", fontSize: "10px", letterSpacing: "0.08em", color: "#8899aa", borderBottom: "1px solid #1a2535", whiteSpace: "nowrap" }}>TREND</th>
              <SortHdr label="VIEWPOINT"   k="viewpoint" />
              <SortHdr label="CONVICTION"  k="conviction"
                title="Conviction %: Green ≥70% · Amber 50–69% · Grey <50% · Blank when Neutral&#10;Components: Trend H · Proximity · OBV" />
              <SortHdr label="ENTRY" k="entrySignal" align="center"
                title="▲ BUY — price within bottom 15% of trade range (prox > 0.85), all timeframes Bullish · ▼ SELL — price within top 15% of trade range (prox > 0.85), all timeframes Bearish" />
              <SortHdr label="TRADE DIR"   k="tradeDir" />
              <SortHdr label="TRADE LRR"   k="tradeLRR" />
              <SortHdr label="TRADE HRR"   k="tradeHRR" />
              <SortHdr label="TREND DIR"   k="trendDir" />
              <SortHdr label="TREND LEVEL" k="trendLRR" />
              <SortHdr label="ASSET CLASS" k="assetClass" />
              <SortHdr label="SECTOR"      k="sector" />
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

      {/* Detail Panel — Change 3: full calculation fields */}
      {selected && (() => {
        const row = ALL_DATA.find(x => x.ticker === selected);
        if (!row) return null;

        const fmtPrice = (v) => v != null ? `$${v.toFixed(2)}` : "—";
        const fmtHurst = (v) => v != null ? v.toFixed(4) : "—";
        const fmtConv  = (v) => v != null ? `${v.toFixed(1)}%` : "—";
        const fmtSince = (iso) => {
          if (!iso) return "—";
          const d = new Date(iso);
          const date = d.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" });
          const time = d.toLocaleString("en-US", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: "America/New_York" });
          return `${date} · ${time} ET`;
        };

        // fields: [label, value, color, isState, warnTip?]
        // warnTip = string → wraps value in <span title> for ⚠ tooltip
        const fields = [
          ["Close",        fmtPrice(row.close),                                                          "#c8d8e8",                              false],
          ["Viewpoint",    row.viewpoint,                                                                  vpColor(row.viewpoint),                 false],
          ...(row.viewpoint !== "Neutral" && row.viewpointSince ? [
            ["Aligned since", fmtSince(row.viewpointSince),                                               vpColor(row.viewpoint),                 false],
          ] : []),
          ["Conviction",   fmtConv(row.conviction),                                                       row.conviction != null ? convColor(row.conviction) : "#8899aa", false],
          ["Vol Direction", row.obvDirection,                                                               dirColor(row.obvDirection),              false],
          ["Vol Signal vs Trade", row.obvConfirming ? "Confirming ✓" : row.obvDirection !== "Neutral" ? "Diverging ✗" : "Neutral —", row.obvConfirming ? "#00e5a0" : row.obvDirection !== "Neutral" ? "#f0b429" : "#8899aa", false],
          ["Trade Dir",    `${dirIcon(row.tradeDir)} ${row.tradeDir}`,                                    dirColor(row.tradeDir),                                    false],
          ["Trade LRR",    `${fmtPrice(row.tradeLRR)}${row.tradeLrrWarn ? " ⚠" : ""}${row.tradeLrrExtended ? " ↓" : ""}`,  dirRangeColor(row.tradeDir, row.tradeLrrWarn),  false, row.tradeLrrExtended ? "Price has closed below LRR — extended beyond target range, do not chase" : row.tradeLrrWarn ? warnTip(row.tradeDir, "lrr", row.tradeC, row.tradeB) : null],
          ["Trade HRR",    `${fmtPrice(row.tradeHRR)}${row.tradeHrrWarn ? " ⚠" : ""}${row.tradeHrrExtended ? " ↑" : ""}`,  dirRangeColor(row.tradeDir, row.tradeHrrWarn),  false, row.tradeHrrExtended ? "Price has closed above HRR — extended beyond target range, do not chase" : row.tradeHrrWarn ? warnTip(row.tradeDir, "hrr", row.tradeC, row.tradeB) : null],
          ["Trade C",      fmtPrice(row.tradeC),                                                          "#8899aa",                                                  false],
          ["Trade B",      fmtPrice(row.tradeB),                                                          "#8899aa",                                                  false],
          ["Trade State",  row.tradeState || "—",                                                          stateColor(row.tradeState),                                true],
          ["Trend Dir",    `${dirIcon(row.trendDir)} ${row.trendDir}`,                                    dirColor(row.trendDir),                                    false],
          ...(row.trendDir !== "Neutral" && row.trendLRR != null ? [
            ["Trend Level", `${fmtPrice(row.trendLRR)}${row.trendLrrWarn ? " ⚠" : ""}`, dirRangeColor(row.trendDir, row.trendLrrWarn), false, row.trendLrrWarn ? warnTip(row.trendDir, "lrr", row.trendC, row.trendB) : null],
          ] : []),
          ["Trend C",      fmtPrice(row.trendC),                                                          "#8899aa",                                                  false],
          ["Trend State",  row.trendState || "—",                                                          stateColor(row.trendState),                                true],
          ["Tail Dir",     `${dirIcon(row.ltDir)} ${row.ltDir}`,                                          dirColor(row.ltDir),                                       false],
          ...(row.ltDir !== "Neutral" && row.ltLRR != null ? [
            ["Tail Level",  fmtPrice(row.ltLRR),                                                           dirColor(row.ltDir),                                       false],
          ] : []),
          ["Hurst (T)",    fmtHurst(row.hurstTrade),                                                       hurstColor(row.hurstTrade),             false],
          ["Hurst (Tr)",   fmtHurst(row.hurstTrend),                                                       hurstColor(row.hurstTrend),             false],
          ["Hurst (Tail)", fmtHurst(row.hurstLt),                                                          hurstColor(row.hurstLt),                false],
          [row.ivSource === "schwab" ? "IV% \u2014 schwab" : "IV% \u2014 proxy",
                           `${row.relIV}%`,                                                                ivColor(row.relIV),                     false],
          ["Updated",      row.updated,                                                                    "#667788",                              false],
        ];

        return (
          <div style={{ position: "fixed", bottom: "0", right: "0", width: "380px", background: "#0a1422", border: "1px solid #1a3050", borderBottom: "none", borderRight: "none", padding: "20px", zIndex: 100 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px" }}>
              <div>
                <div style={{ fontSize: "22px", fontWeight: "700", color: "#e8f4ff", letterSpacing: "0.1em" }}>{row.ticker}</div>
                <div style={{ fontSize: "11px", color: "#8899aa" }}>{row.description}</div>
              </div>
              <button onClick={() => setSelected(null)} style={{ background: "none", border: "none", color: "#8899aa", cursor: "pointer", fontSize: "18px" }}>×</button>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", maxHeight: "calc(100vh - 140px)", overflowY: "auto" }}>
              {fields.map(([label, val, color, isState, tip]) => (
                <div key={label} style={{ background: "#080e18", border: "1px solid #131f2e", borderRadius: "3px", padding: "7px 10px" }}>
                  <div style={{ fontSize: "9px", color: "#99aabb", letterSpacing: "0.1em", marginBottom: "2px" }}>{label}</div>
                  <div style={{ fontSize: "12px", fontWeight: "600", color, letterSpacing: isState ? "0.05em" : "0" }}>
                    {tip ? <span title={tip} style={{ cursor: "help" }}>{val}</span> : val}
                  </div>
                </div>
              ))}
            </div>
            {row.isAlert && (
              <div style={{ marginTop: "10px", background: "#1a1200", border: "1px solid #f0b429", borderRadius: "3px", padding: "8px 12px", fontSize: "10px", color: "#f0b429", letterSpacing: "0.05em" }}>
                ⚡ HIGH CONVICTION ALERT — Trade & Trend aligned with {fmtConv(row.conviction)} conviction
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
