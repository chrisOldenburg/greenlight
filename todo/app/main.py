"""FastAPI-App: Lifespan, Hintergrund-Tasks, Web-Attrappe."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from . import db, telegram
from .api import router
from .config import Settings, load_settings

log = logging.getLogger("todo")

STATIC_DIR = Path(__file__).parent / "static"
PURGE_INTERVAL = 24 * 60 * 60  # taeglich


async def purge_loop(settings: Settings, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=PURGE_INTERVAL)
            return  # stop gesetzt
        except asyncio.TimeoutError:
            pass
        try:
            with db.session(settings.db_path) as conn:
                removed = db.purge_done(conn, settings.keep_done_days)
            if removed:
                log.info("%s erledigte Aufgaben aufgeraeumt", removed)
        except Exception as exc:
            log.warning("Aufraeumen fehlgeschlagen: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)

    with db.session(settings.db_path) as conn:
        db.init_schema(conn)
        removed = db.purge_done(conn, settings.keep_done_days)
    if removed:
        log.info("%s erledigte Aufgaben beim Start aufgeraeumt", removed)

    if not settings.api_key:
        log.warning("API_KEY ist nicht gesetzt — alle /api-Routen antworten mit 401.")

    stop = asyncio.Event()
    tasks = [asyncio.create_task(purge_loop(settings, stop))]
    if settings.telegram_enabled:
        tasks.append(asyncio.create_task(telegram.poll_loop(settings, stop)))
    else:
        log.info("TELEGRAM_ENABLED=false — der Poller bleibt aus.")

    try:
        yield
    finally:
        stop.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def create_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    app = FastAPI(title="Todo Backend", lifespan=lifespan)
    app.state.settings = load_settings()
    app.include_router(router)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/display", include_in_schema=False)
    def display_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "display.html")

    return app


app = create_app()
