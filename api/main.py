"""
main.py — FastAPI crypto analytics API
========================================
Reads from Postgres daily_analytics and hourly_analytics tables.
Serves endpoints for your crypto website.

Run:
    pip install fastapi uvicorn psycopg2-binary python-dotenv
    uvicorn api.main:app --reload --port 8000

Endpoints:
    GET /api/v1/symbols                          — list available symbols
    GET /api/v1/summary/{symbol}                 — latest daily summary
    GET /api/v1/summary/{symbol}/{date}          — summary for a specific date
    GET /api/v1/hourly/{symbol}/{date}           — hourly breakdown for charts
    GET /api/v1/compare?symbols=BTC,ETH&date=... — side-by-side comparison
    GET /health                                  — health check
"""

import os
from datetime import date, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

app = FastAPI(
    title="Crypto Analytics API",
    description="Real-time crypto trade analytics powered by a Kafka → Spark → ADLS pipeline",
    version="1.0.0",
)

# Allow your website frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# DB CONNECTION
# ─────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("PG_HOST",   "localhost"),
    "port":     int(os.getenv("PG_PORT", "5432")),
    "dbname":   os.getenv("PG_DB",     "crypto_analytics"),
    "user":     os.getenv("PG_USER",   "crypto"),
    "password": os.getenv("PG_PASS",   "crypto123"),
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def query(sql: str, params=None) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# RESPONSE MODELS
# ─────────────────────────────────────────────────────────────
class DailySummary(BaseModel):
    trade_date:       date
    symbol:           str
    daily_vwap:       Optional[float]
    total_volume:     Optional[float]
    total_trades:     Optional[int]
    total_value_usdt: Optional[float]
    price_open:       Optional[float]
    price_close:      Optional[float]
    price_high:       Optional[float]
    price_low:        Optional[float]
    peak_buy_hour:    Optional[int]
    peak_sell_hour:   Optional[int]
    avg_imbalance:    Optional[float]
    strongest_signal: Optional[str]


class HourlyData(BaseModel):
    trade_date:      date
    symbol:          str
    hour:            int
    vwap:            Optional[float]
    volume:          Optional[float]
    trade_count:     Optional[int]
    imbalance_ratio: Optional[float]
    pressure:        Optional[str]


# ─────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    try:
        query("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")


@app.get("/api/v1/symbols")
def list_symbols():
    """Return all symbols that have data, with the date range available."""
    rows = query("""
        SELECT
            symbol,
            MIN(trade_date) AS earliest_date,
            MAX(trade_date) AS latest_date,
            COUNT(*)        AS days_available
        FROM daily_analytics
        GROUP BY symbol
        ORDER BY symbol
    """)
    if not rows:
        return {"symbols": [], "message": "No data yet — run the Airflow DAG first"}
    return {"symbols": rows}


@app.get("/api/v1/summary/{symbol}", response_model=DailySummary)
def get_latest_summary(symbol: str):
    """Return the most recent daily summary for a symbol."""
    symbol = symbol.upper() + "USDT" if not symbol.upper().endswith("USDT") else symbol.upper()
    rows = query("""
        SELECT * FROM daily_analytics
        WHERE symbol = %s
        ORDER BY trade_date DESC
        LIMIT 1
    """, (symbol,))

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {symbol}. Available after first Airflow run."
        )
    return rows[0]


@app.get("/api/v1/summary/{symbol}/{trade_date}", response_model=DailySummary)
def get_summary_by_date(symbol: str, trade_date: date):
    """Return daily summary for a specific symbol and date."""
    symbol = symbol.upper() + "USDT" if not symbol.upper().endswith("USDT") else symbol.upper()
    rows = query("""
        SELECT * FROM daily_analytics
        WHERE symbol = %s AND trade_date = %s
    """, (symbol, trade_date))

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No data for {symbol} on {trade_date}"
        )
    return rows[0]


@app.get("/api/v1/hourly/{symbol}/{trade_date}", response_model=list[HourlyData])
def get_hourly_breakdown(symbol: str, trade_date: date):
    """Return hourly VWAP, volume, and imbalance for intraday charts."""
    symbol = symbol.upper() + "USDT" if not symbol.upper().endswith("USDT") else symbol.upper()
    rows = query("""
        SELECT * FROM hourly_analytics
        WHERE symbol = %s AND trade_date = %s
        ORDER BY hour ASC
    """, (symbol, trade_date))

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No hourly data for {symbol} on {trade_date}"
        )
    return rows


@app.get("/api/v1/compare")
def compare_symbols(
    symbols: str = Query(..., description="Comma-separated symbols e.g. BTC,ETH"),
    trade_date: Optional[date] = Query(
        default=None,
        description="Date in YYYY-MM-DD format (default: yesterday)"
    ),
):
    """
    Side-by-side comparison of multiple symbols for a given date.
    Great for your website's comparison page.
    """
    if trade_date is None:
        trade_date = date.today() - timedelta(days=1)

    symbol_list = [
        s.strip().upper() + "USDT"
        if not s.strip().upper().endswith("USDT")
        else s.strip().upper()
        for s in symbols.split(",")
    ]

    placeholders = ",".join(["%s"] * len(symbol_list))
    rows = query(f"""
        SELECT * FROM daily_analytics
        WHERE symbol IN ({placeholders})
          AND trade_date = %s
        ORDER BY total_value_usdt DESC
    """, (*symbol_list, trade_date))

    return {
        "date":    str(trade_date),
        "symbols": rows,
        "count":   len(rows),
    }


@app.get("/api/v1/trend/{symbol}")
def get_trend(
    symbol: str,
    days: int = Query(default=7, ge=1, le=30, description="Number of days (1-30)")
):
    """
    Return the last N days of daily summaries for a symbol.
    Perfect for a trend line chart on your website.
    """
    symbol = symbol.upper() + "USDT" if not symbol.upper().endswith("USDT") else symbol.upper()
    rows = query("""
        SELECT
            trade_date, symbol, daily_vwap, total_volume,
            total_trades, price_high, price_low,
            avg_imbalance, strongest_signal
        FROM daily_analytics
        WHERE symbol = %s
        ORDER BY trade_date DESC
        LIMIT %s
    """, (symbol, days))

    if not rows:
        raise HTTPException(status_code=404, detail=f"No trend data for {symbol}")

    return {
        "symbol": symbol,
        "days":   days,
        "trend":  list(reversed(rows)),  # oldest first for charting
    }