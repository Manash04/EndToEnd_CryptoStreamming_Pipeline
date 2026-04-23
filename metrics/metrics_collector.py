
import os
import time
import logging
from datetime import datetime

import requests
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from kafka import KafkaAdminClient
from kafka.errors import KafkaError

from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)
print(f"DEBUG PG_HOST={os.getenv('PG_HOST')} PG_USER={os.getenv('PG_USER')} PG_PASS={os.getenv('PG_PASS')}")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
SPARK_UI_URL      = os.getenv("SPARK_UI_URL", "http://localhost:4040")
KAFKA_BROKERS     = os.getenv("KAFKA_BROKERS", "localhost:9092")
POLL_INTERVAL_SEC = int(os.getenv("METRICS_POLL_INTERVAL", "60"))

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DB   = os.getenv("PG_DB",   "crypto_analytics")
PG_USER = os.getenv("PG_USER", "crypto")
PG_PASS = os.getenv("PG_PASS", "crypto123")

TOPICS = [
    "btcusdt-trades",
    "ethusdt-trades",
    "solusdt-trades",
    "bnbusdt-trades",
]

CONSUMER_GROUP = "spark-streaming-consumer"


# ─────────────────────────────────────────────────────────────
# POSTGRES
# ─────────────────────────────────────────────────────────────
def get_pg_conn():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        dbname=PG_DB, user=PG_USER, password=PG_PASS
    )


def write_metrics(rows: list[dict]):
    """Bulk insert metric rows into pipeline_metrics."""
    if not rows:
        return
    sql = """
        INSERT INTO pipeline_metrics
            (recorded_at, topic, consumer_lag, records_per_batch,
             processing_ms, query_name, batch_id, is_active)
        VALUES
            (%(recorded_at)s, %(topic)s, %(consumer_lag)s, %(records_per_batch)s,
             %(processing_ms)s, %(query_name)s, %(batch_id)s, %(is_active)s)
    """
    try:
        conn = get_pg_conn()
        with conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(cur, sql, rows)
        conn.close()
        logger.info("Wrote %d metric rows to Postgres", len(rows))
    except Exception as e:
        logger.error("Postgres write failed: %s", e)


# ─────────────────────────────────────────────────────────────
# SPARK METRICS  (via Spark REST API at :4040)
# ─────────────────────────────────────────────────────────────
def collect_spark_metrics() -> list[dict]:
    """
    Hits the Spark Structured Streaming REST endpoint.
    Returns per-query metrics: processing time, batch id, is_active.
    """
    rows = []
    now  = datetime.utcnow()

    try:
        # Get all running Spark apps
        apps_resp = requests.get(f"{SPARK_UI_URL}/api/v1/applications", timeout=5)
        if apps_resp.status_code != 200:
            logger.warning("Spark UI not reachable (status %s)", apps_resp.status_code)
            return rows

        apps = apps_resp.json()
        if not apps:
            logger.warning("No running Spark applications found")
            return rows

        app_id = apps[0]["id"]

        # Get streaming queries for this app
        streams_resp = requests.get(
            f"{SPARK_UI_URL}/api/v1/applications/{app_id}/streaming/statistics",
            timeout=5,
        )

        if streams_resp.status_code == 200:
            stats = streams_resp.json()
            rows.append({
                "recorded_at":        now,
                "topic":              "ALL_TOPICS",
                "consumer_lag":       0,
                "records_per_batch":  stats.get("avgInputRate", 0),
                "processing_ms":      stats.get("avgProcessingRate", 0),
                "query_name":         "streaming_statistics",
                "batch_id":           stats.get("numTotalCompletedBatches", 0),
                "is_active":          True,
            })

        # Per-query metrics from structured streaming
        queries_resp = requests.get(
            f"{SPARK_UI_URL}/api/v1/applications/{app_id}/streaming/receivers",
            timeout=5,
        )
        if queries_resp.status_code == 200:
            for q in queries_resp.json():
                rows.append({
                    "recorded_at":        now,
                    "topic":              q.get("name", "unknown"),
                    "consumer_lag":       q.get("eventRateLastMinute", 0),
                    "records_per_batch":  q.get("avgEventRate", 0),
                    "processing_ms":      q.get("lastErrorTime", 0),
                    "query_name":         q.get("streamName", "unknown"),
                    "batch_id":           q.get("streamId", 0),
                    "is_active":          q.get("active", False),
                })

    except requests.exceptions.ConnectionError:
        logger.warning("Cannot reach Spark UI at %s — job may not be running", SPARK_UI_URL)
    except Exception as e:
        logger.error("Spark metrics collection failed: %s", e)

    return rows


# ─────────────────────────────────────────────────────────────
# KAFKA CONSUMER LAG
# ─────────────────────────────────────────────────────────────
def collect_kafka_lag() -> list[dict]:
    """
    Reads consumer group offsets from Kafka and computes lag
    (latest offset - committed offset) per topic.
    """
    rows = []
    now  = datetime.utcnow()

    try:
        admin = KafkaAdminClient(
            bootstrap_servers=KAFKA_BROKERS,
            client_id="metrics-collector",
            request_timeout_ms=5000,
        )

        # Get latest offsets per topic-partition
        from kafka import KafkaConsumer
        consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BROKERS,
            group_id=CONSUMER_GROUP,
            enable_auto_commit=False,
        )

        for topic in TOPICS:
            try:
                partitions = consumer.partitions_for_topic(topic)
                if not partitions:
                    continue

                from kafka import TopicPartition
                tps = [TopicPartition(topic, p) for p in partitions]

                # End offsets (latest available)
                end_offsets = consumer.end_offsets(tps)
                # Committed offsets (what Spark has consumed)
                committed = {tp: consumer.committed(tp) for tp in tps}

                total_lag = sum(
                    (end_offsets[tp] or 0) - (committed[tp] or 0)
                    for tp in tps
                )

                rows.append({
                    "recorded_at":        now,
                    "topic":              topic,
                    "consumer_lag":       max(total_lag, 0),
                    "records_per_batch":  0,
                    "processing_ms":      0,
                    "query_name":         "kafka_lag",
                    "batch_id":           0,
                    "is_active":          True,
                })

            except Exception as e:
                logger.warning("Could not get lag for topic %s: %s", topic, e)

        consumer.close()
        admin.close()

    except KafkaError as e:
        logger.error("Kafka connection failed: %s", e)
    except Exception as e:
        logger.error("Kafka lag collection failed: %s", e)

    return rows


# ─────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────
def main():
    logger.info("Metrics collector starting...")
    logger.info("  Spark UI    : %s", SPARK_UI_URL)
    logger.info("  Kafka       : %s", KAFKA_BROKERS)
    logger.info("  Postgres    : %s:%s/%s", PG_HOST, PG_PORT, PG_DB)
    logger.info("  Poll interval: %ds", POLL_INTERVAL_SEC)

    # Wait for Spark to start before first poll
    logger.info("Waiting 30s for Spark to initialise...")
    time.sleep(30)

    while True:
        try:
            logger.info("Collecting metrics...")

            rows = []
            rows.extend(collect_spark_metrics())
            rows.extend(collect_kafka_lag())

            write_metrics(rows)
            logger.info("Cycle complete. Next poll in %ds", POLL_INTERVAL_SEC)

        except Exception as e:
            logger.error("Unexpected error in main loop: %s", e)

        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()