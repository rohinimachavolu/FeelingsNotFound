"""Data model: participants, responses, messages, flags (+ page_events for per-page timing)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Round-robin number within source (human / persona); drives the Latin-square row.
    # Assigned only when the four messages are generated (NULL for screened-out / abandoned sessions).
    participant_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="human")  # "human" | "persona"
    pid: Mapped[str | None] = mapped_column(String(128), nullable=True)  # ?pid= (e.g. Prolific ID)
    recruit_source: Mapped[str | None] = mapped_column(String(128), nullable=True)  # ?source=
    latin_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition_order: Mapped[list | None] = mapped_column(JSON, nullable=True)  # index = order position - 1
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="in_progress")
    current_step: Mapped[str] = mapped_column(String(64))
    survey_version: Mapped[str] = mapped_column(String(32))
    persona_card: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class Response(Base):
    __tablename__ = "responses"
    __table_args__ = (UniqueConstraint("participant_id", "item_code", "repeat_index", name="uq_response"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    section: Mapped[str] = mapped_column(String(2))
    # 0 for single-shot items. For F items and Z_RANK: the message's order position (1-4).
    repeat_index: Mapped[int] = mapped_column(Integer, default=0)
    condition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    item_code: Mapped[str] = mapped_column(String(64))
    value: Mapped[str | None] = mapped_column(Text, nullable=True)  # multi-select stored as JSON list
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("participant_id", "condition", name="uq_message"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    condition: Mapped[str] = mapped_column(String(32))
    display_label: Mapped[str] = mapped_column(String(4))  # "A".."D"
    order_position: Mapped[int] = mapped_column(Integer)  # 1..4
    text: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    word_count: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    length_regenerated: Mapped[int] = mapped_column(Integer, default=0)
    temperature_applied: Mapped[float | None] = mapped_column(Float, nullable=True)
    tailoring_targets: Mapped[list | None] = mapped_column(JSON, nullable=True)
    generation_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Flag(Base):
    __tablename__ = "flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    flag_type: Mapped[str] = mapped_column(String(48))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PageEvent(Base):
    """One row per page shown: when it was first shown and when it was submitted."""

    __tablename__ = "page_events"
    __table_args__ = (UniqueConstraint("participant_id", "step", name="uq_page_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    step: Mapped[str] = mapped_column(String(64))
    shown_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
