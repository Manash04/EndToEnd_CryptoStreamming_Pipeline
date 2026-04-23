import json
import logging
import signal
import sys
import time
from datetime import datetime

import websocket
from kafka import KafkaProducer
from kafka.errors import KafkaError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
BINANCE_WS_URL = (
    "wss://stream.binance.com:9443/stream"
    "?streams=btcusdt@trade/ethusdt@trade/solusdt@trade/bnbusdt@trade"
)

# Map Binance stream name -> Kafka topic
STREAM_TO_TOPIC = {
    "btcusdt@trade": "btcusdt-trades",
    "ethusdt@trade": "ethusdt-trades",
    "solusdt@trade": "solusdt-trades",
    "bnbusdt@trade": "bnbusdt-trades",
}


def create_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        # Reliability settings
        acks="all",
        retries=5,
        retry_backoff_ms=500,
        # Throughput settings
        linger_ms=5,
        batch_size=16384,
    )


def parse_trade(raw: dict) -> dict:
    """
    Normalize a raw Binance trade event into a clean flat record.

    Raw Binance fields:
        e = event type, E = event time, s = symbol,
        t = trade id,   p = price,       q = quantity,
        T = trade time, m = is_buyer_market_maker
    """
    data = raw["data"]
    return {
        "event_type":           data["e"],
        "event_time_ms":        data["E"],
        "symbol":               data["s"],
        "trade_id":             data["t"],
        "price":                float(data["p"]),
        "quantity":             float(data["q"]),
        "trade_value_usdt":     float(data["p"]) * float(data["q"]),
        "trade_time_ms":        data["T"],
        "is_buyer_market_maker": data["m"],      # True = seller initiated
        "ingested_at":          datetime.utcnow().isoformat(),
    }


def on_message(ws, message, producer: KafkaProducer):
    try:
        raw = json.loads(message)
        stream_name = raw.get("stream", "")
        topic = STREAM_TO_TOPIC.get(stream_name)

        if not topic:
            logger.warning("Unknown stream: %s", stream_name)
            return

        record = parse_trade(raw)
        symbol = record["symbol"]

        producer.send(
            topic=topic,
            key=symbol,          # partitions by symbol for ordering
            value=record,
        )
        logger.debug("Sent %s trade | price=%.2f qty=%.5f",
                     symbol, record["price"], record["quantity"])

    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.error("Failed to parse message: %s | error: %s", message[:120], e)


def on_error(ws, error):
    logger.error("WebSocket error: %s", error)


def on_close(ws, close_status_code, close_msg):
    logger.warning("WebSocket closed | code=%s msg=%s", close_status_code, close_msg)


def on_open(ws):
    logger.info("WebSocket connection established")
    logger.info("Subscribed to: %s", ", ".join(STREAM_TO_TOPIC.keys()))


def run(producer: KafkaProducer):
    while True:
        try:
            ws = websocket.WebSocketApp(
                BINANCE_WS_URL,
                on_open=on_open,
                on_message=lambda ws, msg: on_message(ws, msg, producer),
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            logger.error("Unexpected error: %s — reconnecting in 5s", e)
        time.sleep(5)
        logger.info("Reconnecting to Binance WebSocket...")


def main():
    logger.info("Starting Binance → Kafka producer")

    producer = None

    def shutdown(sig, frame):
        logger.info("Shutting down...")
        if producer:
            producer.flush()
            producer.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("Connecting to Kafka at %s", KAFKA_BOOTSTRAP_SERVERS)
    producer = create_producer()
    logger.info("Kafka producer ready")

    run(producer)


if __name__ == "__main__":
    main()