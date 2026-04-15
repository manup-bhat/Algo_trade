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

    # ── Group A: Strategy Filter Values ────────────────────────────
    VOLUME_SPIKE_MULTIPLE: float = 20.0
    VOLUME_SMA_PERIOD: int = 500
    MIN_TURNOVER_CRORE: float = 8.0
    MIN_PRICE: float = 50.0
    MAX_PRICE: float = 5000.0
    REIGNITION_VOLUME_MULTIPLE: float = 1.5
    REIGNITION_LOOKBACK_CANDLES: int = 3
    MIN_DRYUP_CANDLES: int = 2
    ASHAPE_RED_CANDLE_PCT: float = 0.5
    ASHAPE_VOLUME_MULTIPLE: float = 1.5
    ASHAPE_MIN_CANDLE_COUNT: int = 2

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
    EXIT_SL_CANCEL_DELAY_MS: int = 500

    # ── Group D: Strategy Calibration Values ───────────────────────
    DRYUP_MAX_MINUTES: int = 10
    MAX_ENTRY_TIME: str = "14:00"
    ENTRY_BUFFER_PCT: float = 0.003
    ENTRY_WIDEN_AFTER_SECONDS: int = 5
    ENTRY_ABANDON_PCT: float = 0.015
    ORDER_FILL_TIMEOUT_SECONDS: int = 30

    # ── Group E: Market Structure Values ───────────────────────────
    MARKET_OPEN_TIME: str = "09:15"
    SQUARE_OFF_TIME: str = "15:20"
    MASS_SQUAREOFF_START_TIME: str = "15:18"
    SESSION_END_TIME: str = "15:25"

    # ── Risk Controls ───────────────────────────────────────────────
    RISK_PER_TRADE_PCT: float = 1.0
    MAX_CONCURRENT_POSITIONS: int = 2
    DAILY_LOSS_LIMIT_PCT: float = 3.0
    MIN_RISK_PER_SHARE_INR: float = 5.0
    PEAK_MARGIN_SAFETY_BUFFER_PCT: float = 15.0

    # ── Server & Operational ────────────────────────────────────────
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    PAPER_TRADE: bool = False
    AUTO_START_ENGINE_WITH_BACKEND: bool = False
    AUTO_STOP_ENGINE_WITH_BACKEND: bool = True
    ENGINE_RUNNER_CMD: str = ""

    # ── Validators ──────────────────────────────────────────────────

    @field_validator("MIN_TURNOVER_CRORE")
    @classmethod
    def validate_min_turnover(cls, v: float) -> float:
        if v < 4.0:
            raise ValueError("MIN_TURNOVER_CRORE must be >= 4.0 (strategy safety floor)")
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
        if not (open_t < entry_t < squareoff_t):
            raise ValueError(
                "Time ordering must be: MARKET_OPEN < MAX_ENTRY_TIME < SQUARE_OFF_TIME"
            )
        return self

    # ── Computed Properties ─────────────────────────────────────────

    @property
    def min_turnover_rupees(self) -> float:
        """MIN_TURNOVER_CRORE converted to rupees for hot-path comparison."""
        return self.MIN_TURNOVER_CRORE * 1e7

    @property
    def is_paper_trade(self) -> bool:
        return self.PAPER_TRADE

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
