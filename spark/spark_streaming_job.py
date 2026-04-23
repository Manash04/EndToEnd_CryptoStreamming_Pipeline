"""
Crypto Trade Streaming Pipeline
================================
Reads raw trades from 4 Kafka topics, runs analytics via Spark
Structured Streaming, and writes results to Azure Data Lake Gen2.

Outputs
-------
  abfss://crypto-lake@<account>.dfs.core.windows.net/
    raw/trades/          -- every raw trade, partitioned by symbol + date
    analytics/vwap/      -- 1-min tumbling window VWAP per symbol
    analytics/imbalance/ -- 1-min buy/sell imbalance ratio per symbol
"""

import os
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField,
    StringType, LongType, DoubleType, BooleanType, TimestampType
)

# ─────────────────────────────────────────────────────────────
# CONFIG  (reads from environment — set in .env / submit.sh)
# ─────────────────────────────────────────────────────────────
ADLS_ACCOUNT   = os.environ["ADLS_ACCOUNT_NAME"]
ADLS_KEY       = os.environ["ADLS_ACCOUNT_KEY"]
ADLS_CONTAINER = os.environ.get("ADLS_CONTAINER", "crypto-lake")

# Kafka is in Docker, but its port 9092 is exposed to localhost
KAFKA_BROKERS  = os.environ.get("KAFKA_BROKERS", "localhost:9092")

ADLS_BASE = f"abfss://{ADLS_CONTAINER}@{ADLS_ACCOUNT}.dfs.core.windows.net"

KAFKA_TOPICS = "btcusdt-trades,ethusdt-trades,solusdt-trades,bnbusdt-trades"

# Checkpoint locations on ADLS — Spark uses these to resume after restarts
CHECKPOINT_RAW       = f"{ADLS_BASE}/checkpoints/raw"
CHECKPOINT_VWAP      = f"{ADLS_BASE}/checkpoints/vwap"
CHECKPOINT_IMBALANCE = f"{ADLS_BASE}/checkpoints/imbalance"

# ─────────────────────────────────────────────────────────────
# SCHEMA  (matches what producer.py writes into Kafka)
# ─────────────────────────────────────────────────────────────
TRADE_SCHEMA = StructType([
    StructField("event_type",             StringType(),  True),
    StructField("event_time_ms",          LongType(),    True),
    StructField("symbol",                 StringType(),  True),
    StructField("trade_id",               LongType(),    True),
    StructField("price",                  DoubleType(),  True),
    StructField("quantity",               DoubleType(),  True),
    StructField("trade_value_usdt",       DoubleType(),  True),
    StructField("trade_time_ms",          LongType(),    True),
    StructField("is_buyer_market_maker",  BooleanType(), True),
    StructField("ingested_at",            StringType(),  True),
])


def build_spark_session() -> SparkSession:
    spark = (
        SparkSession.builder
        .appName("CryptoTradeStreaming")
        # local[*] = use all CPU cores on your machine
        # no Spark cluster needed
        .master("local[*]")
        # ADLS Gen2 authentication
        .config(
            f"fs.azure.account.key.{ADLS_ACCOUNT}.dfs.core.windows.net",
            ADLS_KEY
        )
        # Required JARs are passed via --packages in submit.sh
        # These configs improve local streaming performance
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.streaming.stopGracefullyOnShutdown", "true")
        .config(
            "spark.sql.streaming.statefulOperator.checkCorrectness.enabled",
            "false"
        )
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def read_kafka_stream(spark: SparkSession):
    """
    Subscribe to all 4 topics in one reader.
    Kafka is in Docker with port 9092 exposed → reachable at localhost:9092
    """
    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKERS)
        .option("subscribe", KAFKA_TOPICS)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .option("maxOffsetsPerTrigger", 10000)
        .load()
    )


def parse_trades(raw_df):
    """
    Deserialize JSON value bytes → clean flat record.
    Adds trade_time (proper timestamp), side (BUY/SELL),
    and date_partition (for Parquet folder layout).
    """
    return (
        raw_df
        .selectExpr("CAST(value AS STRING) as json_str", "topic")
        .select(
            F.from_json(F.col("json_str"), TRADE_SCHEMA).alias("d"),
            F.col("topic")
        )
        .select("d.*", "topic")
        .withColumn(
            "trade_time",
            (F.col("trade_time_ms") / 1000).cast(TimestampType())
        )
        .withColumn(
            "side",
            F.when(F.col("is_buyer_market_maker"), "SELL").otherwise("BUY")
        )
        .withColumn(
            "date_partition",
            F.date_format(F.col("trade_time"), "yyyy-MM-dd")
        )
    )


def write_raw_trades(trades_df):
    """
    Sink 1 — Every raw trade → ADLS
    Layout: raw/trades/symbol=BTCUSDT/date_partition=2024-01-01/
    """
    return (
        trades_df
        .coalesce(1)                    
        .writeStream
        .format("parquet")
        .outputMode("append")
        .option("path", f"{ADLS_BASE}/raw/trades")
        .option("checkpointLocation", CHECKPOINT_RAW)
        .partitionBy("symbol", "date_partition")
        .trigger(processingTime="30 seconds")
        .start()
    )


def compute_vwap(trades_df):
    """
    Sink 2 — 1-minute tumbling window VWAP per symbol.
    VWAP = sum(price * qty) / sum(qty)
    Watermark of 10s handles late-arriving records.
    """
    vwap_df = (
        trades_df
        .withWatermark("trade_time", "10 seconds")
        .groupBy(
            F.col("symbol"),
            F.window(F.col("trade_time"), "1 minute").alias("window")
        )
        .agg(
            (F.sum(F.col("price") * F.col("quantity")) / F.sum("quantity"))
                .alias("vwap"),
            F.sum("quantity").alias("total_volume"),
            F.count("*").alias("trade_count"),
            F.sum("trade_value_usdt").alias("total_value_usdt"),
            F.min("price").alias("price_low"),
            F.max("price").alias("price_high"),
        )
        .select(
            "symbol",
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            F.round("vwap", 6).alias("vwap"),
            F.round("total_volume", 8).alias("total_volume"),
            "trade_count",
            F.round("total_value_usdt", 2).alias("total_value_usdt"),
            F.round("price_low", 6).alias("price_low"),
            F.round("price_high", 6).alias("price_high"),
            F.date_format("window.start", "yyyy-MM-dd").alias("date_partition"),
        )
    )

    return (
        vwap_df
        .coalesce(1)
        .writeStream
        .format("parquet")
        .outputMode("append")
        .option("path", f"{ADLS_BASE}/analytics/vwap")
        .option("checkpointLocation", CHECKPOINT_VWAP)
        .partitionBy("symbol", "date_partition")
        .trigger(processingTime="30 seconds")
        .start()
    )


def compute_imbalance(trades_df):
    """
    Sink 3 — 1-minute buy/sell imbalance per symbol.
    imbalance_ratio = buy_volume / total_volume
      > 0.6 → BUY_PRESSURE
      < 0.4 → SELL_PRESSURE
      else  → NEUTRAL
    """
    imbalance_df = (
        trades_df
        .withWatermark("trade_time", "10 seconds")
        .groupBy(
            F.col("symbol"),
            F.window(F.col("trade_time"), "1 minute").alias("window")
        )
        .agg(
            F.sum(
                F.when(F.col("side") == "BUY",  F.col("quantity")).otherwise(0)
            ).alias("buy_volume"),
            F.sum(
                F.when(F.col("side") == "SELL", F.col("quantity")).otherwise(0)
            ).alias("sell_volume"),
            F.count(F.when(F.col("side") == "BUY",  1)).alias("buy_count"),
            F.count(F.when(F.col("side") == "SELL", 1)).alias("sell_count"),
        )
        .withColumn("total_volume", F.col("buy_volume") + F.col("sell_volume"))
        .withColumn(
            "imbalance_ratio",
            F.round(F.col("buy_volume") / F.col("total_volume"), 4)
        )
        .withColumn(
            "pressure",
            F.when(F.col("imbalance_ratio") > 0.6, "BUY_PRESSURE")
             .when(F.col("imbalance_ratio") < 0.4, "SELL_PRESSURE")
             .otherwise("NEUTRAL")
        )
        .select(
            "symbol",
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            F.round("buy_volume",  8).alias("buy_volume"),
            F.round("sell_volume", 8).alias("sell_volume"),
            "buy_count",
            "sell_count",
            "imbalance_ratio",
            "pressure",
            F.date_format("window.start", "yyyy-MM-dd").alias("date_partition"),
        )
    )

    return (
        imbalance_df
        .coalesce(1)
        .writeStream
        .format("parquet")
        .outputMode("append")
        .option("path", f"{ADLS_BASE}/analytics/imbalance")
        .option("checkpointLocation", CHECKPOINT_IMBALANCE)
        .partitionBy("symbol", "date_partition")
        .trigger(processingTime="30 seconds")
        .start()
    )


def main():
    print("=" * 60)
    print("  Crypto Trade Streaming Pipeline starting...")
    print(f"  ADLS target  : {ADLS_BASE}")
    print(f"  Kafka brokers: {KAFKA_BROKERS}")
    print(f"  Topics       : {KAFKA_TOPICS}")
    print("=" * 60)

    spark = build_spark_session()

    raw_df    = read_kafka_stream(spark)
    trades_df = parse_trades(raw_df)

    query_raw       = write_raw_trades(trades_df)
    query_vwap      = compute_vwap(trades_df)
    query_imbalance = compute_imbalance(trades_df)

    print("All streaming queries started.")
    print(f"  Raw trades → {ADLS_BASE}/raw/trades")
    print(f"  VWAP       → {ADLS_BASE}/analytics/vwap")
    print(f"  Imbalance  → {ADLS_BASE}/analytics/imbalance")

    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()