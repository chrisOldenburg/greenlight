from __future__ import annotations

import asyncio
from datetime import timedelta

from app import db
from app.telegram import OFFSET_KEY, poll_loop


def test_purge_removes_only_old_done_tasks(conn):
    old = db.add_task(conn, "alt und erledigt", "api")
    recent = db.add_task(conn, "frisch erledigt", "api")
    open_task = db.add_task(conn, "offen", "api")

    db.set_done(conn, old["id"], True)
    db.set_done(conn, recent["id"], True)
    conn.execute(
        "UPDATE tasks SET done_at = ? WHERE id = ?",
        (db.iso(db.utcnow() - timedelta(days=40)), old["id"]),
    )
    conn.commit()

    assert db.purge_done(conn, keep_days=30) == 1
    remaining = [t["id"] for t in db.list_tasks(conn)]
    assert sorted(remaining) == sorted([recent["id"], open_task["id"]])


def test_purge_is_off_for_zero_days(conn):
    task = db.add_task(conn, "erledigt", "api")
    db.set_done(conn, task["id"], True)
    assert db.purge_done(conn, keep_days=0) == 0
    assert len(db.list_tasks(conn)) == 1


def test_meta_roundtrip(conn):
    assert db.meta_get(conn, OFFSET_KEY) is None
    db.meta_set(conn, OFFSET_KEY, "17")
    db.meta_set(conn, OFFSET_KEY, "18")
    assert db.meta_get(conn, OFFSET_KEY) == "18"


def test_poller_stops_without_token(settings):
    config = settings(TELEGRAM_TOKEN="")
    stop = asyncio.Event()
    # Ohne Token darf der Task sauber zurueckkommen statt zu blockieren.
    asyncio.run(asyncio.wait_for(poll_loop(config, stop), timeout=5))
