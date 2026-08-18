// Design tokens — single source of truth for colors, fonts, and typography.
// Import from here instead of defining per-component constants.

// ── Colors ──
export const GREEN  = "#00e5a0";
export const RED    = "#ff4d6d";
export const AMBER  = "#f0b429";
export const GREY   = "#8899aa";
export const LABEL  = "#c8d8e8";
export const TITLE  = "#e8f4ff";

// Surface hierarchy (darkest → lightest)
export const BG     = "#0a1628";
export const CARD   = "#0d1f35";
export const BORDER = "#2a3a50";
export const GRID   = "#1a2a3a";

// ── Fonts ──
export const FONT_SANS = "-apple-system, 'Segoe UI', sans-serif";
export const FONT_MONO = "'Menlo', 'Consolas', monospace";

// ── Stats table typography (Vol/Macro pages — LOCKED, rule #70) ──
// Format: fontSize / fontWeight / color / letterSpacing / textAlign
export const TYP = {
  pageTitle:    { fontSize: 18, fontWeight: 700, color: TITLE,  letterSpacing: "0.06em", textAlign: "left" },
  subtitle:     { fontSize: 11, fontWeight: 400, color: GREY,   letterSpacing: "0.05em", textAlign: "left" },
  timestamp:    { fontSize: 10, fontWeight: 400, color: GREY,   textAlign: "right" },
  colHeader:    { fontSize: 9,  fontWeight: 700, color: GREY,   letterSpacing: "0.1em",  textAlign: "center" },
  subHeader:    { fontSize: 8,  fontWeight: 700, color: GREY,   letterSpacing: "0.1em",  textAlign: "center" },
  dataValue:    { fontSize: 11, fontWeight: 400, color: LABEL,  textAlign: "center", fontFamily: FONT_MONO },
  rowLabel:     { fontSize: 11, fontWeight: 600, color: LABEL,  textAlign: "left" },
  footerText:   { fontSize: 10, fontWeight: 400, color: GREY,   letterSpacing: "0.03em", textAlign: "left" },
  footerBold:   { fontSize: 10, fontWeight: 600, color: LABEL,  letterSpacing: "0.03em", textAlign: "left" },
};
