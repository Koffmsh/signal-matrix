const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

/**
 * apiFetch — wrapper that always sends the session cookie and redirects to /login on 401.
 *
 * Hard navigation on 401 is intentional — see "Deferred decisions" in
 * Docs/Auth_User_Management_Spec_v1.0.md (rejected useApiFetch hook).
 *
 * Usage:
 *   import { apiFetch } from "../services/api";
 *   const res = await apiFetch("/api/signals/stored");
 *   // pass /api/... only — do NOT include ${API_URL}; this function adds it.
 *
 * DO NOT use this for /api/auth/check, /api/auth/login, /api/auth/logout —
 * those use raw fetch in AuthContext. /api/auth/check returns 200 with
 * authenticated:false when not logged in; calling it via apiFetch would still
 * work today, but if it ever returns 401 the redirect logic would loop.
 */
export const apiFetch = async (path, options = {}) => {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) {
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    return null;
  }
  return res;
};

/**
 * Page load — read-only cache fetch. Never triggers Schwab/Yahoo.
 * Returns whatever is stored in price_cache right now.
 */
export async function fetchCachedMarketData() {
  try {
    const response = await apiFetch(`/api/market-data/cached`);
    if (!response || !response.ok) {
      if (response) console.warn(`[API] Cached fetch failed: ${response.status}`);
      return { map: new Map(), dataSource: "cached" };
    }
    const json    = await response.json();
    const dataMap = new Map();
    (json.data || []).forEach(item => dataMap.set(item.ticker, item));
    console.info(`[API] Loaded cached data for ${dataMap.size} tickers`);
    return { map: dataMap, dataSource: json.data_source || "cached" };
  } catch (err) {
    console.warn("[API] fetchCachedMarketData error — using mock data", err);
    return { map: new Map(), dataSource: "cached" };
  }
}

/**
 * REFRESH DATA button — triggers a full Schwab/Yahoo fetch and updates cache.
 * Returns a Map of ticker -> data object for O(1) lookup.
 * Returns empty Map on any failure — React falls back to mock.
 */
export async function fetchBatchMarketData() {
  try {
    const response = await apiFetch(`/api/market-data/batch`);
    if (!response || !response.ok) {
      if (response) console.warn(`[API] Batch fetch failed: ${response.status}`);
      return { map: new Map(), dataSource: "yahoo" };
    }

    const json = await response.json();
    const dataMap = new Map();

    (json.data || []).forEach(item => {
      dataMap.set(item.ticker, item);
    });

    console.info(`[API] Loaded real data for ${dataMap.size} tickers`);
    return { map: dataMap, dataSource: json.data_source || "yahoo" };

  } catch (err) {
    console.warn("[API] fetchBatchMarketData error — using mock data", err);
    return { map: new Map(), dataSource: "yahoo" };
  }
}

/**
 * SPX Realized Vol chart — rolling HV30/HV90 + daily pct change over full price history.
 */
export async function fetchSpxVolHistory() {
  try {
    const response = await apiFetch(`/api/vol/spx-history`);
    if (!response || !response.ok) return null;
    return await response.json();
  } catch (err) {
    console.warn("[API] fetchSpxVolHistory failed", err);
    return null;
  }
}

/**
 * Fetch single ticker quote.
 * Useful for debugging in browser console:
 *   import { fetchQuote } from './services/api';
 *   fetchQuote('AAPL').then(console.log)
 */
export async function fetchQuote(ticker) {
  try {
    const response = await apiFetch(`/api/market-data/quote/${ticker}`);
    if (!response || !response.ok) return null;
    return await response.json();
  } catch (err) {
    console.warn(`[API] fetchQuote(${ticker}) failed`, err);
    return null;
  }
}
