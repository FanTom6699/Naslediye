from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    signal_threshold: float
    expiration_seconds: int
    min_volatility: float
    rsi_period: int
    atr_period: int
    ema_fast: int
    ema_slow: int
    ws_url: str
    ws_reconnect_seconds: int
    ws_auth_token: str
    ws_subscribe_payload: str
    mock_data: bool
    mock_symbols: list[str]
    webhook_host: str
    webhook_port: int
    webhook_secret: str
    tv_allowed_pairs: list[str]
    signal_cooldown_seconds: int
    signal_batch_window_seconds: int
    active_hours_start: int
    active_hours_end: int
    telegram_chat_id: int | None
    log_level: str
    db_path: str



def _to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    env_path = Path(__file__).resolve().parent / ".env"
    # Keep OS/shell env vars as highest priority and use .env as fallback defaults.
    load_dotenv(dotenv_path=env_path, override=False)

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is empty in .env")

    chat_raw = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    chat_id = int(chat_raw) if chat_raw else None

    symbols_raw = os.getenv("MOCK_SYMBOLS", "EURUSD,GBPUSD,USDJPY")
    symbols = [item.strip() for item in symbols_raw.split(",") if item.strip()]
    tv_pairs_raw = os.getenv(
        "TV_ALLOWED_PAIRS",
        "EURUSD,GBPUSD,USDJPY,AUDUSD,EURJPY,BTCUSD",
    )
    tv_pairs = [item.strip().upper() for item in tv_pairs_raw.split(",") if item.strip()]

    return Settings(
        bot_token=token,
        signal_threshold=float(os.getenv("SIGNAL_THRESHOLD", "6.0")),
        expiration_seconds=int(os.getenv("EXPIRATION_SECONDS", "300")),
        min_volatility=float(os.getenv("MIN_VOLATILITY", "0.0006")),
        rsi_period=int(os.getenv("RSI_PERIOD", "14")),
        atr_period=int(os.getenv("ATR_PERIOD", "14")),
        ema_fast=int(os.getenv("EMA_FAST", "50")),
        ema_slow=int(os.getenv("EMA_SLOW", "200")),
        ws_url=os.getenv("WS_URL", "").strip(),
        ws_reconnect_seconds=int(os.getenv("WS_RECONNECT_SECONDS", "5")),
        ws_auth_token=os.getenv("WS_AUTH_TOKEN", "").strip(),
        ws_subscribe_payload=os.getenv("WS_SUBSCRIBE_PAYLOAD", "").strip(),
        mock_data=_to_bool(os.getenv("MOCK_DATA", "true"), default=True),
        mock_symbols=symbols,
        webhook_host=os.getenv("WEBHOOK_HOST", "0.0.0.0").strip(),
        webhook_port=int(os.getenv("WEBHOOK_PORT", "8088")),
        webhook_secret=os.getenv("WEBHOOK_SECRET", "").strip(),
        tv_allowed_pairs=tv_pairs,
        signal_cooldown_seconds=int(os.getenv("SIGNAL_COOLDOWN_SECONDS", "1800")),
        signal_batch_window_seconds=int(os.getenv("SIGNAL_BATCH_WINDOW_SECONDS", "2")),
        active_hours_start=int(os.getenv("ACTIVE_HOURS_START", "0")),
        active_hours_end=int(os.getenv("ACTIVE_HOURS_END", "24")),
        telegram_chat_id=chat_id,
        log_level=os.getenv("LOG_LEVEL", "INFO").strip(),
        db_path=os.getenv("DB_PATH", "database/market.db").strip(),
    )
