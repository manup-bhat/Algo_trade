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

    # ── Group A: Strategy Filter Values ────────────────────────────
    VOLUME_SPIKE_MULTIPLE: float = 15.0
    VOLUME_SMA_PERIOD: int = 500
    HISTORICAL_WARMUP_ENABLED: bool = True
    HISTORICAL_WARMUP_TRADING_DAYS: int = 5
    HISTORICAL_WARMUP_CONCURRENCY: int = 3
    HISTORICAL_WARMUP_BATCH_DELAY_SEC: float = 0.4
    HISTORICAL_WARMUP_RECENT_CANDLES: int = 180
    MIN_TURNOVER_CRORE: float = 8.0
    MIN_PRICE: float = 50.0
    MAX_PRICE: float = 5000.0
    REIGNITION_VOLUME_MULTIPLE: float = 2.0
    REIGNITION_LOOKBACK_CANDLES: int = 3
    # When True, re-ignition compares volume to the MEAN of all dry-up candles
    # (not just max of last N). This is the correct institutional threshold.
    REIGNITION_USE_AVG_VOLUME: bool = True
    # NEW: Re-ignition candle must also be at least this fraction of the original
    # impact candle volume. Prevents noise above a tiny dry-up baseline triggering entry.
    REIGNITION_MIN_PCT_OF_IMPACT: float = 0.08
    MIN_DRYUP_CANDLES: int = 2
    ASHAPE_RED_CANDLE_PCT: float = 0.5
    ASHAPE_VOLUME_MULTIPLE: float = 1.5
    ASHAPE_MIN_CANDLE_COUNT: int = 2
    # Abandon dryup if any single candle's volume exceeds this fraction of the
    # impact candle's volume — signals institutional selling into the spike.
    ASHAPE_IMPACT_VOLUME_PCT: float = 0.70

    # ── v3 NEW: Re-entry after abandonment (Second Chance Scanner) ─────────────
    # When enabled: after a setup is abandoned, the symbol is tracked for a
    # re-entry opportunity using a lower volume threshold than the original scanner.
    RE_ENTRY_ENABLED: bool = True
    RE_ENTRY_MIN_GAP_MINUTES: int = 15      # Minimum minutes after abandonment before re-entry
    RE_ENTRY_VOLUME_MULTIPLE: float = 5.0   # 5x SMA (vs 20x first scan) for re-entry
    RE_ENTRY_MAX_PER_SYMBOL: int = 2        # Max re-entries per symbol per day

    # ── v3 NEW: Opening noise guard ─────────────────────────────────────────
    # Skip candles in the 9 AM hour before this minute (default 30 = 09:30 start).
    # Research: NSE pre-open queue clears 15-30 min post-open; volume structurally
    # elevated, dry-up is impossible in this window.
    SCANNER_START_MINUTE: int = 30

    # ── v3 NEW: Abandonment price buffer ─────────────────────────────────────
    # Chan & Lakonishok (1993): stop-hunt wicks 0.1-0.3% below key levels are
    # normal NSE institutional behaviour. Use candle wick (not close) + buffer.
    ABANDON_PRICE_BUFFER_PCT: float = 0.003

    # ── v3 NEW: Second spike detection ─────────────────────────────────────
    # Keim & Madhavan (1995): institutions leg into positions in tranches.
    # The inter-spike quiet period is the Wyckoff secondary test at 5-min TF.
    SECOND_SPIKE_MIN_RATIO: float = 0.50
    SECOND_SPIKE_MAX_RATIO: float = 1.00
    SECOND_SPIKE_MIN_GAP_MINUTES: int = 15
    SECOND_SPIKE_EXTENDED_GAP_MINUTES: int = 30
    SECOND_SPIKE_VOLUME_FLOOR: float = 10.0
    SECOND_SPIKE_PRICE_ABOVE_HIGH_THRESHOLD: float = 0.80
    SECOND_SPIKE_PRICE_ABOVE_HIGH_PCT: float = 0.005

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
    DRYUP_MAX_MINUTES: int = 20
    MAX_ENTRY_TIME: str = "13:30"
    ENTRY_BUFFER_PCT: float = 0.003
    ENTRY_WIDEN_AFTER_SECONDS: int = 5
    ENTRY_ABANDON_PCT: float = 0.015
    ORDER_FILL_TIMEOUT_SECONDS: int = 30
    # After this hour, no new scan hits are accepted. Conservative cutoff
    # at 14:00 (40 min before 15:20 square-off) ensures setups have time to
    # progress through dry-up before the session ends.
    SCAN_CUTOFF_HOUR: int = 14
    # In LIVE mode (PAPER_TRADE=False), entries hold in ACTION_PENDING_APPROVAL
    # for this many seconds before auto-reverting to MONITORING.
    # Gives the trader time to review while not missing the entry entirely.
    APPROVAL_TIMEOUT_SECONDS: int = 60

    # ── Market Direction Gate ───────────────────────────────────────
    # When enabled, new Phase 2 entries are blocked unless Nifty 50
    # is above its rolling 20-period 5-minute EMA.
    NIFTY_GATE_ENABLED: bool = True
    NIFTY_EMA_PERIOD: int = 20
    # Nifty 50 instrument token on NSE (Kite standard)
    NIFTY_INSTRUMENT_TOKEN: int = 256265
    # India VIX instrument token on NSE (Kite standard)
    VIX_INSTRUMENT_TOKEN: int = 264969
    # During high-VIX environments, raise the minimum turnover filter
    # to exclude noise spikes from highly volatile stocks.
    HIGH_VIX_THRESHOLD: float = 18.0
    HIGH_VIX_TURNOVER_CRORE: float = 12.0

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

    @field_validator("MIN_TURNOVER_CRORE")
    @classmethod
    def validate_min_turnover(cls, v: float) -> float:
        if v < 4.0:
            raise ValueError("MIN_TURNOVER_CRORE must be >= 4.0 (strategy safety floor)")
        return v

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
    def min_turnover_rupees(self) -> float:
        """MIN_TURNOVER_CRORE converted to rupees for hot-path comparison."""
        return self.MIN_TURNOVER_CRORE * 1e7

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
