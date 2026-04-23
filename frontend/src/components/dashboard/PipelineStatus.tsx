import type { PipelineState } from '../../types';

interface Props {
  state: PipelineState;
}

export default function PipelineStatus({ state }: Props) {
  if (state.status === 'idle') return null;

  const isIngesting = state.status === 'ingesting';

  return (
    <div className={`w-full px-4 py-2 flex items-center gap-3 font-mono text-sm ${
      isIngesting ? 'bg-accent-warning/10 border border-accent-warning/30' : 'bg-accent-danger/10 border border-accent-danger/30'
    }`}>
      <span className={isIngesting ? 'text-accent-warning' : 'text-accent-danger'}>
        {isIngesting ? '⟳' : '⚡'}
      </span>
      <span className={`font-bold ${isIngesting ? 'text-accent-warning' : 'text-accent-danger'}`}>
        {isIngesting ? 'INGESTING' : 'UNLEARNING'}
      </span>
      {state.ticker && (
        <span className="text-text-primary">{state.ticker}</span>
      )}
      {state.progress !== undefined && state.total !== undefined && (
        <span className="text-text-muted">· {state.progress}/{state.total} windows</span>
      )}
      {state.method && (
        <span className="text-text-muted">· {state.method}</span>
      )}
      {state.epoch && (
        <span className="text-text-muted">· epoch {state.epoch}</span>
      )}
      {state.cycle && (
        <span className="text-text-muted">· CYCLE {state.cycle}</span>
      )}
    </div>
  );
}
