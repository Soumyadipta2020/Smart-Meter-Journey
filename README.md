# Smart Meter Journey

A Flask-based operations dashboard for smart meter appointment planning, field capacity, contact-centre forecasting, appointment fallout, and financial scenario modelling.

The application presents a single-page executive dashboard for smart meter utility operations. It uses a connected synthetic data model, so appointment journey metrics, channel volumes, cancellation analysis, engineer capacity, and financial outputs reconcile back to the same operational ledger.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Running the App](#running-the-app)
- [Testing](#testing)
- [Data Model](#data-model)
- [API Reference](#api-reference)
- [AI and Chatbot Features](#ai-and-chatbot-features)
- [Docker](#docker)
- [Render Deployment](#render-deployment)
- [Development Notes](#development-notes)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Overview

The platform helps operations teams understand and improve the end-to-end smart meter appointment journey:

1. Customers enter the booking funnel.
2. Contact-centre channels create and convert appointment demand.
3. Appointments are booked, cancelled, aborted, completed, or left unresolved.
4. Field engineers are allocated across regions and patches.
5. Operational changes are translated into financial impact.

The frontend is a vanilla JavaScript single-page application served by Flask. The backend exposes JSON APIs and delegates analytics work to small Python engine modules. Data is stored as CSV files under `data/inputs`, with a PostgreSQL schema included for future persistent storage.

## Key Features

- Appointment journey dashboard with requests, contacts, bookings, visits, cancellations, aborts, completions, and conversion rates.
- Regional heatmaps and supplier-level views for operational drill-down.
- Contact-centre forecasting using baseline volumes, channel KPIs, and planning target metrics.
- Cancellation and abort analysis with root causes, trend views, regional heatmaps, prediction payloads, and rebooking analytics.
- Field operations planning with engineer utilisation, regional capacity matrices, patch-level plans, engineer performance, capacity forecasts, and workforce optimisation.
- Financial scenario modelling for revenue, cost, margin, completion rates, cancellation rates, abort rates, engineer counts, and productivity assumptions.
- Optional cross-module AI recommendations and an optional floating chatbot backed by a server-side Hugging Face proxy.
- Render and Docker deployment support.
- Smoke tests for the dashboard, health endpoint, region reference endpoint, and core API routes.

## Architecture

| Layer | Technology |
| --- | --- |
| Backend | Flask 3, Flask-CORS, Gunicorn |
| Frontend | HTML, CSS, vanilla ES modules, Chart.js loaded in the browser |
| Analytics | Python engine modules using standard-library data processing patterns |
| Data Store | CSV/JSON files in `data/inputs` |
| Optional Database | PostgreSQL schema in `deployment/schema.sql` |
| Deployment | Render blueprint, Dockerfile, Docker Compose |
| Tests | Python `unittest` smoke suite |

The app follows a flat Flask monolith plus modular engine layer:

- `app.py` owns routing, request parsing, response shaping, health checks, and feature flags.
- `engine/` owns data ingestion, synthetic data generation, forecasting, cancellation logic, field operations logic, financial calculations, and AI recommendation assembly.
- `static/js/` owns frontend view controllers.
- `templates/index.html` serves the SPA shell.

## Project Structure

```text
Smart-Meter-Journey/
|-- app.py                         # Flask app and API routes
|-- requirements.txt               # Python runtime dependencies
|-- Dockerfile                     # Production container image
|-- docker-compose.yml             # Local web + PostgreSQL stack
|-- render.yaml                    # Render web service blueprint
|-- LICENSE
|-- .env.example                   # Local configuration template
|
|-- .github/workflows/
|   |-- test.yml                   # CI smoke tests
|   `-- codeql.yml                 # CodeQL security scanning
|
|-- api/
|   `-- __init__.py
|
|-- engine/
|   |-- ingestion.py               # CSV loading, streaming, cache control, helpers
|   |-- data_generator.py          # Connected synthetic dataset generator
|   |-- forecasting_engine.py      # Channel forecasting and funnel analytics
|   |-- cancellation_engine.py     # Fallout, risk, trends, and rebooking analytics
|   |-- field_ops_engine.py        # Engineer planning and capacity optimisation
|   |-- financial_engine.py        # Financial KPIs and scenario modelling
|   |-- ai_recommendations.py      # Cross-module operational recommendations
|   `-- __init__.py
|
|-- data/
|   `-- inputs/
|       |-- master_operations.csv
|       |-- suppliers.csv
|       |-- channel_volume.csv
|       |-- booking_journey.csv
|       |-- engineers.csv
|       |-- engineer_availability.csv
|       |-- financial_data.csv
|       |-- capacity_demand.csv
|       |-- forecast_baseline_2025.csv
|       `-- manifest.json
|
|-- deployment/
|   `-- schema.sql                 # PostgreSQL schema
|
|-- static/
|   |-- css/style.css
|   `-- js/
|       |-- app.js
|       |-- config.js
|       |-- theme.js
|       |-- dashboard.js
|       |-- forecasting.js
|       |-- cancellations.js
|       |-- field_ops.js
|       `-- financial.js
|
|-- templates/
|   `-- index.html
|
`-- tests/
    `-- test_app_smoke.py
```

## Quick Start

### Prerequisites

- Python 3.11 or newer recommended.
- `pip`.
- Git.

### Local Setup

```bash
git clone <repo-url>
cd Smart-Meter-Journey

python -m venv .venv
.venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

copy .env.example .env
python app.py
```

Open the app at:

```text
http://localhost:5000
```

On macOS or Linux, activate the virtual environment with:

```bash
source .venv/bin/activate
```

and copy the environment template with:

```bash
cp .env.example .env
```

## Configuration

Create a local `.env` file from `.env.example`.

| Variable | Default / Example | Purpose |
| --- | --- | --- |
| `FLASK_ENV` | `development` | Enables Flask development behavior when running locally. |
| `SECRET_KEY` | `change-me...` | Flask secret key. Use a long random value in production. |
| `PORT` | `5000` | Port used by `python app.py`. |
| `DATABASE_URL` | blank | Optional PostgreSQL connection string. The current app primarily uses CSV storage. |
| `ENABLE_DATABASE` | `false` | Feature flag for database-backed extensions. |
| `ENABLE_AI_RECOMMENDATIONS` | `false` | Enables the recommendation endpoints when configured. |
| `OPENAI_API_KEY` | blank | Optional key for the existing recommendation feature if implemented/configured. |
| `HF_TOKEN` | blank | Hugging Face or provider token for the chatbot proxy. |
| `HF_CHAT_PROVIDER` | `novita` | Hugging Face Inference Provider name. |
| `HF_CHAT_MODEL` | `google/gemma-4-31B-it` | Chat model used by the chatbot. |
| `HF_CHAT_BASE_URL` | `https://router.huggingface.co/v1` | OpenAI-compatible Hugging Face router base URL. |
| `HF_CHAT_ENDPOINT` | blank | Optional direct OpenAI-compatible endpoint override. |
| `HF_CHAT_TIMEOUT_SECONDS` | `45` | Chatbot request timeout. |
| `HF_CHAT_MAX_TOKENS` | `450` | Chatbot response token budget. |
| `HF_CHAT_TEMPERATURE` | `0.35` | Chatbot sampling temperature. |
| `SMJ_AUTO_GENERATE_DATA` | unset / `false` | Allows automatic dataset generation when required files are missing. |
| `SMJ_ENABLE_DATA_GENERATE` | unset / `false` | Allows `/api/data/generate` on Render for a one-off maintenance run. |
| `SMJ_CACHE_LARGE_DATASETS` | `false` on Render | Caches large CSV datasets in memory when set to `true`. |

Keep `.env` out of Git. The repository includes `.env.example` for safe defaults.

## Running the App

### Development Server

```bash
python app.py
```

The Flask app prints the local URL and serves both the SPA and API routes.

### Production-style Server

```bash
gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 2 --timeout 120 app:app
```

The repository intentionally uses a small worker count in production examples because the data layer is file-based and Render's lower-memory instances benefit from conservative memory use.

## Testing

Run the smoke test suite:

```bash
python -m unittest discover -s tests -v
```

The tests verify:

- The dashboard page renders.
- `/api/health` reports required datasets as available.
- `/api/regions` returns expected region codes.
- Core module API endpoints return JSON.
- AI recommendations can be disabled cleanly for CI.

The GitHub Actions workflow runs the same smoke tests on Python 3.13.

## Data Model

The connected synthetic dataset is generated around one source-of-truth ledger:

```text
data/inputs/master_operations.csv
```

Dashboard-facing datasets are derived from that ledger:

| File | Purpose |
| --- | --- |
| `master_operations.csv` | Job-level operational ledger with dates, regions, channels, statuses, engineers, suppliers, and financial fields. |
| `suppliers.csv` | Supplier reference data used during generation and reporting. |
| `channel_volume.csv` | Daily contact-centre channel volumes and booking conversion data. |
| `booking_journey.csv` | Weekly appointment funnel aggregation. |
| `engineers.csv` | Engineer dimension data by region, patch, and employment type. |
| `engineer_availability.csv` | Engineer-day capacity, availability, absence, and completed job data. |
| `financial_data.csv` | Monthly revenue, cost, margin, and profitability data. |
| `capacity_demand.csv` | Weekly regional and patch demand joined to capacity. |
| `forecast_baseline_2025.csv` | Baseline forecasting input for planning views. |
| `manifest.json` | Dataset generation metadata. |

To regenerate data locally:

```bash
python engine/data_generator.py
```

You can also trigger regeneration through the API in development:

```text
GET /api/data/generate
```

On Render, this route is disabled unless `SMJ_ENABLE_DATA_GENERATE=true` is explicitly set.

## API Reference

Most read endpoints support:

- `region`: optional region code such as `NW`, `NE`, `MID`, `SE`, `SW`, `WAL`, `SCO`, or `YRK`.
- `year`: supported years are `2025` and `2026`. Unsupported values fall back to `2025`.

### Frontend

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/` | Serves the single-page dashboard. |

### Journey

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/journey/kpis` | Executive funnel KPIs from requests through completions. |
| `GET` | `/api/journey/weekly-trend` | Weekly appointment journey trend. |
| `GET` | `/api/journey/suppliers` | Supplier-level journey performance. |
| `GET` | `/api/journey/regional-heatmap` | Regional journey and completion-rate comparison. |
| `GET` | `/api/journey/interactions` | Contact and interaction analytics. |

### Forecasting

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/forecasting/channel-kpis` | Channel volume and conversion KPIs. |
| `GET` | `/api/forecasting/forecast` | Forward-looking contact-volume forecast. |
| `GET` | `/api/forecasting/funnel` | Booking conversion funnel. |
| `GET` | `/api/forecasting/planning-target-kpis` | Planning targets and operational target KPIs. |

### Cancellations

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/cancellations/kpis` | Cancellation and abort KPIs. |
| `GET` | `/api/cancellations/root-causes` | Root-cause and Pareto-style fallout analysis. |
| `GET` | `/api/cancellations/trends` | Cancellation and abort trend data. |
| `GET` | `/api/cancellations/heatmap` | Regional cancellation heatmap. |
| `GET` | `/api/cancellations/predict` | Cancellation-risk prediction payload. |
| `GET` | `/api/cancellations/rebooking` | Rebooking analytics. |

### Field Operations

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/field-ops/kpis` | Engineer utilisation and field operations KPIs. |
| `GET` | `/api/field-ops/capacity-matrix` | Region-level capacity vs demand matrix. |
| `GET` | `/api/field-ops/patch-plan` | Patch-level weekly plan. Supports `region`, `week`, and `year`. |
| `GET` | `/api/field-ops/engineer-performance` | Engineer performance ranking. Supports `top_n`. |
| `GET` | `/api/field-ops/capacity-forecast` | 2026 capacity forecast. Supports `target`, `jobs_per_fte_day`, and `absence_rate`. |
| `GET` | `/api/field-ops/optimise` | Workforce allocation recommendations. Supports `target`, `jobs_per_fte_day`, and `absence_rate`. |

### Financial

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/financial/kpis` | Revenue, cost, margin, and profitability KPIs. |
| `POST` | `/api/financial/scenario` | Runs a named financial scenario from JSON inputs. |
| `POST` | `/api/financial/compare-scenarios` | Compares multiple scenario payloads. |
| `GET` | `/api/financial/forecast-profitability` | Forecast profitability output. |

Example financial scenario request:

```bash
curl -X POST http://localhost:5000/api/financial/scenario ^
  -H "Content-Type: application/json" ^
  -d "{\"scenario_name\":\"Higher completion rate\",\"job_volume\":50000,\"completion_rate_pct\":74,\"cancel_rate_pct\":12,\"abort_rate_pct\":6,\"revenue_uplift_pct\":3,\"cost_uplift_pct\":1,\"engineer_count\":320,\"productivity_jobs_per_day\":4.2,\"region_code\":\"NW\"}"
```

### AI and Chatbot

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/ai/recommendations` | Cross-module recommendations. Returns a disabled payload when `ENABLE_AI_RECOMMENDATIONS=false`. |
| `GET` | `/api/ai/summary` | Natural-language operations summary. |
| `GET` | `/api/ai/dashboard` | Combined recommendation and summary payload. |
| `POST` | `/api/chatbot/message` | Sends chat messages to the server-side Hugging Face proxy. |
| `GET` | `/api/chatbot/config` | Returns non-secret chatbot configuration diagnostics. |

Example chatbot request:

```bash
curl -X POST http://localhost:5000/api/chatbot/message ^
  -H "Content-Type: application/json" ^
  -d "{\"year\":2025,\"region\":\"NW\",\"view\":\"dashboard\",\"messages\":[{\"role\":\"user\",\"content\":\"What should I focus on today?\"}]}"
```

### System

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health check with dataset existence, row count, and timestamp. |
| `GET` | `/api/data/reload` | Clears in-memory data and forecast caches. |
| `GET` | `/api/data/generate` | Regenerates synthetic datasets when enabled. |
| `GET` | `/api/regions` | Returns supported region reference data. |

## AI and Chatbot Features

The app has two separate AI-related surfaces:

1. Recommendation endpoints under `/api/ai/*`.
2. Floating chatbot endpoint under `/api/chatbot/message`.

For CI and low-cost deployments, recommendations are disabled by default:

```env
ENABLE_AI_RECOMMENDATIONS=false
```

To enable the chatbot, set a Hugging Face token and provider settings:

```env
HF_TOKEN=your_token_here
HF_CHAT_PROVIDER=novita
HF_CHAT_MODEL=google/gemma-4-31B-it
HF_CHAT_BASE_URL=https://router.huggingface.co/v1
```

The chatbot token is never exposed to the browser. The frontend calls Flask, and Flask calls the OpenAI-compatible Hugging Face endpoint server-side.

Use `/api/chatbot/config` to confirm whether the server can see a token and which non-secret model/provider settings are active.

## Docker

Build and run only the web container:

```bash
docker build -t smart-meter-journey .
docker run --rm -p 5000:5000 --env-file .env smart-meter-journey
```

Run the full Docker Compose stack:

```bash
docker compose up --build
```

Services:

| Service | URL / Port | Description |
| --- | --- | --- |
| `web` | `http://localhost:5000` | Flask/Gunicorn app. |
| `db` | `localhost:5432` | PostgreSQL 16 with `deployment/schema.sql` mounted at init. |

The current app can run without PostgreSQL because CSV storage is the primary runtime data source.

## Render Deployment

The repository includes `render.yaml` for a Render web service.

Render settings:

| Setting | Value |
| --- | --- |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 120 --max-requests 150 --max-requests-jitter 30 app:app` |
| Health check | `/api/health` |
| Auto deploy | enabled |

Important Render environment behavior:

- `SECRET_KEY` is generated by Render.
- `HF_TOKEN` is marked `sync: false` and must be added as a secret in Render.
- `ENABLE_AI_RECOMMENDATIONS=false` by default.
- `SMJ_AUTO_GENERATE_DATA=false` by default.
- `SMJ_CACHE_LARGE_DATASETS=false` by default to reduce memory pressure.
- Dataset generation is disabled on Render unless `SMJ_ENABLE_DATA_GENERATE=true` is set for a one-off maintenance run.

## Development Notes

- The app supports 2025 and 2026 as dashboard years. Invalid `year` values fall back to 2025.
- API responses under `/api/*` include no-cache headers.
- Large datasets are streamed instead of cached unless `SMJ_CACHE_LARGE_DATASETS=true`.
- Data is loaded lazily so startup stays light on constrained hosts.
- The smoke tests set `ENABLE_AI_RECOMMENDATIONS=false` and `SMJ_AUTO_GENERATE_DATA=false` to keep CI deterministic.
- The repository includes GitHub Actions test coverage and CodeQL scanning.

## Troubleshooting

### `/api/health` returns `degraded`

One or more required CSV files are missing from `data/inputs`.

Fix locally with:

```bash
python engine/data_generator.py
```

Then reload the app or call:

```text
GET /api/data/reload
```

### Chatbot returns a configuration error

Check:

- `HF_TOKEN` is set on the Flask server.
- `HF_CHAT_PROVIDER` matches the token/provider.
- `HF_CHAT_MODEL` is available through that provider.
- The Flask process was restarted after editing `.env`.

Use:

```text
GET /api/chatbot/config
```

to inspect non-secret active settings.

### Render runs out of memory

Keep these settings:

```env
SMJ_CACHE_LARGE_DATASETS=false
SMJ_AUTO_GENERATE_DATA=false
MALLOC_ARENA_MAX=2
```

Use one Gunicorn worker with a small thread count, as shown in `render.yaml`.

### Tests fail because data is missing

Regenerate the local datasets:

```bash
python engine/data_generator.py
python -m unittest discover -s tests -v
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
