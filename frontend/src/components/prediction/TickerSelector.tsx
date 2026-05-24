import { useAppStore } from '../../store/appStore';

/**
 * TickerSelector — Only AAPL is supported.
 * Displays the fixed ticker; no dropdown needed for single ticker.
 */
export default function TickerSelector() {
  const { selectedTicker } = useAppStore();

  return (
    <div className="relative">
      <div className="flex items-center gap-2 px-3 py-1.5 border border-accent-mint/50 text-accent-mint font-mono text-sm">
        {selectedTicker}
      </div>
    </div>
  );
}
