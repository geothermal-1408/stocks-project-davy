# StockSense — Frontend

> Bloomberg Terminal meets underground quant lab. A real-time AI trading dashboard for live stock pattern learning with poison detection and continuous unlearning.

![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript)
![Tailwind](https://img.shields.io/badge/Tailwind_CSS-3-06B6D4?style=flat-square&logo=tailwindcss)
![Vite](https://img.shields.io/badge/Vite-8-646CFF?style=flat-square&logo=vite)

---

## Overview

StockSense is a multi-page trading dashboard that visualizes AI-driven stock predictions, model health metrics, poison/anomaly detection events, and pipeline control — all through a dark, terminal-inspired interface designed for quantitative analysis.

The frontend is designed to integrate with a **FastAPI backend** and **ML pipeline** (Qwen1.5-0.5B + llm_unlearn). Currently runs on realistic mock data; backend integration points are clearly typed and ready to connect.

---

## Tech Stack

| Layer | Choice | Purpose |
|---|---|---|
| Framework | **React 18 + Vite** | Fast HMR, SPA ideal for dashboards |
| Language | **TypeScript** | Type-safe financial data handling |
| Styling | **Tailwind CSS v3** | Utility-first dark terminal theme |
| Charts | **Recharts** | PPL / MAE trend line charts |
| Candlestick | **Custom SVG** | Hand-built OHLCV candlestick chart |
| State | **Zustand** | Global store for ticker, pipeline, config |
| Routing | **React Router v6** | 4-page SPA navigation |
| Icons | **Lucide React** | Consistent icon set |

---

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev
# → http://localhost:5173

# Type check
npx tsc --noEmit

# Production build
npm run build
```

---

## Pages

### `/` — Prediction

The primary view. Custom SVG candlestick chart showing 90 days of OHLCV data with:

- **Green/red candles** with wicks and volume bars
- **Red diamond markers** at poisoned window dates (hover for details)
- **Amber dashed candle** for next-day prediction
- **Confidence band** (shaded amber region) spanning predicted high–low
- **Crosshair** with OHLCV tooltip on hover
- **Prediction panel** (right 35%): forecasted OPEN/HIGH/LOW/CLOSE with deltas, confidence band, model info chips, directional badge

### `/dashboard` — Metrics Dashboard

Model health monitoring with:

- **5 metric cards**: Forget PPL, Retain PPL, Pred MAE, Dir Acc, MIA AUC — each with sparkline and health indicator
- **Buffer gauge**: Forget window count progress toward unlearn trigger
- **PPL History chart**: Dual-line Recharts (forget green, retain red) per cycle
- **MAE chart**: Single amber line with dashed 2.0 target threshold
- **Cycle history table**: Expandable rows with 5 gate check results per cycle
- **Pipeline status banner**: SSE-driven (idle/ingesting/unlearning)

### `/poison` — Poison Log

Full anomaly audit trail:

- **Filter bar**: Ticker chips + type chips (7 poison types) + inject button
- **Sortable table**: Date, ticker, type badge (color-coded), σ/swing/vol values, window range, status, reason
- **Expandable rows**: Raw detector values + full window text (monospace code block)
- **Inject modal**: Type selector + severity slider (subtle → nuclear)

### `/admin` — Control Plane

Pipeline administration in a 2×2 grid + rollback panel:

| Panel | Controls |
|---|---|
| **Ingestion** | Ticker input + FETCH button, last/next ingest timestamps |
| **Unlearn Control** | Method selector (AD/AKL/GA/RANDOM_LABEL), TRIGGER CYCLE with progress, EMERGENCY UNLEARN |
| **Poison Injector** | Type dropdown + ticker + severity slider |
| **Config Editor** | Sliders for σ threshold, swing %, vol mult, forget trigger, min retain; read-only learning rate |
| **Rollback** | Last 5 cycles with RESTORE buttons, active cycle highlighted |

---

## Project Structure

```
src/
├── App.tsx                                  # Router + layout shell + poison flash
├── main.tsx                                 # Entry point
├── index.css                                # Tailwind + scanline + animations
│
├── types/
│   └── index.ts                             # All TypeScript interfaces
│
├── data/
│   └── mockData.ts                          # 90d OHLCV, 14 poison events, 7 cycles
│
├── store/
│   └── appStore.ts                          # Zustand: ticker, pipeline, config, UI
│
├── hooks/
│   └── useUtils.ts                          # Count-up animation, formatters, colors
│
├── pages/
│   ├── PredictionPage.tsx                   # Candlestick + forecast panel
│   ├── DashboardPage.tsx                    # Metrics + charts + cycle table
│   ├── PoisonLogPage.tsx                    # Filterable poison event table
│   └── AdminPage.tsx                        # Control plane panels
│
└── components/
    ├── shared/
    │   └── Sidebar.tsx                      # 60px icon-only nav sidebar
    ├── prediction/
    │   ├── CandlestickChart.tsx             # Custom SVG candlestick + volume
    │   ├── PredictionPanel.tsx              # Forecast values + confidence
    │   └── TickerSelector.tsx               # AAPL/MSFT/GOOG/NVDA dropdown
    └── dashboard/
        ├── MetricCard.tsx                   # Value + sparkline + health dot
        ├── BufferGauge.tsx                  # Forget buffer progress bar
        ├── PipelineStatus.tsx               # SSE status banner
        ├── Charts.tsx                       # Recharts PPL + MAE line charts
        └── CycleTable.tsx                   # Expandable cycle history table
```

---

## Design System

### Colors

| Token | Hex | Usage |
|---|---|---|
| `bg` | `#080b0f` | App background (cold blue-black) |
| `bg-card` | `#0d1117` | Card surfaces |
| `bg-panel` | `#161b22` | Panel surfaces, expanded sections |
| `bg-hover` | `#1c2128` | Hover states, guides |
| `accent-mint` | `#00e5a0` | Clean / healthy states |
| `accent-danger` | `#ff3b30` | Poison / gate fail states |
| `accent-warning` | `#f5a623` | Warnings, thresholds, predictions |
| `accent-purple` | `#a855f7` | OHLC violation type |
| `accent-cyan` | `#06b6d4` | Regime change type, AKL method |
| `text-primary` | `#e6edf3` | Primary text |
| `text-muted` | `#8b949e` | Secondary text, labels |

### Typography

| Font | Usage |
|---|---|
| **JetBrains Mono** | All numbers, tickers, metric values, code, table data |
| **Barlow Condensed** (500/700) | Headers, labels, section titles |

Both loaded from Google Fonts via CSS `@import`.

### Design Rules

- **No rounded corners** on metric cards, tables, or status badges — sharp 1px borders only
- Borders colored by state: green = clean, red = poison, amber = warning
- **Scanline overlay**: Fixed `::after` pseudo-element with repeating gradient (mint tint)
- **Count-up animation**: All numeric values animate from 0 → final on mount (600ms ease-out)
- **Loading shimmer**: `#161b22 → #1c2128` gradient animation
- **Poison flash**: Red border inset flashes on viewport edge (800ms) — triggered via bottom-right button

---

## Backend Integration

All TypeScript types in `src/types/index.ts` match the FastAPI API contracts. When the backend is ready, replace mock data with API calls:

| Endpoint | Frontend Consumer | Data Type |
|---|---|---|
| `GET /predict?ticker=AAPL` | `PredictionPage` | `Prediction` |
| `GET /data/ohlcv?ticker=AAPL&days=90` | `CandlestickChart` | `OHLCV[]` + `PoisonAnnotation[]` |
| `GET /metrics` | `DashboardPage` | `Metrics` |
| `GET /poison/log` | `PoisonLogPage` | `PoisonEvent[]` |
| `GET /stream/events` (SSE) | `PipelineStatus` | `PipelineState` |
| `POST /ingest/trigger` | `AdminPage` (Fetch) | — |
| `POST /admin/unlearn` | `AdminPage` (Trigger) | — |
| `POST /admin/inject-poison` | `AdminPage` (Inject) | — |

### Recommended integration approach

1. Create `src/api/client.ts` with base URL config
2. Add **TanStack Query v5** (`npm install @tanstack/react-query`)
3. Build hooks in `src/hooks/` (e.g., `usePrediction.ts`, `useMetrics.ts`)
4. Wire `EventSource` in `usePipelineStream.ts` for SSE

---

## Mock Data

All mock data is in `src/data/mockData.ts` with realistic values:

| Data | Details |
|---|---|
| OHLCV | 90 trading days per ticker (AAPL ~$180–190 range) |
| Poison events | 14 events across 4 tickers, 7 poison types |
| Cycle history | 7 cycles with gate results (2 failures, 5 passes) |
| Predictions | Per-ticker forecasts with confidence bands |
| Buffer status | 3/5 forget windows (trigger at 5) |
| Config | Default thresholds matching `.env.example` |

---

## Scripts

| Command | Description |
|---|---|
| `npm run dev` | Start Vite dev server with HMR |
| `npm run build` | TypeScript check + production build |
| `npm run preview` | Preview production build locally |
| `npx tsc --noEmit` | Type check only (no emit) |

---

## License

See [LICENSE](../LICENSE) in the project root.
