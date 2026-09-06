"""HTTP-API. Alle Routen hier verlangen den X-API-Key-Header."""
from __future__ import annotations

import secrets
from typing import Iterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import db, display
from .config import Settings


class TaskIn(BaseModel):
    text: str = Field(min_length=1)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_conn(settings: Settings = Depends(get_settings)) -> Iterator:
    with db.session(settings.db_path) as conn:
        yield conn


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    # Ohne konfigurierten Schluessel ist die API dicht, nicht offen.
    if not settings.api_key or not x_api_key:
        raise HTTPException(status_code=401, detail="invalid api key")
    if not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="invalid api key")


router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])


@router.get("/tasks")
def get_tasks(done: bool | None = None, conn=Depends(get_conn)) -> list[dict]:
    return db.list_tasks(conn, done=done)


@router.post("/tasks", status_code=201)
def post_task(body: TaskIn, conn=Depends(get_conn)) -> dict:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text must not be empty")
    return db.add_task(conn, text, source="api")


@router.post("/tasks/{task_id}/done")
def post_done(task_id: int, conn=Depends(get_conn)) -> dict:
    task = db.set_done(conn, task_id, True)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.post("/tasks/{task_id}/undone")
def post_undone(task_id: int, conn=Depends(get_conn)) -> dict:
    task = db.set_done(conn, task_id, False)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.delete("/tasks/{task_id}", status_code=204, response_class=Response)
def delete_task(task_id: int, conn=Depends(get_conn)) -> Response:
    if not db.delete_task(conn, task_id):
        raise HTTPException(status_code=404, detail="task not found")
    return Response(status_code=204)


def _payload(conn, settings: Settings) -> dict:
    rows = db.list_tasks(conn, done=False)
    return display.build_display(rows, settings.display_limit, db.utcnow())


@router.get("/display")
def get_display(conn=Depends(get_conn), settings: Settings = Depends(get_settings)) -> dict:
    return _payload(conn, settings)


@router.get("/display/version")
def get_display_version(
    conn=Depends(get_conn), settings: Settings = Depends(get_settings)
) -> dict:
    return {"version": _payload(conn, settings)["version"]}
