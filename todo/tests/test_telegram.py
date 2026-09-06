"""Der Poller wird nicht ueber HTTP getestet, nur die reine Verarbeitung."""
from __future__ import annotations

from app import db
from app.telegram import HELP, handle_message

CHAT = 4711


def test_freetext_creates_a_task(conn, settings):
    config = settings()
    reply = handle_message(conn, CHAT, "Rechnung Stadtwerke pruefen", config)
    assert reply == "Notiert: Rechnung Stadtwerke pruefen"

    tasks = db.list_tasks(conn, done=False)
    assert [t["text"] for t in tasks] == ["Rechnung Stadtwerke pruefen"]
    assert tasks[0]["source"] == "telegram"


def test_multiline_creates_one_task_per_line(conn, settings):
    config = settings()
    reply = handle_message(conn, CHAT, "Milch\n\n  Brot  \nKaese", config)
    assert reply == "Notiert:\n- Milch\n- Brot\n- Kaese"
    assert [t["text"] for t in db.list_tasks(conn, done=False)] == ["Milch", "Brot", "Kaese"]


def test_list_numbers_open_tasks(conn, settings):
    config = settings()
    handle_message(conn, CHAT, "eins\nzwei", config)
    assert handle_message(conn, CHAT, "/list", config) == "Offene Aufgaben:\n1. eins\n2. zwei"


def test_list_when_empty(conn, settings):
    assert handle_message(conn, CHAT, "/list", settings()) == "Keine offenen Aufgaben."


def test_done_uses_the_position_from_list(conn, settings):
    config = settings()
    handle_message(conn, CHAT, "eins\nzwei\ndrei", config)

    assert handle_message(conn, CHAT, "/done 2", config) == "Erledigt: zwei"
    assert [t["text"] for t in db.list_tasks(conn, done=False)] == ["eins", "drei"]

    # Die Nummerierung folgt der neuen Liste, nicht der Datenbank-ID.
    assert handle_message(conn, CHAT, "/list", config) == "Offene Aufgaben:\n1. eins\n2. drei"
    assert handle_message(conn, CHAT, "/done 2", config) == "Erledigt: drei"


def test_done_with_bad_argument(conn, settings):
    config = settings()
    handle_message(conn, CHAT, "eins", config)
    assert "Nummer" in handle_message(conn, CHAT, "/done", config)
    assert "Nummer" in handle_message(conn, CHAT, "/done abc", config)
    assert "gibt es nicht" in handle_message(conn, CHAT, "/done 9", config)
    assert "gibt es nicht" in handle_message(conn, CHAT, "/done 0", config)
    assert db.list_tasks(conn, done=False)  # nichts abgehakt


def test_command_with_bot_suffix(conn, settings):
    assert handle_message(conn, CHAT, "/help@meinbot", settings()) == HELP


def test_help_and_start(conn, settings):
    config = settings()
    assert handle_message(conn, CHAT, "/help", config) == HELP
    assert handle_message(conn, CHAT, "/start", config) == HELP


def test_unknown_command(conn, settings):
    reply = handle_message(conn, CHAT, "/quatsch", settings())
    assert "Unbekannter Befehl" in reply
    assert db.list_tasks(conn) == []


def test_foreign_chat_is_ignored(conn, settings):
    assert handle_message(conn, 999, "heimlich", settings()) is None
    assert db.list_tasks(conn) == []


def test_setup_mode_processes_nothing(conn, settings, caplog):
    config = settings(TELEGRAM_CHAT_ID=0)
    with caplog.at_level("INFO"):
        assert handle_message(conn, 12345, "hallo", config) is None
    assert "12345" in caplog.text
    assert db.list_tasks(conn) == []


def test_empty_message_is_ignored(conn, settings):
    config = settings()
    assert handle_message(conn, CHAT, "   ", config) is None
    assert handle_message(conn, CHAT, "", config) is None
    assert db.list_tasks(conn) == []
