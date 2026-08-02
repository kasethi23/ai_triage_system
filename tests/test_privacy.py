"""Privacy P4 (identifier split) + P7 (re-identification + view logging)."""

from app.models import CallIdentifiers, CallView
from app.services import storage


def _classification():
    return {
        "urgency": "urgent",
        "request_type": "patient_status",
        "no_callback": False,
        "insufficient_detail": False,
        "confidence": 0.9,
        "summary": "s",
        "suggested_action": "a",
        "severity": "critical",
        "patient_name": "Jane Doe",
        "room": "ICU 3",
        "caller_name": "Nurse Kim",
        "caller_role": "charge nurse",
    }


def test_identifiers_are_split_out_of_calls(monkeypatch, db):
    monkeypatch.setattr(storage, "classify_transcript", lambda t: _classification())
    call = storage.process_call_transcript(db, "transcript", "SID-P4", "+1", channel="text")

    d = storage.call_to_dict(call)
    for field in ("patient_name", "room", "caller_name", "caller_role"):
        assert field not in d, f"{field} must not appear in the redacted call dict (P4)"

    ci = db.get(CallIdentifiers, call.id)
    assert ci is not None and ci.patient_name == "Jane Doe" and ci.room == "ICU 3"


def test_reidentify_returns_identifiers_and_logs_a_view(monkeypatch, db):
    monkeypatch.setattr(storage, "classify_transcript", lambda t: _classification())
    call = storage.process_call_transcript(db, "transcript", "SID-P7", "+1", channel="text")

    rec = storage.reidentify(db, call.id, user="physician", route="test")
    assert rec["patient_name"] == "Jane Doe" and rec["room"] == "ICU 3"

    views = db.query(CallView).filter_by(call_id=call.id).all()
    assert len(views) == 1
    assert views[0].user == "physician" and views[0].revealed_identifiers is True


def test_reidentify_missing_call_returns_none(db):
    assert storage.reidentify(db, 999999, user="physician", route="test") is None


def test_identified_endpoint_requires_auth(client):
    r = client.get("/calls/1/identified")
    assert r.status_code in (401, 403)
