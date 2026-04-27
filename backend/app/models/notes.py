from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class NoteSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "note_sources"

    file_path: Mapped[str] = mapped_column(String(1000), index=True)
    section_key: Mapped[str] = mapped_column(String(200), index=True)
    heading: Mapped[str] = mapped_column(String(500))
    note_date: Mapped[date | None] = mapped_column(Date, index=True)
    body_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(80), default="Daily note", index=True)
    scan_status: Mapped[str] = mapped_column(String(40), default="Scanned", index=True)
    extraction_status: Mapped[str] = mapped_column(String(40), default="Pending", index=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    extraction_error: Mapped[str | None] = mapped_column(Text)


class NoteExtractionRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "note_extraction_runs"

    source_id: Mapped[UUID] = mapped_column(ForeignKey("note_sources.id", ondelete="CASCADE"), index=True)
    provider_name: Mapped[str] = mapped_column(String(80), index=True)
    model_name: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(80), default="notes-v1")
    status: Mapped[str] = mapped_column(String(40), default="Pending", index=True)
    raw_response_json: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)


class NoteEntityMention(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "note_entity_mentions"

    source_id: Mapped[UUID] = mapped_column(ForeignKey("note_sources.id", ondelete="CASCADE"), index=True)
    extraction_run_id: Mapped[UUID] = mapped_column(ForeignKey("note_extraction_runs.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    raw_text: Mapped[str] = mapped_column(String(300), index=True)
    normalized_text: Mapped[str] = mapped_column(String(300), index=True)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(40), default="Pending", index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text)


class NoteMatchCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "note_match_candidates"

    mention_id: Mapped[UUID] = mapped_column(ForeignKey("note_entity_mentions.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[UUID | None] = mapped_column(index=True)
    label: Mapped[str] = mapped_column(String(300))
    subtitle: Mapped[str | None] = mapped_column(String(500))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[str | None] = mapped_column(Text)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    is_selected: Mapped[bool] = mapped_column(default=False, index=True)


class NoteEventDraft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "note_event_drafts"

    source_id: Mapped[UUID] = mapped_column(ForeignKey("note_sources.id", ondelete="CASCADE"), index=True)
    extraction_run_id: Mapped[UUID] = mapped_column(ForeignKey("note_extraction_runs.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240), index=True)
    event_type: Mapped[str] = mapped_column(String(80), default="Note", index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    started_on: Mapped[date | None] = mapped_column(Date, index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(40), default="Pending", index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text)


class NoteReviewDecision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "note_review_decisions"

    mention_id: Mapped[UUID] = mapped_column(ForeignKey("note_entity_mentions.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    matched_entity_type: Mapped[str | None] = mapped_column(String(40), index=True)
    matched_entity_id: Mapped[UUID | None] = mapped_column(index=True)
    notes: Mapped[str | None] = mapped_column(Text)
