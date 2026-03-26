const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

/**
 * Fetch real market data for all Tier 1 tickers.
 * Returns a Map of ticker -> data object for O(1) lookup.
 * Returns empty Map on any failure — React falls back to mock.
 */
export async function fetchBatchMarketData() {
  try {
    const response = await fetch(`${API_URL}/api/market-data/batch`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    });

    if (!response.ok) {
      console.warn(`[API] Batch fetch failed: ${response.status}`);
      return new Map();
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
 * Fetch single ticker quote.
 * Useful for debugging in browser console:
 *   import { fetchQuote } from './services/api';
 *   fetchQuote('AAPL').then(console.log)
 */
export async function fetchQuote(ticker) {
  try {
    const response = await fetch(`${API_URL}/api/market-data/quote/${ticker}`);
    if (!response.ok) return null;
    return await response.json();
  } catch (err) {
    console.warn(`[API] fetchQuote(${ticker}) failed`, err);
    return null;
  }
}
