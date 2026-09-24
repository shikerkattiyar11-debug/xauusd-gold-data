import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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
FETCH_RETRIES = 3
FETCH_RETRY_DELAY_SECONDS = 5


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


def fetch_from_yahoo(interval: str, period: str) -> pd.DataFrame:
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


def fetch_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "xauusd-gold-data/1.0"})
    with urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_from_twelve_data(interval: str, period: str) -> pd.DataFrame:
    api_key = os.getenv("TWELVE_DATA_API_KEY")
    if not api_key or interval not in {"5m", "15m", "1h", "1d"}:
        return pd.DataFrame()

    payload = fetch_json("https://api.twelvedata.com/time_series?" + urlencode({
        "symbol": "XAU/USD",
        "interval": interval,
        "outputsize": 5000,
        "timezone": "UTC",
        "apikey": api_key,
    }))
    if "values" not in payload:
        raise ValueError(payload.get("message", "Twelve Data returned no values."))

    rows = []
    for value in payload["values"]:
        rows.append({
            "Datetime": value["datetime"],
            "Open": value["open"],
            "High": value["high"],
            "Low": value["low"],
            "Close": value["close"],
            "Volume": value.get("volume", 0),
        })
    return normalize_ohlcv(pd.DataFrame(rows).set_index("Datetime"))


def fetch_from_alpha_vantage(interval: str, period: str) -> pd.DataFrame:
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key or interval not in {"5m", "15m", "1h"}:
        return pd.DataFrame()

    payload = fetch_json("https://www.alphavantage.co/query?" + urlencode({
        "function": "FX_INTRADAY",
        "from_symbol": "XAU",
        "to_symbol": "USD",
        "interval": interval,
        "outputsize": "full",
        "apikey": api_key,
    }))
    series_key = next((key for key in payload if key.startswith("Time Series FX")), None)
    if not series_key:
        raise ValueError(payload.get("Note", payload.get("Information", "Alpha Vantage returned no values.")))

    rows = []
    for timestamp, value in payload[series_key].items():
        rows.append({
            "Datetime": timestamp,
            "Open": value["1. open"],
            "High": value["2. high"],
            "Low": value["3. low"],
            "Close": value["4. close"],
            "Volume": 0,
        })
    return normalize_ohlcv(pd.DataFrame(rows).set_index("Datetime"))


def fetch_ohlcv(interval: str, period: str) -> pd.DataFrame:
    if interval == "10m":
        five_minute_data = fetch_ohlcv("5m", period)
        return resample_ohlcv_to_minutes(five_minute_data, 10)

    providers = {
        "Yahoo Finance": lambda: fetch_from_yahoo(interval, period),
        "Twelve Data": lambda: fetch_from_twelve_data(interval, period),
        "Alpha Vantage": lambda: fetch_from_alpha_vantage(interval, period),
    }
    results = []
    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        pending = {executor.submit(fetcher): name for name, fetcher in providers.items()}
        for future in as_completed(pending):
            provider = pending[future]
            try:
                data = future.result()
                if not data.empty:
                    latest = data["Datetime"].iloc[-1]
                    print(f"{provider}: latest {latest}")
                    results.append((latest, provider, data))
            except Exception as exc:
                print(f"{provider} unavailable for {interval}: {exc}")

    if not results:
        raise ValueError(f"No configured market-data provider returned {interval} data.")
    latest, provider, data = max(results, key=lambda result: result[0])
    print(f"Selected {provider} for {interval}: latest {latest}")
    return data


def fetch_ohlcv_with_retry(interval: str, period: str) -> pd.DataFrame:
    last_error = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            data = fetch_ohlcv(interval, period)
            if not data.empty:
                return data
            last_error = ValueError("Downloaded dataset was empty.")
        except Exception as exc:  # pragma: no cover - defensive network fallback
            last_error = exc
            print(f"Retry {attempt}/{FETCH_RETRIES} for {interval} failed: {exc}")
        if attempt < FETCH_RETRIES:
            time.sleep(FETCH_RETRY_DELAY_SECONDS)
    if last_error is not None:
        print(f"Unable to fetch {interval} data after {FETCH_RETRIES} attempts: {last_error}")
    return pd.DataFrame()


def detect_time_gap(df: pd.DataFrame, interval: str) -> None:
    if df.empty or len(df) < 2:
        return

    interval_minutes = {
        "5m": 5,
        "10m": 10,
        "15m": 15,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }.get(interval, 5)

    timestamps = pd.to_datetime(df["Datetime"], format="%Y-%m-%d %H:%M:%S")
    gaps = timestamps.diff().dropna()
    if gaps.empty:
        return

    longest_gap = gaps.max()
    if longest_gap > pd.Timedelta(minutes=interval_minutes * 2):
        print(f"Possible data gap detected for {interval}: longest gap = {longest_gap}")


def update_timeframe(interval: str, file_name: str) -> None:
    output_path = DATA_DIR / file_name
    data = fetch_ohlcv_with_retry(interval, PERIODS[interval])
    if data.empty:
        if output_path.exists():
            print(f"No fresh {interval} data available; keeping existing file.")
        return

    detect_time_gap(data, interval)

    if output_path.exists():
        existing = pd.read_csv(output_path)
        if not existing.empty and "Datetime" in existing.columns:
            existing["Datetime"] = existing["Datetime"].astype(str)
            existing = existing[CSV_COLUMNS]
            combined = pd.concat([existing, data], ignore_index=True)
            combined = combined.drop_duplicates(subset=["Datetime"], keep="last")
            combined = combined.sort_values("Datetime").reset_index(drop=True)
            if len(combined) > len(existing):
                print(f"Found {len(combined) - len(existing)} new rows for {file_name}")
            elif not data.empty and not existing.tail(1).equals(data.tail(1)):
                print(f"Updated the latest candle for {file_name}")
            combined.to_csv(output_path, index=False)
            return

    if not data.empty:
        if output_path.exists():
            combined = pd.concat([pd.read_csv(output_path), data], ignore_index=True)
        else:
            combined = data
        combined = combined[CSV_COLUMNS].drop_duplicates(subset=["Datetime"]).sort_values("Datetime").reset_index(drop=True)
        combined.to_csv(output_path, index=False)
        print(f"Saved {file_name} with {len(combined)} rows")
    else:
        if not output_path.exists():
            data.to_csv(output_path, index=False)
            print(f"Created {file_name} with {len(data)} rows")
        else:
            print(f"No new rows for {file_name}; existing data already current.")


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
