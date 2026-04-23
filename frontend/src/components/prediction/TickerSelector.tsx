import { useState, useRef, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';
import { useAppStore } from '../../store/appStore';
import { TICKERS } from '../../data/mockData';

export default function TickerSelector() {
  const { selectedTicker, setSelectedTicker } = useAppStore();
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 border border-accent-mint/50 text-accent-mint font-mono text-sm hover:bg-accent-mint/5 transition-colors"
      >
        {selectedTicker}
        <ChevronDown size={14} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-1 bg-bg-panel border border-border z-50 min-w-[100px]">
          {TICKERS.map(ticker => (
            <button
              key={ticker}
              onClick={() => {
                setSelectedTicker(ticker);
                setIsOpen(false);
              }}
              className={`w-full text-left px-3 py-1.5 font-mono text-sm transition-colors
                ${ticker === selectedTicker
                  ? 'text-accent-mint bg-accent-mint/10'
                  : 'text-text-primary hover:bg-bg-hover'
                }`}
            >
              {ticker}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
