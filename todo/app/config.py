"""Konfiguration ausschliesslich aus Umgebungsvariablen."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    api_key: str
    telegram_token: str
    telegram_chat_id: int
    telegram_enabled: bool
    db_path: str
    display_limit: int
    keep_done_days: int

    @property
    def setup_mode(self) -> bool:
        """Ohne Chat-ID wird nur geloggt, nichts verarbeitet."""
        return self.telegram_chat_id == 0


def load_settings() -> Settings:
    return Settings(
        api_key=os.environ.get("API_KEY", "").strip(),
        telegram_token=os.environ.get("TELEGRAM_TOKEN", "").strip(),
        telegram_chat_id=_int("TELEGRAM_CHAT_ID", 0),
        telegram_enabled=_bool("TELEGRAM_ENABLED", True),
        db_path=os.environ.get("DB_PATH", "/data/tasks.db").strip(),
        display_limit=_int("DISPLAY_LIMIT", 12),
        keep_done_days=_int("KEEP_DONE_DAYS", 30),
    )
