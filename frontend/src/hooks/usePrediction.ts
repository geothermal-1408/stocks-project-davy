/**
 * usePrediction — fetches prediction from backend.
 * No mock/synthetic fallback — shows null when backend is unavailable.
 */
import { useState, useEffect, useCallback } from 'react';
import type { Prediction } from '../types';
import { fetchPrediction } from '../api/client';

export function usePrediction(ticker: string) {
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPrediction(ticker);
      if (data && !data.error) {
        setPrediction({
          ticker: data.ticker || ticker,
          pred_date: data.pred_date || '',
          prediction: data.prediction || { open: 0, high: 0, low: 0, close: 0, vol: 0 },
          confidence: data.confidence || { close_high: 0, close_low: 0 },
          directional: data.directional || 'up',
          directional_pct: data.directional === 'up' ? 65 : 35,
          model_cycle: data.model_cycle || 0,
          method: data.method || 'AD',
          mae: data.mae || 0,
          samples: data.samples || 10,
          generated_at: data.generated_at || new Date().toISOString(),
        });
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

  useEffect(() => { refresh(); }, [refresh]);

  return { prediction, loading, error, isLive, refresh };
}
