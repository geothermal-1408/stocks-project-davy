import type { AppConfig } from '../types';

// ── Only AAPL is supported ──
export const TICKERS = ['AAPL'] as const;
export type Ticker = (typeof TICKERS)[number];

// ── Default config (not mock data — these are UI defaults for the config editor) ──
export const DEFAULT_CONFIG: AppConfig = {
  sigma_thresh: 3.0,
  swing_thresh: 0.10,
  vol_multiplier: 5,
  forget_trigger: 5,
  min_retain: 20,
  learning_rate: '5e-6',
};
