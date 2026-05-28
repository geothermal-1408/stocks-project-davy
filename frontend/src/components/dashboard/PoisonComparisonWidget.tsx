import { useState, useEffect } from 'react';
import { fetchPredictionComparison } from '../../api/client';

export default function PoisonComparisonWidget() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const handler = () => setRefreshKey(k => k + 1);
    window.addEventListener("cycle_result", handler);
    window.addEventListener("prediction_updated", handler);
    return () => {
      window.removeEventListener("cycle_result", handler);
      window.removeEventListener("prediction_updated", handler);
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    fetchPredictionComparison('AAPL')
      .then((res) => {
        if (mounted) setData(res);
      })
      .catch(console.error)
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => { mounted = false; };
  }, [refreshKey]);

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

  if (!data || (!data.before_poison && !data.after_unlearn)) {
    return null;
  }

  const { before_poison, after_unlearn } = data;

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
        <div className="text-xs font-mono text-text-muted italic">No data</div>
      )}
    </div>
  );

  return (
    <div className="bg-bg-card border border-border p-4">
      <h3 className="font-barlow text-sm tracking-widest text-text-muted uppercase mb-3">
        Poison vs Unlearn Prediction Impact
      </h3>
      <div className="flex flex-col sm:flex-row gap-4">
        {renderPred('BEFORE POISON', before_poison, 'text-accent-danger')}
        {renderPred('AFTER UNLEARN', after_unlearn, 'text-accent-mint')}
      </div>
    </div>
  );
}
