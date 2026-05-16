# CryptoStream — End-to-End Real-Time Crypto Streaming Pipeline

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Apache Spark](https://img.shields.io/badge/Apache%20Spark-3.5.0-orange.svg)](https://spark.apache.org)
[![Apache Kafka](https://img.shields.io/badge/Apache%20Kafka-7.5.0-black.svg)](https://kafka.apache.org)
[![Delta Lake](https://img.shields.io/badge/Delta%20Lake-3.2.0-blue.svg)](https://delta.io)
[![Apache Airflow](https://img.shields.io/badge/Apache%20Airflow-2.8.0-red.svg)](https://airflow.apache.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org)
[![Azure](https://img.shields.io/badge/Azure-Data%20Lake%20Gen2-blue.svg)](https://azure.microsoft.com)

A production-grade, end-to-end streaming data pipeline that ingests every individual crypto trade from Binance in real time, processes it through Apache Kafka and Spark Structured Streaming, stores it in Azure Data Lake Gen2 using Delta Lake format, runs daily batch analytics via Apache Airflow, and serves results through a FastAPI backend to a live Next.js dashboard.

**Live Demo:** [https://end-to-end-crypto-streaming-pipeli.vercel.app](https://end-to-end-crypto-streaming-pipeli.vercel.app)  
**API Docs:** [http://20.205.25.148:8000/docs](http://20.205.25.148:8000/docs)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Infrastructure — Azure VM + Docker](#infrastructure--azure-vm--docker)
3. [Data Ingestion — Binance WebSocket](#data-ingestion--binance-websocket)
4. [Message Queue — Apache Kafka](#message-queue--apache-kafka)
5. [Stream Processing — Apache Spark](#stream-processing--apache-spark)
6. [Storage — Azure Data Lake Gen2 + Delta Lake](#storage--azure-data-lake-gen2--delta-lake)
7. [Batch Orchestration — Apache Airflow](#batch-orchestration--apache-airflow)
8. [PostgreSQL Schema](#postgresql-schema)
9. [Pipeline Monitoring — Metrics Collector + Grafana](#pipeline-monitoring--metrics-collector--grafana)
10. [REST API — FastAPI](#rest-api--fastapi)
11. [Frontend — Next.js Website](#frontend--nextjs-website)
12. [Project Setup](#project-setup)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AZURE VIRTUAL MACHINE                               │
│                    (Standard D4s v3 — 4 vCPU, 16GB RAM)                   │
│                         IP: 20.205.25.148                                  │
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌─────────────────────────────┐  │
│  │   Binance    │    │    Python    │    │      Apache Kafka            │  │
│  │  WebSocket   │───▶│   Producer  │───▶│  4 Topics × 3 Partitions    │  │
│  │  (4 symbols) │    │  producer.py │    │  24hr retention             │  │
│  └──────────────┘    └──────────────┘    └──────────┬──────────────────┘  │
│                                                       │                     │
│                                          ┌────────────▼──────────────────┐ │
│                                          │   Spark Structured Streaming  │ │
│                                          │   spark_streaming_job.py      │ │
│                                          │   3 Parallel Sinks            │ │
│                                          └────┬──────────┬──────┬───────┘ │
│                                               │          │      │          │
│                              ┌────────────────▼─┐  ┌─────▼──┐ ┌▼───────┐ │
│                              │   raw/trades/    │  │analytics│ │analyt- │ │
│                              │   Delta Lake     │  │/vwap/   │ │ics/    │ │
│                              │   ADLS Gen2      │  │         │ │imbal-  │ │
│                              └────────┬─────────┘  └─────────┘ │ance/   │ │
│                                       │                         └────────┘ │
│                              ┌────────▼─────────┐                          │
│                              │  Apache Airflow  │                          │
│                              │  Daily at 6 UTC  │                          │
│                              │  3-task DAG      │                          │
│                              └────────┬─────────┘                          │
│                                       │                                     │
│                              ┌────────▼─────────┐    ┌──────────────────┐ │
│                              │   PostgreSQL     │◀───│ Metrics Collector│ │
│                              │   Port 5433      │    │ Kafka + Spark    │ │
│                              └────────┬─────────┘    └──────────────────┘ │
│                                       │                                     │
│                              ┌────────▼─────────┐    ┌──────────────────┐ │
│                              │    FastAPI       │    │     Grafana      │ │
│                              │    Port 8000     │    │    Port 3000     │ │
│                              └────────┬─────────┘    └──────────────────┘ │
└───────────────────────────────────────┼─────────────────────────────────────┘
                                        │ HTTP
                                        ▼
                              ┌──────────────────┐
                              │   Next.js        │
                              │   Vercel         │
                              │   (Frontend)     │
                              └──────────────────┘
```

**Architecture Pattern:** Lambda Architecture — streaming layer for real-time data collection, batch layer for daily aggregations.

---

## Infrastructure — Azure VM + Docker

### Azure Virtual Machine

| Property | Value |
|---|---|
| Machine | Standard D4s v3 |
| vCPUs | 4 |
| RAM | 16 GB |
| OS | Ubuntu 24.04 LTS |
| Public IP | 20.205.25.148 |
| Region | East Asia |
| Storage | Azure Data Lake Gen2 (separate) |

### Docker Services

All pipeline services run in Docker containers orchestrated with Docker Compose. A single `docker compose up -d` starts the entire stack.

```
docker-compose.yml
├── zookeeper          (confluentinc/cp-zookeeper:7.5.0)  — Kafka coordination
├── kafka              (confluentinc/cp-kafka:7.5.0)       — Message broker, port 9092
├── kafka-ui           (provectuslabs/kafka-ui)             — Kafka monitoring, port 8080
├── kafka-init         (confluentinc/cp-kafka:7.5.0)       — Creates 4 topics on startup
├── spark-master       (apache/spark:3.5.0)                 — Spark master, ports 7077/8081
├── spark-worker       (apache/spark:3.5.0)                 — Spark worker, 2 cores/2GB
├── postgres           (postgres:15)                        — Analytics DB, port 5433
├── grafana            (grafana/grafana:10.2.0)             — Monitoring, port 3000
└── airflow            (custom Dockerfile)                  — Orchestration, port 8090
```

**Key Docker Design Decisions:**

**Named Volumes** — Persist data across container restarts:
```yaml
volumes:
  postgres-data:    # PostgreSQL data survives restarts
  grafana-data:     # Grafana dashboards persist
  airflow-logs:     # Airflow task logs
  spark-logs:       # Spark application logs
  spark-ivy-cache:  # Cached JARs — no re-download on restart
```

**Custom Airflow Dockerfile** — Installs Java 17 and copies Spark binaries:
```dockerfile
FROM apache/airflow:2.8.0
RUN apt-get install -y openjdk-17-jdk-headless
COPY --from=apache/spark:3.5.0 /opt/spark /opt/spark
```
Uses `COPY --from` multi-stage build to pull Spark from the official image without downloading — instant build since `apache/spark:3.5.0` is already pulled.

**Internal Networking** — All containers communicate via `project_default` Docker network using container names:
```
kafka → connects to → zookeeper:2181
spark → connects to → kafka:29092 (internal listener)
airflow → connects to → postgres:5432 (internal port)
```

**Port Conflict Resolution** — Windows has native PostgreSQL on port 5432:
```yaml
postgres:
  ports:
    - "5433:5432"  # External 5433, internal 5432
```

**Services Running on VM Host (outside Docker):**

These run directly on the VM using a Python virtual environment:
```bash
# Producer — connects to Kafka at localhost:9092
nohup python producer.py > logs/producer.log 2>&1 &

# FastAPI — serves on 0.0.0.0:8000 (publicly accessible)
nohup python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 > logs/api.log 2>&1 &

# Metrics collector — polls Kafka and Spark REST API
nohup python metrics/metrics_collector.py > logs/metrics.log 2>&1 &
```

**Why not containerize these?**
- Producer needs `localhost:9092` — simplest on host
- FastAPI needs `localhost:5433` for Postgres — cleaner on host
- Containers communicate differently from host processes

---

## Data Ingestion — Binance WebSocket

### Connection

```python
# Single combined stream — 4 symbols simultaneously
wss://stream.binance.com:9443/stream?streams=
  btcusdt@trade/
  ethusdt@trade/
  solusdt@trade/
  bnbusdt@trade
```

### Raw Binance Message Format

Every individual trade on Binance triggers one message:

```json
{
  "stream": "btcusdt@trade",
  "data": {
    "e": "trade",          // event type
    "E": 1714024800123,    // event timestamp (ms)
    "s": "BTCUSDT",        // trading pair
    "t": 3456789012,       // unique trade ID
    "p": "94521.43",       // execution price (string)
    "q": "0.00412",        // quantity in base currency (string)
    "T": 1714024800120,    // trade execution time (ms)
    "m": false             // is_buyer_market_maker
                           // false = buyer initiated = BUY trade
                           // true  = seller initiated = SELL trade
  }
}
```

### Normalized Message (after producer processing)

The producer normalizes terse field names and computes one derived field:

```json
{
  "event_type":            "trade",
  "event_time_ms":         1714024800123,
  "symbol":                "BTCUSDT",
  "trade_id":              3456789012,
  "price":                 94521.43,
  "quantity":              0.00412,
  "trade_value_usdt":      389.43,        // DERIVED: price × quantity
  "trade_time_ms":         1714024800120,
  "is_buyer_market_maker": false,
  "ingested_at":           "2026-05-16T09:00:00.123"
}
```

### Serialization

Messages are JSON-serialized with UTF-8 encoding before publishing to Kafka. Each message is keyed by symbol to ensure ordering — all BTCUSDT trades go to the same partition.

### Volume

- BTC/ETH: 5-15 messages/second during trading hours
- SOL/BNB: 2-8 messages/second
- Total: ~20-60 messages/second across all 4 symbols
- Daily: ~1.5-5 million messages per symbol

---

## Message Queue — Apache Kafka

### Topic Configuration

```
btcusdt-trades  │ 3 partitions │ replication factor 1 │ 24hr retention
ethusdt-trades  │ 3 partitions │ replication factor 1 │ 24hr retention
solusdt-trades  │ 3 partitions │ replication factor 1 │ 24hr retention
bnbusdt-trades  │ 3 partitions │ replication factor 1 │ 24hr retention
```

### Listener Configuration

Kafka has two listeners for different network contexts:
```
PLAINTEXT_INTERNAL → kafka:29092    # Docker internal network
PLAINTEXT_EXTERNAL → localhost:9092 # Host machine access
```

### Consumer Lag

```
consumer_lag = latest_offset - committed_offset
```

- `latest_offset` — highest message ID currently in the topic
- `committed_offset` — last message ID Spark successfully processed
- `lag = 0` — Spark is keeping up in real time
- `lag growing` — Spark is falling behind (resource pressure or ADLS write latency)
- `lag spike then drop` — Spark restarted and caught up on backlog

---

## Stream Processing — Apache Spark

### Configuration

```
Mode:           Spark Structured Streaming
Execution:      local[*] inside spark-master container
Trigger:        processingTime = "2 minutes" (micro-batch)
Kafka offset:   auto.offset.reset = earliest
Max offsets:    10,000 per trigger (prevents backlog overload)
```

### Schema After Reading from Kafka

```python
trades_df schema:
  event_type            string
  event_time_ms         long
  symbol                string
  trade_id              long
  price                 double
  quantity              double
  trade_value_usdt      double
  trade_time_ms         long
  is_buyer_market_maker boolean
  ingested_at           string
  trade_time            timestamp   # derived: trade_time_ms / 1000
  side                  string      # derived: "BUY" or "SELL"
  date_partition        string      # derived: yyyy-MM-dd from trade_time
```

### Three Parallel Sinks

The streaming job writes to three destinations simultaneously:

---

#### Sink 1 — Raw Trades

**Purpose:** Store every individual trade tick as ground truth for batch reprocessing.

**Write mode:** Append  
**Trigger:** Every 2 minutes  
**Format:** Delta Lake  
**Partitioning:** `symbol`, `date_partition`

**Path:**
```
abfss://crypto-lake-new@cryptopipelineadlsnew.dfs.core.windows.net/raw/trades/
  symbol=BTCUSDT/
    date_partition=2026-05-16/
      part-00000-xxxx.snappy.parquet
      _delta_log/
```

**Schema stored:**
```
symbol, price, quantity, trade_value_usdt, trade_time,
trade_id, side, is_buyer_market_maker, ingested_at, date_partition
```

---

#### Sink 2 — VWAP Analytics

**Purpose:** Compute Volume Weighted Average Price per 1-minute window per symbol.

**Window type:** Tumbling window (non-overlapping)  
**Window size:** 1 minute  
**Watermark:** 10 seconds (handles late-arriving data)  
**Write mode:** Append  
**Format:** Delta Lake

**VWAP Formula:**

```
VWAP = Σ(price_i × quantity_i) / Σ(quantity_i)
```

Where the sum is over all trades within the 1-minute window for that symbol.

**Why VWAP over simple average?**
A trade of 10 BTC at $94,000 should have more weight than a trade of 0.001 BTC at $94,100. VWAP weights each price by the volume traded at that level, giving a more accurate representation of the true average execution price.

**Schema stored per row:**
```
symbol          = "BTCUSDT"
window_start    = 2026-05-16 09:00:00
window_end      = 2026-05-16 09:01:00
vwap            = 94521.43          ← Σ(p×q) / Σq
total_volume    = 2.34812           ← Σ(quantity) in BTC
trade_count     = 47                ← number of individual trades
total_value_usdt = 221,847.21      ← Σ(price × quantity)
price_low       = 94501.00         ← MIN(price) in window
price_high      = 94548.50         ← MAX(price) in window
date_partition  = "2026-05-16"
```

**Path:**
```
abfss://crypto-lake-new@.../analytics/vwap/
  symbol=BTCUSDT/
    date_partition=2026-05-16/
```

---

#### Sink 3 — Buy/Sell Imbalance

**Purpose:** Measure market pressure by comparing buy vs sell volume per 1-minute window.

**Window type:** Tumbling window, 1 minute  
**Watermark:** 10 seconds

**Imbalance Ratio Formula:**

```
buy_volume  = Σ(quantity) where side = "BUY"
sell_volume = Σ(quantity) where side = "SELL"

imbalance_ratio = buy_volume / (buy_volume + sell_volume)
```

**Signal Classification:**
```
imbalance_ratio > 0.6  → "BUY_PRESSURE"   buyers dominating
imbalance_ratio < 0.4  → "SELL_PRESSURE"  sellers dominating
0.4 ≤ ratio ≤ 0.6     → "NEUTRAL"        balanced market
```

**Economic Interpretation:**
- High buy imbalance suggests aggressive buying — potential upward price pressure
- High sell imbalance suggests aggressive selling — potential downward pressure
- This is a leading indicator used in market microstructure analysis

**Schema stored per row:**
```
symbol          = "BTCUSDT"
window_start    = 2026-05-16 09:00:00
window_end      = 2026-05-16 09:01:00
buy_volume      = 1.24190           ← BTC bought
sell_volume     = 1.10622           ← BTC sold
buy_count       = 25                ← number of BUY trades
sell_count      = 22                ← number of SELL trades
imbalance_ratio = 0.5290            ← 1.24190 / (1.24190 + 1.10622)
pressure        = "NEUTRAL"
date_partition  = "2026-05-16"
```

**Path:**
```
abfss://crypto-lake-new@.../analytics/imbalance/
  symbol=BTCUSDT/
    date_partition=2026-05-16/
```

---

## Storage — Azure Data Lake Gen2 + Delta Lake

### Container Structure

```
crypto-lake-new/
├── raw/
│   └── trades/
│       ├── _delta_log/           ← Delta transaction log
│       ├── _spark_metadata/      ← Spark streaming metadata
│       ├── symbol=BNBUSDT/
│       │   └── date_partition=2026-05-16/
│       │       └── part-00000-xxxx.snappy.parquet
│       ├── symbol=BTCUSDT/
│       ├── symbol=ETHUSDT/
│       └── symbol=SOLUSDT/
│
├── analytics/
│   ├── vwap/
│   │   ├── _delta_log/
│   │   └── symbol=.../date_partition=.../
│   └── imbalance/
│       ├── _delta_log/
│       └── symbol=.../date_partition=.../
│
└── checkpoints/
    ├── raw/       ← Spark checkpoint for raw trades sink
    ├── vwap/      ← Spark checkpoint for VWAP sink
    └── imbalance/ ← Spark checkpoint for imbalance sink
```

### Why Delta Lake Over Plain Parquet

| Feature | Plain Parquet | Delta Lake |
|---|---|---|
| ACID Transactions | ❌ | ✅ No partial writes |
| Schema Enforcement | ❌ | ✅ Rejects bad data |
| Time Travel | ❌ | ✅ Query historical snapshots |
| Concurrent Writes | ❌ Causes corruption | ✅ Serializable isolation |
| Streaming + Batch | Separate tables | ✅ Unified table |
| Audit Log | ❌ | ✅ Full transaction history |

**Time Travel Example:**
```python
# Query data as it existed 3 days ago
spark.read.format("delta") \
  .option("timestampAsOf", "2026-05-13") \
  .load("abfss://crypto-lake-new@.../raw/trades")
```

**ACID in Practice:**
When two Spark streaming jobs accidentally ran simultaneously, Delta Lake detected the conflict and rejected the second writer with `DELTA_CONCURRENT_TRANSACTION` — preventing data corruption. Plain Parquet would have silently overwritten data.

### Small File Problem and Solution

Each 2-minute micro-batch writes one file per partition. Over 24 hours this creates:
```
2 batches/min × 60 min × 24 hr = 2,880 files per symbol per day
```

**Solution:** `coalesce(1)` before each write sink merges all output into one file per batch. Future daily data has manageable file counts. Existing data is compacted with a one-time PySpark job.

### Checkpoints

Spark Structured Streaming writes checkpoint data to ADLS after each processed batch:
```
checkpoint contains:
  - Last committed Kafka offset per partition
  - Streaming query state (window aggregations)
```

If Spark crashes and restarts, it reads the checkpoint and resumes from exactly where it left off — guaranteeing exactly-once processing semantics.

---

## Batch Orchestration — Apache Airflow

### DAG: `crypto_daily_analysis`

```
Schedule:  0 6 * * *  (every day at 06:00 UTC = 11:30 AM IST)
Catchup:   False
Retries:   1 (with 2-minute delay)

Task Graph:
  check_adls_data → run_spark_batch → log_dag_run
```

### Task 1: check_adls_data (PythonOperator)

Validates yesterday's data exists in ADLS before running the expensive Spark job.

```python
path = f"raw/trades/symbol=BTCUSDT/date_partition={yesterday}"
paths = list(fs.get_paths(path=path, max_results=1))
if not paths:
    raise ValueError(f"No data found for {yesterday}")
```

Uses BTCUSDT as a proxy — if BTC data exists, all 4 symbols have data since they come from the same Spark streaming job. Fails fast (5 seconds) instead of wasting 30 minutes on a Spark job that would find no data.

### Task 2: run_spark_batch (BashOperator)

Runs `spark-submit` directly inside the Airflow container (Spark is installed via `COPY --from=apache/spark:3.5.0`):

```bash
/opt/spark/bin/spark-submit \
  --master local[*] \
  --packages "...kafka...hadoop-azure...postgresql...delta..." \
  --conf "spark.driver.memory=2g" \
  --conf "spark.sql.shuffle.partitions=4" \
  /opt/airflow/batch/daily_analysis.py \
  --date "$YESTERDAY"
```

**What daily_analysis.py computes (reads ONLY from `raw/trades/`):**

```python
# 1. Read raw trades for yesterday
df = spark.read.format("delta").load(path).filter(date_partition == yesterday)
df = df.limit(200000).repartition(4)  # performance optimization

# 2. Daily VWAP
daily_vwap = SUM(price × quantity) / SUM(quantity)

# 3. OHLC
price_open  = price WHERE trade_time = MIN(trade_time)  # first trade of day
price_close = price WHERE trade_time = MAX(trade_time)  # last trade of day
price_high  = MAX(price)
price_low   = MIN(price)

# 4. Volume metrics
total_volume     = SUM(quantity)        # in base currency (BTC/ETH/SOL/BNB)
total_trades     = COUNT(*)             # individual trade count
total_value_usdt = SUM(price × qty)    # total USD value traded

# 5. Peak hours
peak_buy_hour  = HOUR where SUM(buy_quantity) is maximum
peak_sell_hour = HOUR where SUM(sell_quantity) is maximum

# 6. Market signal
avg_imbalance = AVG(buy_qty / (buy_qty + sell_qty)) per hour
strongest_signal:
  > 0.6  → "BUY_PRESSURE"
  < 0.4  → "SELL_PRESSURE"
  else   → "NEUTRAL"

# 7. Hourly breakdown (24 rows per symbol per day)
hour_vwap   = SUM(price×qty) / SUM(qty) for each hour
hour_volume = SUM(quantity) for each hour
hour_imbalance_ratio = buy_volume / total_volume per hour
hour_pressure = BUY_PRESSURE / SELL_PRESSURE / NEUTRAL
```

**Why recompute from raw instead of using analytics/vwap/?**
The streaming analytics folders contain 1-minute window aggregates. Accurate `price_open` and `price_close` require the actual first and last individual trade of the day — which only exists in `raw/trades/`. You cannot reconstruct exact OHLC from windowed aggregates.

### Task 3: log_dag_run (PythonOperator)

Writes a success record to `pipeline_metrics` for audit trail and Grafana monitoring:

```python
INSERT INTO pipeline_metrics (recorded_at, topic, query_name, is_active, batch_id)
VALUES (NOW(), 'AIRFLOW', 'daily_dag_success:2026-05-15', TRUE, 0)
```

---

## PostgreSQL Schema

Three tables store all analytics data:

### Table: daily_analytics

One row per symbol per date. Written by the Airflow batch job.

```sql
CREATE TABLE daily_analytics (
    id               SERIAL PRIMARY KEY,
    trade_date       DATE NOT NULL,
    symbol           VARCHAR(20) NOT NULL,
    daily_vwap       NUMERIC(20, 8),   -- Volume Weighted Average Price
    total_volume     NUMERIC(20, 8),   -- Total base currency traded
    total_trades     INTEGER,          -- Number of individual trades
    total_value_usdt NUMERIC(20, 2),   -- Total USD value
    price_open       NUMERIC(20, 8),   -- First trade price of day
    price_close      NUMERIC(20, 8),   -- Last trade price of day
    price_high       NUMERIC(20, 8),   -- Highest trade price
    price_low        NUMERIC(20, 8),   -- Lowest trade price
    peak_buy_hour    INTEGER,          -- Hour (0-23) with highest buy volume
    peak_sell_hour   INTEGER,          -- Hour (0-23) with highest sell volume
    avg_imbalance    NUMERIC(6, 4),    -- Average buy ratio (0.0 to 1.0)
    strongest_signal VARCHAR(20),      -- BUY_PRESSURE / SELL_PRESSURE / NEUTRAL
    created_at       TIMESTAMP DEFAULT NOW()
);
```

### Table: hourly_analytics

Up to 24 rows per symbol per date. Written by the Airflow batch job.

```sql
CREATE TABLE hourly_analytics (
    id               SERIAL PRIMARY KEY,
    trade_date       DATE NOT NULL,
    symbol           VARCHAR(20) NOT NULL,
    hour             INTEGER NOT NULL,     -- 0-23 (UTC hour)
    vwap             NUMERIC(20, 8),       -- VWAP for this hour
    volume           NUMERIC(20, 8),       -- Base currency volume this hour
    trade_count      INTEGER,              -- Individual trades this hour
    imbalance_ratio  NUMERIC(6, 4),        -- Buy ratio this hour
    pressure         VARCHAR(20)           -- BUY_PRESSURE/SELL_PRESSURE/NEUTRAL
);
```

### Table: pipeline_metrics

Written by the metrics collector every 60 seconds and by Airflow on DAG success.

```sql
CREATE TABLE pipeline_metrics (
    id               SERIAL PRIMARY KEY,
    recorded_at      TIMESTAMP NOT NULL,
    topic            VARCHAR(50),          -- btcusdt-trades / AIRFLOW / ALL_TOPICS
    consumer_lag     BIGINT DEFAULT 0,     -- Kafka lag for this topic
    records_per_batch INTEGER DEFAULT 0,   -- Spark: avg records/second
    processing_ms    INTEGER DEFAULT 0,    -- Spark: avg batch processing time
    query_name       VARCHAR(100),         -- kafka_lag / streaming_statistics
    batch_id         INTEGER DEFAULT 0,    -- Spark: completed batch count
    is_active        BOOLEAN DEFAULT TRUE
);
```

---

## Pipeline Monitoring — Metrics Collector + Grafana

### Metrics Collector (metrics/metrics_collector.py)

Runs every 60 seconds on the VM host, collecting from two sources:

**Source 1 — Kafka Consumer Group Offsets:**

```python
# For each of the 4 topics:
latest_offset    = highest message ID in Kafka topic
committed_offset = last message ID Spark confirmed processing
consumer_lag     = latest_offset - committed_offset

# Writes 4 rows per collection cycle (one per topic)
```

**Source 2 — Spark REST API (port 4040):**

```python
GET http://localhost:4040/api/v1/applications
GET http://localhost:4040/api/v1/applications/{app_id}/streaming/statistics

# Collects:
avgInputRate         → records/second flowing from Kafka into Spark
avgProcessingTime    → average milliseconds to process one micro-batch
numCompletedBatches → total number of 2-minute windows processed

GET http://localhost:4040/api/v1/applications/{app_id}/streaming/batches

# Collects from latest batch:
numInputRows   → exact rows in last batch
processingTime → exact ms for last batch
```

**Collection cycle — 5 rows written every 60 seconds:**
```
4 rows → topic-level Kafka lag (btcusdt, ethusdt, solusdt, bnbusdt)
1 row  → Spark streaming statistics (ALL_TOPICS)
```

**300 rows/hour → ~7,200 rows/day → ~216,000 rows/month**

### Grafana Dashboard (port 3000)

Connects directly to PostgreSQL via built-in datasource plugin. Refreshes every 1 minute.

**Panels:**
- **Seconds Since Last Heartbeat** — `EXTRACT(EPOCH FROM (NOW() - MAX(recorded_at)))` — green if fresh, red if stale
- **Consumer Lag per Topic** — time series showing lag history, one line per symbol
- **Gauge per Topic** — current lag visualized as gauge with red/yellow/green thresholds
- **Total Metrics Collected** — `COUNT(*)` from pipeline_metrics
- **Daily VWAP Trend** — all 4 symbols on one chart from daily_analytics
- **Daily Trade Count** — bar chart from daily_analytics
- **Total Lag Across All Topics** — sum of all 4 topic lags over time

**Consumer lag interpretation in Grafana:**
- Flat line = Spark keeping up ✅
- Rising line = Spark falling behind ⚠️
- Sudden drop = Spark restarted and caught up ✅

---

## REST API — FastAPI

### Base URL
```
Production: http://20.205.25.148:8000
Local:      http://localhost:8000
Docs:       http://20.205.25.148:8000/docs
```

### Endpoints

#### GET /api/v1/symbols
Returns all symbols with available date ranges.
```json
{
  "symbols": [
    {
      "symbol": "BTCUSDT",
      "earliest_date": "2026-04-20",
      "latest_date": "2026-05-16",
      "days_available": 15
    }
  ]
}
```

#### GET /api/v1/summary/{symbol}
Returns the most recent daily summary for a symbol.
```
symbol: BTC | ETH | SOL | BNB (or full: BTCUSDT)
```
```json
{
  "trade_date": "2026-05-16",
  "symbol": "BTCUSDT",
  "daily_vwap": 94521.43,
  "total_volume": 1847.23,
  "total_trades": 234891,
  "total_value_usdt": 174623847.21,
  "price_open": 93100.00,
  "price_close": 94800.00,
  "price_high": 95200.00,
  "price_low": 92800.00,
  "peak_buy_hour": 14,
  "peak_sell_hour": 8,
  "avg_imbalance": 0.5342,
  "strongest_signal": "NEUTRAL"
}
```

#### GET /api/v1/summary/{symbol}/{trade_date}
Returns daily summary for a specific date.
```
trade_date format: YYYY-MM-DD
```

#### GET /api/v1/trend/{symbol}?days=7
Returns last N days of daily summaries for trend analysis.
```
days: 1-30 (default 7)
Returns: array of DailySummary objects ordered by date
```

#### GET /api/v1/hourly/{symbol}/{trade_date}
Returns hourly breakdown — up to 24 rows per day.
```json
[
  {
    "trade_date": "2026-05-16",
    "symbol": "BTCUSDT",
    "hour": 9,
    "vwap": 94521.43,
    "volume": 184.23,
    "trade_count": 14758,
    "imbalance_ratio": 0.7454,
    "pressure": "BUY_PRESSURE"
  }
]
```

#### GET /api/v1/compare?symbols=BTC,ETH,SOL,BNB&trade_date=2026-05-16
Side-by-side comparison of multiple symbols for a given date.

### CORS Configuration
```python
allow_origins = ["*"]  # Allows Vercel frontend to call from any domain
allow_methods = ["GET"]
allow_headers = ["*"]
```

---

## Frontend — Next.js Website

### Deployment
- **Platform:** Vercel (auto-deploys on GitHub push)
- **URL:** https://end-to-end-crypto-streaming-pipeli.vercel.app
- **Framework:** Next.js 15 with Tailwind CSS

### Data Sources

**From Binance WebSocket (browser → Binance directly):**
```javascript
wss://stream.binance.com:9443/stream?streams=
  btcusdt@miniTicker/ethusdt@miniTicker/solusdt@miniTicker/bnbusdt@miniTicker

// Provides: live price, 24hr % change — updates every ~1 second
// No backend involved — zero latency
```

**From FastAPI via Next.js rewrites:**
```javascript
// next.config.js rewrites /api/crypto/* → http://20.205.25.148:8000/api/v1/*
// All analytics data comes through this proxy
```

### Pages

**Dashboard (`/`):**
- Live price ticker with flash animation on price changes
- Stats bar: total trades, total USD value, symbols tracked, pipeline status
- Symbol cards: VWAP, OHLC, volume, trades, buy/sell imbalance bar, signal badge

**Analytics (`/analytics`):**
- Symbol selector (BTC/ETH/SOL/BNB)
- 7-day VWAP area chart with gradient fill
- Hourly trade volume bar chart (color-coded by BUY/SELL/NEUTRAL)
- Hourly buy/sell imbalance stacked bar chart
- Daily breakdown table with VWAP, OHLC, volume, trades, signal

**Compare (`/compare`):**
- Metrics comparison table with progress bars
- Performance radar chart (all 4 symbols overlaid)
- Market signals panel with imbalance visualization
- VWAP ranking

**Pipeline (`/pipeline`):**
- 6-step pipeline flow explanation
- Technology stack cards
- Kafka message schema and API response schema
- Delta Lake benefits explanation

---

## Project Setup

### Prerequisites
- Docker Desktop
- Python 3.10+
- Node.js 22+
- Azure subscription with Data Lake Gen2

### Environment Variables (.env)

```env
ADLS_ACCOUNT_NAME=your_storage_account
ADLS_ACCOUNT_KEY=your_account_key
ADLS_CONTAINER=crypto-lake-new
KAFKA_BROKERS=localhost:9092
PG_HOST=127.0.0.1
PG_PORT=5433
PG_DB=crypto_analytics
PG_USER=crypto
PG_PASS=crypto123
```

### Local Development

```bash
# 1. Clone repository
git clone https://github.com/Manash04/EndToEnd_CryptoStreamming_Pipeline.git
cd EndToEnd_CryptoStreamming_Pipeline

# 2. Start all Docker services
docker compose up -d

# 3. Install Python dependencies
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r api/requirements.txt
pip install -r metrics/requirements.txt

# 4. Start producer
python producer.py

# 5. Submit Spark streaming job
bash spark/submit.sh

# 6. Start FastAPI
python -m uvicorn api.main:app --reload --port 8000

# 7. Start metrics collector
python metrics/metrics_collector.py

# 8. Start frontend
cd frontend && npm install && npm run dev
```

### Azure VM Deployment

```bash
# SSH into VM
ssh -i key.pem azureuser@20.205.25.148

# Clone and setup
git clone https://github.com/Manash04/EndToEnd_CryptoStreamming_Pipeline.git
cd EndToEnd_CryptoStreamming_Pipeline

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Create .env with production values
nano .env

# Start all containers
docker compose up -d

# Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r api/requirements.txt -r metrics/requirements.txt

# Start services in background
mkdir -p logs
nohup python producer.py > logs/producer.log 2>&1 &
nohup python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 > logs/api.log 2>&1 &
nohup python metrics/metrics_collector.py > logs/metrics.log 2>&1 &
bash spark/submit.sh
```

### Run Batch Job Manually

```bash
export ADLS_KEY=$(grep "^ADLS_ACCOUNT_KEY" .env | cut -d'=' -f2-)

docker exec \
  -e ADLS_ACCOUNT_NAME="your_account" \
  -e ADLS_ACCOUNT_KEY="$ADLS_KEY" \
  -e ADLS_CONTAINER="crypto-lake-new" \
  -e PG_HOST="postgres" \
  -e PG_PORT="5432" \
  -e PG_DB="crypto_analytics" \
  -e PG_USER="crypto" \
  -e PG_PASS="crypto123" \
  spark-master \
  /opt/spark/bin/spark-submit \
  --master "local[*]" \
  --packages "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.hadoop:hadoop-azure:3.3.4,com.azure:azure-storage-blob:12.25.1,org.postgresql:postgresql:42.6.0,io.delta:delta-spark_2.12:3.2.0" \
  --conf "spark.driver.memory=6g" \
  --conf "spark.sql.shuffle.partitions=4" \
  --conf "spark.hadoop.fs.azure.account.key.your_account.dfs.core.windows.net=$ADLS_KEY" \
  /opt/spark-apps/daily_analysis.py \
  --date 2026-05-15
```

### Access Services

| Service | Local | VM |
|---|---|---|
| Website | http://localhost:3001 | https://vercel.app |
| FastAPI Docs | http://localhost:8000/docs | http://20.205.25.148:8000/docs |
| Grafana | http://localhost:3000 | http://20.205.25.148:3000 |
| Airflow | http://localhost:8090 | http://20.205.25.148:8090 |
| Kafka UI | http://localhost:8080 | http://20.205.25.148:8080 |
| Spark UI | http://localhost:8081 | http://20.205.25.148:8081 |

---

## Tech Stack Summary

| Layer | Technology | Version |
|---|---|---|
| Data Source | Binance WebSocket API | — |
| Message Queue | Apache Kafka | 7.5.0 (Confluent) |
| Stream Processing | Apache Spark Structured Streaming | 3.5.0 |
| Storage Format | Delta Lake | 3.2.0 |
| Cloud Storage | Azure Data Lake Gen2 | — |
| Orchestration | Apache Airflow | 2.8.0 |
| Analytics DB | PostgreSQL | 15 |
| Monitoring | Grafana | 10.2.0 |
| REST API | FastAPI + Pydantic | 0.109 |
| Frontend | Next.js + Tailwind CSS | 15 |
| Containerization | Docker + Docker Compose | — |
| Cloud VM | Azure Standard D4s v3 | Ubuntu 24.04 |
| Frontend Hosting | Vercel | — |
| Language | Python 3.10, TypeScript | — |