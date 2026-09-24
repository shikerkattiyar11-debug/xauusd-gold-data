# XAU/USD Gold OHLCV Data System

This project downloads and stores free OHLCV market data for XAU/USD using the Yahoo Finance ticker `GC=F`.

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

## Auto-update behavior

The project includes a GitHub Actions workflow that runs every 30 minutes and pushes updated CSV files back to the repository automatically.

## Assumptions

- Yahoo Finance continues to provide free `GC=F` data access without a paid plan.
- The repository is intended for educational, personal, or research use.
- The automation runs on GitHub-hosted runners and the repository is public or has valid push permissions.

## License

This project is provided for educational and research use.
