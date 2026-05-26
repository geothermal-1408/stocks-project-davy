# StockSense Run Instructions

This guide covers how to run the StockSense project using VS Code for the frontend/backend and Google Colab for the ML training loop (or optionally running the ML pipeline locally).

## Prerequisites
- Node.js v18+
- Python 3.10+
- A Google Colab account (for GPU training, if desired)

---

## Part 1: Running the Application (VS Code)

### 1. Database & Backend Setup
1. Open the project in **VS Code**.
2. Open a terminal and navigate to the `backend` folder:
   ```bash
   cd backend
   ```
3. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   # On Windows
   .\venv\Scripts\activate
   # On macOS/Linux
   source venv/bin/activate
   pip install -r requirements.txt
   ```
4. Verify your `.env` file (one was created automatically, using SQLite by default):
   ```env
   DATABASE_URL=sqlite+aiosqlite:///./stocksense.db
   ```
5. Start the FastAPI server:
   ```bash
   uvicorn app.main:app --reload
   ```
   *The backend will be running at `http://localhost:8000`.*

### 2. Frontend Setup
1. Open a new terminal in VS Code and navigate to the `frontend` folder:
   ```bash
   cd frontend
   ```
2. Install the Node modules:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   *The frontend will be running at `http://localhost:5173`.*

---

## Part 2: Running the ML Pipeline

You can run the machine learning tasks (ingestion, window building, and training) either locally in VS Code or in Google Colab if you want to fine-tune the Qwen model on a GPU.

### Option A: Local Execution (VS Code)

If you only want to use the LSTM and Statistical models, you don't need a GPU! You can run the pipeline right here in VS Code.

1. Ensure your terminal is in the `backend` folder and your `venv` is activated.
2. Add the `ml` folder to your PYTHONPATH so the scripts can find the `stocksense` package:
   ```bash
   # Windows (PowerShell)
   $env:PYTHONPATH = "..\ml"
   
   # macOS/Linux
   export PYTHONPATH="../ml"
   ```
3. **Bootstrap the data**:
   This downloads 2 years of AAPL data from yfinance, computes technical indicators, and builds sliding windows.
   ```bash
   python ../ml/stocksense/pipeline/bootstrap.py
   ```
4. **Run the LSTM Training (Optional)**:
   ```bash
   python ../ml/stocksense/training/lstm_trainer.py
   ```
   *The newly trained LSTM will be saved to `ml/output/stock/lstm/latest`.*

### Option B: Google Colab (For Qwen LoRA Fine-Tuning)

If you want to use the NLP-based Qwen model with Unlearning capabilities, you'll need a GPU. Colab's free T4 GPU is perfect for this.

1. Zip the `backend/` and `ml/` directories and upload them to your Google Drive, or clone your GitHub repo directly into Colab.
2. Open a new Colab Notebook and set the Runtime to **T4 GPU**.
3. Install the requirements:
   ```python
   !pip install -e backend/
   ```
4. **Run the ingestion and window building**:
   ```python
   !python ml/stocksense/pipeline/bootstrap.py
   ```
5. **Run the Model Training/Unlearning Cycle**:
   This simulates the unlearning of poisoned data.
   ```python
   !python ml/stocksense/pipeline/cycle_manager.py
   ```
6. Download the resulting weights from `ml/output/stock/current` and place them in your local `ml/output/stock/current` folder so the backend can use them!

### Option C: Running the Entire Backend + ML in Google Colab (Frontend Locally)

If you want to run the full FastAPI backend alongside the ML models in Colab (to utilize the GPU for live API inference), you can use `localtunnel` or `ngrok` to expose the backend to your local frontend.

1. Zip the entire `backend/` and `ml/` folders and upload them to Colab (or clone your GitHub repo in Colab).
2. Install all requirements and `localtunnel`:
   ```python
   !pip install -e backend/
   !npm install -g localtunnel
   ```
3. First, bootstrap the data and train the models as outlined in Option B (Steps 4 and 5).
4. Run the FastAPI backend in the background:
   ```python
   import subprocess
   # Start the FastAPI server in the background
   subprocess.Popen(["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"])
   ```
5. Expose port 8000 using localtunnel:
   ```python
   import urllib.request
   print("Password/Endpoint IP for localtunnel is:", urllib.request.urlopen('https://ipv4.icanhazip.com').read().decode('utf8').strip("\n"))
   !lt --port 8000
   ```
6. `localtunnel` will output a public URL (e.g., `https://some-random-url.loca.lt`). It may ask for an Endpoint IP password; use the IP printed in the step above.
7. Back on your local machine, open the `frontend` folder in VS Code, find where the API URL is configured (e.g., `frontend/.env` or inside `src/api.js`), and point it to the localtunnel URL:
   ```env
   VITE_API_URL=https://some-random-url.loca.lt
   ```
8. Start the local frontend in VS Code:
   ```bash
   cd frontend
   npm run dev
   ```
---

## Verification

Once everything is running:
1. Go to `http://localhost:5173`
2. Log in with the default admin credentials (if set up) or navigate to the Dashboard.
3. Verify that the **Prediction Service** shows predictions from either the `LSTM` or `Statistical` fallback.
4. Try injecting poison using the **Admin** panel, then check the `ml/output/logs/poison_log.json` file.
