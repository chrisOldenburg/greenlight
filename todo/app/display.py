"""Aufbau des Display-Payloads. Reine Funktionen, keine DB, kein I/O."""
from __future__ import annotations

import hashlib
from datetime import datetime

from .db import iso, parse_iso

# Bei 960 px Breite und Schriftgroesse fuer einen Meter Abstand passen
# rund 38 Zeichen auf eine Zeile.
TEXT_MAX = 38


def truncate(text: str, max_len: int = TEXT_MAX) -> str:
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def age_days(created_at: str, now: datetime) -> int:
    delta = now - parse_iso(created_at)
    return max(0, delta.days)


def display_version(items: list[dict]) -> str:
    """Kurzer, stabiler Hash ueber die ausgelieferten Eintraege.

    Bewusst nur ueber id und Text: keine Zeitstempel, kein age_days. Sonst
    wuerde sich die Version taeglich aendern und das E-Ink neu zeichnen.
    """
    payload = "\n".join(f"{item['id']}:{item['text']}" for item in items)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


def build_display(rows: list[dict], limit: int, now: datetime) -> dict:
    """rows sind die offenen Aufgaben in Anzeigereihenfolge."""
    items = [
        {
            "id": row["id"],
            "text": truncate(row["text"]),
            "age_days": age_days(row["created_at"], now),
        }
        for row in rows[:limit]
    ]
    return {
        "version": display_version(items),
        "generated_at": iso(now),
        "open_count": len(rows),
        "items": items,
    }
