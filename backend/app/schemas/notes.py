from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import TimestampedSchema


class NoteMentionDraft(BaseModel):
    raw_text: str = Field(min_length=1, max_length=300)
    normalized_text: str | None = Field(default=None, max_length=300)
    evidence_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class NoteEventDraftPayload(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    event_type: str = Field(default="Note", max_length=80)
    summary: str | None = None
    evidence_text: str | None = None
    started_on: date | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    people: list[str] = []
    organizations: list[str] = []
    locations: list[str] = []


class NoteExtractionPayload(BaseModel):
    people: list[NoteMentionDraft] = []
    organizations: list[NoteMentionDraft] = []
    locations: list[NoteMentionDraft] = []
    events: list[NoteEventDraftPayload] = []


class NoteScanRequest(BaseModel):
    root_path: str
    recursive: bool = True
    max_files: int = Field(default=50, ge=1, le=500)
    include_glob: str = "*.md"


class NoteSourceRead(TimestampedSchema):
    file_path: str
    section_key: str
    heading: str
    note_date: date | None
    body_text: str
    content_hash: str
    source_type: str
    scan_status: str
    extraction_status: str
    last_scanned_at: datetime | None
    last_extracted_at: datetime | None
    extraction_error: str | None


class NoteScanResult(BaseModel):
    files_seen: int
    sections_seen: int
    created: int
    updated: int
    unchanged: int
    sources: list[NoteSourceRead]


class NoteMatchCandidateRead(TimestampedSchema):
    mention_id: UUID
    entity_type: str
    entity_id: UUID | None
    label: str
    subtitle: str | None
    score: float
    rationale: str | None
    rank: int
    is_selected: bool


class NoteEntityMentionRead(TimestampedSchema):
    source_id: UUID
    extraction_run_id: UUID
    entity_type: str
    raw_text: str
    normalized_text: str
    evidence_text: str | None
    confidence: float | None
    review_status: str
    metadata_json: str | None
    candidates: list[NoteMatchCandidateRead] = []


class NoteEventDraftRead(TimestampedSchema):
    source_id: UUID
    extraction_run_id: UUID
    title: str
    event_type: str
    summary: str | None
    evidence_text: str | None
    started_on: date | None
    confidence: float | None
    review_status: str
    metadata_json: str | None


class NoteExtractionRunRead(TimestampedSchema):
    source_id: UUID
    provider_name: str
    model_name: str | None
    prompt_version: str
    status: str
    raw_response_json: str | None
    error_detail: str | None


class NoteSourceDetailRead(NoteSourceRead):
    extraction_runs: list[NoteExtractionRunRead] = []
    mentions: list[NoteEntityMentionRead] = []
    event_drafts: list[NoteEventDraftRead] = []


class NoteReviewUpdate(BaseModel):
    action: str = Field(pattern="^(accept_match|reject|defer|create_new)$")
    matched_entity_type: str | None = None
    matched_entity_id: UUID | None = None
    selected_candidate_id: UUID | None = None
    notes: str | None = None


class NoteMentionUpdate(BaseModel):
    entity_type: str = Field(pattern="^(Person|Organization|Location|Event)$")
    raw_text: str = Field(min_length=1, max_length=300)
    normalized_text: str | None = Field(default=None, max_length=300)
    evidence_text: str | None = None


class NoteCanonicalCreateRequest(BaseModel):
    entity_type: str = Field(pattern="^(Person|Organization|Location|Event)$")
    display_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    primary_location: str | None = None
    relationship_summary: str | None = None
    how_we_met: str | None = None
    notes: str | None = None
    organization_type: str | None = None
    industry: str | None = None
    location_label: str | None = None
    location_address_line: str | None = None
    location_city: str | None = None
    location_region: str | None = None
    location_country: str | None = None
    location_type: str | None = None
    event_title: str | None = None
    event_type: str | None = None
    event_summary: str | None = None
    event_started_at: datetime | None = None
    event_ended_at: datetime | None = None
    selected_person_ids: list[UUID] = []
    selected_organization_ids: list[UUID] = []
    selected_location_ids: list[UUID] = []


class NoteReviewDecisionRead(TimestampedSchema):
    mention_id: UUID
    action: str
    matched_entity_type: str | None
    matched_entity_id: UUID | None
    notes: str | None


class NoteCanonicalCreateResult(BaseModel):
    entity_type: str
    entity_id: UUID
    review_decision: NoteReviewDecisionRead


class NoteExtractionResult(BaseModel):
    source: NoteSourceRead
    run: NoteExtractionRunRead
    mentions: list[NoteEntityMentionRead]
    event_drafts: list[NoteEventDraftRead]


class NoteSourceListResponse(BaseModel):
    items: list[NoteSourceRead]


class NoteProviderStatus(BaseModel):
    provider_name: str
    configured: bool
    reachable: bool
    model_name: str | None
    detail: str | None = None


class NoteProviderHealthResponse(BaseModel):
    primary: NoteProviderStatus
    fallback: NoteProviderStatus | None = None
