from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import Call
from app.services.corrections import record_correction
from app.services.storage import call_to_dict
from app.sse import broker

router = APIRouter(tags=["calls"])


class CorrectionIn(BaseModel):
    corrected_field: str = "severity"
    corrected_label: str


@router.get("/calls")
def list_calls(limit: int = 50) -> list[dict]:
    """Return recent calls, newest first."""
    db = SessionLocal()
    try:
        calls = (
            db.query(Call)
            .order_by(Call.received_at.desc())
            .limit(limit)
            .all()
        )
        return [call_to_dict(c) for c in calls]
    finally:
        db.close()


@router.get("/calls/stream")
async def stream_calls() -> StreamingResponse:
    """SSE stream of new Call events as JSON."""
    return StreamingResponse(broker.stream(), media_type="text/event-stream")


@router.get("/calls/{call_id}/audio")
def get_call_audio(call_id: int) -> FileResponse:
    """Stream the audio file for a given call."""
    db = SessionLocal()
    try:
        call = db.get(Call, call_id)
    finally:
        db.close()

    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    return FileResponse(call.audio_path)


@router.patch("/calls/{call_id}/resolve")
def resolve_call(call_id: int) -> dict:
    """Mark a call as handled/resolved."""
    db = SessionLocal()
    try:
        call = db.get(Call, call_id)
        if call is None:
            raise HTTPException(status_code=404, detail="Call not found")

        call.resolved = True
        db.commit()
        db.refresh(call)
        return call_to_dict(call)
    finally:
        db.close()


@router.patch("/calls/{call_id}/correct")
def correct_call(call_id: int, body: CorrectionIn) -> dict:
    """Record a physician override of a classification (Task 12).

    Persists a Correction row and applies the override to the call. The
    correction becomes a *candidate* for the runtime few-shot pool; promotion is
    a separate, human-approved step (scripts/promote_corrections.py).
    """
    db = SessionLocal()
    try:
        call = db.get(Call, call_id)
        if call is None:
            raise HTTPException(status_code=404, detail="Call not found")
        try:
            record_correction(db, call, body.corrected_field, body.corrected_label)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return call_to_dict(call)
    finally:
        db.close()
