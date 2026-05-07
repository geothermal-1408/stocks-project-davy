import { create } from 'zustand';
import type { PipelineState, AppConfig } from '../types';

// Tickers supported by the system (only AAPL has real data)
export const TICKERS = ['AAPL'] as const;
export type Ticker = (typeof TICKERS)[number];

const DEFAULT_CONFIG: AppConfig = {
  sigma_thresh: 3.0,
  swing_thresh: 0.10,
  vol_multiplier: 5,
  forget_trigger: 5,
  min_retain: 20,
  learning_rate: '5e-6',
};

interface AppStore {
  // Ticker selection
  selectedTicker: Ticker;
  setSelectedTicker: (ticker: Ticker) => void;

  // Pipeline status
  pipelineState: PipelineState;
  setPipelineState: (state: PipelineState) => void;

  // Poison flash
  poisonFlashActive: boolean;
  triggerPoisonFlash: () => void;

  // Config
  config: AppConfig;
  setConfig: (config: Partial<AppConfig>) => void;

  // Expanded rows
  expandedCycleRows: Set<number>;
  toggleCycleRow: (cycle: number) => void;

  expandedPoisonRows: Set<string>;
  togglePoisonRow: (id: string) => void;
}

export const useAppStore = create<AppStore>((set, get) => ({
  // Ticker
  selectedTicker: 'AAPL',
  setSelectedTicker: (ticker) => set({ selectedTicker: ticker }),

  // Pipeline
  pipelineState: { status: 'idle' },
  setPipelineState: (state) => set({ pipelineState: state }),

  // Poison flash
  poisonFlashActive: false,
  triggerPoisonFlash: () => {
    set({ poisonFlashActive: true });
    setTimeout(() => set({ poisonFlashActive: false }), 800);
  },

  // Config
  config: { ...DEFAULT_CONFIG },
  setConfig: (partial) => set({ config: { ...get().config, ...partial } }),

  // Expanded rows
  expandedCycleRows: new Set(),
  toggleCycleRow: (cycle) => {
    const current = new Set(get().expandedCycleRows);
    if (current.has(cycle)) current.delete(cycle);
    else current.add(cycle);
    set({ expandedCycleRows: current });
  },

  expandedPoisonRows: new Set(),
  togglePoisonRow: (id) => {
    const current = new Set(get().expandedPoisonRows);
    if (current.has(id)) current.delete(id);
    else current.add(id);
    set({ expandedPoisonRows: current });
  },
}));
