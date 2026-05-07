/**
 * useMetrics — fetches dashboard metrics from backend, polled every 60s.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import type { Metrics } from '../types';
import { fetchMetrics } from '../api/client';
import { METRICS } from '../data/mockData';

export function useMetrics(pollIntervalMs = 60_000) {
  const [metrics, setMetrics] = useState<Metrics>(METRICS);
  const [loading, setLoading] = useState(true);
  const [isLive, setIsLive] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchMetrics();
      if (data && data.current_cycle !== undefined) {
        // Merge backend response with the expected shape
        setMetrics({
          ...METRICS,
          ...data,
          buffer_status: {
            ...METRICS.buffer_status,
            ...(data.buffer_status || {}),
          },
          history: data.history?.length > 0 ? data.history.map((c: any) => ({
            ...c,
            date: c.created_at?.split('T')[0] || '',
            gates: [],  // Backend doesn't return full gates yet
          })) : METRICS.history,
        });
        setIsLive(true);
      }
    } catch {
      setMetrics(METRICS);
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
