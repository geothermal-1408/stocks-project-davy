/**
 * useMetrics — fetches dashboard metrics from backend, polled every 60s.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import type { Metrics } from '../types';
import { fetchMetrics } from '../api/client';

const EMPTY_METRICS: Metrics = {
  current_cycle: 0,
  mae: 0,
  forget_ppl: 0,
  retain_ppl: 0,
  mia_auc: 0.5,
  directional_acc: 0.5,
  buffer_status: { forget_size: 0, retain_size: 0, next_unlearn_at: 5 },
  history: []
};

export function useMetrics(pollIntervalMs = 60_000) {
  const [metrics, setMetrics] = useState<Metrics>(EMPTY_METRICS);
  const [loading, setLoading] = useState(true);
  const [isLive, setIsLive] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchMetrics();
      if (data && data.current_cycle !== undefined) {
        setMetrics({
          ...EMPTY_METRICS,
          ...data,
          buffer_status: {
            ...EMPTY_METRICS.buffer_status,
            ...(data.buffer_status || {}),
          },
          history: data.history?.length > 0 ? data.history.map((c: any) => ({
            ...c,
            date: c.created_at?.split('T')[0] || '',
            gates: [],
          })) : [],
        });
        setIsLive(true);
      }
    } catch {
      setMetrics(EMPTY_METRICS);
      setIsLive(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    intervalRef.current = setInterval(refresh, pollIntervalMs);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [refresh, pollIntervalMs]);

  return { metrics, loading, isLive, refresh };
}
