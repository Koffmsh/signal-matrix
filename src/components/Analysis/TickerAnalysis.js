import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";

export default function TickerAnalysis() {
  const { symbol } = useParams();
  const navigate = useNavigate();
  const [input, setInput] = useState("");

  function handleNav(e) {
    e.preventDefault();
    const s = input.trim().toUpperCase();
    if (s) navigate(`/ticker/${s}`);
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#0a1628",
        color: "#e8f4ff",
        fontFamily: "monospace",
        padding: "32px 40px",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 32 }}>
        <div
          style={{
            width: 4,
            height: 32,
            background: "linear-gradient(180deg, #00e5a0, #0077ff)",
            borderRadius: 2,
          }}
        />
        <div>
          <div
            style={{
              fontSize: 9,
              letterSpacing: "0.2em",
              color: "#8899aa",
              marginBottom: 4,
            }}
          >
            TICKER ANALYSIS
          </div>
          <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: "0.1em" }}>
            {symbol}
          </div>
        </div>
      </div>

      {/* Ticker navigation */}
      <form onSubmit={handleNav} style={{ display: "flex", gap: 8, marginBottom: 48 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Enter ticker symbol…"
          style={{
            background: "#0d1f35",
            border: "1px solid #1a2a3a",
            borderRadius: 4,
            color: "#e8f4ff",
            fontSize: 11,
            letterSpacing: "0.1em",
            padding: "6px 12px",
            outline: "none",
            width: 200,
            fontFamily: "monospace",
          }}
        />
        <button
          type="submit"
          style={{
            background: "#0d3a2a",
            border: "1px solid #00e5a0",
            borderRadius: 4,
            color: "#00e5a0",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: "0.15em",
            padding: "6px 14px",
            cursor: "pointer",
            fontFamily: "monospace",
          }}
        >
          GO
        </button>
      </form>

      {/* Placeholder body */}
      <div
        style={{
          border: "1px solid #1a2a3a",
          borderRadius: 6,
          padding: "40px 32px",
          color: "#8899aa",
          fontSize: 11,
          letterSpacing: "0.1em",
          lineHeight: 2,
          maxWidth: 600,
        }}
      >
        <div style={{ color: "#00e5a0", marginBottom: 12, fontWeight: 700 }}>
          COMING SOON
        </div>
        {symbol} deep-dive analysis — charts, IV surface, ABC structure, regime
        context, and conviction breakdown. Select or enter a ticker above to
        navigate between instruments.
      </div>
    </div>
  );
}
