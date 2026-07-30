"""APNs push dispatch — the single source of truth for the push policy.

Push policy (repo severity is the CTAS 4-tier enum; see classification.py):

    severity      | APNs behavior
    --------------|--------------------------------------------------------
    severe        | push, interruption-level time-sensitive, distinct sound
    emergent      | push, interruption-level time-sensitive, default sound
    semi-urgent   | no push
    non-urgent    | no push

The product speaks of "critical" / "urgent" calls; those map onto the repo's
`severe` / `emergent` respectively (see display_severity()).

De-identification guard: push payloads travel through Apple's servers, so a
payload carries ONLY severity, the patient name as already stored, the room,
and the summary. Never transcripts, caller identity, or phone numbers. See
SECURITY.md.

A push failure must never break call ingestion — dispatch is wrapped in a
try/except and only ever logs.
"""

import asyncio
import logging

from sqlalchemy.orm import Session

from app import config
from app.models import Call, Device

logger = logging.getLogger(__name__)

# --- Push policy ------------------------------------------------------------

# `severe` is designed to upgrade to Apple's dedicated `critical` interruption
# level once the Critical Alerts entitlement is granted by Apple. That upgrade
# is isolated to this one constant so it can flip in a single place.
SEVERE_INTERRUPTION_LEVEL = "time-sensitive"  # -> "critical" once entitled

DISTINCT_SOUND = "critical.caf"
DEFAULT_SOUND = "default"

# Reasons APNs returns for a token that will never deliver again.
DEAD_TOKEN_REASONS = {"BadDeviceToken", "Unregistered"}


class PushRule:
    __slots__ = ("should_push", "interruption_level", "sound")

    def __init__(self, should_push: bool, interruption_level: str | None, sound: str | None):
        self.should_push = should_push
        self.interruption_level = interruption_level
        self.sound = sound


_NO_PUSH = PushRule(False, None, None)

# severity (repo CTAS value) -> rule. The ONE place the policy table lives.
_POLICY: dict[str, PushRule] = {
    "severe": PushRule(True, SEVERE_INTERRUPTION_LEVEL, DISTINCT_SOUND),
    "emergent": PushRule(True, "time-sensitive", DEFAULT_SOUND),
    "semi-urgent": _NO_PUSH,
    "non-urgent": _NO_PUSH,
}

# Product-facing label shown in the notification title.
_DISPLAY_SEVERITY: dict[str, str] = {
    "severe": "CRITICAL",
    "emergent": "URGENT",
    "semi-urgent": "ROUTINE",
    "non-urgent": "FYI",
}


def rule_for(severity: str) -> PushRule:
    return _POLICY.get(severity, _NO_PUSH)


def should_push(severity: str) -> bool:
    return rule_for(severity).should_push


def display_severity(severity: str) -> str:
    return _DISPLAY_SEVERITY.get(severity, severity.upper())


# --- Payload ----------------------------------------------------------------

_SUMMARY_MAX = 150


def build_message(call_dict: dict, badge: int) -> dict:
    """Build the APNs message body (the value under `message=` for aioapns).

    Pure function — no I/O — so it is trivially testable. Honors the
    de-identification guard: only severity, patient name, room, summary.
    """
    severity = call_dict.get("severity", "")
    rule = rule_for(severity)

    patient = call_dict.get("patient_name") or "Unknown patient"
    room = (call_dict.get("room") or "").strip()
    summary = (call_dict.get("summary") or "")[:_SUMMARY_MAX]
    body = f"{room} — {summary}" if room else summary

    aps: dict = {
        "alert": {
            "title": f"{display_severity(severity)}: {patient}",
            "body": body,
        },
        "sound": rule.sound or DEFAULT_SOUND,
        "badge": badge,
        "thread-id": f"severity-{severity}",
    }
    if rule.interruption_level:
        aps["interruption-level"] = rule.interruption_level

    return {"aps": aps, "call_id": call_dict.get("id")}


def unresolved_alert_count(db: Session) -> int:
    """Badge = count of unresolved calls that warrant an alert (severe+emergent)."""
    alerting = [s for s, r in _POLICY.items() if r.should_push]
    return (
        db.query(Call)
        .filter(Call.resolved.is_(False), Call.severity.in_(alerting))
        .count()
    )


# --- APNs client ------------------------------------------------------------

_key_path: str | None = None


def _ensure_key_file() -> str | None:
    """Materialize the base64-encoded .p8 key to a temp file (once per process)."""
    global _key_path
    if _key_path is not None:
        return _key_path
    if not config.APNS_KEY_BASE64:
        return None
    import base64
    import tempfile

    data = base64.b64decode(config.APNS_KEY_BASE64)
    tmp = tempfile.NamedTemporaryFile(suffix=".p8", delete=False)
    tmp.write(data)
    tmp.close()
    _key_path = tmp.name
    return _key_path


def _get_client():
    """Return a fresh aioapns client, or None if APNs is not configured.

    A fresh client is built per dispatch on purpose: dispatch runs inside a
    short-lived event loop (see dispatch_push_for_call), and an aioapns client
    is bound to the loop it was created in. Tests monkeypatch this function.
    """
    if not (config.APNS_KEY_BASE64 and config.APNS_KEY_ID and config.APNS_TEAM_ID):
        return None
    key_path = _ensure_key_file()
    from aioapns import APNs

    return APNs(
        key=key_path,
        key_id=config.APNS_KEY_ID,
        team_id=config.APNS_TEAM_ID,
        topic=config.APNS_BUNDLE_ID,
        use_sandbox=config.APNS_USE_SANDBOX,
    )


async def _send_one(client, token: str, message: dict) -> tuple[bool, str | None]:
    from aioapns import NotificationRequest, PushType

    request = NotificationRequest(
        device_token=token,
        message=message,
        push_type=PushType.ALERT,
    )
    response = await client.send_notification(request)
    return bool(response.is_successful), getattr(response, "description", None)


async def _dispatch_async(db: Session, call_dict: dict) -> None:
    devices = db.query(Device).all()
    if not devices:
        logger.info("No registered devices; skipping push for call_id=%s", call_dict.get("id"))
        return

    client = _get_client()
    if client is None:
        logger.warning("APNs not configured; skipping push for call_id=%s", call_dict.get("id"))
        return

    message = build_message(call_dict, unresolved_alert_count(db))

    removed = 0
    for device in list(devices):
        ok, reason = await _send_one(client, device.token, message)
        if not ok and reason in DEAD_TOKEN_REASONS:
            db.delete(device)
            removed += 1
    if removed:
        db.commit()
        logger.info("Removed %d dead device token(s)", removed)


def dispatch_push_for_call(db: Session, call_dict: dict) -> None:
    """Fire-and-forget push for a stored call. Never raises.

    Called from sync ingestion (storage.process_call_recording, which runs in a
    worker thread or the seed script — neither has a running event loop) and
    from the dev test-push endpoint (via asyncio.to_thread). Both are safe to
    drive with asyncio.run().
    """
    try:
        severity = call_dict.get("severity", "")
        if not should_push(severity):
            logger.debug("No push for severity=%s (call_id=%s)", severity, call_dict.get("id"))
            return
        asyncio.run(_dispatch_async(db, call_dict))
    except Exception:  # noqa: BLE001 — ingestion must survive any push failure
        logger.exception("Push dispatch failed for call_id=%s", call_dict.get("id"))
