-- IMSERV Platform — PostgreSQL Schema
-- Extends DAA file-based architecture with persistent relational storage

-- ─── Core Reference Tables ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS regions (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(10) UNIQUE NOT NULL,
    name        VARCHAR(100) NOT NULL,
    area_mgr    VARCHAR(100),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meter_types (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(20) UNIQUE NOT NULL,
    name        VARCHAR(100) NOT NULL,
    avg_job_mins INT DEFAULT 90
);

CREATE TABLE IF NOT EXISTS job_types (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(30) UNIQUE NOT NULL,
    name            VARCHAR(100) NOT NULL,
    avg_duration_mins INT DEFAULT 60,
    revenue_gbp     NUMERIC(10,2),
    cost_gbp        NUMERIC(10,2)
);

-- ─── Smart Meter Jobs ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS smart_meter_jobs (
    id              BIGSERIAL PRIMARY KEY,
    job_ref         VARCHAR(20) UNIQUE NOT NULL,
    region_code     VARCHAR(10) REFERENCES regions(code),
    patch_code      VARCHAR(20),
    meter_type      VARCHAR(20) REFERENCES meter_types(code),
    job_type        VARCHAR(30) REFERENCES job_types(code),
    status          VARCHAR(30) NOT NULL DEFAULT 'Requested',
    requested_date  DATE,
    booked_date     DATE,
    completed_date  DATE,
    engineer_id     VARCHAR(20),
    customer_mpan   VARCHAR(30),
    cancellation_reason VARCHAR(200),
    abort_reason    VARCHAR(200),
    contacts_count  SMALLINT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_smj_region    ON smart_meter_jobs(region_code);
CREATE INDEX idx_smj_status    ON smart_meter_jobs(status);
CREATE INDEX idx_smj_booked    ON smart_meter_jobs(booked_date);
CREATE INDEX idx_smj_engineer  ON smart_meter_jobs(engineer_id);

-- ─── Contact Centre ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS channel_contacts (
    id              BIGSERIAL PRIMARY KEY,
    contact_date    DATE NOT NULL,
    region_code     VARCHAR(10) REFERENCES regions(code),
    channel         VARCHAR(30) NOT NULL,  -- Phone, Web, App, SMS, IVR, Agent Callback
    contact_reason  VARCHAR(50),
    volume          INT NOT NULL DEFAULT 0,
    bookings        INT DEFAULT 0,
    cancellations   INT DEFAULT 0,
    abandoned       INT DEFAULT 0,
    avg_handle_mins NUMERIC(5,2),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cc_date    ON channel_contacts(contact_date);
CREATE INDEX idx_cc_channel ON channel_contacts(channel);

-- ─── Engineer Workforce ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS engineers (
    id              SERIAL PRIMARY KEY,
    engineer_id     VARCHAR(20) UNIQUE NOT NULL,
    name            VARCHAR(100) NOT NULL,
    region_code     VARCHAR(10) REFERENCES regions(code),
    patch_code      VARCHAR(20),
    employment_type VARCHAR(20) DEFAULT 'Permanent',  -- Permanent, Contract, Agency
    skills          TEXT[],
    target_jobs_day SMALLINT DEFAULT 4,
    active          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS engineer_availability (
    id              BIGSERIAL PRIMARY KEY,
    engineer_id     VARCHAR(20) REFERENCES engineers(engineer_id),
    avail_date      DATE NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'Available',  -- Available, Annual Leave, Sick, Training, Unavailable
    jobs_completed  SMALLINT DEFAULT 0,
    jobs_target     SMALLINT DEFAULT 4,
    utilisation_pct NUMERIC(5,2),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(engineer_id, avail_date)
);

CREATE INDEX idx_ea_date      ON engineer_availability(avail_date);
CREATE INDEX idx_ea_engineer  ON engineer_availability(engineer_id);

-- ─── Forecasting Storage ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS forecasts (
    id              BIGSERIAL PRIMARY KEY,
    forecast_type   VARCHAR(30) NOT NULL,  -- contact_volume, job_demand, completion_rate
    model_name      VARCHAR(50) NOT NULL,  -- prophet, arima, xgboost, ensemble
    region_code     VARCHAR(10),
    channel         VARCHAR(30),
    forecast_date   DATE NOT NULL,
    p10             NUMERIC(12,2),
    p50             NUMERIC(12,2),
    p90             NUMERIC(12,2),
    actuals         NUMERIC(12,2),
    mae             NUMERIC(10,4),
    rmse            NUMERIC(10,4),
    generated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_fcst_type ON forecasts(forecast_type);
CREATE INDEX idx_fcst_date ON forecasts(forecast_date);

-- ─── Financial Scenarios ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS financial_scenarios (
    id              BIGSERIAL PRIMARY KEY,
    scenario_name   VARCHAR(100) NOT NULL,
    created_by      VARCHAR(50),
    period_start    DATE,
    period_end      DATE,
    job_volume      INT,
    revenue_gbp     NUMERIC(12,2),
    cost_gbp        NUMERIC(12,2),
    margin_gbp      NUMERIC(12,2),
    margin_pct      NUMERIC(6,2),
    cost_per_job    NUMERIC(8,2),
    assumptions     JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── AI Recommendations ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai_recommendations (
    id              BIGSERIAL PRIMARY KEY,
    rec_type        VARCHAR(50),  -- understaffing, cancellation_risk, capacity_alert
    priority        VARCHAR(10) DEFAULT 'Medium',  -- Critical, High, Medium, Low
    region_code     VARCHAR(10),
    title           VARCHAR(200) NOT NULL,
    body            TEXT,
    metric_value    NUMERIC(12,2),
    metric_label    VARCHAR(50),
    action_required BOOLEAN DEFAULT FALSE,
    acknowledged    BOOLEAN DEFAULT FALSE,
    generated_at    TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ
);

-- ─── Audit Trail ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    entity_type     VARCHAR(50),
    entity_id       VARCHAR(50),
    action          VARCHAR(30),  -- CREATE, UPDATE, DELETE, VIEW
    changed_by      VARCHAR(50),
    changed_at      TIMESTAMPTZ DEFAULT NOW(),
    old_values      JSONB,
    new_values      JSONB
);

-- ─── Reference Data Seed ──────────────────────────────────────────────────────

INSERT INTO regions (code, name) VALUES
    ('NW',  'North West'),
    ('NE',  'North East'),
    ('MID', 'Midlands'),
    ('SE',  'South East'),
    ('SW',  'South West'),
    ('WAL', 'Wales'),
    ('SCO', 'Scotland'),
    ('YRK', 'Yorkshire')
ON CONFLICT DO NOTHING;

INSERT INTO meter_types (code, name, avg_job_mins) VALUES
    ('SMETS1',     'SMETS1 Electric',  75),
    ('SMETS2',     'SMETS2 Electric',  90),
    ('SMETS2_GAS', 'SMETS2 Gas',       85),
    ('IHD',        'In-Home Display',  45)
ON CONFLICT DO NOTHING;

INSERT INTO job_types (code, name, avg_duration_mins, revenue_gbp, cost_gbp) VALUES
    ('NEW_INSTALL',  'New Installation',  95, 185.00, 95.00),
    ('EXCHANGE',     'Meter Exchange',    80, 165.00, 82.00),
    ('REPAIR',       'Repair & Inspect',  60, 120.00, 65.00),
    ('REMOVAL',      'Meter Removal',     45,  90.00, 48.00),
    ('ABORT',        'Aborted Visit',     30,   0.00, 38.00)
ON CONFLICT DO NOTHING;
