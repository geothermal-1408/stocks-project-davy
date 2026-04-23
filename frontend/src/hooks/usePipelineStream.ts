/**
 * usePipelineStream — SSE: GET /stream/events
 *
 * Listens to real-time pipeline events from the backend.
 * Updates the pipeline state in the Zustand store.
 */
import { useEffect, useRef } from 'react';
import { useAppStore } from '../store/appStore';
import { createEventSource } from '../api/client';

export function usePipelineStream() {
  const { setPipelineState, triggerPoisonFlash } = useAppStore();
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let es: EventSource;
    try {
      es = createEventSource();
      esRef.current = es;

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
        // SSE disconnected — backend might be down, ignore silently
      };
    } catch {
      // Backend not available — running in mock mode
    }

    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [setPipelineState, triggerPoisonFlash]);
}
