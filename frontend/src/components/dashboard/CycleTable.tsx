import { ChevronDown, ChevronRight } from 'lucide-react';
import { useAppStore } from '../../store/appStore';
import { getCycleStatus, getMethodColor } from '../../hooks/useUtils';
import type { CycleRecord } from '../../types';

interface Props {
  cycles: CycleRecord[];
}

export default function CycleTable({ cycles }: Props) {
  const { expandedCycleRows, toggleCycleRow } = useAppStore();

  return (
    <div className="bg-bg-card border border-border">
      <div className="px-4 py-3 border-b border-border">
        <h3 className="font-display text-sm text-text-muted tracking-wider uppercase">CYCLE HISTORY</h3>
      </div>

      {/* Table header */}
      <div className="grid grid-cols-[40px_60px_100px_80px_100px_90px_70px_80px_90px] gap-0 px-2 py-2 border-b border-border text-[10px] font-mono text-text-muted uppercase tracking-wider">
        <span></span>
        <span>CYCLE</span>
        <span>DATE</span>
        <span>METHOD</span>
        <span>FORGET PPL</span>
        <span>RETAIN PPL</span>
        <span>MAE</span>
        <span>DIR ACC</span>
        <span>STATUS</span>
      </div>

      {/* Rows */}
      {[...cycles].reverse().map((cycle, idx) => {
        const isExpanded = expandedCycleRows.has(cycle.cycle_num);
        const status = getCycleStatus(cycle.deployed, cycle.gate_failure);
        const methodColor = getMethodColor(cycle.method);

        return (
          <div key={cycle.cycle_num}>
            <div
              onClick={() => toggleCycleRow(cycle.cycle_num)}
              className={`grid grid-cols-[40px_60px_100px_80px_100px_90px_70px_80px_90px] gap-0 px-2 py-2 cursor-pointer transition-colors font-mono text-xs ${
                idx % 2 === 0 ? 'bg-bg-card' : 'bg-bg/50'
              } hover:bg-bg-hover`}
            >
              <span className="flex items-center text-text-muted">
                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </span>
              <span className="text-text-primary">{cycle.cycle_num}</span>
              <span className="text-text-muted">{cycle.date}</span>
              <span>
                <span
                  className="px-1.5 py-0.5 border text-[10px]"
                  style={{ borderColor: methodColor, color: methodColor }}
                >
                  {cycle.method.toUpperCase()}
                </span>
              </span>
              <span className="text-text-primary">{cycle.forget_ppl?.toFixed(1) ?? '—'}</span>
              <span className="text-text-primary">{cycle.retain_ppl?.toFixed(1) ?? '—'}</span>
              <span className="text-text-primary">{cycle.mae_validation?.toFixed(2) ?? '—'}</span>
              <span className={cycle.directional_acc && cycle.directional_acc >= 0.52 ? 'text-accent-mint' : cycle.directional_acc ? 'text-accent-danger' : 'text-text-muted'}>
                {cycle.directional_acc ? `${(cycle.directional_acc * 100).toFixed(1)}%` : '—'}
              </span>
              <span>
                <span
                  className="px-1.5 py-0.5 text-[10px] border"
                  style={{ borderColor: status.color, color: status.color }}
                >
                  {status.symbol} {status.label}
                </span>
              </span>
            </div>

            {/* Expanded gate details */}
            {isExpanded && (
              <div className="px-10 py-3 bg-bg-panel border-t border-b border-border">
                <div className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">
                  GATE CHECKS
                </div>
                <div className="space-y-1">
                  {cycle.gates.map((gate, gi) => (
                    <div key={gi} className="flex items-center gap-3 font-mono text-xs">
                      <span className={gate.passed ? 'text-accent-mint' : 'text-accent-danger'}>
                        {gate.passed ? '✓' : '✗'}
                      </span>
                      <span className="text-text-muted w-[160px]">{gate.name}</span>
                      <span className="text-text-primary">{typeof gate.value === 'number' ? gate.value.toFixed(3) : gate.value}</span>
                      <span className="text-text-muted text-[10px]">{gate.threshold}</span>
                    </div>
                  ))}
                </div>
                {cycle.gate_failure && (
                  <div className="mt-2 text-xs font-mono text-accent-danger">
                    ✗ {cycle.gate_failure}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
