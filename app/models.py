from datetime import datetime, timezone

from sqlalchemy import Boolean, Float, Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_sid: Mapped[str] = mapped_column(String, unique=True, index=True)
    from_number: Mapped[str] = mapped_column(String)
    received_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    audio_path: Mapped[str] = mapped_column(String)
    transcript: Mapped[str] = mapped_column(Text, default="")

    urgency: Mapped[str] = mapped_column(String, default="")
    request_type: Mapped[str] = mapped_column(String, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[str] = mapped_column(Text, default="")
    suggested_action: Mapped[str] = mapped_column(Text, default="")
    raw_classification_json: Mapped[str] = mapped_column(Text, default="")

    # Ingestion channel — set from the ingestion path, not LLM-inferred.
    channel: Mapped[str] = mapped_column(String, default="voicemail")

    # LLM-inferred triage flags.
    no_callback: Mapped[bool] = mapped_column(Boolean, default=False)
    insufficient_detail: Mapped[bool] = mapped_column(Boolean, default=False)

    # Conduit Physician Console fields
    severity: Mapped[str] = mapped_column(String, default="fyi")
    patient_name: Mapped[str] = mapped_column(String, default="Unknown")
    room: Mapped[str] = mapped_column(String, default="")
    caller_name: Mapped[str] = mapped_column(String, default="")
    caller_role: Mapped[str] = mapped_column(String, default="")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
