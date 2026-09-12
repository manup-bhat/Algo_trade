# PostgreSQL Windows Service Setup & Migration Guide

This guide explains how to install and run PostgreSQL natively as a lightweight Windows service (no Docker needed, minimal RAM usage) and migrate existing SQLite (`trading.db`) data to PostgreSQL.

---

## 1. Install PostgreSQL via Windows CLI (winget)

Windows 10 and 11 have `winget` built-in. Run the following command in **PowerShell as Administrator**:

```powershell
winget install PostgreSQL.PostgreSQL.16 --accept-package-agreements --accept-source-agreements
```

> **RAM Efficiency**: Running PostgreSQL as a native Windows service consumes only ~40–60 MB of RAM, compared to Docker Desktop which typically consumes 2–4 GB.

### Verify Installation & Path
By default, PostgreSQL installs into:
`C:\Program Files\PostgreSQL\16\bin`

Add PostgreSQL to your user/system PATH if not already added:
```powershell
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\PostgreSQL\16\bin", [EnvironmentVariableTarget]::Machine)
```

---

## 2. Windows Service Management

PostgreSQL runs automatically in the background as a Windows service named `postgresql-x64-16`.

To verify, start, or stop the service via PowerShell:

```powershell
# Check service status
Get-Service postgresql-x64-16

# Start the service (if stopped)
Start-Service postgresql-x64-16
# or
net start postgresql-x64-16

# Stop the service (if needed)
Stop-Service postgresql-x64-16
```

---

## 3. Create the Database

Open PowerShell or CMD and run:

```powershell
# Connect using psql and create trading_bot database:
psql -U postgres -c "CREATE DATABASE trading_bot;"
```
*(If prompted for a password, enter the password configured during installation or your postgres superuser password).*

---

## 4. Configure Application Environment (`.env`)

In your trading bot root directory, set `DATABASE_URL` in your `.env` file (or system environment):

```env
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/trading_bot
```

Replace `YOUR_PASSWORD` with your PostgreSQL password.

---

## 5. Migrate Data from SQLite to PostgreSQL

We provide an automated migration script [`scripts/migrate_sqlite_to_postgres.py`](file:///d:/volume_algo_trading/trading_bot/scripts/migrate_sqlite_to_postgres.py).

### Step A: Dry Run (Inspect SQLite data without touching PostgreSQL)
```powershell
.venv\Scripts\python scripts/migrate_sqlite_to_postgres.py --dry-run
```

### Step B: Execute Live Migration
```powershell
.venv\Scripts\python scripts/migrate_sqlite_to_postgres.py --pg-url postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/trading_bot
```

The script will automatically:
1. Create all application tables (`strategies`, `signals`, `signal_snapshots`, `order_events`, `trades`, `daily_pnl`) in PostgreSQL.
2. Transfer all existing records in chunks.
3. Automatically update PostgreSQL auto-increment sequences (`setval`) so future inserts work seamlessly.
4. Verify record count parity between SQLite and PostgreSQL.

---

## 6. Verification

Run your test suite with PostgreSQL configured:
```powershell
.venv\Scripts\python -m pytest -q
```
