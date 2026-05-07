/**
 * useMetrics — fetches dashboard metrics from backend only (no mock fallback).
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import type { Metrics } from '../types';
import { fetchMetrics } from '../api/client';

const EMPTY_METRICS: Metrics = {
  current_cycle: 0,
  method: '',
  latest: {
    forget_ppl: 0,
    retain_ppl: 0,
    mae_validation: 0,
    directional_acc: 0,
    mia_auc: 0.5,
  },
  history: [],
  buffer_status: {
    forget_count: 0,
    retain_count: 0,
    trigger_at: 5,
    min_retain: 20,
  },
  last_ingest: '',
  next_ingest: '',
};

export function useMetrics(pollIntervalMs = 60_000) {
  const [metrics, setMetrics] = useState<Metrics>(EMPTY_METRICS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchMetrics();
      if (data && data.current_cycle !== undefined) {
        setMetrics({
          current_cycle: data.current_cycle,
          method: data.method || '',
          latest: {
            forget_ppl: data.latest?.forget_ppl || 0,
            retain_ppl: data.latest?.retain_ppl || 0,
            mae_validation: data.latest?.mae_validation || 0,
            directional_acc: data.latest?.directional_acc || 0,
            mia_auc: data.latest?.mia_auc || 0.5,
          },
          history: (data.history || []).map((c: any) => ({
            ...c,
            date: c.created_at?.split('T')[0] || c.date || '',
            gates: c.gates || [],
          })),
          buffer_status: {
            forget_count: data.buffer_status?.forget_count || 0,
            retain_count: data.buffer_status?.retain_count || 0,
            trigger_at: data.buffer_status?.trigger_at || 5,
            min_retain: data.buffer_status?.min_retain || 20,
          },
          last_ingest: data.last_ingest || '',
          next_ingest: data.next_ingest || '',
        });
        setIsLive(true);
        setError(null);
      } else {
        setError('No metrics data available');
        setIsLive(false);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch metrics');
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

  return { metrics, loading, error, isLive, refresh };
}
