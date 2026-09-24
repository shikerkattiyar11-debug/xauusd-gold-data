import argparse
import csv
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import websocket

WS_URL = "wss://ws.twelvedata.com/v1/quotes/price"


class LiveCollector:
    def __init__(self, symbol: str, output_dir: Path) -> None:
        self.symbol = symbol
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.output_dir / "live_ohlcv.db")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS ticks "
            "(timestamp TEXT NOT NULL, symbol TEXT NOT NULL, price REAL NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS candles "
            "(datetime TEXT PRIMARY KEY, open REAL NOT NULL, high REAL NOT NULL, "
            "low REAL NOT NULL, close REAL NOT NULL, volume INTEGER NOT NULL)"
        )
        self.db.commit()
        self.current_bucket = None
        self.current_candle = None

    def close(self) -> None:
        self.flush_candle()
        self.db.close()

    def record_tick(self, price: float, received_at: datetime) -> None:
        timestamp = received_at.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        self.db.execute(
            "INSERT INTO ticks (timestamp, symbol, price) VALUES (?, ?, ?)",
            (timestamp, self.symbol, price),
        )

        bucket = received_at.astimezone(timezone.utc).replace(second=0, microsecond=0)
        if self.current_bucket != bucket:
            self.flush_candle()
            self.current_bucket = bucket
            self.current_candle = {
                "Datetime": bucket.strftime("%Y-%m-%d %H:%M:%S"),
                "Open": price,
                "High": price,
                "Low": price,
                "Close": price,
                "Volume": 1,
            }
        else:
            self.current_candle["High"] = max(self.current_candle["High"], price)
            self.current_candle["Low"] = min(self.current_candle["Low"], price)
            self.current_candle["Close"] = price
            self.current_candle["Volume"] += 1
        self.db.commit()

    def flush_candle(self) -> None:
        if self.current_candle is None:
            return
        candle = self.current_candle
        self.db.execute(
            "INSERT OR REPLACE INTO candles "
            "(datetime, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?)",
            tuple(candle[column] for column in ("Datetime", "Open", "High", "Low", "Close", "Volume")),
        )
        self.db.commit()
        csv_path = self.output_dir / "xauusd_1m_live.csv"
        write_header = not csv_path.exists()
        with csv_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["Datetime", "Open", "High", "Low", "Close", "Volume"])
            if write_header:
                writer.writeheader()
            writer.writerow(candle)
        self.save_parquet_snapshot()
        self.current_candle = None

    def save_parquet_snapshot(self) -> None:
        rows = pd.read_sql_query(
            "SELECT datetime AS Datetime, open AS Open, high AS High, low AS Low, close AS Close, volume AS Volume "
            "FROM candles ORDER BY datetime",
            self.db,
        )
        if not rows.empty:
            rows.to_parquet(self.output_dir / "xauusd_1m_live.parquet", index=False)

    def run(self) -> None:
        api_key = os.getenv("TWELVE_DATA_API_KEY")
        if not api_key:
            raise RuntimeError("Set TWELVE_DATA_API_KEY before starting the live collector.")

        while True:
            try:
                print(f"Connecting to Twelve Data for {self.symbol}...")
                socket = websocket.create_connection(WS_URL, timeout=30)
                socket.send(json.dumps({
                    "action": "subscribe",
                    "params": {"symbols": self.symbol, "apikey": api_key},
                }))
                while True:
                    message = json.loads(socket.recv())
                    if message.get("event") == "price":
                        price = float(message["price"])
                        self.record_tick(price, datetime.now(timezone.utc))
                        print(f"{self.symbol} {price}", flush=True)
                    elif message.get("event") in {"error", "warning"}:
                        raise RuntimeError(message.get("message", "Twelve Data stream error"))
            except KeyboardInterrupt:
                self.close()
                return
            except Exception as exc:
                print(f"Live stream disconnected: {exc}; retrying in 5 seconds.", flush=True)
                time.sleep(5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect live XAU/USD ticks and build 1-minute OHLCV.")
    parser.add_argument("--symbol", default="XAU/USD", help="Twelve Data symbol to stream.")
    parser.add_argument("--output-dir", type=Path, default=Path("data"), help="Directory for live outputs.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    collector = LiveCollector(args.symbol, args.output_dir)
    try:
        collector.run()
    finally:
        collector.close()


if __name__ == "__main__":
    main()
