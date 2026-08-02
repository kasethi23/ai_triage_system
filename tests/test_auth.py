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


def test_sse_stream_rejects_missing_token(client):
    # 401 is raised before the stream opens, so this returns immediately.
    resp = client.get("/calls/stream")
    assert resp.status_code == 401


async def test_bearer_accepts_token_query_param():
    """EventSource can't set headers; the ?token= fallback must be accepted.

    Exercised as a unit test on the dependency — opening the real SSE stream
    would block forever (it never yields without a published event).
    """
    from starlette.requests import Request

    from app.auth import require_bearer

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/calls/stream",
        "headers": [],
        "query_string": f"token={TEST_TOKEN}".encode(),
    }
    # Does not raise -> auth passed via query param.
    await require_bearer(Request(scope), credentials=None)
