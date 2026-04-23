import { useState } from 'react';
import { ChevronDown, ChevronRight, X } from 'lucide-react';
import { useAppStore } from '../store/appStore';
import { POISON_EVENTS, TICKERS } from '../data/mockData';
import { getPoisonColor } from '../hooks/useUtils';
import type { PoisonType, PoisonEvent } from '../types';

const POISON_TYPES: PoisonType[] = [
  'price_outlier', 'flash_crash', 'volume_spike',
  'negative_price', 'ohlc_violation', 'stale_data', 'regime_change'
];

export default function PoisonLogPage() {
  const { expandedPoisonRows, togglePoisonRow } = useAppStore();
  const [tickerFilter, setTickerFilter] = useState<string>('ALL');
  const [typeFilter, setTypeFilter] = useState<string>('ALL');
  const [sortField, setSortField] = useState<keyof PoisonEvent>('created_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [showInjectModal, setShowInjectModal] = useState(false);
  const [injectType, setInjectType] = useState<string>('flash_crash');
  const [injectSeverity, setInjectSeverity] = useState(3);

  const filteredEvents = POISON_EVENTS
    .filter(e => tickerFilter === 'ALL' || e.ticker === tickerFilter)
    .filter(e => typeFilter === 'ALL' || e.poison_type === typeFilter)
    .sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      return 0;
    });

  const handleSort = (field: keyof PoisonEvent) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const severityLabels = ['subtle', 'moderate', 'severe', 'extreme', 'nuclear'];

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      {/* Filter bar */}
      <div className="flex items-center gap-4 flex-wrap bg-bg-card border border-border p-3">
        {/* Ticker filter */}
        <div className="flex items-center gap-1">
          <span className="font-display text-[10px] text-text-muted tracking-wider uppercase mr-2">TICKER</span>
          {['ALL', ...TICKERS].map(t => (
            <button
              key={t}
              onClick={() => setTickerFilter(t)}
              className={`px-2 py-0.5 font-mono text-[11px] border transition-colors ${
                tickerFilter === t
                  ? 'border-accent-mint text-accent-mint bg-accent-mint/10'
                  : 'border-border text-text-muted hover:text-text-primary'
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="w-px h-6 bg-border" />

        {/* Type filter */}
        <div className="flex items-center gap-1 flex-wrap">
          <span className="font-display text-[10px] text-text-muted tracking-wider uppercase mr-2">TYPE</span>
          {['ALL', ...POISON_TYPES].map(t => (
            <button
              key={t}
              onClick={() => setTypeFilter(t)}
              className={`px-2 py-0.5 font-mono text-[10px] border transition-colors ${
                typeFilter === t
                  ? 'border-accent-mint text-accent-mint bg-accent-mint/10'
                  : 'border-border text-text-muted hover:text-text-primary'
              }`}
            >
              {t === 'ALL' ? 'ALL' : t.replace(/_/g, ' ').toUpperCase()}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        {/* Inject button */}
        <button
          onClick={() => setShowInjectModal(true)}
          className="px-3 py-1.5 border border-accent-warning text-accent-warning font-mono text-xs hover:bg-accent-warning/10 transition-colors"
        >
          INJECT SYNTHETIC POISON
        </button>
      </div>

      {/* Table */}
      <div className="bg-bg-card border border-border">
        {/* Table header */}
        <div className="grid grid-cols-[90px_70px_130px_130px_100px_80px_1fr] gap-0 px-2 py-2 border-b border-border">
          {[
            { key: 'created_at', label: 'DATE' },
            { key: 'ticker', label: 'TICKER' },
            { key: 'poison_type', label: 'TYPE' },
            { key: 'sigma', label: 'σ / SWING / VOL' },
            { key: 'window_start', label: 'WINDOW' },
            { key: 'buffered', label: 'STATUS' },
            { key: 'reason', label: 'REASON' },
          ].map(col => (
            <button
              key={col.key}
              onClick={() => handleSort(col.key as keyof PoisonEvent)}
              className="text-left font-mono text-[10px] text-text-muted uppercase tracking-wider hover:text-text-primary transition-colors"
            >
              {col.label}
              {sortField === col.key && (
                <span className="ml-1">{sortDir === 'asc' ? '↑' : '↓'}</span>
              )}
            </button>
          ))}
        </div>

        {/* Rows */}
        {filteredEvents.map((event, idx) => {
          const isExpanded = expandedPoisonRows.has(event.id);
          const color = getPoisonColor(event.poison_type);

          return (
            <div key={event.id}>
              <div
                onClick={() => togglePoisonRow(event.id)}
                className={`grid grid-cols-[90px_70px_130px_130px_100px_80px_1fr] gap-0 px-2 py-2 cursor-pointer transition-colors font-mono text-xs ${
                  idx % 2 === 0 ? 'bg-bg-card' : 'bg-bg/50'
                } hover:bg-bg-hover`}
              >
                <span className="text-text-muted flex items-center gap-1">
                  {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  {new Date(event.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                </span>
                <span className="text-text-primary">{event.ticker}</span>
                <span>
                  <span
                    className={`px-1.5 py-0.5 text-[10px] border ${
                      event.poison_type === 'negative_price' ? 'animate-pulse-red' : ''
                    }`}
                    style={{ borderColor: color, color }}
                  >
                    {event.poison_type.replace(/_/g, ' ').toUpperCase()}
                  </span>
                </span>
                <span className="text-text-primary">
                  {(() => {
                    const parts: string[] = [];
                    if (event.sigma != null) parts.push(`σ=${event.sigma.toFixed(2)}`);
                    if (event.swing_ratio != null) parts.push(`sw=${event.swing_ratio.toFixed(3)}`);
                    if (event.vol_ratio != null) parts.push(`vol=${event.vol_ratio.toFixed(1)}x`);
                    return parts.length > 0 ? parts.join(' · ') : '—';
                  })()}
                </span>
                <span className="text-text-muted text-[10px]">
                  {event.window_start.slice(5)} → {event.window_end.slice(5)}
                </span>
                <span className={event.buffered ? 'text-accent-mint' : 'text-text-muted'}>
                  {event.buffered ? 'BUFFERED' : 'PENDING'}
                </span>
                <span className="text-text-muted truncate">{event.reason}</span>
              </div>

              {/* Expanded details */}
              {isExpanded && (
                <div className="px-6 py-3 bg-bg-panel border-t border-b border-border">
                  <div className="font-mono text-[10px] text-text-muted uppercase tracking-wider mb-2">
                    RAW DETECTOR VALUES
                  </div>
                  <div className="grid grid-cols-3 gap-2 font-mono text-xs mb-3">
                    <span className="text-text-muted">sigma: <span className="text-text-primary">{event.sigma?.toFixed(2) ?? 'N/A'}</span></span>
                    <span className="text-text-muted">swing: <span className="text-text-primary">{event.swing_ratio?.toFixed(3) ?? 'N/A'}</span></span>
                    <span className="text-text-muted">vol_mult: <span className="text-text-primary">{event.vol_ratio?.toFixed(1) ?? 'N/A'}</span></span>
                  </div>
                  {event.window_text && (
                    <>
                      <div className="font-mono text-[10px] text-text-muted uppercase tracking-wider mb-1">
                        WINDOW TEXT
                      </div>
                      <div className="bg-bg p-2 border border-border font-mono text-[10px] text-text-muted overflow-x-auto whitespace-pre">
                        {event.window_text}
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {filteredEvents.length === 0 && (
          <div className="px-4 py-8 text-center font-mono text-sm text-text-muted">
            No poison events match filters
          </div>
        )}
      </div>

      {/* Inject Modal */}
      {showInjectModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center">
          <div className="bg-bg-card border border-border w-[400px] p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="font-display font-bold text-sm text-text-primary tracking-wider">INJECT SYNTHETIC POISON</h3>
              <button onClick={() => setShowInjectModal(false)} className="text-text-muted hover:text-text-primary">
                <X size={16} />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="font-mono text-[10px] text-text-muted uppercase tracking-wider block mb-1">
                  POISON TYPE
                </label>
                <select
                  value={injectType}
                  onChange={e => setInjectType(e.target.value)}
                  className="w-full bg-bg-panel border border-border text-text-primary font-mono text-xs px-3 py-2 outline-none focus:border-accent-warning"
                >
                  {POISON_TYPES.map(t => (
                    <option key={t} value={t}>{t.replace(/_/g, ' ').toUpperCase()}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="font-mono text-[10px] text-text-muted uppercase tracking-wider block mb-1">
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
                <div className="flex justify-between font-mono text-[9px] text-text-muted mt-1">
                  {severityLabels.map(l => (
                    <span key={l}>{l}</span>
                  ))}
                </div>
              </div>

              <button
                onClick={() => setShowInjectModal(false)}
                className="w-full py-2 border border-accent-warning text-accent-warning font-mono text-sm hover:bg-accent-warning/10 transition-colors"
              >
                INJECT
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
