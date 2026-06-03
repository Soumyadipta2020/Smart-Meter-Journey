# IMSERV Smart Meter Field Planning & Utility Operations Platform

Enterprise-grade utility operations planning platform for IMSERV — extended from the DAA-Project architecture.

---

## Architecture Overview

| Layer       | Technology                                           |
|-------------|------------------------------------------------------|
| Backend     | Flask 3 (Python), Gunicorn                          |
| Frontend    | Vanilla ES6+, Chart.js 4.4, SPA architecture        |
| Analytics   | Python (pandas, scikit-learn, statsmodels)           |
| Data Store  | File-based CSV/JSON (PostgreSQL schema included)     |
| Deployment  | Render.com / Docker                                  |

Inherits the DAA-Project pattern: flat Flask monolith with modular Python engine layer, dark glassmorphism design system, Chart.js dashboards, and file-based lazy-loaded data.

---

## Modules

| # | Module                          | Description                                                  |
|---|---------------------------------|--------------------------------------------------------------|
| 1 | Bookings to Completions Journey | Executive funnel KPIs, regional heatmap, AI recommendations  |
| 2 | Contact Centre Forecasting      | Prophet/ARIMA/XGBoost/LightGBM multi-model ensemble          |
| 3 | Cancellations & Aborts          | Pareto root cause, trend, AI risk prediction, rebooking      |
| 4 | Field Operations & Engineering  | Patch planning, utilisation matrix, understaffing forecast    |
| 5 | Financial Scenario Planning     | Interactive P&L simulator, waterfall charts, 2026 forecast   |

---

## Quick Start

```bash
# 1. Clone and enter project
cd IMSERV-Project

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Generate synthetic datasets (auto-runs on first startup)
python engine/data_generator.py

# 4. Start the platform
python app.py
# → http://localhost:5000
```

---

### Hugging Face Chatbot

The floating app assistant uses a Flask proxy so the Hugging Face token stays server-side. Set these variables in `.env`:

```bash
HF_TOKEN=hf_or_provider_key
HF_CHAT_PROVIDER=novita
HF_CHAT_MODEL=google/gemma-4-31B-it
HF_CHAT_BASE_URL=https://router.huggingface.co/v1
# or point directly at a dedicated endpoint:
# HF_CHAT_ENDPOINT=https://your-endpoint.endpoints.huggingface.cloud/v1/chat/completions
```

---

## Docker

```bash
docker-compose up --build
# Platform: http://localhost:5000
# PostgreSQL: localhost:5432
```

---

## Render.com Deployment

1. Create a new **Web Service** in Render
2. Connect this repository
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 120 app:app`
5. Environment variable: `SECRET_KEY` (auto-generated)
6. Add `HF_TOKEN` in Render as a secret environment variable. The blueprint includes the non-secret chatbot defaults:
   - `HF_CHAT_PROVIDER=novita`
   - `HF_CHAT_MODEL=google/gemma-4-31B-it`
   - `HF_CHAT_BASE_URL=https://router.huggingface.co/v1`

The Render config is tuned for 512MB instances: data loads lazily, large CSVs are not cached by default, and dataset generation is disabled at runtime unless explicitly enabled.

The `render.yaml` file handles all non-secret configuration automatically. Keep `HF_TOKEN` only in Render's environment settings.

---

## Project Structure

```
IMSERV-Project/
├── app.py                      # Flask application — all API routes
├── requirements.txt
├── render.yaml                 # Render.com deployment config
├── Dockerfile
├── docker-compose.yml
│
├── engine/                     # Analytics engines (modular Python)
│   ├── data_generator.py       # Synthetic dataset generator
│   ├── ingestion.py            # Data loading + lazy cache
│   ├── forecasting_engine.py   # Contact centre forecasting (Prophet/ARIMA/XGBoost/LightGBM)
│   ├── cancellation_engine.py  # Cancellation analysis + AI prediction
│   ├── field_ops_engine.py     # Engineer planning + optimisation
│   ├── financial_engine.py     # Financial scenario simulation
│   └── ai_recommendations.py  # Cross-module AI recommendation engine
│
├── static/
│   ├── css/style.css           # Dark glassmorphism design system
│   └── js/
│       ├── app.js              # SPA controller
│       ├── config.js           # Chart.js config + utilities
│       ├── theme.js            # Dark/light mode toggle
│       ├── dashboard.js        # Module 1: Journey dashboard
│       ├── forecasting.js      # Module 2: CC forecasting
│       ├── cancellations.js    # Module 3: Cancellations
│       ├── field_ops.js        # Module 4: Field operations
│       └── financial.js        # Module 5: Financial scenarios
│
├── templates/index.html        # Single-page application template
│
├── data/
│   ├── inputs/                 # CSV datasets (auto-generated)
│   │   ├── master_operations.csv     # Source-of-truth job ledger
│   │   ├── channel_volume.csv        # Daily channel aggregation from master
│   │   ├── booking_journey.csv       # Weekly funnel aggregation from master
│   │   ├── engineers.csv             # Engineer dimension
│   │   ├── engineer_availability.csv # Engineer-day capacity and completed jobs
│   │   ├── financial_data.csv        # Monthly P&L aggregation from master
│   │   └── capacity_demand.csv       # Weekly patch demand joined to capacity
│   └── outputs/                # Generated analytics cache
│
└── deployment/
    └── schema.sql              # PostgreSQL schema for persistent storage
```

---

## API Reference

### Journey (Module 1)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/journey/kpis` | GET | Funnel KPIs: requests→completions |
| `/api/journey/weekly-trend` | GET | Weekly completion/cancellation trend |
| `/api/journey/regional-heatmap` | GET | Regional completion rate RAG |

### Contact Centre Forecasting (Module 2)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/forecasting/channel-kpis` | GET | Channel volume and conversion KPIs |
| `/api/forecasting/forecast` | GET | 26-week multi-model forecast with P10/P50/P90 |
| `/api/forecasting/funnel` | GET | Booking conversion funnel |

### Cancellations (Module 3)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/cancellations/kpis` | GET | Cancellation/abort KPIs |
| `/api/cancellations/root-causes` | GET | Pareto root cause analysis |
| `/api/cancellations/trends` | GET | Monthly trend + 6-month forecast |
| `/api/cancellations/heatmap` | GET | Regional RAG comparison |
| `/api/cancellations/predict` | GET | AI risk score + recommendations |
| `/api/cancellations/rebooking` | GET | Rebooking rate analytics |

### Field Operations (Module 4)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/field-ops/kpis` | GET | Engineer utilisation KPIs |
| `/api/field-ops/capacity-matrix` | GET | Regional capacity vs demand |
| `/api/field-ops/patch-plan` | GET | Patch-level utilisation |
| `/api/field-ops/engineer-performance` | GET | Top 20 engineer performance |
| `/api/field-ops/understaffing-forecast` | GET | 8-week understaffing prediction |
| `/api/field-ops/optimise` | GET | Workforce rebalancing recommendations |

### Financial (Module 5)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/financial/kpis` | GET | Revenue, cost, margin KPIs |
| `/api/financial/scenario` | POST | Run named P&L scenario |
| `/api/financial/compare-scenarios` | POST | Compare multiple scenarios |
| `/api/financial/forecast-profitability` | GET | 2026 P&L forecast |

### System
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check + data status |
| `/api/regions` | GET | Region reference list |
| `/api/data/reload` | GET | Force reload all data caches |
| `/api/data/generate` | GET | Regenerate synthetic datasets |
| `/api/ai/recommendations` | GET | Cross-module AI insights |
| `/api/ai/summary` | GET | Natural language health summary |

### Query Parameters (most endpoints)
- `region` — filter by region code (NW, NE, MID, SE, SW, WAL, SCO, YRK)
- `year` — 2025 (default: 2025)

---

## Datasets

All datasets cover **2025 actuals** + **2026 forecasts** with:
- Regional seasonality (8 UK regions)
- Operational anomalies and realistic noise
- Cancellation behaviour by region and reason
- Engineer workforce constraints and absence patterns
- Capacity bottlenecks in high-demand weeks

Regenerate with: `python engine/data_generator.py`

---

## PostgreSQL Extension

For production persistence, the full normalised schema is in `deployment/schema.sql`.
Enable with `ENABLE_DATABASE=true` and `DATABASE_URL=postgresql://...` in `.env`.

---

## Integration with DAA-Project

This platform is designed as a **natural evolution** of DAA-Project:
- Same Flask + Vanilla JS SPA architecture
- Same dark glassmorphism CSS design system (`--navy`, `--accent`, `--ok`, `--warn`, `--crit`)
- Same Chart.js 4.4 visualisation patterns
- Same three-tier planning philosophy (strategic / tactical / operational)
- Same lazy-loading data cache pattern
- Same modular Python engine architecture
- Same Render.com deployment approach
- Gunicorn WSGI server production setup

DAA modules can be registered as Flask blueprints and mounted under `/api/daa/`.
