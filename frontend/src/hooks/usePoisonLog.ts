/**
 * usePoisonLog — fetches paginated poison event log from backend.
 */
import { useState, useEffect, useCallback } from 'react';
import type { PoisonEvent } from '../types';
import { fetchPoisonLog } from '../api/client';

export function usePoisonLog(page = 1, limit = 20, ticker?: string, type?: string) {
  const [events, setEvents] = useState<PoisonEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [isLive, setIsLive] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchPoisonLog(page, limit, ticker, type);
      if (data && data.events) {
        setEvents(data.events);
        setTotal(data.total);
        setIsLive(true);
      } else {
        setEvents([]);
        setTotal(0);
        setIsLive(false);
      }
    } catch {
      setEvents([]);
      setTotal(0);
      setIsLive(false);
    } finally {
      setLoading(false);
    }
  }, [page, limit, ticker, type]);

  useEffect(() => { refresh(); }, [refresh]);

  return { events, total, loading, isLive, refresh };
}
