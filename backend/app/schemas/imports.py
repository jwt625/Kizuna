from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.event import EventType


class PeopleImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[str]


class NoteJsonlSource(BaseModel):
    key: str = Field(min_length=1, max_length=180)
    heading: str = Field(min_length=1, max_length=500)
    note_date: date


class NoteJsonlMention(BaseModel):
    ref: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    entity_type: Literal["Person", "Organization", "Location"]
    raw_text: str = Field(min_length=1, max_length=300)
    normalized_text: str | None = Field(default=None, max_length=300)
    evidence_text: str | None = None
    confidence: float = Field(ge=0, le=1)


class NoteJsonlEvent(BaseModel):
    ref: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    title: str = Field(min_length=1, max_length=240)
    event_type: EventType
    occurred_on: date
    occurred_at: datetime | None = None
    date_precision: Literal["date", "datetime", "approximate"] = "date"
    summary: str | None = None
    evidence_text: str | None = None
    confidence: float = Field(ge=0, le=1)
    participant_refs: list[str] = []
    organization_refs: list[str] = []
    location_refs: list[str] = []
    review_reasons: list[str] = []

    @model_validator(mode="after")
    def validate_time_and_refs(self) -> "NoteJsonlEvent":
        if self.occurred_at is not None and self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        if self.date_precision == "datetime" and self.occurred_at is None:
            raise ValueError("date_precision datetime requires occurred_at")
        for field in ("participant_refs", "organization_refs", "location_refs"):
            refs = getattr(self, field)
            if len(refs) != len(set(refs)):
                raise ValueError(f"{field} must not contain duplicates")
        return self


class NoteJsonlRecord(BaseModel):
    schema_version: Literal["kizuna.note-extraction.v1"]
    source: NoteJsonlSource
    mentions: list[NoteJsonlMention] = []
    events: list[NoteJsonlEvent] = []

    @model_validator(mode="after")
    def validate_refs(self) -> "NoteJsonlRecord":
        mention_refs = [mention.ref for mention in self.mentions]
        if len(mention_refs) != len(set(mention_refs)):
            raise ValueError("mention refs must be unique within a record")
        event_refs = [event.ref for event in self.events]
        if len(event_refs) != len(set(event_refs)):
            raise ValueError("event refs must be unique within a record")
        mention_types = {mention.ref: mention.entity_type for mention in self.mentions}
        expected = {
            "participant_refs": "Person",
            "organization_refs": "Organization",
            "location_refs": "Location",
        }
        for event in self.events:
            for field, entity_type in expected.items():
                for ref in getattr(event, field):
                    if mention_types.get(ref) != entity_type:
                        raise ValueError(f"{event.ref}.{field} references missing or wrong-type mention {ref}")
        return self


class NoteJsonlImportResult(BaseModel):
    lines_received: int
    staged: int
    skipped: int
    errors: list[str]
    source_ids: list[str]


class NoteEventReviewRequest(BaseModel):
    action: Literal["commit", "reject"]


class NoteEventReviewResult(BaseModel):
    event_draft_id: str
    status: str
    canonical_event_id: str | None = None
