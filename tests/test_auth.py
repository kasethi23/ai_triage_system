"""Bearer auth enforcement on the JSON API."""

from tests.conftest import TEST_TOKEN


def test_calls_rejects_missing_token(client):
    resp = client.get("/calls")
    assert resp.status_code == 401


def test_calls_rejects_wrong_token(client):
    resp = client.get("/calls", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_calls_accepts_correct_token(client, auth_headers):
    resp = client.get("/calls", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_devices_requires_token(client):
    resp = client.post("/devices", json={"token": "abc"})
    assert resp.status_code == 401


def test_sse_accepts_token_query_param(client):
    # EventSource can't set headers; the ?token= fallback must be accepted.
    # Just assert auth passes (200 + event-stream); don't drain the stream.
    with client.stream("GET", f"/calls/stream?token={TEST_TOKEN}") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
