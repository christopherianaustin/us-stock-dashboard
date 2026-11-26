// Every API address and data-mode setting for the prototype lives in this one file.

/** FastAPI from Phase 8. Use 127.0.0.1 (not "localhost"): it is ~2 s faster on Windows.
 *  On a phone over Wi-Fi, set VITE_API_BASE=http://<your-PC-IP>:8000 (see README). */
export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export const API = {
  summary: (t: string) => `${API_BASE}/stocks/${t}/summary`,
  financials: (t: string) => `${API_BASE}/stocks/${t}/financials`,
  ratios: (t: string) => `${API_BASE}/stocks/${t}/ratios`,
  valuation: (t: string) => `${API_BASE}/stocks/${t}/valuation`,
  technicals: (t: string) => `${API_BASE}/stocks/${t}/technicals`,
  earnings: (t: string) => `${API_BASE}/stocks/${t}/earnings`,
  dividends: (t: string) => `${API_BASE}/stocks/${t}/dividends`,
  ownership: (t: string) => `${API_BASE}/stocks/${t}/ownership`,
  news: (t: string) => `${API_BASE}/stocks/${t}/news`,
  profile: (t: string) => `${API_BASE}/stocks/${t}/profile`,
  fx: () => `${API_BASE}/fx/usdidr`,
  ai: (t: string) => `${API_BASE}/stocks/${t}/ai-summary`,
  aiFeedback: () => `${API_BASE}/ai-feedback`,
  aiUsage: () => `${API_BASE}/ai/usage`,
}

/** Saved API answers ("mock data mode"), made by scripts/make_mobile_mocks.py. */
export const MOCK_BASE = `${import.meta.env.BASE_URL}mock`

/** Data mode at start-up:
 *  auto = live API, and saved data if the API can't be reached;  live = API only;  mock = saved data only. */
export const DEFAULT_MODE: 'auto' | 'live' | 'mock' = 'auto'

/** Fixed USD → IDR rate, used only when neither the API nor the saved rate is available. Shown as "Mock rate". */
export const MOCK_USD_IDR = 18000

/** Tickers that have saved data in public/mock/. */
export const MOCK_TICKERS = ['AAPL', 'KO', 'TSLA', 'JPM'] as const

/** Quick picks in the debug menu. */
export const QUICK_TICKERS = ['AAPL', 'KO', 'TSLA', 'JPM', 'BRK-B'] as const
