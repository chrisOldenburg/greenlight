"""Telegram-Anbindung per Long Polling.

handle_message ist bewusst eine reine Funktion ohne HTTP: der Poller holt
die Updates, handle_message entscheidet, was passiert und was zurueckgeht.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3

import httpx

from . import db
from .config import Settings

log = logging.getLogger("todo.telegram")

API_BASE = "https://api.telegram.org"
OFFSET_KEY = "telegram_offset"
POLL_TIMEOUT = 25  # Sekunden Long-Poll
ERROR_BACKOFF = 5  # Pause nach einem Netzwerkfehler

HELP = (
    "So geht's:\n"
    "\n"
    "Einfach Text schicken — daraus wird eine Aufgabe.\n"
    "Mehrere Zeilen ergeben mehrere Aufgaben.\n"
    "\n"
    "/list — offene Aufgaben mit Nummer\n"
    "/done <Nummer> — Aufgabe abhaken\n"
    "/help — diese Hilfe"
)


def _format_list(tasks: list[dict]) -> str:
    if not tasks:
        return "Keine offenen Aufgaben."
    lines = [f"{i}. {t['text']}" for i, t in enumerate(tasks, start=1)]
    return "Offene Aufgaben:\n" + "\n".join(lines)


def handle_message(
    conn: sqlite3.Connection, chat_id: int, text: str, settings: Settings
) -> str | None:
    """Verarbeitet eine eingehende Nachricht.

    Rueckgabe None heisst: nichts zu tun, keine Antwort senden.
    """
    if settings.setup_mode:
        # Einrichtungsmodus: nur die Chat-ID ins Log, sonst passiert nichts.
        log.info("TELEGRAM_CHAT_ID ist nicht gesetzt. Eingehende Chat-ID: %s", chat_id)
        return None

    if chat_id != settings.telegram_chat_id:
        log.info("Nachricht von fremder Chat-ID %s ignoriert", chat_id)
        return None

    text = (text or "").strip()
    if not text:
        return None

    if text.startswith("/"):
        command, _, argument = text.partition(" ")
        command = command.split("@", 1)[0].lower()  # /done@meinbot -> /done
        argument = argument.strip()

        if command == "/help" or command == "/start":
            return HELP

        if command == "/list":
            return _format_list(db.list_tasks(conn, done=False))

        if command == "/done":
            if not argument.isdigit():
                return "Bitte eine Nummer angeben, zum Beispiel: /done 2"
            open_tasks = db.list_tasks(conn, done=False)
            index = int(argument)
            if index < 1 or index > len(open_tasks):
                return f"Nummer {index} gibt es nicht. /list zeigt die aktuelle Liste."
            task = open_tasks[index - 1]
            db.set_done(conn, task["id"], True)
            return f"Erledigt: {task['text']}"

        return f"Unbekannter Befehl {command}. /help zeigt, was geht."

    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return None

    for line in lines:
        db.add_task(conn, line, source="telegram")

    if len(lines) == 1:
        return f"Notiert: {lines[0]}"
    return "Notiert:\n" + "\n".join(f"- {line}" for line in lines)


async def send_message(
    client: httpx.AsyncClient, token: str, chat_id: int, text: str
) -> None:
    await client.post(
        f"{API_BASE}/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )


async def get_updates(
    client: httpx.AsyncClient, token: str, offset: int
) -> list[dict]:
    response = await client.get(
        f"{API_BASE}/bot{token}/getUpdates",
        params={
            "offset": offset,
            "timeout": POLL_TIMEOUT,
            "allowed_updates": '["message"]',
        },
        timeout=POLL_TIMEOUT + 10,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram meldet einen Fehler: {payload}")
    return payload.get("result", [])


async def _process(
    conn: sqlite3.Connection,
    client: httpx.AsyncClient,
    update: dict,
    settings: Settings,
) -> None:
    message = update.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is None:
        return
    reply = handle_message(conn, int(chat_id), message.get("text", ""), settings)
    if reply is not None:
        await send_message(client, settings.telegram_token, int(chat_id), reply)


async def poll_loop(settings: Settings, stop: asyncio.Event) -> None:
    """Laeuft als Hintergrund-Task, bis stop gesetzt oder der Task gecancelt wird."""
    if not settings.telegram_token:
        log.warning("TELEGRAM_TOKEN fehlt, der Poller startet nicht.")
        return

    log.info("Telegram-Poller gestartet.")
    with db.session(settings.db_path) as conn:
        offset = int(db.meta_get(conn, OFFSET_KEY) or 0)
        async with httpx.AsyncClient() as client:
            while not stop.is_set():
                try:
                    updates = await get_updates(client, settings.telegram_token, offset)
                    for update in updates:
                        offset = int(update["update_id"]) + 1
                        # Offset vor der Verarbeitung merken: lieber eine
                        # Nachricht verlieren als sie doppelt anlegen.
                        db.meta_set(conn, OFFSET_KEY, str(offset))
                        await _process(conn, client, update, settings)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # Netzwerk, Telegram-Fehler, kaputtes JSON
                    log.warning("Poll fehlgeschlagen (%s), neuer Versuch in %ss", exc, ERROR_BACKOFF)
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=ERROR_BACKOFF)
                    except asyncio.TimeoutError:
                        pass
    log.info("Telegram-Poller beendet.")
