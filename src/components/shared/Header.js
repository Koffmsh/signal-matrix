export default function Header() {
  return (
    <div style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      height: 48,
      background: "#060e1a",
      borderBottom: "1px solid #1a2a3a",
      display: "flex",
      alignItems: "center",
      padding: "0 20px",
      zIndex: 200,
      boxSizing: "border-box",
    }}>
      {/* Brand */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, userSelect: "none" }}>
        <div style={{
          width: 4,
          height: 20,
          background: "linear-gradient(180deg, #00e5a0, #0077ff)",
          borderRadius: 2,
          flexShrink: 0,
        }} />
        <span style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: "0.2em",
          color: "#e8f4ff",
          whiteSpace: "nowrap",
        }}>
          SIGNAL MATRIX
        </span>
        <span style={{
          fontSize: 9,
          fontWeight: 500,
          letterSpacing: "0.1em",
          color: "#445566",
          marginLeft: 4,
          whiteSpace: "nowrap",
        }}>
          MULTI-TIMEFRAME · PROBABILISTIC
        </span>
      </div>

      {/* Right side — future tools + user profile */}
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
        {/* User profile placeholder */}
        <div
          title="User Profile"
          style={{
            width: 30,
            height: 30,
            borderRadius: "50%",
            background: "#0d1f33",
            border: "1px solid #1a2a3a",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <circle cx="7" cy="4.5" r="2.5" stroke="#8899aa" strokeWidth="1.2" />
            <path d="M1.5 13c0-2.8 2.46-4.5 5.5-4.5s5.5 1.7 5.5 4.5" stroke="#8899aa" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
        </div>
      </div>
    </div>
  );
}
