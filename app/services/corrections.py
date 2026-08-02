"""Physician-correction capture (Task 12 — correction feedback loop).

When a physician overrides a classification we persist a Correction row AND apply
the override to the Call so the console reflects it. Corrections are candidates
for few-shot inclusion, not automatically used — scripts/promote_corrections.py
promotes selected rows into the runtime few-shot pool in a human-approved step.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Call, Correction

# Fields a physician may override, and the classifier tail they feed.
CORRECTABLE_FIELDS = {"severity", "request_type", "no_callback", "insufficient_detail"}


def record_correction(
    db: Session, call: Call, corrected_field: str, corrected_label: str
) -> Correction:
    """Store the override and apply it to the call. Returns the Correction row."""
    if corrected_field not in CORRECTABLE_FIELDS:
        raise ValueError(
            f"corrected_field must be one of {sorted(CORRECTABLE_FIELDS)}, got {corrected_field!r}"
        )

    model_label = getattr(call, corrected_field, "")
    correction = Correction(
        call_id=call.id,
        transcript=call.transcript,
        corrected_field=corrected_field,
        model_label="" if model_label is None else str(model_label),
        corrected_label=corrected_label,
    )
    db.add(correction)

    # Apply the override so the physician's view is authoritative going forward.
    if corrected_field in ("no_callback", "insufficient_detail"):
        setattr(call, corrected_field, str(corrected_label).lower() in ("1", "true", "yes"))
    else:
        setattr(call, corrected_field, corrected_label)

    db.commit()
    db.refresh(correction)
    db.refresh(call)
    return correction
