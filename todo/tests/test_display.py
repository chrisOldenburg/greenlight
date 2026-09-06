from __future__ import annotations

from datetime import datetime, timezone

from app.display import TEXT_MAX, age_days, build_display, truncate


def test_version_changes_on_create_and_done(client):
    empty = client.get("/api/display/version").json()["version"]

    task = client.post("/api/tasks", json={"text": "Rechnung pruefen"}).json()
    after_create = client.get("/api/display/version").json()["version"]
    assert after_create != empty

    client.post(f"/api/tasks/{task['id']}/done")
    after_done = client.get("/api/display/version").json()["version"]
    assert after_done != after_create
    assert after_done == empty  # wieder leere Liste


def test_version_is_stable_across_calls(client):
    client.post("/api/tasks", json={"text": "bleibt gleich"})
    versions = {client.get("/api/display/version").json()["version"] for _ in range(5)}
    assert len(versions) == 1
    assert versions.pop() == client.get("/api/display").json()["version"]


def test_version_endpoint_returns_only_version(client):
    payload = client.get("/api/display/version").json()
    assert list(payload.keys()) == ["version"]


def test_display_limit_is_respected(make_client):
    with make_client(DISPLAY_LIMIT=3) as client:
        for i in range(7):
            client.post("/api/tasks", json={"text": f"Aufgabe {i}"})

        payload = client.get("/api/display").json()
        assert len(payload["items"]) == 3
        assert payload["open_count"] == 7
        assert [item["text"] for item in payload["items"]] == [
            "Aufgabe 0",
            "Aufgabe 1",
            "Aufgabe 2",
        ]


def test_display_shows_only_open_tasks(client):
    keep = client.post("/api/tasks", json={"text": "offen"}).json()
    gone = client.post("/api/tasks", json={"text": "erledigt"}).json()
    client.post(f"/api/tasks/{gone['id']}/done")

    payload = client.get("/api/display").json()
    assert [item["id"] for item in payload["items"]] == [keep["id"]]
    assert payload["open_count"] == 1


def test_text_is_truncated_for_the_display(client):
    client.post("/api/tasks", json={"text": "A" * 100})
    item = client.get("/api/display").json()["items"][0]
    assert len(item["text"]) == TEXT_MAX
    assert item["text"].endswith("…")


def test_truncate_leaves_short_text_alone():
    assert truncate("kurz") == "kurz"
    assert truncate("mehrere    Leerzeichen") == "mehrere Leerzeichen"


def test_age_days_counts_full_days():
    now = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)
    assert age_days("2026-09-06T07:00:00Z", now) == 0
    assert age_days("2026-09-03T08:00:00Z", now) == 3
    assert age_days("2026-09-07T08:00:00Z", now) == 0  # keine negativen Werte


def test_version_ignores_timestamps():
    rows = [{"id": 1, "text": "gleich", "created_at": "2026-09-01T08:00:00Z"}]
    early = build_display(rows, 12, datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc))
    late = build_display(rows, 12, datetime(2026, 12, 24, 8, 0, tzinfo=timezone.utc))
    assert early["version"] == late["version"]
    assert early["items"][0]["age_days"] != late["items"][0]["age_days"]
