import { useState, useEffect } from "react";
import { apiFetch } from "../../services/api";

const GREEN   = "#00e5a0";
const ORANGE  = "#ff4d6d";
const PINK    = "#e879f9";
const GREY    = "#8899aa";
const BG      = "#07111f";
const BORDER  = "#1a2a3a";
const HEADER  = "#c8d8e8";

function fmt(n, digits = 2) {
  if (n == null) return "—";
  return n.toFixed(digits) + "%";
}

function fmtSigned(n, digits = 2) {
  if (n == null) return "—";
  const s = Math.abs(n).toFixed(digits) + "%";
  return (n >= 0 ? "+" : "-") + s;
}

function ImpactTable({ rows, side }) {
  const isPos = side === "contributors";
  const accentColor = isPos ? GREEN : ORANGE;
  const labelTicker = isPos ? "Top Contributor" : "Top Detractor";

  return (
    <table style={{ borderCollapse: "collapse", width: "100%", tableLayout: "fixed" }}>
      <colgroup>
        <col style={{ width: "28%" }} />
        <col style={{ width: "24%" }} />
        <col style={{ width: "24%" }} />
        <col style={{ width: "24%" }} />
      </colgroup>
      <thead>
        <tr>
          {[labelTicker, "Daily Return", "% of Move", "% Weight"].map((h, i) => (
            <th
              key={i}
              style={{
                padding: "6px 10px",
                textAlign: i === 0 ? "left" : "right",
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: "0.08em",
                color: GREY,
                borderBottom: `1px solid ${BORDER}`,
                whiteSpace: "nowrap",
              }}
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.ticker} style={{ borderBottom: `1px solid ${BORDER}` }}>
            <td style={{ padding: "8px 10px", fontSize: 13, fontWeight: 700, color: HEADER, letterSpacing: "0.04em" }}>
              {row.ticker}
            </td>
            <td style={{ padding: "8px 10px", fontSize: 13, fontWeight: 600, color: accentColor, textAlign: "right" }}>
              {isPos ? "+" : ""}{fmt(row.daily_return_pct)}
            </td>
            <td style={{ padding: "8px 10px", fontSize: 13, fontWeight: 600, color: accentColor, textAlign: "right" }}>
              {row.contribution_norm != null ? (isPos ? "+" : "-") + row.contribution_norm.toFixed(2) + "%" : "—"}
            </td>
            <td style={{ padding: "8px 10px", fontSize: 13, fontWeight: 600, color: PINK, textAlign: "right" }}>
              {fmt(row.weight_pct)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const SNAPSHOTS = [
  { key: "eod",  label: "EOD" },
  { key: "11am", label: "11 AM" },
  { key: "1pm",  label: "1 PM"  },
];

export default function SpxImpactDashboard() {
  const [snapshots, setSnapshots] = useState({ eod: null, "11am": null, "1pm": null });
  const [active, setActive]       = useState("eod");
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);

  useEffect(() => {
    apiFetch("/api/spx-impact")
      .then(r => r.json())
      .then(d => { setSnapshots(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const data = snapshots[active];
  const spxColor = data?.spx_return_pct == null
    ? GREY
    : data.spx_return_pct >= 0 ? GREEN : ORANGE;

  return (
    <div style={{ padding: "28px 164px 28px 164px", minHeight: "100vh", background: BG, color: HEADER }}>

      {/* ── Page header ─────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
          <h1 style={{ margin: 0, fontSize: 16, fontWeight: 700, letterSpacing: "0.12em", color: HEADER }}>
            SPX CONSTITUENTS — RELATIVE IMPACT BY MARKET CAP
          </h1>
          {data?.spx_return_pct != null && (
            <span style={{ fontSize: 13, fontWeight: 600, color: spxColor }}>
              Est. SPX {fmtSigned(data.spx_return_pct, 3)}
            </span>
          )}
        </div>

        {/* Subtitle + snapshot toggle */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 10, flexWrap: "wrap", gap: 12 }}>
          <div style={{ display: "flex", gap: 24, fontSize: 11, flexWrap: "wrap" }}>
            <span style={{ color: GREEN, fontWeight: 600, letterSpacing: "0.08em" }}>▲ LARGEST POSITIVE IMPACT</span>
            <span style={{ color: ORANGE, fontWeight: 600, letterSpacing: "0.08em" }}>▼ LARGEST NEGATIVE IMPACT</span>
            {data?.computed_date && (
              <span style={{ color: GREY }}>
                {active === "eod" ? "EOD" : active.toUpperCase()} {data.computed_date}
              </span>
            )}
            {data?.tickers_priced && (
              <span style={{ color: GREY }}>{data.tickers_priced} constituents priced</span>
            )}
          </div>

          {/* Snapshot toggle */}
          <div style={{ display: "flex", gap: 6 }}>
            {SNAPSHOTS.map(({ key, label }) => {
              const available = !!snapshots[key];
              const isActive  = active === key;
              return (
                <button
                  key={key}
                  onClick={() => available && setActive(key)}
                  disabled={!available}
                  style={{
                    padding: "4px 12px",
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: "0.1em",
                    borderRadius: 4,
                    border: `1px solid ${isActive ? GREEN : available ? BORDER : BORDER}`,
                    background: isActive ? "rgba(0,229,160,0.1)" : "transparent",
                    color: isActive ? GREEN : available ? GREY : "#2a3a4a",
                    cursor: available ? "pointer" : "default",
                    transition: "all 150ms ease",
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── States ──────────────────────────────────────────────────────── */}
      {loading && (
        <div style={{ color: GREY, fontSize: 13, padding: "40px 0" }}>Loading...</div>
      )}
      {error && (
        <div style={{ color: ORANGE, fontSize: 13, padding: "40px 0" }}>Error: {error}</div>
      )}
      {!loading && !error && !snapshots.eod && (
        <div style={{ color: GREY, fontSize: 13, padding: "40px 0" }}>
          No data yet — runs at 4 PM ET on trading days.
        </div>
      )}

      {/* ── Dual table ──────────────────────────────────────────────────── */}
      {!loading && data?.contributors?.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>

          {/* Contributors */}
          <div style={{ background: "#060e1a", border: `1px solid ${BORDER}`, borderRadius: 6, overflow: "hidden" }}>
            <div style={{
              padding: "10px 12px",
              borderBottom: `1px solid ${BORDER}`,
              fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: GREEN,
            }}>
              TOP CONTRIBUTORS
            </div>
            <ImpactTable rows={data.contributors} side="contributors" />
          </div>

          {/* Detractors */}
          <div style={{ background: "#060e1a", border: `1px solid ${BORDER}`, borderRadius: 6, overflow: "hidden" }}>
            <div style={{
              padding: "10px 12px",
              borderBottom: `1px solid ${BORDER}`,
              fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: ORANGE,
            }}>
              TOP DETRACTORS
            </div>
            <ImpactTable rows={data.detractors} side="detractors" />
          </div>
        </div>
      )}

      {/* ── Footer note ─────────────────────────────────────────────────── */}
      <div style={{ marginTop: 20, fontSize: 10, color: GREY, letterSpacing: "0.06em" }}>
        % of Move = |Contribution| ÷ Σ|All Contributions|. Contribution = Daily Return × Weight. Source: iShares IVV holdings (EOD).
      </div>
    </div>
  );
}
