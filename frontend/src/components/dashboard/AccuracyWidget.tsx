import { useMetrics } from '../../hooks/useMetrics';

interface AccuracyRingProps {
  value: number; // 0–100
  size?: number;
  strokeWidth?: number;
}

function AccuracyRing({ value, size = 100, strokeWidth = 6 }: AccuracyRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;
  const center = size / 2;

  const color = value >= 60 ? '#00e5a0' : value >= 52 ? '#f5a623' : '#ff3b30';

  return (
    <svg width={size} height={size} className="transform -rotate-90">
      {/* Background ring */}
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        className="text-bg-hover"
      />
      {/* Progress ring */}
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        className="transition-all duration-1000 ease-out"
      />
    </svg>
  );
}

export default function AccuracyWidget() {
  const { metrics } = useMetrics();
  const { latest, history } = metrics;

  const dirAcc = latest?.directional_acc;
  const hasValue = dirAcc != null && !isNaN(dirAcc);
  const percentage = hasValue ? dirAcc * 100 : 0;

  // Trend from last 2 cycles
  const validHistory = (history || []).filter(h => h.directional_acc != null && h.directional_acc > 0);
  const lastTwo = validHistory.slice(-2);
  let trendLabel = '';
  let trendColor = 'text-text-muted';
  if (lastTwo.length >= 2) {
    const prev = lastTwo[0].directional_acc * 100;
    const curr = lastTwo[1].directional_acc * 100;
    const diff = curr - prev;
    if (diff > 0) {
      trendLabel = `↑ +${diff.toFixed(1)}%`;
      trendColor = 'text-accent-mint';
    } else if (diff < 0) {
      trendLabel = `↓ ${diff.toFixed(1)}%`;
      trendColor = 'text-accent-danger';
    } else {
      trendLabel = '→ 0.0%';
    }
  }

  const statusLabel = percentage >= 60
    ? 'EXCELLENT'
    : percentage >= 52
      ? 'ACCEPTABLE'
      : percentage > 0
        ? 'BELOW TARGET'
        : 'NO DATA';

  const statusColor = percentage >= 60
    ? 'text-accent-mint'
    : percentage >= 52
      ? 'text-accent-warning'
      : percentage > 0
        ? 'text-accent-danger'
        : 'text-text-muted';

  return (
    <div className="bg-bg-card border border-border p-4">
      <h3 className="font-display text-sm text-text-muted tracking-wider uppercase mb-4 pb-2 border-b border-border">
        MODEL ACCURACY (POST-UNLEARN)
      </h3>

      <div className="flex items-center gap-6">
        {/* Radial progress */}
        <div className="relative shrink-0">
          <AccuracyRing value={hasValue ? percentage : 0} size={96} strokeWidth={5} />
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="font-mono text-xl text-text-primary leading-none">
              {hasValue ? `${percentage.toFixed(1)}` : '—'}
            </span>
            {hasValue && (
              <span className="font-mono text-[9px] text-text-muted">%</span>
            )}
          </div>
        </div>

        {/* Details */}
        <div className="flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <span className={`font-mono text-xs font-bold ${statusColor}`}>
              {statusLabel}
            </span>
          </div>

          <div className="space-y-1 font-mono text-[11px]">
            <div className="flex justify-between">
              <span className="text-text-muted">Directional Acc</span>
              <span className="text-text-primary">
                {hasValue ? `${percentage.toFixed(1)}%` : '—'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Target</span>
              <span className="text-text-muted">≥ 52.0%</span>
            </div>
            {trendLabel && (
              <div className="flex justify-between">
                <span className="text-text-muted">Trend</span>
                <span className={trendColor}>{trendLabel}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-text-muted">Cycle</span>
              <span className="text-text-primary">
                {metrics.current_cycle > 0 ? `#${metrics.current_cycle}` : '—'}
              </span>
            </div>
          </div>

          {/* Mini bar showing accuracy zone */}
          <div className="h-1.5 bg-bg-hover flex mt-1">
            <div className="w-[52%] bg-accent-danger/30 border-r border-bg-card" title="Below coin-flip" />
            <div className="w-[8%] bg-accent-warning/40 border-r border-bg-card" title="Acceptable" />
            <div className="flex-1 bg-accent-mint/30" title="Excellent" />
            {hasValue && (
              <div
                className="absolute h-1.5 w-0.5 bg-text-primary"
                style={{ marginLeft: `${Math.min(percentage, 100)}%` }}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
