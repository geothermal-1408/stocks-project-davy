interface Props {
  forgetCount: number;
  triggerAt: number;
  minRetain: number;
}

export default function BufferGauge({ forgetCount, triggerAt, minRetain }: Props) {
  const pct = Math.min((forgetCount / triggerAt) * 100, 100);
  const isTriggered = forgetCount >= triggerAt;

  return (
    <div className="bg-bg-card border border-border p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="font-display text-xs text-text-muted tracking-wider uppercase">
          {isTriggered ? (
            <span className="text-accent-danger animate-pulse">⚡ CYCLE TRIGGERED</span>
          ) : (
            <>FORGET BUFFER  <span className="text-text-primary font-mono">{forgetCount} / {triggerAt}</span>  windows</>
          )}
        </span>
        <span className="font-mono text-[10px] text-text-muted">
          TRIGGER AT {triggerAt} · MIN RETAIN {minRetain}
        </span>
      </div>

      <div className="h-[6px] bg-bg-hover w-full relative">
        <div
          className={`h-full transition-all duration-500 ${isTriggered ? 'buffer-pulse' : ''}`}
          style={{
            width: `${pct}%`,
            background: isTriggered
              ? 'linear-gradient(90deg, #ff3b30, #ff6b5a)'
              : `linear-gradient(90deg, #ff3b30 0%, #ff6b5a ${pct}%)`,
          }}
        />
        {/* Tick marks */}
        {Array.from({ length: triggerAt }, (_, i) => (
          <div
            key={i}
            className="absolute top-0 h-full w-px bg-bg"
            style={{ left: `${((i + 1) / triggerAt) * 100}%` }}
          />
        ))}
      </div>
    </div>
  );
}
