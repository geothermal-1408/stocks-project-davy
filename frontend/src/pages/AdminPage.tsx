import { useState, useEffect, useRef } from 'react';
import { useAppStore } from '../store/appStore';
import { useMetrics } from '../hooks/useMetrics';
import { triggerIngest, triggerUnlearn, injectPoison, triggerRollback } from '../api/client';
import type { PoisonType } from '../types';
import PoisonComparisonWidget from '../components/dashboard/PoisonComparisonWidget';

const METHODS = ['AD', 'AKL', 'GA', 'RANDOM_LABEL'] as const;
const POISON_TYPES: PoisonType[] = [
  'price_outlier', 'flash_crash', 'volume_spike',
  'negative_price', 'ohlc_violation', 'stale_data', 'regime_change'
];

export default function AdminPage() {
  const { config, setConfig, pipelineState, setPipelineState } = useAppStore();
  const [selectedMethod, setSelectedMethod] = useState<string>('AD');
  const [fetchTicker, setFetchTicker] = useState('AAPL');
  const [injectType, setInjectType] = useState<string>('flash_crash');
  const [injectTicker, setInjectTicker] = useState('AAPL');
  const [injectSeverity, setInjectSeverity] = useState(3);
  // Track whether WE triggered the cycle (to show the button state correctly)
  const [cycleTriggered, setCycleTriggered] = useState(false);

  const severityLabels = ['subtle', 'moderate', 'severe', 'extreme', 'nuclear'];

  const [_fetchStatus, setFetchStatus] = useState<string | null>(null);
  const [injectResult, setInjectResult] = useState<string | null>(null);
  const [_rollbackStatus, setRollbackStatus] = useState<string | null>(null);
  const { metrics, refresh: refetchMetrics } = useMetrics();

  // Derive unlearning state from the shared store (updated by SSE events)
  const isUnlearning = pipelineState.status === 'unlearning' || cycleTriggered;
  const unlearnProgress = pipelineState.status === 'unlearning' ? (pipelineState.progress ?? 0) : 0;

  // Reset local trigger flag when pipeline goes idle (cycle finished)
  const prevStatus = useRef(pipelineState.status);
  useEffect(() => {
    if (prevStatus.current === 'unlearning' && pipelineState.status === 'idle') {
      setCycleTriggered(false);
      refetchMetrics();
    }
    prevStatus.current = pipelineState.status;
  }, [pipelineState.status, refetchMetrics]);

  const handleFetch = async () => {
    setPipelineState({ status: 'ingesting', ticker: fetchTicker, progress: 0, total: 30 });
    setFetchStatus(null);
    try {
      await triggerIngest(fetchTicker);
      setFetchStatus('Ingest triggered successfully');
    } catch {
      setFetchStatus('Backend unavailable — please start the server');
      setPipelineState({ status: 'idle' });
    }
  };
  const [devMode, setDevMode] = useState(false);

  const handleTriggerCycle = async () => {
    setCycleTriggered(true);
    const stepsForMode = devMode ? 10 : -1;
    setPipelineState({ status: 'unlearning', progress: 0, cycle: (metrics.current_cycle || 7) + 1, method: selectedMethod.toLowerCase(), epoch: '1/1' });
    try {
      const methodMap: Record<string, string> = { AD: 'ascent_plus_descent', AKL: 'akl', GA: 'gradient_ascent', RANDOM_LABEL: 'random_label' };
      await triggerUnlearn(methodMap[selectedMethod] || 'ascent_plus_descent', 5e-6, 1, stepsForMode);
      // Note: the HTTP call returns immediately (background task).
      // Progress will be updated via SSE events → pipelineState.
    } catch {
      setCycleTriggered(false);
      setPipelineState({ status: 'idle' });
    }
  };

  const displayHistory = metrics.history || [];
  const recentCycles = [...displayHistory].reverse().slice(0, 5);

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      <h2 className="font-display font-bold text-lg text-text-primary tracking-[0.15em] uppercase mb-2">
        CONTROL PLANE
      </h2>

      {/* 2×2 Grid */}
      <div className="grid grid-cols-2 gap-4">
        {/* Panel 1: Ingestion */}
        <div className="bg-bg-card border border-border p-4">
          <h3 className="font-display text-sm text-text-muted tracking-wider uppercase mb-4 pb-2 border-b border-border">
            INGESTION
          </h3>
          <div className="flex items-center gap-2 mb-4">
            <input
              type="text"
              value={fetchTicker}
              onChange={e => setFetchTicker(e.target.value.toUpperCase())}
              className="bg-bg-panel border border-border text-text-primary font-mono text-sm px-3 py-1.5 w-24 outline-none focus:border-accent-mint"
              placeholder="AAPL"
            />
            <button
              onClick={handleFetch}
              className="px-4 py-1.5 bg-accent-mint/10 border border-accent-mint text-accent-mint font-mono text-sm hover:bg-accent-mint/20 transition-colors"
            >
              FETCH
            </button>
          </div>
          <div className="space-y-2 font-mono text-xs text-text-muted">
            <div>
              Last ingest: <span className="text-text-primary">{metrics.last_ingest ? new Date(metrics.last_ingest).toLocaleString('en-US', { hour12: false, timeZone: 'America/New_York' }) + ' ET' : '—'}</span>
            </div>
            <div>
              Next scheduled: <span className="text-text-primary">{metrics.next_ingest ? new Date(metrics.next_ingest).toLocaleString('en-US', { hour12: false, timeZone: 'America/New_York' }) + ' ET' : '—'}</span>
            </div>
          </div>
        </div>

        {/* Panel 2: Unlearn Control */}
        <div className="bg-bg-card border border-border p-4">
          <h3 className="font-display text-sm text-text-muted tracking-wider uppercase mb-4 pb-2 border-b border-border">
            UNLEARN CONTROL
          </h3>
          <div className="flex items-center gap-2 mb-4">
            {METHODS.map(m => (
              <button
                key={m}
                onClick={() => setSelectedMethod(m)}
                className={`px-3 py-1 font-mono text-xs border transition-colors ${
                  selectedMethod === m
                    ? 'border-accent-mint text-accent-mint bg-accent-mint/10'
                    : 'border-border text-text-muted hover:text-text-primary'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 mb-3 cursor-pointer">
            <input
              type="checkbox"
              checked={devMode}
              onChange={e => setDevMode(e.target.checked)}
              className="accent-accent-warning"
            />
            <span className="font-mono text-[10px] text-accent-warning uppercase">
              DEV MODE (10 steps only — ~30s)
            </span>
          </label>
          <button
            onClick={handleTriggerCycle}
            disabled={isUnlearning}
            className={`w-full py-2 border font-mono text-sm transition-colors mb-3 ${
              isUnlearning
                ? 'border-accent-danger/50 text-accent-danger/50 cursor-not-allowed'
                : 'border-accent-danger text-accent-danger hover:bg-accent-danger hover:text-white'
            }`}
          >
            {isUnlearning ? `UNLEARNING... ${Math.min(unlearnProgress, 100)}%` : 'TRIGGER CYCLE'}
          </button>
          {isUnlearning && (
            <div className="h-1 bg-bg-hover mb-3">
              <div
                className="h-full bg-accent-danger transition-all duration-300"
                style={{ width: `${Math.min(unlearnProgress, 100)}%` }}
              />
            </div>
          )}
          <button className="w-full py-2 border border-accent-danger bg-accent-danger/10 text-accent-danger font-mono text-xs">
            EMERGENCY UNLEARN (GA)
          </button>
        </div>

        {/* Panel 3: Poison Injector */}
        <div className="bg-bg-card border border-border p-4">
          <h3 className="font-display text-sm text-text-muted tracking-wider uppercase mb-4 pb-2 border-b border-border">
            POISON INJECTOR (TESTING)
          </h3>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="font-mono text-[10px] text-text-muted uppercase block mb-1">TYPE</label>
                <select
                  value={injectType}
                  onChange={e => setInjectType(e.target.value)}
                  className="w-full bg-bg-panel border border-border text-text-primary font-mono text-xs px-2 py-1.5 outline-none focus:border-accent-warning"
                >
                  {POISON_TYPES.map(t => (
                    <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="font-mono text-[10px] text-text-muted uppercase block mb-1">TICKER</label>
                <select
                  value={injectTicker}
                  onChange={e => setInjectTicker(e.target.value)}
                  className="w-full bg-bg-panel border border-border text-text-primary font-mono text-xs px-2 py-1.5 outline-none focus:border-accent-warning"
                >
                  <option value="AAPL">AAPL</option>
                </select>
              </div>
            </div>
            <div>
              <label className="font-mono text-[10px] text-text-muted uppercase block mb-1">
                SEVERITY ({severityLabels[injectSeverity - 1]})
              </label>
              <input
                type="range"
                min={1}
                max={5}
                value={injectSeverity}
                onChange={e => setInjectSeverity(Number(e.target.value))}
                className="w-full"
              />
              <div className="flex justify-between font-mono text-[8px] text-text-muted mt-0.5">
                {severityLabels.map(l => <span key={l}>{l}</span>)}
              </div>
            </div>
            {injectResult && (
              <div className={`p-2 border font-mono text-[10px] space-y-1 ${
                injectResult.includes('✓') ? 'border-accent-mint/30 bg-accent-mint/5 text-accent-mint'
                : injectResult.includes('✗') ? 'border-accent-danger/30 bg-accent-danger/5 text-accent-danger'
                : 'border-accent-warning/30 bg-accent-warning/5 text-accent-warning'
              }`}>
                <div>{injectResult}</div>
              </div>
            )}
            <button
              onClick={async () => {
                setInjectResult(null);
                try {
                  const result = await injectPoison(injectTicker, injectType, new Date().toISOString().split('T')[0]);
                  if (result.error) {
                    setInjectResult(`⚠ ${result.error}`);
                  } else if (result.detected) {
                    setInjectResult(`✓ Detected — ${injectType.replace(/_/g, ' ')} on ${injectTicker}\n→ Routed to forget_buffer.jsonl\n→ Will trigger unlearn at threshold`);
                  } else {
                    setInjectResult(`✗ Not detected — ${injectType.replace(/_/g, ' ')} evaded the 7-signal screener`);
                  }
                } catch (e: any) {
                  setInjectResult(`⚠ ${e?.message || 'Backend offline — injection failed'}`);
                }
              }}
              className="w-full py-1.5 border border-accent-warning text-accent-warning font-mono text-xs hover:bg-accent-warning/10 transition-colors"
            >
              INJECT
            </button>

            {/* Latest unlearn cycle metrics */}
            {metrics.latest && (metrics.latest.forget_ppl !== null || metrics.latest.retain_ppl !== null) && (
              <div className="mt-2 p-2 border border-border bg-bg-panel">
                <div className="font-mono text-[9px] text-text-muted uppercase mb-1">
                  LATEST UNLEARN METRICS (Cycle {metrics.current_cycle || '—'})
                </div>
                <div className="grid grid-cols-3 gap-2 font-mono text-[10px]">
                  <div>
                    <span className="text-text-muted">Forget PPL: </span>
                    <span className="text-accent-mint">{metrics.latest.forget_ppl?.toFixed(2) ?? '—'}</span>
                  </div>
                  <div>
                    <span className="text-text-muted">Retain PPL: </span>
                    <span className="text-text-primary">{metrics.latest.retain_ppl?.toFixed(2) ?? '—'}</span>
                  </div>
                  <div>
                    <span className="text-text-muted">MAE: </span>
                    <span className="text-text-primary">{metrics.latest.mae_validation?.toFixed(4) ?? '—'}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Panel 4: Config Editor */}
        <div className="bg-bg-card border border-border p-4">
          <h3 className="font-display text-sm text-text-muted tracking-wider uppercase mb-4 pb-2 border-b border-border">
            CONFIG EDITOR
          </h3>
          <div className="space-y-3">
            {/* σ threshold */}
            <div>
              <div className="flex justify-between font-mono text-xs mb-1">
                <span className="text-text-muted">σ threshold</span>
                <span className="text-text-primary">{config.sigma_thresh.toFixed(1)}</span>
              </div>
              <input
                type="range"
                min={1}
                max={6}
                step={0.1}
                value={config.sigma_thresh}
                onChange={e => setConfig({ sigma_thresh: Number(e.target.value) })}
                className="w-full"
              />
            </div>
            {/* Swing % */}
            <div>
              <div className="flex justify-between font-mono text-xs mb-1">
                <span className="text-text-muted">Swing %</span>
                <span className="text-text-primary">{(config.swing_thresh * 100).toFixed(0)}%</span>
              </div>
              <input
                type="range"
                min={0.01}
                max={0.30}
                step={0.01}
                value={config.swing_thresh}
                onChange={e => setConfig({ swing_thresh: Number(e.target.value) })}
                className="w-full"
              />
            </div>
            {/* Vol mult */}
            <div>
              <div className="flex justify-between font-mono text-xs mb-1">
                <span className="text-text-muted">Vol mult</span>
                <span className="text-text-primary">{config.vol_multiplier}×</span>
              </div>
              <input
                type="range"
                min={2}
                max={15}
                step={1}
                value={config.vol_multiplier}
                onChange={e => setConfig({ vol_multiplier: Number(e.target.value) })}
                className="w-full"
              />
            </div>
            {/* Forget trigger */}
            <div>
              <div className="flex justify-between font-mono text-xs mb-1">
                <span className="text-text-muted">Forget trigger</span>
                <span className="text-text-primary">{config.forget_trigger}</span>
              </div>
              <input
                type="range"
                min={2}
                max={20}
                step={1}
                value={config.forget_trigger}
                onChange={e => setConfig({ forget_trigger: Number(e.target.value) })}
                className="w-full"
              />
            </div>
            {/* Min retain */}
            <div>
              <div className="flex justify-between font-mono text-xs mb-1">
                <span className="text-text-muted">Min retain</span>
                <span className="text-text-primary">{config.min_retain}</span>
              </div>
              <input
                type="range"
                min={5}
                max={100}
                step={5}
                value={config.min_retain}
                onChange={e => setConfig({ min_retain: Number(e.target.value) })}
                className="w-full"
              />
            </div>
            {/* Learning rate (read-only) */}
            <div className="flex justify-between font-mono text-xs">
              <span className="text-text-muted">Learning rate</span>
              <span className="text-text-primary">{config.learning_rate}</span>
            </div>

            <button className="w-full py-1.5 border border-accent-mint text-accent-mint font-mono text-xs hover:bg-accent-mint/10 transition-colors mt-2">
              SAVE CONFIG
            </button>
          </div>
        </div>
      </div>
      
      {/* Prediction Comparison Widget */}
      <PoisonComparisonWidget />

      {/* Panel 5: Rollback (full width) */}
      <div className="bg-bg-card border border-border p-4">
        <h3 className="font-display text-sm text-text-muted tracking-wider uppercase mb-4 pb-2 border-b border-border">
          ROLLBACK
        </h3>
        <p className="font-mono text-[10px] text-text-muted mb-3">
          Rollback rewrites ./output/stock/current symlink. Current cycle weights are NOT deleted.
        </p>
        <div className="space-y-1">
          {recentCycles.map(cycle => (
            <div
              key={cycle.cycle_num}
              className="flex items-center justify-between px-3 py-2 border border-border hover:bg-bg-hover transition-colors"
            >
              <div className="flex items-center gap-3 font-mono text-xs">
                <span className="text-text-primary">CYCLE {cycle.cycle_num}</span>
                <span className="text-text-muted">{cycle.date}</span>
                <span className="text-text-muted">{cycle.method}</span>
                <span className="text-text-muted">MAE {cycle.mae_validation?.toFixed(2) ?? '—'}</span>
                {cycle.deployed && (
                  <span className="px-1.5 py-0.5 border border-accent-mint text-accent-mint text-[10px]">
                    → ACTIVE
                  </span>
                )}
                {cycle.gate_failure && (
                  <span className="px-1.5 py-0.5 border border-accent-danger/50 text-accent-danger text-[10px]">
                    ✗ {cycle.gate_failure}
                  </span>
                )}
              </div>
              <button
                disabled={cycle.cycle_num === (metrics.current_cycle || 7)}
                onClick={async () => {
                  try {
                    await triggerRollback(cycle.cycle_num);
                    setRollbackStatus(`Rolled back to cycle ${cycle.cycle_num}`);
                  } catch { setRollbackStatus('Backend offline — rollback failed'); }
                }}
                className={`px-3 py-1 border font-mono text-[10px] transition-colors ${
                  cycle.cycle_num === (metrics.current_cycle || 7)
                    ? 'border-border text-text-muted cursor-not-allowed'
                    : 'border-accent-warning text-accent-warning hover:bg-accent-warning/10'
                }`}
              >
                RESTORE
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}