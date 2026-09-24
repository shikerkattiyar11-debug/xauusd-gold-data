# XAU/USD Gold OHLCV Data System

This project downloads and stores OHLCV market data for XAU/USD. It queries all configured providers in parallel and selects the response with the newest candle. Yahoo Finance works without a key; Twelve Data and Alpha Vantage are optional fallbacks.

## Included timeframes

The project automatically prepares the following CSV files under the `data/` folder:

- `xauusd_5m.csv`
- `xauusd_10m.csv`
- `xauusd_15m.csv`
- `xauusd_1h.csv`
- `xauusd_4h.csv`
- `xauusd_1d.csv`

## Output format

Each CSV file contains the following columns:

```
Datetime,Open,High,Low,Close,Volume
```

All timestamps are stored in IST (`Asia/Kolkata`) and formatted as `YYYY-MM-DD HH:MM:SS` strings.

## Local usage

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Download the initial datasets:

```bash
python main.py --init
```

3. Refresh in a loop for continuous updates:

```bash
python main.py --poll-seconds 300
```

4. Refresh once without looping:

```bash
python main.py --once
```

## Live one-minute collector

For live ticks, set `TWELVE_DATA_API_KEY` and run:

```bash
python live_collector.py
```

The collector reconnects automatically and writes live ticks to `data/live_ohlcv.db`,
one-minute candles to `data/xauusd_1m_live.csv`, and a Parquet snapshot to
`data/xauusd_1m_live.parquet`. The `Volume` column is the number of received quotes,
because a quote stream does not provide exchange-traded volume for spot XAU/USD.

This process must stay running on a local machine or VPS. GitHub Actions and GitHub
Pages are not suitable for a one-second live stream.

## Virtual deployment

The collector is containerized for a continuously running cloud worker. For local Docker:

```bash
copy .env.example .env
docker compose up -d --build
```

For Render, create a new Blueprint from this repository. `render.yaml` creates a free web
service that serves the dashboard and runs the collector in the same container; add
`TWELVE_DATA_API_KEY` when Render asks for the secret. Open the Render service URL to
view the dashboard when the laptop is offline. Render's free service can sleep after
inactivity and its filesystem is ephemeral, so a restart can reset the live CSV history.
Use a paid persistent disk or VPS for guaranteed 24/7 collection and durable history.

## Auto-update behavior

The project includes a GitHub Actions workflow that runs every 5 minutes and pushes updated CSV files back to the repository automatically.

### Optional multi-source providers

Add these repository secrets under **Settings > Secrets and variables > Actions**:

- `TWELVE_DATA_API_KEY`
- `ALPHA_VANTAGE_API_KEY`

The workflow will query the available providers together. A provider that is unavailable, rate-limited, or returns older data is ignored in favor of the freshest successful response. Without these secrets, Yahoo Finance remains the active provider.

## Assumptions

- Yahoo Finance continues to provide free `GC=F` data access without a paid plan.
- Optional provider API keys are available and their free-tier limits are sufficient for the five-minute schedule.
- The repository is intended for educational, personal, or research use.
- The automation runs on GitHub-hosted runners and the repository is public or has valid push permissions.

## License

This project is provided for educational and research use.
