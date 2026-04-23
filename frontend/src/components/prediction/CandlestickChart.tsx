import { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import type { OHLCV, PoisonAnnotation } from '../../types';
import { formatDate, formatVolume } from '../../hooks/useUtils';

interface Props {
  data: OHLCV[];
  poisonAnnotations: PoisonAnnotation[];
  predictionCandle?: {
    open: number;
    high: number;
    low: number;
    close: number;
    date: string;
  };
  confidenceBand?: {
    high: number;
    low: number;
  };
}

export default function CandlestickChart({ data, poisonAnnotations, predictionCandle, confidenceBand }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width,
          height: Math.max(entry.contentRect.height, 400),
        });
      }
    });
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const padding = { top: 20, right: 70, bottom: 80, left: 10 };
  const chartHeight = dimensions.height * 0.68;
  const volumeHeight = dimensions.height * 0.18;
  const volumeTop = chartHeight + 30;

  const allData = useMemo(() => {
    if (predictionCandle) {
      return [...data, { ...predictionCandle, vol: 0, isPrediction: true }];
    }
    return data.map(d => ({ ...d, isPrediction: false }));
  }, [data, predictionCandle]);

  const { minPrice, maxPrice, maxVol } = useMemo(() => {
    let min = Infinity, max = -Infinity, mVol = 0;
    for (const d of data) {
      if (d.low < min) min = d.low;
      if (d.high > max) max = d.high;
      if (d.vol > mVol) mVol = d.vol;
    }
    if (confidenceBand) {
      if (confidenceBand.low < min) min = confidenceBand.low;
      if (confidenceBand.high > max) max = confidenceBand.high;
    }
    if (predictionCandle) {
      if (predictionCandle.low < min) min = predictionCandle.low;
      if (predictionCandle.high > max) max = predictionCandle.high;
    }
    const range = max - min;
    return { minPrice: min - range * 0.05, maxPrice: max + range * 0.05, maxVol: mVol };
  }, [data, confidenceBand, predictionCandle]);

  const candleWidth = useMemo(() => {
    const available = dimensions.width - padding.left - padding.right;
    return Math.max(2, Math.min(12, available / allData.length - 2));
  }, [dimensions.width, allData.length]);

  const getX = useCallback((i: number) => {
    const available = dimensions.width - padding.left - padding.right;
    return padding.left + (i / (allData.length - 1)) * available;
  }, [dimensions.width, allData.length]);

  const getY = useCallback((price: number) => {
    const range = maxPrice - minPrice;
    return padding.top + (1 - (price - minPrice) / range) * chartHeight;
  }, [maxPrice, minPrice, chartHeight]);

  const getVolY = useCallback((vol: number) => {
    return volumeTop + volumeHeight - (vol / maxVol) * volumeHeight;
  }, [maxVol, volumeTop, volumeHeight]);

  const poisonIndices = useMemo(() => {
    const map = new Map<number, PoisonAnnotation>();
    poisonAnnotations.forEach(pa => {
      const idx = data.findIndex(d => d.date === pa.date);
      if (idx >= 0) map.set(idx, pa);
    });
    return map;
  }, [data, poisonAnnotations]);

  // Y-axis labels
  const yLabels = useMemo(() => {
    const count = 6;
    const labels = [];
    for (let i = 0; i <= count; i++) {
      const price = minPrice + (maxPrice - minPrice) * (i / count);
      labels.push({ price, y: getY(price) });
    }
    return labels;
  }, [minPrice, maxPrice, getY]);

  // X-axis labels
  const xLabels = useMemo(() => {
    const count = 8;
    const step = Math.floor(data.length / count);
    return Array.from({ length: count }, (_, i) => {
      const idx = i * step;
      return {
        date: data[idx]?.date || '',
        x: getX(idx),
      };
    });
  }, [data, getX]);

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const available = dimensions.width - padding.left - padding.right;
    const idx = Math.round(((x - padding.left) / available) * (allData.length - 1));
    if (idx >= 0 && idx < data.length) {
      setHoverIndex(idx);
      setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    } else {
      setHoverIndex(null);
    }
  }, [dimensions.width, allData.length, data.length]);

  return (
    <div ref={containerRef} className="w-full h-full relative" style={{ minHeight: 400 }}>
      <svg
        width={dimensions.width}
        height={dimensions.height}
        className="select-none"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        {/* Horizontal guide lines */}
        {yLabels.map((l, i) => (
          <line
            key={i}
            x1={padding.left}
            y1={l.y}
            x2={dimensions.width - padding.right}
            y2={l.y}
            stroke="#1c2128"
            strokeWidth={1}
          />
        ))}

        {/* Y-axis labels */}
        {yLabels.map((l, i) => (
          <text
            key={`y-${i}`}
            x={dimensions.width - padding.right + 8}
            y={l.y + 4}
            fill="#8b949e"
            fontSize={10}
            fontFamily="JetBrains Mono"
          >
            {l.price.toFixed(2)}
          </text>
        ))}

        {/* X-axis labels */}
        {xLabels.map((l, i) => (
          <text
            key={`x-${i}`}
            x={l.x}
            y={dimensions.height - 8}
            fill="#8b949e"
            fontSize={9}
            fontFamily="JetBrains Mono"
            textAnchor="middle"
          >
            {formatDate(l.date)}
          </text>
        ))}

        {/* Confidence band */}
        {confidenceBand && predictionCandle && (
          <rect
            x={getX(data.length) - candleWidth * 2}
            y={getY(confidenceBand.high)}
            width={candleWidth * 4}
            height={getY(confidenceBand.low) - getY(confidenceBand.high)}
            fill="rgba(245, 166, 35, 0.08)"
            stroke="rgba(245, 166, 35, 0.3)"
            strokeWidth={1}
            strokeDasharray="4,2"
          />
        )}

        {/* Volume bars */}
        {data.map((d, i) => {
          const isGreen = d.close >= d.open;
          return (
            <rect
              key={`vol-${i}`}
              x={getX(i) - candleWidth / 2}
              y={getVolY(d.vol)}
              width={candleWidth}
              height={volumeTop + volumeHeight - getVolY(d.vol)}
              fill={isGreen ? 'rgba(0, 229, 160, 0.12)' : 'rgba(255, 59, 48, 0.12)'}
            />
          );
        })}

        {/* Candlesticks */}
        {data.map((d, i) => {
          const isGreen = d.close >= d.open;
          const color = isGreen ? '#00e5a0' : '#ff3b30';
          const bodyTop = getY(Math.max(d.open, d.close));
          const bodyBottom = getY(Math.min(d.open, d.close));
          const bodyHeight = Math.max(1, bodyBottom - bodyTop);

          return (
            <g key={`candle-${i}`}>
              {/* Wick */}
              <line
                x1={getX(i)}
                y1={getY(d.high)}
                x2={getX(i)}
                y2={getY(d.low)}
                stroke={color}
                strokeWidth={1}
              />
              {/* Body */}
              <rect
                x={getX(i) - candleWidth / 2}
                y={bodyTop}
                width={candleWidth}
                height={bodyHeight}
                fill={isGreen ? color : color}
                fillOpacity={isGreen ? 0.9 : 0.9}
                stroke={color}
                strokeWidth={0.5}
              />
            </g>
          );
        })}

        {/* Prediction candle (dashed amber outline) */}
        {predictionCandle && (
          <g>
            <line
              x1={getX(data.length)}
              y1={getY(predictionCandle.high)}
              x2={getX(data.length)}
              y2={getY(predictionCandle.low)}
              stroke="#f5a623"
              strokeWidth={1}
              strokeDasharray="3,2"
            />
            <rect
              x={getX(data.length) - candleWidth / 2}
              y={getY(Math.max(predictionCandle.open, predictionCandle.close))}
              width={candleWidth}
              height={Math.max(1, getY(Math.min(predictionCandle.open, predictionCandle.close)) - getY(Math.max(predictionCandle.open, predictionCandle.close)))}
              fill="transparent"
              stroke="#f5a623"
              strokeWidth={1.5}
              strokeDasharray="4,2"
            />
          </g>
        )}

        {/* Poison markers */}
        {Array.from(poisonIndices.entries()).map(([idx, pa]) => {
          const x = getX(idx);
          const y = getY(data[idx].high) - 14;
          return (
            <g key={`poison-${idx}`} className="cursor-pointer">
              {/* Diamond marker */}
              <polygon
                points={`${x},${y - 6} ${x + 5},${y} ${x},${y + 6} ${x - 5},${y}`}
                fill="#ff3b30"
                stroke="#ff3b30"
                strokeWidth={1}
              />
              {/* Tooltip on hover */}
              <title>{`${pa.type}${pa.sigma ? ` | σ=${pa.sigma}` : ''}${pa.swing_ratio ? ` | swing=${pa.swing_ratio}` : ''}${pa.vol_ratio ? ` | vol=${pa.vol_ratio}x` : ''}`}</title>
            </g>
          );
        })}

        {/* Crosshair */}
        {hoverIndex !== null && hoverIndex < data.length && (
          <g>
            <line
              x1={getX(hoverIndex)}
              y1={padding.top}
              x2={getX(hoverIndex)}
              y2={volumeTop + volumeHeight}
              stroke="rgba(230, 237, 243, 0.15)"
              strokeWidth={1}
              strokeDasharray="2,2"
            />
            <line
              x1={padding.left}
              y1={getY(data[hoverIndex].close)}
              x2={dimensions.width - padding.right}
              y2={getY(data[hoverIndex].close)}
              stroke="rgba(230, 237, 243, 0.15)"
              strokeWidth={1}
              strokeDasharray="2,2"
            />
          </g>
        )}
      </svg>

      {/* Hover tooltip */}
      {hoverIndex !== null && hoverIndex < data.length && (
        <div
          className="absolute pointer-events-none z-40 bg-bg-panel border border-border p-2 shadow-lg"
          style={{
            left: tooltipPos.x > dimensions.width / 2 ? tooltipPos.x - 180 : tooltipPos.x + 16,
            top: Math.min(tooltipPos.y, dimensions.height - 120),
          }}
        >
          <div className="font-mono text-[10px] text-text-muted mb-1">{data[hoverIndex].date}</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-[11px]">
            <span className="text-text-muted">O</span>
            <span className="text-text-primary">{data[hoverIndex].open.toFixed(2)}</span>
            <span className="text-text-muted">H</span>
            <span className="text-text-primary">{data[hoverIndex].high.toFixed(2)}</span>
            <span className="text-text-muted">L</span>
            <span className="text-text-primary">{data[hoverIndex].low.toFixed(2)}</span>
            <span className="text-text-muted">C</span>
            <span className={data[hoverIndex].close >= data[hoverIndex].open ? 'text-accent-mint' : 'text-accent-danger'}>
              {data[hoverIndex].close.toFixed(2)}
            </span>
            <span className="text-text-muted">V</span>
            <span className="text-text-primary">{formatVolume(data[hoverIndex].vol)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
