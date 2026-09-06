from __future__ import annotations

from tests.conftest import API_KEY


def test_create_done_undone(client):
    created = client.post("/api/tasks", json={"text": "Milch kaufen"})
    assert created.status_code == 201
    task = created.json()
    assert task["text"] == "Milch kaufen"
    assert task["done"] == 0
    assert task["done_at"] is None
    assert task["source"] == "api"

    done = client.post(f"/api/tasks/{task['id']}/done")
    assert done.status_code == 200
    assert done.json()["done"] == 1
    assert done.json()["done_at"] is not None

    undone = client.post(f"/api/tasks/{task['id']}/undone")
    assert undone.status_code == 200
    assert undone.json()["done"] == 0
    assert undone.json()["done_at"] is None


def test_done_is_idempotent(client):
    task = client.post("/api/tasks", json={"text": "Zweimal"}).json()
    first = client.post(f"/api/tasks/{task['id']}/done").json()
    second = client.post(f"/api/tasks/{task['id']}/done").json()
    assert first == second


def test_list_filters_and_orders(client):
    first = client.post("/api/tasks", json={"text": "eins"}).json()
    client.post("/api/tasks", json={"text": "zwei"})
    client.post(f"/api/tasks/{first['id']}/done")

    open_tasks = client.get("/api/tasks", params={"done": "false"}).json()
    assert [t["text"] for t in open_tasks] == ["zwei"]

    everything = client.get("/api/tasks").json()
    # Offene zuerst, erledigte danach.
    assert [t["text"] for t in everything] == ["zwei", "eins"]


def test_delete(client):
    task = client.post("/api/tasks", json={"text": "weg damit"}).json()
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 204
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 404
    assert client.get("/api/tasks").json() == []


def test_unknown_task_is_404(client):
    assert client.post("/api/tasks/999/done").status_code == 404
    assert client.post("/api/tasks/999/undone").status_code == 404


def test_empty_text_is_rejected(client):
    assert client.post("/api/tasks", json={"text": "   "}).status_code == 422
    assert client.post("/api/tasks", json={"text": ""}).status_code == 422


def test_auth_required(client):
    routes = [
        ("get", "/api/tasks"),
        ("post", "/api/tasks/1/done"),
        ("post", "/api/tasks/1/undone"),
        ("delete", "/api/tasks/1"),
        ("get", "/api/display"),
        ("get", "/api/display/version"),
    ]
    for method, path in routes:
        without = getattr(client, method)(path, headers={"X-API-Key": ""})
        assert without.status_code == 401, path
        wrong = getattr(client, method)(path, headers={"X-API-Key": "falsch"})
        assert wrong.status_code == 401, path

    assert client.post("/api/tasks", json={"text": "x"}, headers={"X-API-Key": "falsch"}).status_code == 401


def test_missing_header_is_401(make_client):
    with make_client() as client:
        client.headers.pop("X-API-Key")
        assert client.get("/api/tasks").status_code == 401


def test_healthz_needs_no_auth(client):
    response = client.get("/healthz", headers={"X-API-Key": ""})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_display_page_is_served(client):
    response = client.get("/display")
    assert response.status_code == 200
    assert "M5Paper" in response.text


def test_valid_key_still_works(client):
    assert client.get("/api/tasks", headers={"X-API-Key": API_KEY}).status_code == 200
