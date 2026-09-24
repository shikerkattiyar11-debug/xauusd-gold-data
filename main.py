import argparse
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TIMEFRAMES = {
    "5m": "5m",
    "10m": "10m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}
PERIODS = {
    "5m": "60d",
    "10m": "60d",
    "15m": "60d",
    "1h": "365d",
    "4h": "365d",
    "1d": "5y",
}
CSV_COLUMNS = ["Datetime", "Open", "High", "Low", "Close", "Volume"]


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        raise ValueError("No OHLCV data returned from yfinance.")

    cleaned = df.copy()
    if isinstance(cleaned.index, pd.DatetimeIndex):
        idx = cleaned.index
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        else:
            idx = idx.tz_convert("UTC")
        cleaned.index = idx.tz_convert("Asia/Kolkata")
        cleaned.index.name = "Datetime"
        cleaned = cleaned.reset_index()
    else:
        cleaned = cleaned.reset_index()
        cleaned = cleaned.rename(columns={cleaned.columns[0]: "Datetime"})
        cleaned["Datetime"] = pd.to_datetime(cleaned["Datetime"], errors="coerce", utc=True)
        cleaned["Datetime"] = cleaned["Datetime"].dt.tz_convert("Asia/Kolkata")

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in cleaned.columns]
    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")

    cleaned = cleaned[["Datetime", *required]].copy()
    cleaned = cleaned.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()
    cleaned["Datetime"] = cleaned["Datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    cleaned = cleaned[CSV_COLUMNS]
    cleaned = cleaned.drop_duplicates(subset=["Datetime"]).sort_values("Datetime").reset_index(drop=True)
    return cleaned


def resample_ohlcv_to_minutes(df: pd.DataFrame, interval_minutes: int) -> pd.DataFrame:
    base = df.copy()
    base["Datetime"] = pd.to_datetime(base["Datetime"], format="%Y-%m-%d %H:%M:%S")
    base = base.set_index("Datetime")
    resampled = base.resample(f"{interval_minutes}min").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    })
    resampled = resampled.reset_index()
    resampled["Datetime"] = resampled["Datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return resampled[CSV_COLUMNS]


def fetch_ohlcv(interval: str, period: str) -> pd.DataFrame:
    if interval == "10m":
        five_minute_data = fetch_ohlcv("5m", period)
        return resample_ohlcv_to_minutes(five_minute_data, 10)

    data = yf.download(
        tickers="GC=F",
        period=period,
        interval=interval,
        auto_adjust=False,
        actions=False,
        progress=False,
        threads=True,
        group_by="ticker",
    )
    if isinstance(data.columns, pd.MultiIndex):
        data = data.xs("GC=F", level=0, axis=1)
    return normalize_ohlcv(data)


def update_timeframe(interval: str, file_name: str) -> None:
    output_path = DATA_DIR / file_name
    data = fetch_ohlcv(interval, PERIODS[interval])

    if output_path.exists():
        existing = pd.read_csv(output_path)
        if not existing.empty and "Datetime" in existing.columns:
            existing["Datetime"] = existing["Datetime"].astype(str)
            latest_existing = existing["Datetime"].max()
            data = data[data["Datetime"] > latest_existing].copy()

    if not data.empty:
        if output_path.exists():
            combined = pd.concat([pd.read_csv(output_path), data], ignore_index=True)
        else:
            combined = data
        combined = combined[CSV_COLUMNS].drop_duplicates(subset=["Datetime"]).sort_values("Datetime").reset_index(drop=True)
        combined.to_csv(output_path, index=False)
    else:
        if not output_path.exists():
            data.to_csv(output_path, index=False)


def update_all_timeframes() -> None:
    ensure_data_dir()
    for interval, file_name in {key: f"xauusd_{key}.csv" for key in TIMEFRAMES}.items():
        update_timeframe(interval, file_name)
        print(f"Updated {file_name}")


def fetch_all_initial_data() -> None:
    ensure_data_dir()
    for interval, file_name in {key: f"xauusd_{key}.csv" for key in TIMEFRAMES}.items():
        data = fetch_ohlcv(interval, PERIODS[interval])
        data.to_csv(DATA_DIR / file_name, index=False)
        print(f"Saved {file_name} with {len(data)} rows")


def run_loop(poll_seconds: int = 300) -> None:
    while True:
        update_all_timeframes()
        print(f"Waiting {poll_seconds} seconds before the next refresh...\n")
        time.sleep(poll_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and maintain XAU/USD Gold OHLCV CSV files.")
    parser.add_argument("--init", action="store_true", help="Download initial data for all intervals once.")
    parser.add_argument("--once", action="store_true", help="Refresh all CSV files once without running a loop.")
    parser.add_argument("--poll-seconds", type=int, default=300, help="Seconds to sleep between auto-refreshes when looping.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.init:
        fetch_all_initial_data()
        return
    if args.once:
        update_all_timeframes()
        return
    run_loop(poll_seconds=args.poll_seconds)


if __name__ == "__main__":
    main()
