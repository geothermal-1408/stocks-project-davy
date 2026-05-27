import { useState, useEffect } from 'react';
import { fetchPredictionComparison } from '../../api/client';
import { useAppStore } from '../../store/appStore';

export default function PoisonComparisonWidget() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const { pipelineState } = useAppStore();

  const loadData = () => {
    setLoading(true);
    fetchPredictionComparison('AAPL')
      .then((res) => setData(res))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  // Initial load
  useEffect(() => {
    loadData();
  }, []);

  // Auto-refresh when pipeline goes idle (after unlearn cycle completes)
  useEffect(() => {
    if (pipelineState.status === 'idle') {
      const timer = setTimeout(loadData, 2000);
      return () => clearTimeout(timer);
    }
  }, [pipelineState.status]);

  if (loading) {
    return (
      <div className="bg-bg-card border border-border p-4 animate-pulse">
        <h3 className="font-barlow text-sm tracking-widest text-text-muted uppercase mb-3">
          Poison / Unlearn Impact
        </h3>
        <div className="h-16 flex items-center justify-center text-xs font-mono text-text-muted">
          Loading comparison...
        </div>
      </div>
    );
  }

  const hasBefore = data?.before_poison;
  const hasAfter = data?.after_unlearn;

  const renderPred = (title: string, pred: any, colorClass: string) => (
    <div className="flex-1 p-3 border border-border/50 bg-bg-main/50 rounded-sm">
      <div className={`font-mono text-[10px] tracking-wider mb-2 ${colorClass}`}>
        {title} {pred ? `(Cycle ${pred.model_cycle})` : ''}
      </div>
      {pred ? (
        <div className="space-y-1 font-mono text-xs text-text-primary">
          <div className="flex justify-between">
            <span className="text-text-muted">Close:</span>
            <span>₹{pred.prediction.close.toFixed(2)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-muted">High:</span>
            <span>₹{pred.prediction.high.toFixed(2)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-muted">Low:</span>
            <span>₹{pred.prediction.low.toFixed(2)}</span>
          </div>
        </div>
      ) : (
        <div className="text-xs font-mono text-text-muted italic">No data yet</div>
      )}
    </div>
  );

  return (
    <div className="bg-bg-card border border-border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-barlow text-sm tracking-widest text-text-muted uppercase">
          Poison vs Unlearn Prediction Impact
        </h3>
        <button
          onClick={loadData}
          className="px-2 py-0.5 border border-border text-text-muted font-mono text-[10px] hover:text-text-primary hover:border-accent-mint transition-colors"
        >
          REFRESH
        </button>
      </div>
      {!hasBefore && !hasAfter ? (
        <div className="py-4 text-center font-mono text-xs text-text-muted">
          <div className="mb-1">No comparison data yet</div>
          <div className="text-[10px]">Inject poison → trigger unlearn cycle → predictions will appear here</div>
        </div>
      ) : (
        <div className="flex flex-col sm:flex-row gap-4">
          {renderPred('BEFORE POISON', hasBefore, 'text-accent-danger')}
          {renderPred('AFTER UNLEARN', hasAfter, 'text-accent-mint')}
        </div>
      )}
    </div>
  );
}
