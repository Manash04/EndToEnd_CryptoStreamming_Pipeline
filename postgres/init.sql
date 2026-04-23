-- ─────────────────────────────────────────────────────────────
-- init.sql — runs automatically when Postgres container starts
-- ─────────────────────────────────────────────────────────────

-- Pipeline health metrics (written by metrics_collector.py every 60s)
CREATE TABLE IF NOT EXISTS pipeline_metrics (
    id                SERIAL PRIMARY KEY,
    recorded_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    topic             VARCHAR(50),
    consumer_lag      BIGINT       DEFAULT 0,
    records_per_batch INTEGER      DEFAULT 0,
    processing_ms     INTEGER      DEFAULT 0,
    query_name        VARCHAR(100),
    batch_id          INTEGER      DEFAULT 0,
    is_active         BOOLEAN      DEFAULT TRUE
);

CREATE INDEX idx_metrics_recorded_at ON pipeline_metrics(recorded_at DESC);
CREATE INDEX idx_metrics_topic       ON pipeline_metrics(topic);

-- Daily analytics (written by Airflow DAG at 3PM)
CREATE TABLE IF NOT EXISTS daily_analytics (
    id                SERIAL PRIMARY KEY,
    trade_date        DATE         NOT NULL,
    symbol            VARCHAR(20)  NOT NULL,
    daily_vwap        NUMERIC(20,8),
    total_volume      NUMERIC(20,8),
    total_trades      INTEGER,
    total_value_usdt  NUMERIC(20,2),
    price_open        NUMERIC(20,8),
    price_close       NUMERIC(20,8),
    price_high        NUMERIC(20,8),
    price_low         NUMERIC(20,8),
    peak_buy_hour     INTEGER,
    peak_sell_hour    INTEGER,
    avg_imbalance     NUMERIC(6,4),
    strongest_signal  VARCHAR(20),
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE(trade_date, symbol)
);

CREATE INDEX idx_daily_date   ON daily_analytics(trade_date DESC);
CREATE INDEX idx_daily_symbol ON daily_analytics(symbol);

-- Hourly breakdown (used by FastAPI for charts)
CREATE TABLE IF NOT EXISTS hourly_analytics (
    id               SERIAL PRIMARY KEY,
    trade_date       DATE         NOT NULL,
    symbol           VARCHAR(20)  NOT NULL,
    hour             INTEGER      NOT NULL,
    vwap             NUMERIC(20,8),
    volume           NUMERIC(20,8),
    trade_count      INTEGER,
    imbalance_ratio  NUMERIC(6,4),
    pressure         VARCHAR(20),
    UNIQUE(trade_date, symbol, hour)
);

CREATE INDEX idx_hourly_date_symbol ON hourly_analytics(trade_date, symbol);