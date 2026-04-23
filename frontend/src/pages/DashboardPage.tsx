import { METRICS, CYCLE_HISTORY } from '../data/mockData';
import { useAppStore } from '../store/appStore';
import MetricCard from '../components/dashboard/MetricCard';
import BufferGauge from '../components/dashboard/BufferGauge';
import PipelineStatus from '../components/dashboard/PipelineStatus';
import { PPLChart, MAEChart } from '../components/dashboard/Charts';
import CycleTable from '../components/dashboard/CycleTable';

export default function DashboardPage() {
  const { pipelineState } = useAppStore();
  const { latest, history, buffer_status } = METRICS;

  // Build sparkline data from history
  const forgetPplSpark = history.map(h => h.forget_ppl);
  const retainPplSpark = history.map(h => h.retain_ppl);
  const maeSpark = history.map(h => h.mae_validation);
  const dirAccSpark = history.map(h => h.directional_acc * 100);
  const miaSpark = history.map(h => h.mia_auc);

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      {/* Pipeline status banner */}
      <PipelineStatus state={pipelineState} />

      {/* Top metrics strip */}
      <div className="grid grid-cols-5 gap-3">
        <MetricCard
          label="FORGET PPL"
          value={latest.forget_ppl}
          sparklineData={forgetPplSpark}
          trendDirection="up"
          status="healthy"
        />
        <MetricCard
          label="RETAIN PPL"
          value={latest.retain_ppl}
          sparklineData={retainPplSpark}
          trendDirection="down"
          status="healthy"
        />
        <MetricCard
          label="PRED MAE"
          value={latest.mae_validation}
          sparklineData={maeSpark}
          trendDirection="down"
          status={latest.mae_validation > 2.0 ? 'warning' : 'healthy'}
        />
        <MetricCard
          label="DIR ACC"
          value={latest.directional_acc * 100}
          unit="%"
          sparklineData={dirAccSpark}
          trendDirection="up"
          status={latest.directional_acc >= 0.52 ? 'healthy' : 'danger'}
        />
        <MetricCard
          label="MIA AUC"
          value={latest.mia_auc}
          suffix="→ 0.5 target"
          sparklineData={miaSpark}
          trendDirection="down"
        />
      </div>

      {/* Buffer gauge */}
      <BufferGauge
        forgetCount={buffer_status.forget_count}
        triggerAt={buffer_status.trigger_at}
        minRetain={buffer_status.min_retain}
      />

      {/* Charts row */}
      <div className="grid grid-cols-2 gap-3">
        <PPLChart history={history} />
        <MAEChart history={history} />
      </div>

      {/* Cycle table */}
      <CycleTable cycles={CYCLE_HISTORY} />
    </div>
  );
}
