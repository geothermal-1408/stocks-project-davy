/**
 * usePrediction — fetches prediction from backend with localStorage caching.
 * Caches predictions for 5 minutes to avoid re-running the model on every page visit.
 */
import { useState, useEffect, useCallback } from 'react';
import type { Prediction } from '../types';
import { fetchPrediction } from '../api/client';

const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

interface CachedPrediction {
  data: Prediction;
  timestamp: number;
}

function getCacheKey(ticker: string): string {
  return `ss_pred_${ticker}`;
}

function getCachedPrediction(ticker: string): Prediction | null {
  try {
    const raw = localStorage.getItem(getCacheKey(ticker));
    if (!raw) return null;
    const cached: CachedPrediction = JSON.parse(raw);
    if (Date.now() - cached.timestamp > CACHE_TTL_MS) {
      localStorage.removeItem(getCacheKey(ticker));
      return null;
    }
    return cached.data;
  } catch {
    return null;
  }
}

function setCachedPrediction(ticker: string, data: Prediction): void {
  try {
    const cached: CachedPrediction = { data, timestamp: Date.now() };
    localStorage.setItem(getCacheKey(ticker), JSON.stringify(cached));
  } catch {
    // localStorage full or unavailable — ignore
  }
}

export function usePrediction(ticker: string) {
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);

  const refresh = useCallback(async (bypassCache = false) => {
    setLoading(true);
    setError(null);

    // Check cache first (unless bypassed)
    if (!bypassCache) {
      const cached = getCachedPrediction(ticker);
      if (cached) {
        setPrediction(cached);
        setIsLive(true);
        setLoading(false);
        return;
      }
    }

    try {
      const data = await fetchPrediction(ticker);
      if (data && !data.error) {
        const pred: Prediction = {
          ticker: data.ticker || ticker,
          pred_date: data.pred_date || '',
          prediction: data.prediction || { open: 0, high: 0, low: 0, close: 0, vol: 0 },
          confidence: data.confidence || { close_high: 0, close_low: 0 },
          directional: data.directional || 'up',
          directional_pct: data.directional_pct || 50,
          model_cycle: data.model_cycle || 0,
          method: data.method || 'AD',
          mae: data.mae || 0,
          samples: data.samples || 10,
          generated_at: data.generated_at || new Date().toISOString(),
        };
        setPrediction(pred);
        setCachedPrediction(ticker, pred);
        setIsLive(true);
      } else {
        setPrediction(null);
        setIsLive(false);
      }
    } catch {
      // Backend unavailable — no mock fallback
      setPrediction(null);
      setIsLive(false);
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  /** Force refresh — bypasses cache */
  const forceRefresh = useCallback(() => refresh(true), [refresh]);

  useEffect(() => { refresh(); }, [refresh]);

  return { prediction, loading, error, isLive, refresh: forceRefresh };
}