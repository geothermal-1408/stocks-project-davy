/**
 * usePoisonLog — fetches paginated poison event log from backend.
 */
import { useState, useEffect, useCallback } from 'react';
import type { PoisonEvent } from '../types';
import { fetchPoisonLog } from '../api/client';
import { POISON_EVENTS } from '../data/mockData';

export function usePoisonLog(page = 1, limit = 20, ticker?: string, type?: string) {
  const [events, setEvents] = useState<PoisonEvent[]>(POISON_EVENTS);
  const [total, setTotal] = useState(POISON_EVENTS.length);
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
      }
    } catch {
      // Filter mock data by ticker/type
      let filtered = [...POISON_EVENTS];
      if (ticker) filtered = filtered.filter(e => e.ticker === ticker);
      if (type) filtered = filtered.filter(e => e.poison_type === type);
      setEvents(filtered);
      setTotal(filtered.length);
      setIsLive(false);
    } finally {
      setLoading(false);
    }
  }, [page, limit, ticker, type]);

  useEffect(() => { refresh(); }, [refresh]);

  return { events, total, loading, isLive, refresh };
}
