# CLAUDE.md — StockSense Full-Stack Website

## Project Identity

**Name:** `stocksense-unlearn` (web platform)
**Goal:** A full-stack web application that ingests live AAPL (and multi-ticker) OHLCV data, detects poisoned/anomalous windows, continuously unlearns bad patterns and super-learns validated signals, and serves price predictions with confidence bands — all visible through a real-time trading dashboard.
**Model backend:** Qwen1.5-0.5B (text-based time-series) + llm_unlearn pipeline (AscentPlusDescent primary)
**Data source:** yfinance daily OHLCV; extendable to Alpaca / Polygon
**Target infra:** Single T4 GPU VM (GCP / Vast.ai / Colab Pro)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         BROWSER  (React)                             │
│                                                                      │
│  ┌────────────────┐  ┌───────────────────┐  ┌────────────────────┐  │
│  │ Prediction     │  │ Metrics Dashboard  │  │ Admin / Pipeline   │  │
│  │ Dashboard      │  │ PPL / AUC / MAE    │  │ Inject poison,     │  │
│  │ Price chart    │  │ Cycle history      │  │ force unlearn,     │  │
│  │ Confidence     │  │ Poison event log   │  │ config editor      │  │
│  └──────┬─────────┘  └────────┬──────────┘  └────────┬───────────┘  │
└─────────┼────────────────────┼─────────────────────┼──────────────┘
          │  REST + SSE         │  REST polling         │  REST
          ▼                     ▼                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        FASTAPI  (Python 3.11)                         │
│                                                                      │
│  GET  /predict           → inference → next-day OHLCV prediction     │
│  GET  /predict/ticker    → multi-ticker prediction endpoint          │
│  POST /ingest/trigger    → manual fetch + window build + route       │
│  GET  /poison/log        → paginated poison event log                │
│  GET  /metrics           → PPL, MAE, AUC, cycle history              │
│  POST /admin/unlearn     → manual cycle trigger                      │
│  POST /admin/inject-poison → synthetic injection for testing         │
│  GET  /stream/events     → SSE: ingest progress + cycle progress     │
│  GET  /health            → model loaded? ingest running?             │
│                                                                      │
│  ┌─────────────────────┐   ┌──────────────────────────────────────┐  │
│  │  PredictorWorker    │   │  PipelineWorker (BackgroundTask)     │  │
│  │  – loads model      │   │  – fetch → build windows → detect   │  │
│  │  – generate() x10   │   │  – route → maybe unlearn cycle      │  │
│  │  – decode prices    │   │  – eval gates → symlink update       │  │
│  │  – confidence bands │   │  – SSE progress events              │  │
│  └─────────────────────┘   └──────────────────────────────────────┘  │
└───────────────────┬───────────────────────┬──────────────────────────┘
                    │                        │
          ┌─────────▼──────┐      ┌──────────▼──────────────────────┐
          │   PostgreSQL   │      │   Redis                          │
          │  (predictions, │      │  (SSE pub/sub, ingest job lock, │
          │   poison log,  │      │   rate limits, ticker cache)    │
          │   cycle meta,  │      └────────────────────────────────┘
          │   user prefs)  │
          └────────────────┘
                    │
          ┌─────────▼──────────────────────────────────────────┐
          │     Filesystem                                      │
          │  ./models/Qwen1.5-0.5B/                            │
          │  ./output/stock/current  ← symlink                  │
          │  ./data/raw/aapl_raw.csv                           │
          │  ./data/buffers/forget_buffer.jsonl                │
          │  ./data/buffers/retain_buffer.jsonl                │
          │  ./data/windows/clean_windows.jsonl                │
          │  ./data/windows/poisoned_windows.jsonl             │
          │  ./data/validation/held_out_clean.jsonl            │
          │  ./tokenized_dataset/stock/                        │
          │  ./output/logs/cycle_history.json                  │
          │  ./output/logs/poison_log.json                     │
          └────────────────────────────────────────────────────┘
```

---

## Tech Stack

### Frontend
| Layer | Choice | Reason |
|---|---|---|
| Framework | **React 18 + Vite** | Fast HMR, SPA ideal for dashboard |
| Language | **TypeScript** | Required; financial data types need precision |
| Styling | **Tailwind CSS v3** | Utility-first; dark trading terminal theme |
| Charts | **Lightweight Charts (TradingView)** | Native OHLCV candlestick charts |
| Secondary charts | **Recharts** | PPL/MAE/AUC trend lines |
| State | **Zustand** | Prediction state, ticker selection, cycle state |
| Data fetching | **TanStack Query v5** | Auto-polling metrics + prediction cache |
| SSE | **EventSource API** | Ingest + cycle progress streaming |
| Tables | **TanStack Table v8** | Poison log, cycle history, sortable/filterable |
| Date handling | **date-fns** | OHLCV date parsing, window labels |
| Auth | **JWT (simple)** | Admin gate for unlearn trigger |
| Icons | **Lucide React** | |
| Routing | **React Router v6** | |

### Backend
| Layer | Choice | Reason |
|---|---|---|
| Framework | **FastAPI** | Async native; matches ML Python stack |
| Language | **Python 3.11** | |
| ASGI server | **Uvicorn + Gunicorn** | |
| Task queue | **Celery + Redis** | Ingest loop + long unlearn jobs isolated |
| Scheduling | **APScheduler** | Cron daily ingest at market close |
| Auth | **python-jose + passlib** | JWT |
| Validation | **Pydantic v2** | |
| ORM | **SQLAlchemy 2.0 async** | |
| Migrations | **Alembic** | |
| Market data | **yfinance** | Free OHLCV; Alpaca as upgrade path |
| Stats | **scipy / statsmodels** | Chow test for regime detection |

### Database
| Role | DB | Notes |
|---|---|---|
| Primary | **PostgreSQL 15** | Predictions, poison events, cycles, users |
| Cache / jobs | **Redis 7** | Celery broker, SSE bus, ticker cache (5min TTL) |
| TimeSeries (optional upgrade) | **TimescaleDB** | Hypertable for OHLCV; drop-in PostgreSQL extension |
| File store | **Filesystem** | Raw CSVs, JSONL windows, PT datasets, model weights |

### Model Pipeline
| Component | File | Notes |
|---|---|---|
| Predictor | `stocksense/prediction/predictor.py` | generate() x10 samples, text_decoder.py → prices |
| Ingestion | `stocksense/data/ingestion.py` | yfinance → raw CSV append |
| Window builder | `stocksense/data/window_builder.py` | 30-day OHLCV → text documents |
| Poison detector | `stocksense/data/poison_detector.py` | 7 signal types, configurable thresholds |
| Buffer router | `stocksense/data/buffer_router.py` | Routes clean/poison to JSONL buffers |
| Cycle manager | `stocksense/pipeline/cycle_manager.py` | Full super-learning loop |
| Unlearn | `stocksense/method/ad.py` | AscentPlusDescentTrainer (primary) |
| Eval | `stocksense/evaluation/run_eval.py` | PPL + accuracy |
| Prediction eval | `stocksense/evaluation/prediction_eval.py` | MAE, RMSE, directional accuracy |
| MIA | `stocksense/evaluation/run_mia.py` | AUC |

### DevOps
| Tool | Purpose |
|---|---|
| **Docker + Docker Compose** | API + Celery worker + Postgres + Redis containers |
| **Nginx** | Reverse proxy, SSL, static serving |
| **APScheduler / cron** | Daily `daily_ingest.sh` at 17:00 ET |
| **GitHub Actions** | CI lint + type-check + unit tests |
| **Fly.io / GCP + T4** | GPU-attached deployment |

---

## Repository Structure

```
stocksense-web/
│
├── CLAUDE.md                              ← This file
├── README.md
├── docker-compose.yml
├── .env.example
├── Makefile
│
├── frontend/
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       │
│       ├── pages/
│       │   ├── PredictionPage.tsx         ← Main: candlestick + prediction overlay
│       │   ├── DashboardPage.tsx          ← Metrics: PPL, MAE, AUC, cycles
│       │   ├── PoisonLogPage.tsx          ← Sortable table of poison events
│       │   ├── AdminPage.tsx              ← Pipeline control, inject poison, config
│       │   └── LoginPage.tsx
│       │
│       ├── components/
│       │   ├── prediction/
│       │   │   ├── CandlestickChart.tsx   ← TradingView Lightweight Charts
│       │   │   ├── PredictionOverlay.tsx  ← Next-day predicted candle + bands
│       │   │   ├── ConfidenceBands.tsx    ← Upper/lower from 10-sample generation
│       │   │   ├── TickerSelector.tsx     ← Dropdown: AAPL, MSFT, GOOG, ...
│       │   │   └── DirectionalBadge.tsx   ← ↑ Bull / ↓ Bear prediction badge
│       │   │
│       │   ├── dashboard/
│       │   │   ├── MetricsRow.tsx         ← forget_ppl, retain_ppl, MAE, MIA_AUC
│       │   │   ├── PPLChart.tsx           ← Recharts: forget/retain PPL per cycle
│       │   │   ├── MAEChart.tsx           ← Recharts: prediction MAE per cycle
│       │   │   ├── CycleTable.tsx         ← All cycles with gate pass/fail status
│       │   │   ├── PipelineStatus.tsx     ← SSE: ingesting / unlearning / idle
│       │   │   └── BufferGauge.tsx        ← forget_count / FORGET_TRIGGER progress
│       │   │
│       │   ├── poison/
│       │   │   ├── PoisonTable.tsx        ← TanStack Table: date, type, reason
│       │   │   ├── PoisonBadge.tsx        ← flash_crash | volume_spike | etc.
│       │   │   └── AnomalyAnnotation.tsx  ← Marks poison windows on candlestick
│       │   │
│       │   ├── admin/
│       │   │   ├── IngestPanel.tsx        ← "Fetch Now" button + ticker config
│       │   │   ├── UnlearnPanel.tsx       ← Method selector + trigger button
│       │   │   ├── PoisonInjector.tsx     ← Synthetic injection form (testing)
│       │   │   ├── ConfigEditor.tsx       ← sigma_thresh, swing_thresh, lr sliders
│       │   │   └── RollbackPanel.tsx      ← Previous cycle rollback selector
│       │   │
│       │   └── shared/
│       │       ├── Navbar.tsx
│       │       ├── StreamBanner.tsx       ← SSE status indicator
│       │       ├── CycleChip.tsx          ← "Cycle 7 · AD" badge
│       │       └── GateStatus.tsx         ← Pass/Fail gate display
│       │
│       ├── store/
│       │   ├── predictionStore.ts         ← Zustand: predictions, ticker, window
│       │   ├── cycleStore.ts              ← cycle state, SSE events
│       │   └── authStore.ts
│       │
│       ├── hooks/
│       │   ├── usePrediction.ts           ← GET /predict?ticker=AAPL
│       │   ├── useMetrics.ts              ← GET /metrics (polled 60s)
│       │   ├── usePoisonLog.ts            ← GET /poison/log (paginated)
│       │   ├── usePipelineStream.ts       ← SSE: GET /stream/events
│       │   └── useOHLCV.ts               ← GET /data/ohlcv?ticker=AAPL&days=90
│       │
│       ├── api/
│       │   └── client.ts
│       │
│       └── types/
│           ├── ohlcv.ts
│           ├── prediction.ts
│           ├── poison.ts
│           ├── cycle.ts
│           └── metrics.ts
│
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/versions/
│   │
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── deps.py
│       │
│       ├── routers/
│       │   ├── predict.py              ← GET /predict, GET /predict/{ticker}
│       │   ├── ingest.py               ← POST /ingest/trigger, GET /ingest/status
│       │   ├── poison.py               ← GET /poison/log, POST /admin/inject-poison
│       │   ├── metrics.py              ← GET /metrics, GET /data/ohlcv
│       │   ├── admin.py                ← POST /admin/unlearn, POST /admin/rollback
│       │   ├── stream.py               ← GET /stream/events (SSE)
│       │   └── auth.py
│       │
│       ├── services/
│       │   ├── prediction_service.py   ← Loads model, generates x10, decodes prices
│       │   ├── ingest_service.py       ← yfinance fetch → window build → route
│       │   ├── poison_service.py       ← Runs poison_detector, logs events to DB
│       │   ├── cycle_service.py        ← Full super-learning cycle
│       │   ├── metrics_service.py      ← Reads eval JSONs + cycle_history.json
│       │   └── sse_service.py          ← Redis pub/sub → SSE
│       │
│       ├── models/                     ← SQLAlchemy ORM
│       │   ├── user.py
│       │   ├── prediction_log.py       ← (ticker, date, pred_open/high/low/close/vol, actual, mae)
│       │   ├── poison_event.py         ← (ticker, window_start, window_end, type, reason, sigma)
│       │   ├── cycle_record.py         ← (cycle_num, method, forget_ppl, retain_ppl, mae, mia_auc)
│       │   └── ohlcv_cache.py          ← (ticker, date, open, high, low, close, vol) [optional]
│       │
│       ├── schemas/
│       │   ├── prediction.py
│       │   ├── poison.py
│       │   ├── cycle.py
│       │   └── metrics.py
│       │
│       ├── workers/
│       │   ├── predictor_worker.py     ← Singleton model + GPU lock
│       │   ├── pipeline_worker.py      ← Long-running ingest + unlearn job
│       │   └── scheduler.py            ← APScheduler: daily ingest cron
│       │
│       └── db/
│           ├── session.py
│           └── init_db.py
│
├── ml/                                 ← llm_unlearn pipeline (submodule or copy)
│   ├── stocksense/
│   │   ├── method/                     ← gradient_ascent, akl, ad, unlearn_arg
│   │   ├── data/                       ← ingestion, window_builder, poison_detector
│   │   │   ├── ingestion.py            ← yfinance → CSV
│   │   │   ├── window_builder.py       ← OHLCV rows → text windows
│   │   │   ├── poison_detector.py      ← 7-signal anomaly detector
│   │   │   ├── buffer_router.py
│   │   │   ├── buffer_tokenizer.py
│   │   │   └── adv_dataset.py
│   │   ├── training/                   ← finetune.py, run_unlearn.py
│   │   ├── pipeline/                   ← ingest_loop.py, cycle_manager.py
│   │   ├── evaluation/                 ← run_eval.py, run_mia.py, prediction_eval.py
│   │   ├── prediction/                 ← predictor.py, text_decoder.py, confidence.py
│   │   └── utils/
│   │
│   ├── models/Qwen1.5-0.5B/
│   ├── output/stock/
│   ├── data/
│   │   ├── raw/aapl_raw.csv
│   │   ├── buffers/
│   │   ├── windows/
│   │   └── validation/
│   ├── tokenized_dataset/stock/
│   └── configs/
│
├── nginx/nginx.conf
│
└── tests/
    ├── backend/
    │   ├── test_prediction_service.py
    │   ├── test_ingest_service.py
    │   ├── test_poison_service.py
    │   └── test_cycle_service.py
    └── frontend/
        ├── candlestick.test.tsx
        └── dashboard.test.tsx
```

---

## Database Schema

```sql
-- Users
CREATE TABLE users (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email        TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role         TEXT DEFAULT 'user',
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- OHLCV data (optional: replace with TimescaleDB hypertable)
CREATE TABLE ohlcv (
  id      BIGSERIAL PRIMARY KEY,
  ticker  TEXT NOT NULL,
  date    DATE NOT NULL,
  open    NUMERIC(12,4),
  high    NUMERIC(12,4),
  low     NUMERIC(12,4),
  close   NUMERIC(12,4),
  volume  BIGINT,
  UNIQUE (ticker, date)
);

-- Model predictions per ticker per date
CREATE TABLE prediction_logs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker      TEXT NOT NULL,
  pred_date   DATE NOT NULL,         -- date being predicted
  pred_open   NUMERIC(12,4),
  pred_high   NUMERIC(12,4),
  pred_low    NUMERIC(12,4),
  pred_close  NUMERIC(12,4),
  pred_vol    BIGINT,
  conf_high   NUMERIC(12,4),         -- upper confidence band (close)
  conf_low    NUMERIC(12,4),         -- lower confidence band (close)
  actual_close NUMERIC(12,4),        -- filled in next day by ingest
  mae         NUMERIC(10,6),         -- filled in retrospectively
  directional_correct BOOLEAN,
  model_cycle INT,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- Poison detection events
CREATE TABLE poison_events (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker       TEXT NOT NULL,
  window_start DATE NOT NULL,
  window_end   DATE NOT NULL,
  poison_type  TEXT NOT NULL,    -- price_outlier|flash_crash|volume_spike|negative_price|ohlc_violation|stale_data|regime_change
  reason       TEXT,             -- human-readable description
  sigma        NUMERIC(8,4),     -- z-score for price_outlier type
  swing_ratio  NUMERIC(8,4),     -- for flash_crash type
  vol_ratio    NUMERIC(8,4),     -- for volume_spike type
  buffered     BOOLEAN DEFAULT true,
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- Cycle metadata
CREATE TABLE cycle_records (
  id                SERIAL PRIMARY KEY,
  cycle_num         INT UNIQUE NOT NULL,
  method            TEXT NOT NULL,
  forget_ppl        FLOAT,
  retain_ppl        FLOAT,
  mae_validation    FLOAT,
  directional_acc   FLOAT,
  mia_auc           FLOAT,
  forget_count      INT,
  retain_count      INT,
  duration_sec      INT,
  deployed          BOOLEAN DEFAULT false,
  gate_failure      TEXT,          -- null if deployed
  created_at        TIMESTAMPTZ DEFAULT now()
);

-- Ingest job log
CREATE TABLE ingest_jobs (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker         TEXT NOT NULL,
  job_type       TEXT NOT NULL,    -- 'daily' | 'manual' | 'bootstrap'
  windows_built  INT,
  clean_count    INT,
  poison_count   INT,
  cycle_triggered BOOLEAN DEFAULT false,
  status         TEXT,             -- 'running' | 'complete' | 'failed'
  error          TEXT,
  started_at     TIMESTAMPTZ DEFAULT now(),
  finished_at    TIMESTAMPTZ
);
```

---

## API Reference

### `GET /predict`
```json
Query params: ticker=AAPL&samples=10
Response: {
  "ticker": "AAPL",
  "pred_date": "2024-11-05",
  "prediction": { "open": 222.50, "high": 224.10, "low": 221.30, "close": 223.40, "vol": 38500000 },
  "confidence": { "close_high": 225.20, "close_low": 221.60 },
  "directional": "up",
  "model_cycle": 7,
  "latency_ms": 1840
}
```

### `GET /data/ohlcv`
```json
Query params: ticker=AAPL&days=90
Response: {
  "ticker": "AAPL",
  "data": [
    { "date": "2024-08-01", "open": 218.0, "high": 220.5, "low": 217.0, "close": 219.8, "vol": 42000000 },
    ...
  ],
  "poison_annotations": [
    { "date": "2024-09-03", "type": "flash_crash", "swing_ratio": 0.12 }
  ]
}
```

### `GET /metrics`
```json
Response: {
  "current_cycle": 7,
  "method": "ascent_plus_descent",
  "latest": {
    "forget_ppl": 18.2, "retain_ppl": 6.4,
    "mae_validation": 1.82, "directional_acc": 0.57, "mia_auc": 0.58
  },
  "history": [...],
  "buffer_status": { "forget_count": 3, "retain_count": 87, "trigger_at": 5 },
  "last_ingest": "2024-11-04T17:03:22Z",
  "next_ingest": "2024-11-05T17:00:00Z"
}
```

### `GET /poison/log`
```json
Query params: page=1&limit=20&ticker=AAPL&type=flash_crash
Response: {
  "total": 14,
  "events": [
    {
      "id": "uuid",
      "ticker": "AAPL",
      "window_start": "2024-08-05",
      "window_end": "2024-09-04",
      "poison_type": "flash_crash",
      "swing_ratio": 0.121,
      "created_at": "2024-09-05T17:12:00Z"
    }
  ]
}
```

### `POST /admin/inject-poison`
```json
Request:  { "ticker": "AAPL", "inject_type": "flash_crash", "target_date": "2024-11-01" }
Response: { "window_id": "uuid", "injected": true, "detected": true, "test_passed": true }
```

### `GET /stream/events` (SSE)
```
event: ingest_start
data: {"ticker": "AAPL", "job_id": "uuid"}

event: ingest_progress
data: {"step": "fetching", "pct": 20}

event: poison_detected
data: {"type": "flash_crash", "window_start": "2024-10-01", "swing_ratio": 0.11}

event: ingest_complete
data: {"clean": 28, "poison": 1, "cycle_triggered": true}

event: cycle_progress
data: {"step": "unlearning", "pct": 55}

event: cycle_complete
data: {"cycle": 8, "forget_ppl": 19.1, "mae": 1.74, "deployed": true}
```

---

## Predictor Service — Critical Details

```python
# backend/app/workers/predictor_worker.py

class PredictorWorker:
    """Singleton. GPU model. asyncio.Lock shared with PipelineWorker."""
    _model = None
    _tokenizer = None
    _lock = asyncio.Lock()
    _current_cycle = -1

    async def predict(self, ticker: str, window_text: str, n_samples: int = 10) -> PredictionResult:
        async with self._lock:
            self._maybe_reload_model()
            inputs = self._tokenizer(window_text, return_tensors="pt").to(self._model.device)
            samples = []
            for _ in range(n_samples):
                with torch.no_grad():
                    out = self._model.generate(
                        **inputs, max_new_tokens=64,
                        do_sample=True, temperature=0.7, top_p=0.9
                    )
                decoded = self._tokenizer.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
                parsed = text_decoder.parse(decoded)   # regex → {open, high, low, close, vol}
                if parsed:
                    samples.append(parsed)

            return build_prediction_result(samples)   # mean + std → confidence bands
```

**Window text format passed to model:**
```
date=2024-10-01 open=226.21 high=227.52 low=225.41 close=226.78 vol=40121300 | date=2024-10-02 ...
```
Last 30 days. Model generates the next day token sequence. `text_decoder.parse()` extracts values via regex `(open|high|low|close|vol)=(\d+\.?\d*)`.

---

## Poison Detector — All 7 Signals

```python
# ml/stocksense/data/poison_detector.py

def is_poisoned(window_df: pd.DataFrame, config: PoisonConfig) -> tuple[bool, str | None]:
    """
    Check window (30 rows of OHLCV) against 7 anomaly signals.
    Returns (is_poisoned, reason_code).
    """

    # 1. Price z-score outlier (uses rolling 90d baseline passed in config)
    if abs(zscore(window_df['close'].iloc[-1], config.rolling_mean, config.rolling_std)) > config.sigma_thresh:
        return True, f"price_outlier:sigma={zscore:.2f}"

    # 2. Flash crash — intraday swing > 10%
    max_swing = ((window_df['high'] - window_df['low']) / window_df['low']).max()
    if max_swing > config.swing_thresh:
        return True, f"flash_crash:swing={max_swing:.3f}"

    # 3. Volume spike — > 5x 30d rolling median
    vol_ratio = window_df['vol'].iloc[-1] / config.rolling_vol_median
    if vol_ratio > config.volume_spike_multiplier:
        return True, f"volume_spike:ratio={vol_ratio:.1f}"

    # 4. Negative price
    if (window_df[['open','high','low','close']] <= 0).any().any():
        return True, "negative_price"

    # 5. OHLC violation (high < low, close outside band)
    if (window_df['high'] < window_df['low']).any():
        return True, "ohlc_violation:high_lt_low"
    if ((window_df['close'] > window_df['high']) | (window_df['close'] < window_df['low'])).any():
        return True, "ohlc_violation:close_out_of_band"

    # 6. Stale data (duplicate dates or non-monotonic)
    if window_df['date'].duplicated().any() or not window_df['date'].is_monotonic_increasing:
        return True, "stale_data"

    # 7. Regime change (Chow test — optional, expensive)
    if config.regime_change_enabled:
        if chow_test_pvalue(window_df['close']) < config.regime_p_threshold:
            return True, "regime_change"

    return False, None
```

---

## Ingest Pipeline — Daily Flow

```python
# backend/app/services/ingest_service.py

async def run_daily_ingest(ticker: str, job_id: str):
    emit_sse(job_id, "ingest_start", {"ticker": ticker})

    # 1. Fetch
    emit_sse(job_id, "ingest_progress", {"step": "fetching", "pct": 10})
    new_rows = await asyncio.to_thread(fetch_new_ohlcv, ticker)
    await upsert_ohlcv(db, ticker, new_rows)

    # 2. Build windows (sliding 30-day)
    emit_sse(job_id, "ingest_progress", {"step": "building_windows", "pct": 30})
    windows = await asyncio.to_thread(build_windows, new_rows, window_size=30)

    # 3. Screen + route
    clean, poison = 0, 0
    for window_df, window_text in windows:
        is_bad, reason = await asyncio.to_thread(is_poisoned, window_df, config)
        if is_bad:
            append_jsonl(FORGET_BUFFER, window_text)
            await log_poison_event(db, ticker, window_df, reason)
            emit_sse(job_id, "poison_detected", parse_reason(reason))
            poison += 1
        else:
            append_jsonl(RETAIN_BUFFER, window_text)
            clean += 1

    # 4. Trigger cycle if threshold hit
    forget_count = count_lines(FORGET_BUFFER)
    cycle_triggered = forget_count >= config.FORGET_TRIGGER and clean >= config.MIN_RETAIN_SIZE
    emit_sse(job_id, "ingest_complete", {"clean": clean, "poison": poison, "cycle_triggered": cycle_triggered})

    if cycle_triggered:
        await cycle_service.run_cycle(method="ascent_plus_descent", job_id=new_job_id())

    await log_ingest_job(db, job_id, clean=clean, poison=poison, cycle_triggered=cycle_triggered)
```

---

## Deployment Gates

```python
def passes_gates(new: Metrics, prior: Metrics) -> tuple[bool, str]:
    if new.forget_ppl <= prior.forget_ppl * 1.10:
        return False, "forget_ppl not improved by 10%"
    if new.retain_ppl > prior.retain_ppl * 1.10:
        return False, "retain_ppl degraded >10%"
    if new.mae_validation > prior.mae_validation * 1.05:
        return False, "MAE degraded >5%"
    if new.directional_acc < 0.52:
        return False, "directional accuracy below coin-flip"
    # MIA gate is warning-only for stocks
    return True, ""
```

---

## Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/stocksense_db
REDIS_URL=redis://localhost:6379/0

# Auth
SECRET_KEY=your-jwt-secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Market data
TICKER=AAPL
FETCH_PERIOD=2y
WINDOW_SIZE=30
INGEST_CRON=0 17 * * 1-5        # 5pm ET weekdays

# ML pipeline
MODEL_BASE_PATH=./ml/models/Qwen1.5-0.5B
OUTPUT_BASE=./ml/output/stock
DATA_BASE=./ml/data
TOKENIZED_BASE=./ml/tokenized_dataset

# Poison detector
POISON_SIGMA_THRESH=3.0
POISON_SWING_THRESH=0.10
POISON_VOL_MULTIPLIER=5
REGIME_CHANGE_ENABLED=false

# Unlearn config
FORGET_TRIGGER=5
MIN_RETAIN_SIZE=20
UNLEARN_METHOD=ascent_plus_descent
LEARNING_RATE=5e-6
FINETUNE_EPOCHS=1

# Prediction
PREDICTION_SAMPLES=10
PREDICTION_TEMPERATURE=0.7

# Misc
WANDB_API_KEY=
WANDB_MODE=offline
ADMIN_EMAIL=admin@yourdomain.com
```

---

## Docker Compose

```yaml
version: "3.9"
services:
  postgres:
    image: postgres:15
    volumes: [postgres_data:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: stocksense_db
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass

  redis:
    image: redis:7-alpine

  backend:
    build: ./backend
    depends_on: [postgres, redis]
    volumes:
      - ./ml:/app/ml
    runtime: nvidia
    environment:
      - DATABASE_URL
      - REDIS_URL
    ports: ["8000:8000"]

  celery_worker:
    build: ./backend
    command: celery -A app.celery_app worker --loglevel=info --pool=solo
    depends_on: [redis, postgres]
    volumes: [./ml:/app/ml]
    runtime: nvidia          # Celery worker needs GPU for unlearn jobs

  celery_beat:
    build: ./backend
    command: celery -A app.celery_app beat --loglevel=info
    depends_on: [redis]

  frontend:
    build: ./frontend
    ports: ["3000:80"]

  nginx:
    image: nginx:alpine
    volumes: [./nginx/nginx.conf:/etc/nginx/nginx.conf]
    ports: ["80:80", "443:443"]
    depends_on: [backend, frontend]

volumes:
  postgres_data:
```

---

## Frontend Pages

### `PredictionPage` — Primary UX
- TradingView candlestick chart (90-day history)
- Poison windows annotated directly on the chart (red markers)
- "Next Day Prediction" panel: predicted OHLCV values + confidence band
- Directional badge: ↑ / ↓ with confidence %
- Ticker selector (AAPL default, extendable)
- Cycle chip: "Cycle 7 · AD · MAE 1.82"

### `DashboardPage` — Metrics
- Metrics row: forget_ppl, retain_ppl, MAE, directional_acc, MIA_AUC
- PPL line chart over cycles (forget trending up = healthy)
- MAE line chart over cycles (should trend down = improving)
- Buffer gauge: `3 / 5 forget windows` progress bar
- Cycle history table: all cycles, gate status, method, metrics
- SSE pipeline status banner

### `PoisonLogPage` — Anomaly Audit
- Full TanStack Table of all poison events
- Filter by: ticker, poison type, date range
- Expandable row: full reason, sigma/swing/vol values
- "Inject synthetic poison" button → test detector in staging

### `AdminPage` — Control Plane (admin only)
- Ingest panel: "Fetch Now" for any ticker, last ingest time
- Unlearn panel: method selector, manual trigger, current job status
- Poison injector: form to inject specific poison type for testing
- Config editor: all poison thresholds + unlearn hyperparams (sliders)
- Rollback panel: select prior cycle, restore symlink

---

## Key Implementation Rules

1. **Celery for long jobs.** Ingest (API calls + window building) and unlearn cycles are Celery tasks. FastAPI only dispatches and streams progress. Never `asyncio.to_thread` for jobs >30 seconds.
2. **One GPU lock.** `PredictorWorker` and unlearn Celery task share a Redis-backed lock. Predictions queue; unlearn blocks inference during weight swap.
3. **Validation set is sacred.** `data/validation/held_out_clean.jsonl` is read-only. Never ingested, never trained on. Gate 3 (MAE) depends on it.
4. **TimescaleDB upgrade path.** OHLCV table maps cleanly to a TimescaleDB hypertable — enable the extension and call `create_hypertable('ohlcv', 'date')` in migration when scaling to multi-ticker.
5. **Daily ingest cron.** APScheduler or Celery Beat fires `daily_ingest` at 17:00 ET (market close + 30min buffer) on weekdays only.
6. **Poison log is immutable.** Poison events are never deleted. They're the audit trail. Archive → DB, never file-only.
7. **Lower LR than chatbot.** `5e-6` is the default. Market signal-to-noise is subtle. Aggressive unlearning erases real volatility alongside poison.
8. **No prediction caching for <1hr.** Predictions reflect the current model. Stale predictions mislead. Max TTL = 1 hour in Redis (for identical ticker+window combos only).
