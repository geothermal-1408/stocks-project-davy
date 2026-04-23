import { useCountUp } from '../../hooks/useUtils';

interface Props {
  label: string;
  value: number;
  unit?: string;
  suffix?: string;
  sparklineData: number[];
  trendDirection: 'up' | 'down'; // which direction is "healthy"
  status?: 'healthy' | 'warning' | 'danger';
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 80;
  const h = 24;

  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={w} height={h} className="shrink-0">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function MetricCard({ label, value, unit, suffix, sparklineData, trendDirection, status }: Props) {
  const animated = useCountUp(value, 600, label === 'DIR ACC' ? 1 : 2);

  const borderColor = status === 'danger' ? 'border-accent-danger'
    : status === 'warning' ? 'border-accent-warning'
    : 'border-accent-mint/30';

  const sparkColor = status === 'danger' ? '#ff3b30'
    : status === 'warning' ? '#f5a623'
    : '#00e5a0';

  // Determine if current trend is healthy
  const last = sparklineData[sparklineData.length - 1];
  const prev = sparklineData[sparklineData.length - 2];
  const isHealthy = trendDirection === 'up' ? last >= prev : last <= prev;

  return (
    <div className={`bg-bg-card border ${borderColor} p-3 flex flex-col justify-between`}>
      <div className="flex items-start justify-between mb-2">
        <span className="font-display text-[11px] text-text-muted tracking-wider uppercase">
          {label}
        </span>
        <div className={`w-1.5 h-1.5 ${isHealthy ? 'bg-accent-mint' : 'bg-accent-danger'}`} />
      </div>

      <div className="flex items-end justify-between">
        <div className="flex items-baseline gap-1">
          <span className="font-mono text-2xl text-text-primary leading-none">
            {animated}
          </span>
          {unit && <span className="font-mono text-xs text-text-muted">{unit}</span>}
          {suffix && <span className="font-mono text-[10px] text-text-muted">{suffix}</span>}
        </div>
        <Sparkline data={sparklineData} color={sparkColor} />
      </div>
    </div>
  );
}
