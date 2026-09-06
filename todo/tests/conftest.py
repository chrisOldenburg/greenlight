from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import load_settings

API_KEY = "test-key"


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    """Baut eine App mit frischer SQLite-Datei im Temp-Verzeichnis."""

    def factory(**overrides):
        env = {
            "API_KEY": API_KEY,
            "TELEGRAM_ENABLED": "false",
            "TELEGRAM_TOKEN": "",
            "TELEGRAM_CHAT_ID": "0",
            "DB_PATH": str(tmp_path / "tasks.db"),
            "DISPLAY_LIMIT": "12",
            "KEEP_DONE_DAYS": "30",
        }
        env.update({k: str(v) for k, v in overrides.items()})
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        from app.main import create_app

        client = TestClient(create_app())
        client.headers.update({"X-API-Key": API_KEY})
        return client

    return factory


@pytest.fixture
def client(make_client):
    with make_client() as running:
        yield running


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(str(tmp_path / "direct.db"))
    db.init_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def settings(monkeypatch, tmp_path):
    def factory(**overrides):
        env = {
            "API_KEY": API_KEY,
            "TELEGRAM_ENABLED": "true",
            "TELEGRAM_TOKEN": "token",
            "TELEGRAM_CHAT_ID": "4711",
            "DB_PATH": str(tmp_path / "direct.db"),
            "DISPLAY_LIMIT": "12",
            "KEEP_DONE_DAYS": "30",
        }
        env.update({k: str(v) for k, v in overrides.items()})
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        return load_settings()

    return factory
