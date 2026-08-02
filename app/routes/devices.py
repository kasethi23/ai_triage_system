"""Device registration and a dev-only test-push endpoint.

All routes here are bearer-protected (applied at include time in app/main.py).
"""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import Device
from app.services import push

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceRegistration(BaseModel):
    token: str
    platform: str = "ios"


class TestPushRequest(BaseModel):
    # Repo CTAS severity value; defaults to the highest so the demo pushes.
    severity: str = "severe"
    patient_name: str = "Test Patient"
    room: str = "ICU 1"
    summary: str = "This is a ClinRoute test push."


@router.post("")
def register_device(reg: DeviceRegistration) -> dict:
    """Register (or refresh) a device token. Idempotent upsert on token."""
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.token == reg.token).one_or_none()
        if device is None:
            device = Device(token=reg.token, platform=reg.platform, created_at=now)
            db.add(device)
        else:
            device.platform = reg.platform
        device.last_seen_at = now
        db.commit()
        db.refresh(device)
        return {
            "id": device.id,
            "token": device.token,
            "platform": device.platform,
            "created_at": device.created_at.isoformat() if device.created_at else None,
            "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        }
    finally:
        db.close()


@router.delete("/{token}")
def unregister_device(token: str) -> dict:
    """Remove a device token (e.g. on logout / uninstall)."""
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.token == token).one_or_none()
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")
        db.delete(device)
        db.commit()
        return {"deleted": token}
    finally:
        db.close()


@router.post("/test-push")
async def test_push(req: TestPushRequest) -> dict:
    """Dev/demo helper: dispatch a push of a chosen severity to all devices.

    Bearer-protected. Used to drive a deterministic end-to-end push demo
    (see ios/TESTING.md) since scripts/seed_demo.py cannot force a severity.
    """
    db = SessionLocal()
    try:
        call_dict = {
            "id": -1,
            "severity": req.severity,
            "patient_name": req.patient_name,
            "room": req.room,
            "summary": req.summary,
        }
        would_push = push.should_push(req.severity)
        # Reuse the exact sync dispatch path off the event loop.
        await asyncio.to_thread(push.dispatch_push_for_call, db, call_dict)
        return {"severity": req.severity, "would_push": would_push}
    finally:
        db.close()
