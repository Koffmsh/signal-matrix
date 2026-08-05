import { useState, useEffect } from "react";
import { apiFetch } from "../../services/api";

// ── Design tokens ─────────────────────────────────────────────────────────────
const BG      = "#07111f";
const SURFACE = "#0b1929";
const BORDER  = "#1a2a3a";
const GREEN   = "#00e5a0";
const RED     = "#ff4d6d";
const GREY    = "#8899aa";
const HEADER  = "#c8d8e8";
const WHITE   = "#e8f4ff";

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtPrice(n) {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(n) {
  if (n == null) return "—";
  const s = Math.abs(n).toFixed(2) + "%";
  return (n >= 0 ? "+" : "-") + s;
}

function cellStyle(val, isSpx = false) {
  if (val == null) {
    return {
      background: "transparent",
      color: GREY,
      fontWeight: 500,
    };
  }
  const positive = val >= 0;
  return {
    background: positive
      ? "rgba(0, 229, 160, 0.13)"
      : "rgba(255, 77, 109, 0.13)",
    color:      positive ? GREEN : RED,
    fontWeight: isSpx ? 700 : 600,
  };
}

// ── Single performance table ──────────────────────────────────────────────────
function PerfTable({ title, rows, labels, showSpxSeparator, asOf }) {
  return (
    <div style={{ marginBottom: 40 }}>
      {/* Table header */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-end",
        marginBottom: 14,
      }}>
        <div>
          <div style={{
            fontSize: 18,
            fontWeight: 700,
            color: WHITE,
            letterSpacing: "0.02em",
          }}>
            {title}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: GREY, letterSpacing: "0.08em" }}>
            SIGNAL MATRIX
          </div>
          <div style={{ fontSize: 10, color: GREY, marginTop: 2 }}>
            {asOf}
          </div>
        </div>
      </div>

      {/* Table */}
      <div style={{
        border: `1px solid ${BORDER}`,
        borderRadius: 6,
        overflow: "hidden",
        background: SURFACE,
      }}>
        <table style={{ borderCollapse: "collapse", width: "100%", tableLayout: "fixed" }}>
          <colgroup>
            <col style={{ width: "30%" }} />
            <col style={{ width: "8%"  }} />
            <col style={{ width: "12%" }} />
            <col style={{ width: "12.5%" }} />
            <col style={{ width: "12.5%" }} />
            <col style={{ width: "12.5%" }} />
            <col style={{ width: "12.5%" }} />
          </colgroup>
          <thead>
            <tr style={{ borderBottom: `2px solid ${BORDER}` }}>
              {[
                { label: "SECTOR",           align: "left"  },
                { label: "TICKER",           align: "center"},
                { label: "PRICE",            align: "right" },
                { label: "1-DAY %",          align: "center"},
                { label: `MTD %`,            align: "center"},
                { label: `QTD %`,            align: "center"},
                { label: `YTD %`,            align: "center"},
              ].map(({ label, align }, i) => (
                <th key={i} style={{
                  padding: "10px 12px",
                  textAlign: align,
                  fontSize: 9,
                  fontWeight: 700,
                  letterSpacing: "0.12em",
                  color: HEADER,
                  background: "#0d1e30",
                  whiteSpace: "nowrap",
                }}>
                  {label}
                  {label === "MTD %" && labels?.mtd && (
                    <div style={{ fontSize: 8, fontWeight: 500, color: GREY, marginTop: 1 }}>
                      {labels.mtd}
                    </div>
                  )}
                  {label === "QTD %" && labels?.qtd && (
                    <div style={{ fontSize: 8, fontWeight: 500, color: GREY, marginTop: 1 }}>
                      {labels.qtd}
                    </div>
                  )}
                  {label === "YTD %" && labels?.ytd && (
                    <div style={{ fontSize: 8, fontWeight: 500, color: GREY, marginTop: 1 }}>
                      {labels.ytd}
                    </div>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => {
              const isSpx = row.ticker === "SPX";
              const isLast = idx === rows.length - 1;
              const separatorStyle = (showSpxSeparator && isSpx)
                ? { borderTop: `2px solid ${BORDER}` }
                : {};

              return (
                <tr
                  key={row.ticker}
                  style={{
                    borderBottom: isLast ? "none" : `1px solid ${BORDER}`,
                    background: isSpx ? "rgba(0,0,0,0.15)" : "transparent",
                    ...separatorStyle,
                  }}
                >
                  {/* Sector name */}
                  <td style={{
                    padding: "9px 12px",
                    fontSize: 12,
                    fontWeight: isSpx ? 700 : 500,
                    color: isSpx ? WHITE : HEADER,
                    letterSpacing: isSpx ? "0.04em" : "0.02em",
                  }}>
                    {row.description}
                  </td>

                  {/* Ticker */}
                  <td style={{
                    padding: "9px 8px",
                    textAlign: "center",
                    fontSize: 11,
                    fontWeight: 700,
                    color: isSpx ? WHITE : GREY,
                    letterSpacing: "0.06em",
                  }}>
                    {row.ticker}
                  </td>

                  {/* Price */}
                  <td style={{
                    padding: "9px 12px",
                    textAlign: "right",
                    fontSize: 12,
                    fontWeight: isSpx ? 700 : 500,
                    color: isSpx ? WHITE : HEADER,
                    fontVariantNumeric: "tabular-nums",
                    letterSpacing: "0.02em",
                  }}>
                    {row.close != null ? (isSpx ? row.close.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : `$${fmtPrice(row.close)}`) : "—"}
                  </td>

                  {/* Pct change cells */}
                  {["chg_1d", "chg_mtd", "chg_qtd", "chg_ytd"].map((key) => {
                    const val = row[key];
                    const cs  = cellStyle(val, isSpx);
                    return (
                      <td key={key} style={{
                        padding: "0 4px",
                        textAlign: "center",
                      }}>
                        <div style={{
                          margin: "4px auto",
                          padding: "4px 0",
                          borderRadius: 4,
                          background: cs.background,
                          color: cs.color,
                          fontWeight: cs.fontWeight,
                          fontSize: 12,
                          fontVariantNumeric: "tabular-nums",
                          letterSpacing: "0.02em",
                          minWidth: "80%",
                          textAlign: "center",
                        }}>
                          {fmtPct(val)}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function SectorPerformance() {
  const cached = sessionStorage.getItem("sectorLive");
  const cachedLive = cached ? JSON.parse(cached) : null;
  const [snapshots, setSnapshots] = useState({ eod: null, live: cachedLive });
  const [active, setActive]       = useState(cachedLive ? "live" : "eod");
  const [loading, setLoading]     = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError]         = useState(null);

  useEffect(() => {
    apiFetch("/api/sector-performance")
      .then(r => r.json())
      .then(d => {
        setSnapshots(prev => ({ ...prev, eod: d }));
        setLoading(false);
      })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const handleLive = async () => {
    setRefreshing(true);
    try {
      const res = await apiFetch("/api/sector-performance?live=true");
      const d = await res.json();
      setSnapshots(prev => ({ ...prev, live: d }));
      setActive("live");
      sessionStorage.setItem("sectorLive", JSON.stringify(d));
    } catch (e) {
      setError(e.message);
    } finally {
      setRefreshing(false);
    }
  };

  const containerStyle = {
    minHeight: "100vh",
    background: BG,
    padding: "28px 164px",
    boxSizing: "border-box",
  };

  if (loading) {
    return (
      <div style={{ ...containerStyle, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ color: GREY, fontSize: 13, letterSpacing: "0.1em" }}>⟳ LOADING SECTOR DATA...</div>
      </div>
    );
  }

  if (error && !snapshots.eod) {
    return (
      <div style={{ ...containerStyle, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ color: RED, fontSize: 13 }}>Failed to load sector data</div>
      </div>
    );
  }

  const data = snapshots[active] || snapshots.eod;

  // Disable LIVE after EOD run: check if current ET time is past 4:15 PM on a weekday
  const nowET = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" }));
  const dayOfWeek = nowET.getDay();
  const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5;
  const pastEOD = isWeekday && nowET.getHours() >= 16;
  const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
  const liveDisabled = pastEOD || isWeekend;

  return (
    <div style={containerStyle}>
      {/* Snapshot toggle */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
        {[
          { key: "eod",  label: "EOD" },
          { key: "live", label: "LIVE" },
        ].map(({ key, label }) => {
          const available = !!snapshots[key];
          const isActive = active === key;
          const timestamp = key === "live" && snapshots.live?.refreshed_at
            ? snapshots.live.refreshed_at : null;
          const disabled = key === "live" && (refreshing || liveDisabled);
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
                padding: "6px 14px",
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: "0.1em",
                fontFamily: "monospace",
                cursor: (key === "live" && refreshing) ? "wait" : "pointer",
                border: `1px solid ${isActive ? GREEN : BORDER}`,
                borderRadius: 4,
                background: isActive ? "rgba(0, 229, 160, 0.12)" : "transparent",
                color: isActive ? GREEN : available ? HEADER : GREY,
                opacity: (!available && key !== "live") ? 0.4 : 1,
              }}
            >
              {key === "live" && refreshing ? "⟳ FETCHING..." : label}
              {timestamp && <span style={{ fontWeight: 400, marginLeft: 6, opacity: 0.7 }}>{timestamp}</span>}
            </button>
          );
        })}
      </div>

      <PerfTable
        title="Sector Performance"
        rows={data.absolute}
        labels={data.labels}
        showSpxSeparator
        asOf={active === "live" && data.refreshed_at ? `Live · ${data.refreshed_at}` : data.as_of}
      />
      <PerfTable
        title="Sector Relative Performance"
        rows={data.relative}
        labels={data.labels}
        showSpxSeparator={false}
        asOf={active === "live" && data.refreshed_at ? `Live · ${data.refreshed_at}` : data.as_of}
      />
    </div>
  );
}
