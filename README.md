# IVBS Trading Bot

Institutional Volume Breakout Strategy (IVBS) automated trading system for NSE equities using Zerodha Kite Connect.

This repository contains:
- FastAPI backend and real-time dashboard
- Async trading engine with scanner + strategy state machine
- Redis-backed runtime state and pub/sub
- SQLite persistence for signals, orders, trades, and daily PnL

The strategy reference for this repo is:
- `IVBS_Final_Spec.md`

## Core Features

- 4-phase strategy lifecycle: scan, dry-up monitoring, entry, management
- Live and paper-trade modes (`PAPER_TRADE`)
- Graceful stop (`STOP`) blocks new entries while managing existing positions
- Emergency stop (`EMERGENCY_STOP`) immediately initiates square-off
- Exit lifecycle is postback-safe (no immediate synthetic close in live mode)
- Margin block tracking on fill/close
- Reconciliation loop for missed postbacks and rejected exits

## Tech Stack

- Python 3.12+
- FastAPI + Uvicorn
- Redis 7
- SQLAlchemy async + SQLite
- APScheduler
- Zerodha Kite Connect v3
- Pytest for unit/integration tests

## Project Layout

- `app/` API and dashboard
- `engine/` trading engine and strategy logic
- `tests/` unit + integration tests
- `scripts/` diagnostics and helper scripts
- `IVBS_Final_Spec.md` final strategy and production specification

## Prerequisites

1. Python 3.12 or newer
2. Zerodha Kite Connect app credentials
3. Redis running on `localhost:6379` (Docker recommended)
4. Windows PowerShell (commands below are Windows-friendly)

## Setup

1. Create and activate virtual environment

```powershell
cd d:\volume_algo_trading\trading_bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

Alternative install path using requirements.txt:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

3. Configure environment

```powershell
copy .env.example .env
```

Edit `.env` and set at minimum:
- `KITE_API_KEY`
- `KITE_API_SECRET`
- `KITE_REDIRECT_URL`
- `PAPER_TRADE=true` (recommended initially)

4. Start Redis

```powershell
docker compose up -d redis
```

5. Run DB migrations

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## Run

Open two terminals.

Terminal 1: API + dashboard

```powershell
cd d:\volume_algo_trading\trading_bot
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Terminal 2: trading engine

```powershell
cd d:\volume_algo_trading\trading_bot
.\.venv\Scripts\python.exe -m engine.runner
```

Open dashboard:
- `http://127.0.0.1:8000/`

## Authentication Flow

1. Open `GET /api/v1/auth/login`
2. Complete Zerodha login in browser
3. Callback stores token in `.kite_token` and Redis (`.kite_token` is gitignored)
4. Start or resume engine

If your Kite redirect is `http://127.0.0.1` only, use:

```powershell
.\.venv\Scripts\python.exe scripts\kite_port80_redirect.py
```

(run as Administrator when required)

## Useful API Endpoints

- `GET /health`
- `GET /api/v1/status`
- `GET /api/v1/positions`
- `GET /api/v1/scanner`
- `POST /api/v1/start`
- `POST /api/v1/stop`
- `POST /api/v1/emergency_stop`
- `GET /api/v1/ws` (WebSocket)

## Tests

Run full suite:

```powershell
cd d:\volume_algo_trading\trading_bot
.\.venv\Scripts\python.exe -m pytest
```

Current expected status in this workspace:
- `176 passed`

## Safety Notes

- Use `PAPER_TRADE=true` until end-to-end behavior is verified in your environment.
- Keep `DAILY_LOSS_LIMIT_PCT`, `MAX_CONCURRENT_POSITIONS`, and time cutoffs conservative.
- Review and refresh `nse_holidays.json` regularly.
- Keep `.kite_token` local only and never commit it.
- Verify broker policy changes (MIS square-off, margin rules) periodically.

## License / Usage

Internal strategy project. Use at your own risk. Trading involves financial risk.
