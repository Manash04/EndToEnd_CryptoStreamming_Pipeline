"""
daily_analysis.py
==================
PySpark batch job triggered by Airflow every day at 3 PM.
Reads previous day's Parquet from ADLS, computes daily and hourly
summaries, and writes them to Postgres.

Called by Airflow via:
    spark-submit airflow/batch/daily_analysis.py --date 2024-01-15
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql import Window
from pyspark.sql.types import DoubleType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
ADLS_ACCOUNT   = os.environ["ADLS_ACCOUNT_NAME"]
ADLS_KEY       = os.environ["ADLS_ACCOUNT_KEY"]
ADLS_CONTAINER = os.environ.get("ADLS_CONTAINER", "crypto-lake")
ADLS_BASE      = f"abfss://{ADLS_CONTAINER}@{ADLS_ACCOUNT}.dfs.core.windows.net"

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_DB   = os.environ.get("PG_DB",   "crypto_analytics")
PG_USER = os.environ.get("PG_USER", "crypto")
PG_PASS = os.environ.get("PG_PASS", "crypto123")
PG_URL  = f"jdbc:postgresql://{PG_HOST}:{PG_PORT}/{PG_DB}"
PG_PROPS = {
    "user":     PG_USER,
    "password": PG_PASS,
    "driver":   "org.postgresql.Driver",
}


def build_spark() -> SparkSession:
    return (
        SparkSession.builder
        .appName("CryptoDailyAnalysis")
        .master("local[*]")
        .config(
            f"fs.azure.account.key.{ADLS_ACCOUNT}.dfs.core.windows.net",
            ADLS_KEY
        )
        .config("spark.sql.files.maxPartitionBytes", "134217728")
        .config("spark.sql.files.openCostInBytes", "134217728")
        .config("spark.hadoop.mapreduce.input.fileinputformat.split.minsize", "134217728")
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )


def read_raw_trades(spark: SparkSession, date_str: str):
    path = f"{ADLS_BASE}/raw/trades"
    logger.info("Reading raw trades from %s for date %s", path, date_str)

    df = (
        spark.read
        .parquet(path)
        .filter(F.col("date_partition") == date_str)
        .repartition(8)
        .limit(500000)
    )

    count = df.count()
    logger.info("Loaded %d trades for %s", count, date_str)

    if count == 0:
        raise ValueError(f"No trade data found for {date_str}.")
    return df


def compute_daily_summary(trades_df, date_str: str):
    """
    Compute one row per symbol for the given date.
    Includes: VWAP, volume, trade count, OHLC, peak hours, imbalance.
    """
    # Window to get first/last price (open/close)
    w_asc  = Window.partitionBy("symbol").orderBy("trade_time_ms")
    w_desc = Window.partitionBy("symbol").orderBy(F.desc("trade_time_ms"))

    with_rank = (
        trades_df
        .withColumn("rn_asc",  F.row_number().over(w_asc))
        .withColumn("rn_desc", F.row_number().over(w_desc))
    )

    open_prices  = (with_rank.filter(F.col("rn_asc")  == 1)
                    .select("symbol", F.col("price").alias("price_open")))
    close_prices = (with_rank.filter(F.col("rn_desc") == 1)
                    .select("symbol", F.col("price").alias("price_close")))

    # Main aggregation
    summary = (
        trades_df
        .groupBy("symbol")
        .agg(
            (F.sum(F.col("price") * F.col("quantity")) / F.sum("quantity"))
                .alias("daily_vwap"),
            F.sum("quantity").alias("total_volume"),
            F.count("*").alias("total_trades"),
            F.sum("trade_value_usdt").alias("total_value_usdt"),
            F.max("price").alias("price_high"),
            F.min("price").alias("price_low"),
            F.avg(
                F.when(F.col("side") == "BUY", F.col("quantity")).otherwise(0)
                / (F.col("quantity"))
            ).alias("avg_imbalance"),
        )
        .join(open_prices,  "symbol")
        .join(close_prices, "symbol")
    )

    # Peak buy/sell hour
    hourly_sides = (
        trades_df
        .withColumn("hour", F.hour(F.col("trade_time").cast("timestamp")))
        .groupBy("symbol", "hour")
        .agg(
            F.sum(F.when(F.col("side") == "BUY",  F.col("quantity")).otherwise(0))
                .alias("buy_vol"),
            F.sum(F.when(F.col("side") == "SELL", F.col("quantity")).otherwise(0))
                .alias("sell_vol"),
        )
    )

    w_buy  = Window.partitionBy("symbol").orderBy(F.desc("buy_vol"))
    w_sell = Window.partitionBy("symbol").orderBy(F.desc("sell_vol"))

    peak_buy  = (hourly_sides.withColumn("rn", F.row_number().over(w_buy))
                 .filter(F.col("rn") == 1)
                 .select("symbol", F.col("hour").alias("peak_buy_hour")))
    peak_sell = (hourly_sides.withColumn("rn", F.row_number().over(w_sell))
                 .filter(F.col("rn") == 1)
                 .select("symbol", F.col("hour").alias("peak_sell_hour")))

    result = (
        summary
        .join(peak_buy,  "symbol", "left")
        .join(peak_sell, "symbol", "left")
        .withColumn("trade_date", F.lit(date_str).cast("date"))
        .withColumn(
            "strongest_signal",
            F.when(F.col("avg_imbalance") > 0.6, "BUY_PRESSURE")
             .when(F.col("avg_imbalance") < 0.4, "SELL_PRESSURE")
             .otherwise("NEUTRAL")
        )
        .withColumn("daily_vwap",       F.round("daily_vwap",       8))
        .withColumn("total_volume",     F.round("total_volume",      8))
        .withColumn("total_value_usdt", F.round("total_value_usdt",  2))
        .withColumn("price_high",       F.round("price_high",        8))
        .withColumn("price_low",        F.round("price_low",         8))
        .withColumn("price_open",       F.round("price_open",        8))
        .withColumn("price_close",      F.round("price_close",       8))
        .withColumn("avg_imbalance",    F.round("avg_imbalance",     4))
        .select(
            "trade_date", "symbol",
            "daily_vwap", "total_volume", "total_trades", "total_value_usdt",
            "price_open", "price_close", "price_high", "price_low",
            "peak_buy_hour", "peak_sell_hour",
            "avg_imbalance", "strongest_signal",
        )
    )

    logger.info("Daily summary computed for %d symbols", result.count())
    return result


def compute_hourly_breakdown(trades_df, date_str: str):
    """
    Compute one row per symbol per hour.
    Used by FastAPI for intraday chart endpoints.
    """
    result = (
        trades_df
        .withColumn("hour", F.hour(F.col("trade_time").cast("timestamp")))
        .groupBy("symbol", "hour")
        .agg(
            (F.sum(F.col("price") * F.col("quantity")) / F.sum("quantity"))
                .alias("vwap"),
            F.sum("quantity").alias("volume"),
            F.count("*").alias("trade_count"),
            (F.sum(F.when(F.col("side") == "BUY", F.col("quantity")).otherwise(0))
             / F.sum("quantity")).alias("imbalance_ratio"),
        )
        .withColumn("trade_date",      F.lit(date_str).cast("date"))
        .withColumn("vwap",            F.round("vwap",            8))
        .withColumn("volume",          F.round("volume",          8))
        .withColumn("imbalance_ratio", F.round("imbalance_ratio", 4))
        .withColumn(
            "pressure",
            F.when(F.col("imbalance_ratio") > 0.6, "BUY_PRESSURE")
             .when(F.col("imbalance_ratio") < 0.4, "SELL_PRESSURE")
             .otherwise("NEUTRAL")
        )
        .select(
            "trade_date", "symbol", "hour",
            "vwap", "volume", "trade_count",
            "imbalance_ratio", "pressure",
        )
        .orderBy("symbol", "hour")
    )

    logger.info("Hourly breakdown computed: %d rows", result.count())
    return result


def write_to_postgres(df, table: str, mode: str = "append"):
    """Write a Spark DataFrame to Postgres via JDBC."""
    logger.info("Writing to Postgres table: %s (mode=%s)", table, mode)
    (
        df.write
        .jdbc(
            url=PG_URL,
            table=table,
            mode=mode,
            properties=PG_PROPS,
        )
    )
    logger.info("Write to %s complete", table)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        default=(datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d"),
        help="Date to process in YYYY-MM-DD format (default: yesterday)",
    )
    args = parser.parse_args()
    date_str = args.date

    logger.info("=" * 60)
    logger.info("  Daily batch analysis starting")
    logger.info("  Processing date : %s", date_str)
    logger.info("  ADLS source     : %s", ADLS_BASE)
    logger.info("  Postgres target : %s/%s", PG_URL, PG_DB)
    logger.info("=" * 60)

    spark = build_spark()

    # Read
    trades_df = read_raw_trades(spark, date_str)

    # Compute
    daily_df  = compute_daily_summary(trades_df, date_str)
    hourly_df = compute_hourly_breakdown(trades_df, date_str)

    # Write — upsert by deleting existing date first then appending
    # (simpler than JDBC upsert for a portfolio project)
    write_to_postgres(daily_df,  "daily_analytics",  mode="append")
    write_to_postgres(hourly_df, "hourly_analytics", mode="append")

    logger.info("Daily analysis complete for %s", date_str)
    spark.stop()


if __name__ == "__main__":
    main()