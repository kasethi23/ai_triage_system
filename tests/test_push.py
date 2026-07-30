"""Push policy, payload construction, dead-token pruning, and the guarantee
that a push failure never breaks call ingestion."""

import pytest

from app.models import Call, Device
from app.services import push, storage


# --- Fakes ------------------------------------------------------------------

class FakeResponse:
    def __init__(self, ok=True, description=None):
        self.is_successful = ok
        self.description = description


class FakeClient:
    def __init__(self, ok=True, description=None):
        self.sent = []
        self._ok = ok
        self._desc = description

    async def send_notification(self, request):
        self.sent.append(request)
        return FakeResponse(self._ok, self._desc)


def _register(db, token="tkn"):
    db.add(Device(token=token))
    db.commit()


# --- Policy -----------------------------------------------------------------

@pytest.mark.parametrize(
    "severity,expected",
    [
        ("severe", True),
        ("emergent", True),
        ("semi-urgent", False),
        ("non-urgent", False),
        ("garbage", False),
    ],
)
def test_should_push(severity, expected):
    assert push.should_push(severity) is expected


# --- Payload ----------------------------------------------------------------

def test_build_message_severe_distinct_sound():
    call = {
        "id": 7,
        "severity": "severe",
        "patient_name": "Jane D.",
        "room": "ICU 3",
        "summary": "Chest pain, hypotensive",
    }
    msg = push.build_message(call, badge=4)
    aps = msg["aps"]
    assert aps["alert"]["title"] == "CRITICAL: Jane D."
    assert aps["alert"]["body"].startswith("ICU 3 — ")
    assert aps["interruption-level"] == "time-sensitive"
    assert aps["sound"] == "critical.caf"
    assert aps["thread-id"] == "severity-severe"
    assert aps["badge"] == 4
    assert msg["call_id"] == 7


def test_build_message_emergent_default_sound_and_unknown_patient():
    call = {"id": 1, "severity": "emergent", "patient_name": "", "room": "", "summary": "x"}
    aps = push.build_message(call, badge=0)["aps"]
    assert aps["alert"]["title"] == "URGENT: Unknown patient"
    assert aps["interruption-level"] == "time-sensitive"
    assert aps["sound"] == "default"


def test_build_message_truncates_summary_to_150():
    call = {"id": 1, "severity": "severe", "patient_name": "A", "room": "", "summary": "y" * 300}
    body = push.build_message(call, badge=0)["aps"]["alert"]["body"]
    assert body == "y" * 150
    assert len(body) == 150


# --- Dispatch ---------------------------------------------------------------

def test_no_send_for_routine_and_fyi(monkeypatch, db):
    fake = FakeClient()
    monkeypatch.setattr(push, "_get_client", lambda: fake)
    _register(db)
    for severity in ("semi-urgent", "non-urgent"):
        push.dispatch_push_for_call(
            db, {"id": 1, "severity": severity, "patient_name": "A", "room": "", "summary": "s"}
        )
    assert fake.sent == []


def test_sends_for_alerting_severities(monkeypatch, db):
    fake = FakeClient()
    monkeypatch.setattr(push, "_get_client", lambda: fake)
    _register(db, "tok-1")
    push.dispatch_push_for_call(
        db, {"id": 1, "severity": "severe", "patient_name": "A", "room": "ICU", "summary": "s"}
    )
    assert len(fake.sent) == 1
    assert fake.sent[0].device_token == "tok-1"


def test_bad_device_token_is_removed(monkeypatch, db):
    fake = FakeClient(ok=False, description="BadDeviceToken")
    monkeypatch.setattr(push, "_get_client", lambda: fake)
    _register(db, "dead-token")
    assert db.query(Device).count() == 1

    push.dispatch_push_for_call(
        db, {"id": 1, "severity": "severe", "patient_name": "A", "room": "", "summary": "s"}
    )
    assert db.query(Device).count() == 0


def test_ingestion_survives_push_failure(monkeypatch, db):
    """process_call_recording must still store the call if push blows up."""
    monkeypatch.setattr(storage, "transcribe_audio", lambda path: "transcript text")
    monkeypatch.setattr(
        storage,
        "classify_transcript",
        lambda transcript: {
            "urgency": "urgent",
            "request_type": "patient_status",
            "confidence": 0.9,
            "summary": "summary",
            "suggested_action": "call back",
            "severity": "severe",
            "patient_name": "Jane",
            "room": "ICU 1",
            "caller_name": "Nurse",
            "caller_role": "charge nurse",
        },
    )

    async def boom(*args, **kwargs):
        raise RuntimeError("APNs is down")

    monkeypatch.setattr(push, "_dispatch_async", boom)

    call = storage.process_call_recording(db, b"fake-audio", "CALLSID-1", "+15550001111", "wav")

    assert call.id is not None
    assert db.get(Call, call.id) is not None
    assert call.severity == "severe"
