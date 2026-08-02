"""Device registration upsert + delete."""

from app.models import Device


def test_register_device_is_idempotent_upsert(client, auth_headers, db):
    token = "device-token-123"

    r1 = client.post("/devices", json={"token": token}, headers=auth_headers)
    assert r1.status_code == 200
    first_seen = r1.json()["last_seen_at"]

    r2 = client.post("/devices", json={"token": token}, headers=auth_headers)
    assert r2.status_code == 200

    # Exactly one row for the token; last_seen_at refreshed.
    rows = db.query(Device).filter(Device.token == token).all()
    assert len(rows) == 1
    assert r2.json()["last_seen_at"] >= first_seen
    assert r2.json()["platform"] == "ios"


def test_delete_device(client, auth_headers, db):
    token = "to-delete"
    client.post("/devices", json={"token": token}, headers=auth_headers)
    assert db.query(Device).filter(Device.token == token).count() == 1

    resp = client.delete(f"/devices/{token}", headers=auth_headers)
    assert resp.status_code == 200
    assert db.query(Device).filter(Device.token == token).count() == 0


def test_delete_missing_device_404(client, auth_headers):
    resp = client.delete("/devices/nonexistent", headers=auth_headers)
    assert resp.status_code == 404
