/**
 * usePipelineStream — SSE: GET /stream/events
 *
 * Listens to real-time pipeline events from the backend.
 * Updates the pipeline state in the Zustand store.
 * Auto-reconnects with exponential backoff on disconnect.
 */
import { useEffect, useRef } from 'react';
import { useAppStore } from '../store/appStore';
import { createEventSource } from '../api/client';

const MAX_RECONNECT_DELAY = 30_000; // 30s max backoff
const INITIAL_RECONNECT_DELAY = 1_000; // 1s initial

export function usePipelineStream() {
  const { setPipelineState, triggerPoisonFlash } = useAppStore();
  const esRef = useRef<EventSource | null>(null);
  const reconnectDelay = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let unmounted = false;

    function connect() {
      if (unmounted) return;

      let es: EventSource;
      try {
        es = createEventSource();
        esRef.current = es;
      } catch {
        // Backend not available — schedule reconnect
        scheduleReconnect();
        return;
      }

      es.addEventListener('open', () => {
        // Reset backoff on successful connection
        reconnectDelay.current = INITIAL_RECONNECT_DELAY;
      });

      es.addEventListener('ingest_start', (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        setPipelineState({ status: 'ingesting', ticker: data.ticker, progress: 0 });
      });

      es.addEventListener('ingest_progress', (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        setPipelineState({
          status: 'ingesting',
          ticker: data.ticker,
          progress: data.pct,
        });
      });

      es.addEventListener('poison_detected', (_e: MessageEvent) => {
        triggerPoisonFlash();
      });

      es.addEventListener('ingest_complete', (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        if (data.cycle_triggered) {
          setPipelineState({ status: 'unlearning' });
        } else {
          setPipelineState({ status: 'idle' });
        }
      });

      es.addEventListener('cycle_progress', (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        setPipelineState({
          status: 'unlearning',
          progress: data.pct,
          method: data.step,
        });
      });

      es.addEventListener('cycle_complete', (_e: MessageEvent) => {
        setPipelineState({ status: 'idle' });
      });

      es.onerror = () => {
        // SSE disconnected — close and schedule reconnect
        es.close();
        esRef.current = null;
        scheduleReconnect();
      };
    }

    function scheduleReconnect() {
      if (unmounted) return;
      reconnectTimer.current = setTimeout(() => {
        reconnectDelay.current = Math.min(
          reconnectDelay.current * 2,
          MAX_RECONNECT_DELAY,
        );
        connect();
      }, reconnectDelay.current);
    }

    connect();

    return () => {
      unmounted = true;
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
    };
  }, [setPipelineState, triggerPoisonFlash]);
}
