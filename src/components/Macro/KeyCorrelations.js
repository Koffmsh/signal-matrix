import React, { useEffect, useState, useCallback } from "react";
import { fetchCorrelations } from "../../services/api";

const GRID  = "#1a2a3a";
const TEXT  = "#8899aa";
const LABEL = "#c8d8e8";
const GREEN = "#00e5a0";
const RED   = "#ff4d6d";

const WINDOWS = ["15D", "30D", "90D", "120D", "180D"];

function corrColor(v) {
  if (v == null) return TEXT;
  const abs = Math.abs(v);
  if (abs >= 0.60) return v > 0 ? GREEN : RED;
  if (abs >= 0.40) return v > 0 ? "#66eebb" : "#ff8da6";
  return LABEL;
}

function corrBg(v) {
  if (v == null) return "transparent";
  const abs = Math.abs(v);
  if (abs >= 0.60) return v > 0 ? "rgba(0,229,160,0.14)" : "rgba(255,77,109,0.14)";
  if (abs >= 0.40) return v > 0 ? "rgba(0,229,160,0.07)" : "rgba(255,77,109,0.07)";
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

export default function KeyCorrelations() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
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
    setData(res);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

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
            KEY CORRELATIONS
          </h1>
          <span style={{ fontSize: 11, color: TEXT, letterSpacing: "0.05em" }}>
            ROLLING CORRELATIONS vs {data?.base ?? "DXY"}
          </span>
          {data?.updated && (
            <span style={{ fontSize: 10, color: TEXT, marginLeft: "auto" }}>
              EOD &middot; {data.updated}
            </span>
          )}
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
                  <th style={{ ...thStyle, borderLeft: `2px solid ${GRID}` }}>High</th>
                  <th style={thStyle}>Low</th>
                  <th style={thStyle}>% Time Pos</th>
                  <th style={thStyle}>% Time Neg</th>
                </tr>
                <tr>
                  <th style={{ ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#8899aa", fontSize: 8 }} />
                  <th colSpan={WINDOWS.length} style={{
                    ...thStyle, borderBottom: `2px solid ${GRID}`, color: "#8899aa", fontSize: 8,
                    textAlign: "center", fontStyle: "italic",
                  }}>
                    *Days = Trading Days
                  </th>
                  <th colSpan={4} style={{
                    ...thStyle, borderBottom: `2px solid ${GRID}`, borderLeft: `2px solid ${GRID}`,
                    color: "#8899aa", fontSize: 8, textAlign: "center",
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
                            color: corrColor(v),
                            background: corrBg(v),
                            fontWeight: Math.abs(v ?? 0) >= 0.60 ? 700 : 400,
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
            <span style={{ color: LABEL, fontWeight: 600 }}>Key $DXY Correlations</span> show
            rolling Pearson correlations of log returns vs the US Dollar Index across multiple timeframes.
            {" "}
            <span style={{ color: GREEN }}>Green</span> = strong positive correlation (moves with DXY);
            {" "}<span style={{ color: RED }}>Red</span> = strong negative correlation (moves inversely to DXY).
            {" "}The 52-week rolling 30D window computes the 30-day correlation every trading day for the past year —
            High/Low shows the range, % Time Pos/Neg shows how often the relationship was positive vs negative.
          </div>
        </div>
      )}
    </div>
  );
}
