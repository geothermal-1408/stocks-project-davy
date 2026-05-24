import { useAppStore } from '../store/appStore';
import { useOHLCV } from '../hooks/useOHLCV';
import { usePrediction } from '../hooks/usePrediction';
import { getNextBusinessDay } from '../utils/dateUtils';
import CandlestickChart from '../components/prediction/CandlestickChart';
import PredictionPanel from '../components/prediction/PredictionPanel';
import TickerSelector from '../components/prediction/TickerSelector';

export default function PredictionPage() {
  const { selectedTicker } = useAppStore();
  const { data, poisonAnnotations, loading: dataLoading, isLive: isDataLive } = useOHLCV(selectedTicker);
  const { prediction, loading: predLoading, isLive: isPredLive } = usePrediction(selectedTicker);
  const lastCandle = data.length > 0 ? data[data.length - 1] : null;

  // Build prediction candle only when we have both prediction and lastCandle
  const predictionCandle = prediction && lastCandle ? {
    open: prediction.prediction.open,
    high: prediction.prediction.high,
    low: prediction.prediction.low,
    close: prediction.prediction.close,
    date: getNextBusinessDay(lastCandle.date),
  } : undefined;

  const confidenceBand = prediction ? {
    high: prediction.confidence.close_high,
    low: prediction.confidence.close_low,
  } : undefined;

  return (
    <div className="h-full flex flex-col">
      {/* Top bar */}
      <div className="h-12 flex items-center justify-between px-4 border-b border-border shrink-0">
        <TickerSelector />
        <div className="flex items-center gap-3">
          <h1 className="font-display font-bold text-base text-text-primary tracking-[0.3em]">
            STOCKSENSE
          </h1>
          {/* Data source status indicators */}
          <div className="flex items-center gap-1.5">
            <span className={`flex items-center gap-1 px-1.5 py-0.5 border font-mono text-[9px] ${
              isDataLive
                ? 'border-accent-mint/30 text-accent-mint bg-accent-mint/5'
                : dataLoading
                  ? 'border-accent-warning/30 text-accent-warning bg-accent-warning/5'
                  : 'border-border text-text-muted'
            }`}>
              <span className={`w-1 h-1 ${isDataLive ? 'bg-accent-mint animate-pulse' : dataLoading ? 'bg-accent-warning animate-pulse' : 'bg-text-muted/30'}`} />
              OHLCV
            </span>
            <span className={`flex items-center gap-1 px-1.5 py-0.5 border font-mono text-[9px] ${
              isPredLive
                ? 'border-accent-mint/30 text-accent-mint bg-accent-mint/5'
                : predLoading
                  ? 'border-accent-warning/30 text-accent-warning bg-accent-warning/5'
                  : 'border-border text-text-muted'
            }`}>
              <span className={`w-1 h-1 ${isPredLive ? 'bg-accent-mint animate-pulse' : predLoading ? 'bg-accent-warning animate-pulse' : 'bg-text-muted/30'}`} />
              MODEL
            </span>
          </div>
        </div>
        {prediction ? (
          <div className={`flex items-center gap-2 px-3 py-1 border font-mono text-sm ${prediction.directional === 'up'
              ? 'border-accent-mint text-accent-mint'
              : 'border-accent-danger text-accent-danger'
            }`}>
            <span>{prediction.directional === 'up' ? '↑' : '↓'}</span>
            <span className="font-bold">{prediction.directional === 'up' ? 'BULL' : 'BEAR'}</span>
            <span>{prediction.directional_pct}%</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 px-3 py-1 border border-border font-mono text-sm text-text-muted">
            <span>—</span>
            <span>{predLoading ? 'LOADING...' : 'AWAITING PREDICTION'}</span>
          </div>
        )}
      </div>

      {/* Main content */}
      <div className="flex-1 flex min-h-0">
        {/* Chart area (65%) */}
        <div className="w-[65%] border-r border-border p-3 flex flex-col">
          <div className="flex-1 min-h-0">
            {data.length === 0 && !dataLoading ? (
              /* Empty state when no data */
              <div className="h-full flex flex-col items-center justify-center text-center">
                <div className="w-12 h-12 mb-4 border-2 border-text-muted/20 flex items-center justify-center">
                  <span className="text-text-muted/40 text-2xl">⊘</span>
                </div>
                <p className="font-display text-sm text-text-muted tracking-wider uppercase mb-2">
                  NO MARKET DATA
                </p>
                <p className="font-mono text-[10px] text-text-muted/60 max-w-xs">
                  Trigger an ingest from the Admin → Control Plane to fetch OHLCV data from yfinance.
                </p>
              </div>
            ) : (
              <CandlestickChart
                data={data}
                poisonAnnotations={poisonAnnotations}
                predictionCandle={predictionCandle}
                confidenceBand={confidenceBand}
              />
            )}
          </div>
        </div>

        {/* Prediction panel (35%) */}
        <div className="w-[35%] p-4">
          {prediction && lastCandle ? (
            <PredictionPanel prediction={prediction} lastCandle={lastCandle} />
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center">
              <div className="w-10 h-10 mb-3 border border-text-muted/20 flex items-center justify-center">
                <span className="text-text-muted/30 text-lg">◇</span>
              </div>
              <p className="font-display text-xs text-text-muted tracking-wider uppercase mb-1">
                {predLoading ? 'LOADING PREDICTION...' : 'AWAITING FORECAST'}
              </p>
              <p className="font-mono text-[9px] text-text-muted/50 max-w-[200px]">
                {!lastCandle
                  ? 'No OHLCV data available. Run ingest first.'
                  : 'Model not loaded or prediction unavailable.'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
