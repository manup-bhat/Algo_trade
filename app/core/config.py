"""
app/core/config.py — All settings via pydantic-settings v2.

Every configurable value in .env is represented here with type safety.
extra="forbid" means unknown env vars raise ValidationError at startup (catches typos).
"""

from __future__ import annotations

import datetime
from functools import lru_cache
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
    )

    # ── Kite Connect Credentials ────────────────────────────────────
    KITE_API_KEY: str = "your_api_key_here"
    KITE_API_SECRET: str = "your_api_secret_here"
    KITE_REDIRECT_URL: str = "http://localhost:8000/api/v1/auth/callback"
    KITE_TOKEN_PATH: str = ".kite_token"

    # ── Infrastructure ──────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    DATABASE_URL: str = "sqlite+aiosqlite:///./trading.db"
    UNIVERSE_FILE: str = "universe.txt"

    # ── Group A: Historical Warmup (engine-wide) ────────────────────
    HISTORICAL_WARMUP_ENABLED: bool = True
    HISTORICAL_WARMUP_TRADING_DAYS: int = 3
    HISTORICAL_WARMUP_CONCURRENCY: int = 8
    HISTORICAL_WARMUP_BATCH_DELAY_SEC: float = 0.2
    HISTORICAL_WARMUP_RECENT_CANDLES: int = 180

    # ── NSE Instrument Tokens (engine-wide, fixed NSE constants) ────
    # Used by Coordinator for Nifty/VIX ticks regardless of strategy.
    NIFTY_INSTRUMENT_TOKEN: int = 256265
    VIX_INSTRUMENT_TOKEN: int = 264969

    # ── Strategy selection ──────────────────────────────────────────
    # Comma-separated strategy ids to run (must match engine/strategies/<id>).
    ENABLED_STRATEGIES: str = "ivbs"

    # ── Group B: SEBI / Regulatory Values ──────────────────────────
    STT_INTRADAY_SELL_PCT: float = 0.00025
    NSE_TXFEE_PER_LAKH_INR: float = 3.25
    SEBI_TXFEE_PER_CRORE_INR: float = 10.0
    GST_ON_BROKERAGE_PCT: float = 18.0
    STAMP_DUTY_BUY_PCT: float = 0.00003

    # ── Group C: Broker / API Operational Values ────────────────────
    BROKERAGE_PER_ORDER_INR: float = 20.0
    ORDER_MAX_RETRIES: int = 3
    ORDER_RETRY_BASE_DELAY_SEC: float = 0.5
    WS_MAX_RECONNECT_ATTEMPTS: int = 10
    WS_RECONNECT_DELAY_SEC: int = 5
    MAX_WS_INSTRUMENTS: int = 3000
    # Delay (ms) between SL cancel and MARKET sell in _initiate_exit()
    EXIT_SL_CANCEL_DELAY_MS: int = 500

    # ── Group D: Global Risk / Execution ────────────────────────────
    # These are engine-wide: they apply across ALL strategies and positions.
    # Strategy-specific parameters (scanner thresholds, dry-up timing, etc.)
    # are in engine/strategies/<id>/config.yaml.
    MAX_ENTRY_TIME: str = "13:30"   # Last allowable entry time (engine-wide squareoff fence)
    # Backtest/replay mode: bypasses wall-clock market-open + entry-cutoff checks
    # in pre-trade checks. Scoped ON only during a backtest run; never live.
    BACKTEST_MODE: bool = False

    # ── Group E: Market Structure Values ───────────────────────────
    MARKET_OPEN_TIME: str = "09:15"
    SQUARE_OFF_TIME: str = "15:20"
    MASS_SQUAREOFF_START_TIME: str = "15:18"
    SESSION_END_TIME: str = "15:25"

    # ── Risk Controls ───────────────────────────────────────────────
    RISK_PER_TRADE_PCT: float = 1.0
    MAX_CONCURRENT_POSITIONS: int = 2
    DAILY_LOSS_LIMIT_PCT: float = 3.0
    MIN_RISK_PER_SHARE_INR: float = 5.0  # Global floor — rejects entries with too-small risk-per-share
    PEAK_MARGIN_SAFETY_BUFFER_PCT: float = 15.0

    # ── Mode Selection ──────────────────────────────────────────────────────────
    # PAPER: all entries simulated with live LTP, no Kite orders placed.
    # LIVE:  real Kite orders placed, requires manual approval via dashboard.
    # SIMULTANEOUS: PAPER auto-entries + LIVE entries with approval.
    #               First signal on a symbol → PAPER, second → LIVE, alternates.
    #               Max 1 LIVE trade per symbol at a time (respects MAX_CONCURRENT).
    TRADE_MODE: str = "PAPER"
    PAPER_TRADE: bool = False  # Legacy — use TRADE_MODE instead

    # ── Server & Operational ────────────────────────────────────────
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    AUTO_START_ENGINE_WITH_BACKEND: bool = True
    AUTO_STOP_ENGINE_WITH_BACKEND: bool = True
    ENGINE_RUNNER_CMD: str = ""
    DASHBOARD_TICK_FLUSH_INTERVAL_MS: int = 250
    DASHBOARD_WS_TICK_INTERVAL_MS: int = 500
    DASHBOARD_WS_HEARTBEAT_INTERVAL_MS: int = 2000

    # ── Validators ──────────────────────────────────────────────────

    @field_validator("HISTORICAL_WARMUP_TRADING_DAYS", "HISTORICAL_WARMUP_CONCURRENCY",
                     "HISTORICAL_WARMUP_RECENT_CANDLES", "DASHBOARD_TICK_FLUSH_INTERVAL_MS",
                     "DASHBOARD_WS_TICK_INTERVAL_MS", "DASHBOARD_WS_HEARTBEAT_INTERVAL_MS")
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("value must be positive")
        return v

    @field_validator("HISTORICAL_WARMUP_BATCH_DELAY_SEC")
    @classmethod
    def validate_non_negative_delay(cls, v: float) -> float:
        if v < 0:
            raise ValueError("HISTORICAL_WARMUP_BATCH_DELAY_SEC must be >= 0")
        return v

    @field_validator("DEBUG", mode="before")
    @classmethod
    def validate_debug_flag(cls, v: Any) -> Any:
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no", "off"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "yes", "on"}:
                return True
        return v

    @field_validator("TRADE_MODE", mode="before")
    @classmethod
    def validate_trade_mode(cls, v: Any) -> Any:
        if isinstance(v, str):
            normalized = v.strip().upper()
            if normalized not in {"PAPER", "LIVE", "SIMULTANEOUS"}:
                raise ValueError(
                    "TRADE_MODE must be PAPER, LIVE, or SIMULTANEOUS"
                )
            return normalized
        return v

    @field_validator("MAX_ENTRY_TIME", "MARKET_OPEN_TIME", "SQUARE_OFF_TIME",
                     "MASS_SQUAREOFF_START_TIME", "SESSION_END_TIME", mode="before")
    @classmethod
    def validate_time_string(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                datetime.time.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Time value '{v}' must be in HH:MM format")
        return v

    @model_validator(mode="after")
    def validate_time_ordering(self) -> "Settings":
        open_t = datetime.time.fromisoformat(self.MARKET_OPEN_TIME)
        squareoff_t = datetime.time.fromisoformat(self.SQUARE_OFF_TIME)
        entry_t = datetime.time.fromisoformat(self.MAX_ENTRY_TIME)
        session_end_t = datetime.time.fromisoformat(self.SESSION_END_TIME)
        if not (open_t < entry_t < squareoff_t):
            raise ValueError(
                "Time ordering must be: MARKET_OPEN < MAX_ENTRY_TIME < SQUARE_OFF_TIME"
            )
        if not (squareoff_t < session_end_t):
            raise ValueError(
                "Time ordering must be: SQUARE_OFF_TIME < SESSION_END_TIME"
            )
        return self

    # ── Computed Properties ─────────────────────────────────────────
    @property
    def is_paper_trade(self) -> bool:
        return self.TRADE_MODE == "PAPER"

    @property
    def is_live_trade(self) -> bool:
        return self.TRADE_MODE == "LIVE"

    @property
    def is_simultaneous(self) -> bool:
        return self.TRADE_MODE == "SIMULTANEOUS"

    def trade_mode_for_symbol(self, symbol: str, entry_count: int = 0) -> str:
        """
        Return PAPER or LIVE for a given entry.

        PAPER: always returns "PAPER"
        LIVE:  always returns "LIVE"
        SIMULTANEOUS: alternates based on entry count for this symbol.
                      entry_count=0 → PAPER (first), 1 → LIVE (second),
                      2 → PAPER (third), etc.
        """
        if self.TRADE_MODE == "PAPER":
            return "PAPER"
        if self.TRADE_MODE == "LIVE":
            return "LIVE"
        # SIMULTANEOUS: alternate, starting with PAPER
        return "LIVE" if entry_count % 2 == 1 else "PAPER"

    @property
    def market_open_time(self) -> datetime.time:
        return datetime.time.fromisoformat(self.MARKET_OPEN_TIME)

    @property
    def square_off_time(self) -> datetime.time:
        return datetime.time.fromisoformat(self.SQUARE_OFF_TIME)

    @property
    def max_entry_time(self) -> datetime.time:
        return datetime.time.fromisoformat(self.MAX_ENTRY_TIME)

    @property
    def session_end_time(self) -> datetime.time:
        return datetime.time.fromisoformat(self.SESSION_END_TIME)

    @property
    def mass_squareoff_start_time(self) -> datetime.time:
        return datetime.time.fromisoformat(self.MASS_SQUAREOFF_START_TIME)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance. Called at startup and in tests."""
    return Settings()


# Module-level singleton for use in engine (avoids circular imports)
settings = get_settings()
