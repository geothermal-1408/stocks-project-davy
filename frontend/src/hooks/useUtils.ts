import { useState, useEffect, useRef } from 'react';

/**
 * Animates a number from 0 to target value over duration ms.
 */
export function useCountUp(target: number, duration: number = 600, decimals: number = 2): string {
  const [value, setValue] = useState(0);
  const startTime = useRef<number | null>(null);
  const rafId = useRef<number>(0);

  useEffect(() => {
    startTime.current = null;

    const animate = (timestamp: number) => {
      if (!startTime.current) startTime.current = timestamp;
      const progress = Math.min((timestamp - startTime.current) / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(target * eased);

      if (progress < 1) {
        rafId.current = requestAnimationFrame(animate);
      }
    };

    rafId.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafId.current);
  }, [target, duration]);

  return value.toFixed(decimals);
}

/**
 * Format a number with commas.
 */
export function formatNumber(n: number): string {
  return n.toLocaleString('en-US');
}

/**
 * Format volume (e.g. 42000000 → "42.0M")
 */
export function formatVolume(vol: number): string {
  if (vol >= 1_000_000_000) return (vol / 1_000_000_000).toFixed(1) + 'B';
  if (vol >= 1_000_000) return (vol / 1_000_000).toFixed(1) + 'M';
  if (vol >= 1_000) return (vol / 1_000).toFixed(1) + 'K';
  return vol.toString();
}

/**
 * Format a date string to short format.
 */
export function formatDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Format datetime string.
 */
export function formatDateTime(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  });
}

/**
 * Get color class for poison type.
 */
export function getPoisonColor(type: string): string {
  switch (type) {
    case 'flash_crash': return '#ff3b30';
    case 'volume_spike': return '#f5a623';
    case 'price_outlier': return '#ff8c00';
    case 'ohlc_violation': return '#a855f7';
    case 'stale_data': return '#8b949e';
    case 'negative_price': return '#ff3b30';
    case 'regime_change': return '#06b6d4';
    default: return '#8b949e';
  }
}

/**
 * Get cycle status info.
 */
export function getCycleStatus(deployed: boolean, gateFailure: string | null): {
  label: string;
  color: string;
  symbol: string;
} {
  if (deployed) return { label: 'PASS', color: '#00e5a0', symbol: '✓' };
  if (gateFailure?.includes('rollback')) return { label: 'ROLLBACK', color: '#f5a623', symbol: '↩' };
  return { label: 'FAIL', color: '#ff3b30', symbol: '✗' };
}

/**
 * Get method color.
 */
export function getMethodColor(method: string): string {
  switch (method.toUpperCase()) {
    case 'AD': return '#00e5a0';
    case 'AKL': return '#06b6d4';
    case 'GA': return '#f5a623';
    case 'RANDOM_LABEL': return '#a855f7';
    default: return '#8b949e';
  }
}
