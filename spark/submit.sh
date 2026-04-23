#!/bin/bash
# ─────────────────────────────────────────────────────────────
# submit.sh — Submit Spark job inside spark-master container
# Usage: bash spark/submit.sh
# ─────────────────────────────────────────────────────────────

set -e

# Load .env from project root
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
export $(grep -v '^#' "$ENV_FILE" | tr -d '\r' | xargs)
else
  echo "ERROR: .env file not found at $ENV_FILE"
  exit 1
fi

# Validate required vars
: "${ADLS_ACCOUNT_NAME:?Need ADLS_ACCOUNT_NAME in .env}"
: "${ADLS_ACCOUNT_KEY:?Need ADLS_ACCOUNT_KEY in .env}"
: "${ADLS_CONTAINER:?Need ADLS_CONTAINER in .env}"

echo ""
echo "Submitting Spark job to spark-master container..."
echo "  ADLS account : $ADLS_ACCOUNT_NAME"
echo "  Kafka brokers: ${KAFKA_BROKERS:-kafka:29092}"
echo ""

# apache/spark image uses /opt/spark, not /opt/bitnami/spark
docker exec \
  -e ADLS_ACCOUNT_NAME="$ADLS_ACCOUNT_NAME" \
  -e ADLS_ACCOUNT_KEY="$ADLS_ACCOUNT_KEY" \
  -e ADLS_CONTAINER="$ADLS_CONTAINER" \
  -e KAFKA_BROKERS="kafka:29092" \
  spark-master \
  /opt/spark/bin/spark-submit \
  --master "local[*]" \
  --packages \
"org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.hadoop:hadoop-azure:3.3.4,com.azure:azure-storage-blob:12.25.1" \
  --conf "spark.executor.memory=1g" \
  --conf "spark.driver.memory=1g" \
  --conf "spark.sql.shuffle.partitions=4" \
  --conf "spark.streaming.stopGracefullyOnShutdown=true" \
  --conf "spark.hadoop.fs.azure.account.key.${ADLS_ACCOUNT_NAME}.dfs.core.windows.net=${ADLS_ACCOUNT_KEY}" \
  --conf "spark.kafka.consumer.request.timeout.ms=120000" \
  --conf "spark.kafka.consumer.session.timeout.ms=120000" \
  /opt/spark-apps/spark_streaming_job.py