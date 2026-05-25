# StockSense — Free-Tier Deployment Guide

Deploy the full StockSense stack (frontend, backend, ML models, database) using free-tier services.

---

## Architecture for Deployment

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   VERCEL      │────▶│   RENDER      │────▶│   NEON        │
│   Frontend    │     │   Backend     │     │   PostgreSQL  │
│   (Static)    │     │   (FastAPI)   │     │   (Free)      │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                     ┌──────┴───────┐
                     │   HF Hub      │
                     │   Model Store  │
                     └──────────────┘
```

| Service | Provider | Free Tier |
|---------|----------|-----------|
| Frontend | Vercel | Unlimited static, 100GB bandwidth |
| Backend | Render | 750 hours/month, 512MB RAM |
| Database | Neon | 0.5 GB storage, serverless Postgres |
| Model Store | Hugging Face Hub | Unlimited public repos |
| Scheduling | Render Cron | 1 cron job free |
| Monitoring | UptimeRobot | 50 monitors free |

---

## Prerequisites

- Git repository (GitHub/GitLab)
- Node.js 18+ (for local build)
- Python 3.10+ (for local testing)
- Accounts on: Vercel, Render, Neon, Hugging Face

---

## Step 1: Database (Neon PostgreSQL)

### 1.1 Create Database

1. Go to [neon.tech](https://neon.tech) → Sign up
2. Create project: "stocksense"
3. Create database: "stocksense_prod"
4. Copy the connection string:
   ```
   postgresql://user:pass@ep-xxxx.us-east-2.aws.neon.tech/stocksense_prod?sslmode=require
   ```

### 1.2 Note Environment Variables

```env
DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxxx.us-east-2.aws.neon.tech/stocksense_prod?sslmode=require
```

> **Important:** Replace `postgresql://` with `postgresql+asyncpg://` for async SQLAlchemy.

---

## Step 2: Backend (Render)

### 2.1 Prepare Backend

Create `render.yaml` in the project root:

```yaml
services:
  - type: web
    name: stocksense-api
    runtime: python
    plan: free
    buildCommand: |
      cd backend
      pip install -r requirements.txt
      cd ../ml
      pip install -e .
    startCommand: cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: SECRET_KEY
        generateValue: true
      - key: CORS_ORIGINS
        value: https://stocksense.vercel.app
      - key: TICKER
        value: AAPL
      - key: MODEL_BASE_PATH
        value: ./ml/models/Qwen1.5-0.5B
      - key: OUTPUT_BASE
        value: ./ml/output/stock
      - key: DATA_BASE
        value: ./ml/data
    autoDeploy: true
```

### 2.2 Create requirements.txt

Ensure `backend/requirements.txt` includes:

```txt
fastapi>=0.100
uvicorn[standard]>=0.23
sqlalchemy[asyncio]>=2.0
asyncpg
pydantic-settings
bcrypt
python-jose[cryptography]
python-multipart
aiosqlite
yfinance
pandas
numpy
torch
transformers
```

### 2.3 Deploy

1. Push to GitHub
2. Go to [render.com](https://render.com) → New Web Service
3. Connect your repo
4. Set root directory: (leave blank, use render.yaml)
5. Add environment variables:
   - `DATABASE_URL` = your Neon connection string
   - `SECRET_KEY` = (auto-generated)
   - `NEWSAPI_KEY` = your NewsAPI key (optional)

### 2.4 Cron Job for Daily Ingest

On Render → New Cron Job:
```
Schedule: 0 22 * * 1-5    (10 PM UTC = 5 PM ET, weekdays)
Command:  cd backend && python -c "
import asyncio
from app.services.ingest_service import run_ingest
asyncio.run(run_ingest('AAPL'))
"
```

---

## Step 3: Frontend (Vercel)

### 3.1 Configure for Production

Update `frontend/vite.config.ts` for production:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
```

### 3.2 Create API Proxy for Production

Create `frontend/vercel.json`:

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://stocksense-api.onrender.com/:path*"
    },
    {
      "source": "/stream/:path*",
      "destination": "https://stocksense-api.onrender.com/stream/:path*"
    }
  ]
}
```

### 3.3 Deploy

1. Go to [vercel.com](https://vercel.com) → Import Project
2. Select your repo
3. Set root directory: `frontend`
4. Build command: `npm run build`
5. Output directory: `dist`
6. Deploy

---

## Step 4: Model Storage (Hugging Face Hub)

### 4.1 Upload Base Model

```bash
# Install HF CLI
pip install huggingface-hub

# Login
huggingface-cli login

# Upload the Qwen model
huggingface-cli upload your-username/stocksense-qwen ml/models/Qwen1.5-0.5B/

# Upload LSTM checkpoint (after bootstrap)
huggingface-cli upload your-username/stocksense-lstm ml/output/stock/lstm/latest/
```

### 4.2 Configure Render to Pull Models on Startup

Add to your Render build command:
```bash
pip install huggingface-hub
python -c "
from huggingface_hub import snapshot_download
snapshot_download('your-username/stocksense-qwen', local_dir='ml/models/Qwen1.5-0.5B')
snapshot_download('your-username/stocksense-lstm', local_dir='ml/output/stock/lstm/latest')
"
```

---

## Step 5: Environment Variables Summary

### Render (Backend)

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://...@neon.tech/...` |
| `SECRET_KEY` | (auto-generated, 32+ chars) |
| `ALGORITHM` | `HS256` |
| `CORS_ORIGINS` | `https://your-app.vercel.app` |
| `TICKER` | `AAPL` |
| `MODEL_BASE_PATH` | `./ml/models/Qwen1.5-0.5B` |
| `OUTPUT_BASE` | `./ml/output/stock` |
| `DATA_BASE` | `./ml/data` |
| `NEWSAPI_KEY` | (optional, from newsapi.org) |
| `WANDB_MODE` | `offline` |

### Vercel (Frontend)

No environment variables needed — the API proxy handles routing.

---

## Step 6: Bootstrap After Deployment

After deploying the backend for the first time:

```bash
# SSH into Render shell or run via cron:
cd ml
python -m stocksense.pipeline.bootstrap --ticker AAPL --epochs 30

# This will:
# 1. Fetch 2 years of AAPL data from yfinance
# 2. Build sliding windows
# 3. Populate retain_buffer.jsonl
# 4. Train initial LSTM model
```

---

## Step 7: Monitoring

### UptimeRobot (Free)

1. Go to [uptimerobot.com](https://uptimerobot.com) → Sign up
2. Add monitors:
   - **Backend Health**: `https://stocksense-api.onrender.com/health` (HTTP, 5 min)
   - **Frontend**: `https://your-app.vercel.app` (HTTP, 5 min)

### Render Logs

View backend logs in real-time:
- Render Dashboard → your service → Logs

---

## Troubleshooting

### Backend Cold Starts

Render free tier sleeps after 15 minutes of inactivity. First request takes ~30s.

**Fix:** Use UptimeRobot to ping `/health` every 14 minutes.

### Database Connection Limits

Neon free tier: 5 concurrent connections.

**Fix:** Use connection pooling in SQLAlchemy:
```python
DATABASE_URL = "postgresql+asyncpg://...?prepared_statement_cache_size=0"
```

### Model Too Large for Render

Render free tier has 512MB RAM. Qwen1.5-0.5B needs ~1GB.

**Options:**
1. Use Render paid tier ($7/month for 1GB RAM)
2. Run LSTM-only mode (requires ~50MB RAM)
3. Use quantized Qwen (GPTQ/AWQ for 4-bit, ~250MB)

### CORS Errors

If you see CORS errors in the browser console:
1. Verify `CORS_ORIGINS` on Render includes your Vercel URL
2. Check Vercel `vercel.json` rewrites are correct
3. Ensure no trailing slashes in URLs

---

## Cost Summary

| Service | Monthly Cost |
|---------|-------------|
| Vercel (Frontend) | $0 |
| Render (Backend) | $0 |
| Neon (Database) | $0 |
| HF Hub (Models) | $0 |
| UptimeRobot | $0 |
| NewsAPI | $0 (100 req/day) |
| **Total** | **$0/month** |

> **Note:** Render free tier spins down after inactivity. For always-on, Render Starter is $7/month.
