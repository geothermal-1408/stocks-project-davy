/**
 * usePipelineStream — SSE: GET /stream/events
 *
 * Listens to real-time pipeline events from the backend.
 * Updates the pipeline state in the Zustand store.
 * Auto-reconnects with exponential backoff on disconnect.
 */
import { useEffect, useRef } from 'react';
import { useAppStore } from '../store/appStore';
import { fetchEventSource } from '@microsoft/fetch-event-source';

const MAX_RECONNECT_DELAY = 30_000;
const INITIAL_RECONNECT_DELAY = 1_000;

export function usePipelineStream() {
  const { setPipelineState, triggerPoisonFlash } = useAppStore();
  const abortCtrlRef = useRef<AbortController | null>(null);
  const reconnectDelay = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let unmounted = false;

    function connect() {
      if (unmounted) return;
      
      const abortCtrl = new AbortController();
      abortCtrlRef.current = abortCtrl;

      fetchEventSource('/api/stream/events', {
        signal: abortCtrl.signal,
        headers: {
          'ngrok-skip-browser-warning': '69420',
        },
        async onopen(res) {
          if (res.ok && res.headers.get('content-type')?.includes('text/event-stream')) {
            reconnectDelay.current = INITIAL_RECONNECT_DELAY;
            return;
          }
        },
        onmessage(e) {
          if (e.event === 'ingest_start') {
            const data = JSON.parse(e.data);
            setPipelineState({ status: 'ingesting', ticker: data.ticker, progress: 0 });
          } else if (e.event === 'ingest_progress') {
            const data = JSON.parse(e.data);
            setPipelineState({ status: 'ingesting', ticker: data.ticker, progress: data.pct });
          } else if (e.event === 'poison_detected') {
            triggerPoisonFlash();
          } else if (e.event === 'ingest_complete') {
            const data = JSON.parse(e.data);
            if (data.cycle_triggered) {
              setPipelineState({ status: 'unlearning' });
            } else {
              setPipelineState({ status: 'idle' });
            }
          } else if (e.event === 'cycle_progress') {
            const data = JSON.parse(e.data);
            setPipelineState({ status: 'unlearning', progress: data.pct, method: data.step });
          } else if (e.event === 'cycle_complete') {
            const data = JSON.parse(e.data);
            setPipelineState({ status: 'idle' });
            // Store cycle result for display
            if (typeof window !== 'undefined') {
              window.dispatchEvent(new CustomEvent('cycle_result', { detail: data }));
            }
          } else if (e.event === 'cycle_error') {
            const data = JSON.parse(e.data);
            setPipelineState({ status: 'idle' });
            if (typeof window !== 'undefined') {
              window.dispatchEvent(new CustomEvent('cycle_result', { detail: { error: data.error } }));
            }
          }
        },
        onclose() {
          scheduleReconnect();
        },
        onerror() {
          scheduleReconnect();
          return;
        }
      }).catch(() => {
        // Ignored
      });
    }

    function scheduleReconnect() {
      if (unmounted) return;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      
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
      if (abortCtrlRef.current) {
        abortCtrlRef.current.abort();
        abortCtrlRef.current = null;
      }
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
    };
  }, [setPipelineState, triggerPoisonFlash]);
}
