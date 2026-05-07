/**
 * useOHLCV — fetches OHLCV data from backend only (no mock fallback).
 */
import { useState, useEffect, useCallback } from 'react';
import type { OHLCV, PoisonAnnotation } from '../types';
import { fetchOHLCV } from '../api/client';

export function useOHLCV(ticker: string, days = 90) {
  const [data, setData] = useState<OHLCV[]>([]);
  const [poisonAnnotations, setPoisonAnnotations] = useState<PoisonAnnotation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetchOHLCV(ticker, days);
      if (resp && resp.data && resp.data.length > 0) {
        setData(resp.data);
        setPoisonAnnotations(resp.poison_annotations || []);
        setIsLive(true);
      } else {
        setData([]);
        setPoisonAnnotations([]);
        setError('No OHLCV data available. Run data ingestion first.');
        setIsLive(false);
      }
    } catch (err: any) {
      setData([]);
      setPoisonAnnotations([]);
      setError(err.message || 'Failed to fetch OHLCV data');
      setIsLive(false);
    } finally {
      setLoading(false);
    }
  }, [ticker, days]);

  useEffect(() => { refresh(); }, [refresh]);

  return { data, poisonAnnotations, loading, error, isLive, refresh };
}
