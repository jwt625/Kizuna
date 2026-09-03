from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, func, select

from app.api.deps import DbSession
from app.models import (
    InteractionEvent,
    Location,
    NoteEntityMention,
    NoteEventDraft,
    NoteExtractionRun,
    NoteMatchCandidate,
    NoteReviewDecision,
    NoteSource,
    Organization,
    Person,
)
from app.schemas.notes import (
    NoteCanonicalCreateRequest,
    NoteCanonicalCreateResult,
    NoteEntityMentionRead,
    NoteEventDraftUpdate,
    NoteEventDraftPayload,
    NoteEventDraftRead,
    NoteExtractionResult,
    NoteExtractionRunRead,
    NoteMentionUpdate,
    NoteManualMatchRequest,
    NoteExtractionPayload,
    NoteMatchCandidateRead,
    NoteProviderHealthResponse,
    NoteReviewDecisionRead,
    NoteReviewUpdate,
    NoteReviewSummaryResponse,
    NoteScanRequest,
    NoteScanResult,
    NoteSourceDetailRead,
    NoteSourceListResponse,
    NoteSourceRead,
    NoteSourceReviewSummary,
)
from app.schemas.imports import NoteEventReviewRequest, NoteEventReviewResult
from app.services.note_llm import PROMPT_VERSION, get_note_extraction_provider
from app.services.note_parsing import normalize_mention_text, parse_note_sections
from app.services.note_retrieval import find_candidate_matches
from app.services.note_jsonl import commit_event_draft, event_reference_summary, reject_event_draft


router = APIRouter(prefix="/notes", tags=["notes"])


@router.post("/scan", response_model=NoteScanResult, status_code=status.HTTP_201_CREATED)
def scan_notes(payload: NoteScanRequest, db: DbSession) -> NoteScanResult:
    root = Path(payload.root_path).expanduser()
    if not root.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="root_path does not exist")
    files = sorted(root.rglob(payload.include_glob) if payload.recursive else root.glob(payload.include_glob))[: payload.max_files]

    created = 0
    updated = 0
    unchanged = 0
    sections_seen = 0
    touched_ids: list[UUID] = []
    scanned_at = datetime.now(timezone.utc)

    for file_path in files:
        if file_path.is_dir():
            continue
        text = file_path.read_text(encoding="utf-8")
        for section in parse_note_sections(text):
            sections_seen += 1
            existing = db.scalar(
                select(NoteSource).where(NoteSource.file_path == str(file_path), NoteSource.section_key == section.section_key)
            )
            if existing is None:
                source = NoteSource(
                    file_path=str(file_path),
                    section_key=section.section_key,
                    heading=section.heading,
                    note_date=section.note_date,
                    body_text=section.body_text,
                    content_hash=section.content_hash,
                    last_scanned_at=scanned_at,
                )
                db.add(source)
                db.flush()
                touched_ids.append(source.id)
                created += 1
                continue
            if existing.content_hash == section.content_hash:
                existing.last_scanned_at = scanned_at
                unchanged += 1
                touched_ids.append(existing.id)
                continue
            existing.heading = section.heading
            existing.note_date = section.note_date
            existing.body_text = section.body_text
            existing.content_hash = section.content_hash
            existing.scan_status = "Scanned"
            existing.extraction_status = "Pending"
            existing.extraction_error = None
            existing.last_scanned_at = scanned_at
            updated += 1
            touched_ids.append(existing.id)

    db.commit()
    sources = list(db.scalars(select(NoteSource).where(NoteSource.id.in_(touched_ids)).order_by(NoteSource.note_date, NoteSource.file_path)))
    return NoteScanResult(
        files_seen=len(files),
        sections_seen=sections_seen,
        created=created,
        updated=updated,
        unchanged=unchanged,
        sources=[NoteSourceRead.model_validate(source) for source in sources],
    )


@router.get("/sources", response_model=NoteSourceListResponse)
def list_note_sources(
    db: DbSession,
    extraction_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> NoteSourceListResponse:
    statement = select(NoteSource).order_by(NoteSource.note_date.desc().nullslast(), NoteSource.created_at.desc()).limit(limit)
    if extraction_status:
        statement = statement.where(NoteSource.extraction_status == extraction_status)
    items = list(db.scalars(statement))
    return NoteSourceListResponse(items=[NoteSourceRead.model_validate(item) for item in items])


@router.get("/review-summary", response_model=NoteReviewSummaryResponse)
def note_review_summary(db: DbSession, limit: int = Query(default=200, ge=1, le=500)) -> NoteReviewSummaryResponse:
    sources = list(
        db.scalars(select(NoteSource).order_by(NoteSource.note_date.desc().nullslast(), NoteSource.created_at.desc()).limit(limit))
    )
    source_ids = [source.id for source in sources]
    mention_counts = _status_counts(db, NoteEntityMention, source_ids)
    event_counts = _status_counts(db, NoteEventDraft, source_ids)
    items: list[NoteSourceReviewSummary] = []
    for source in sources:
        mentions = mention_counts.get(source.id, {})
        events = event_counts.get(source.id, {})
        mention_total = sum(mentions.values())
        event_total = sum(events.values())
        pending_mentions = sum(mentions.get(key, 0) for key in ("Pending", "Deferred", "Create new"))
        resolved_mentions = sum(mentions.get(key, 0) for key in ("Auto matched", "Accepted", "Created"))
        rejected_mentions = mentions.get("Rejected", 0)
        ready_events = events.get("Ready", 0)
        needs_review_events = events.get("Needs review", 0)
        imported_events = events.get("Imported", 0)
        rejected_events = events.get("Rejected", 0)
        if event_total == 0:
            review_status = "No events"
        elif imported_events == event_total:
            review_status = "Imported"
        elif rejected_events == event_total:
            review_status = "Rejected"
        elif imported_events:
            review_status = "Partially imported"
        elif pending_mentions or needs_review_events:
            review_status = "Needs review"
        elif ready_events:
            review_status = "Ready"
        else:
            review_status = "Staged"
        items.append(
            NoteSourceReviewSummary(
                id=source.id,
                heading=source.heading,
                note_date=source.note_date,
                source_type=source.source_type,
                extraction_status=source.extraction_status,
                review_status=review_status,
                mention_total=mention_total,
                pending_mentions=pending_mentions,
                resolved_mentions=resolved_mentions,
                rejected_mentions=rejected_mentions,
                event_total=event_total,
                ready_events=ready_events,
                needs_review_events=needs_review_events,
                imported_events=imported_events,
                rejected_events=rejected_events,
            )
        )
    return NoteReviewSummaryResponse(items=items)


@router.get("/sources/{source_id}", response_model=NoteSourceDetailRead)
def get_note_source(source_id: UUID, db: DbSession) -> NoteSourceDetailRead:
    source = db.scalar(select(NoteSource).where(NoteSource.id == source_id))
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note source not found")
    return _serialize_source_detail(db, source)


@router.get("/provider-health", response_model=NoteProviderHealthResponse)
def note_provider_health() -> NoteProviderHealthResponse:
    provider = get_note_extraction_provider()
    return NoteProviderHealthResponse(primary=provider.healthcheck(), fallback=provider.fallback_healthcheck())


@router.post("/sources/{source_id}/extract", response_model=NoteExtractionResult, status_code=status.HTTP_201_CREATED)
def extract_note_source(source_id: UUID, db: DbSession) -> NoteExtractionResult:
    source = db.scalar(select(NoteSource).where(NoteSource.id == source_id))
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note source not found")

    provider = get_note_extraction_provider()
    run = NoteExtractionRun(
        source_id=source.id,
        provider_name=provider.provider_name(),
        model_name=provider.model_name(),
        prompt_version=PROMPT_VERSION,
        status="Running",
    )
    db.add(run)
    db.flush()

    try:
        result = provider.extract(source.heading, source.note_date.isoformat() if source.note_date else None, source.body_text)
        run.status = "Completed"
        run.raw_response_json = result.model_dump_json()
        source.extraction_status = "Completed"
        source.last_extracted_at = datetime.now(timezone.utc)
        source.extraction_error = None
    except Exception as exc:
        run.status = "Failed"
        run.error_detail = str(exc)
        source.extraction_status = "Failed"
        source.extraction_error = str(exc)
        source.last_extracted_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    db.execute(delete(NoteMatchCandidate).where(NoteMatchCandidate.mention_id.in_(select(NoteEntityMention.id).where(NoteEntityMention.source_id == source.id))))
    db.execute(delete(NoteEntityMention).where(NoteEntityMention.source_id == source.id))
    db.execute(delete(NoteEventDraft).where(NoteEventDraft.source_id == source.id))

    mentions = _create_mentions(db, source, run, result)
    event_drafts = _create_event_drafts(db, source, run, result.events)
    db.commit()
    return NoteExtractionResult(
        source=NoteSourceRead.model_validate(source),
        run=NoteExtractionRunRead.model_validate(run),
        mentions=[_serialize_mention(db, mention) for mention in mentions],
        event_drafts=[NoteEventDraftRead.model_validate(event_draft) for event_draft in event_drafts],
    )


@router.post("/mentions/{mention_id}/review", response_model=NoteReviewDecisionRead)
def review_note_mention(mention_id: UUID, payload: NoteReviewUpdate, db: DbSession) -> NoteReviewDecisionRead:
    mention = db.scalar(select(NoteEntityMention).where(NoteEntityMention.id == mention_id))
    if mention is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note mention not found")

    if payload.action == "accept_match" and payload.selected_candidate_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="accept_match requires a selected candidate")

    if payload.selected_candidate_id is not None:
        candidates = list(db.scalars(select(NoteMatchCandidate).where(NoteMatchCandidate.mention_id == mention.id)))
        found = False
        for candidate in candidates:
            candidate.is_selected = candidate.id == payload.selected_candidate_id
            if candidate.is_selected:
                payload.matched_entity_type = candidate.entity_type
                payload.matched_entity_id = candidate.entity_id
                found = True
        if not found:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected candidate does not belong to mention")

    mention.review_status = {
        "accept_match": "Accepted",
        "reject": "Rejected",
        "defer": "Deferred",
        "create_new": "Create new",
    }[payload.action]
    decision = NoteReviewDecision(
        mention_id=mention.id,
        action=payload.action,
        matched_entity_type=payload.matched_entity_type,
        matched_entity_id=payload.matched_entity_id,
        notes=payload.notes,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return NoteReviewDecisionRead.model_validate(decision)


@router.post("/event-drafts/{draft_id}/review", response_model=NoteEventReviewResult)
def review_event_draft(
    draft_id: UUID, payload: NoteEventReviewRequest, db: DbSession
) -> NoteEventReviewResult:
    draft = db.get(NoteEventDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event draft not found")
    if payload.action == "reject":
        reject_event_draft(draft)
        db.commit()
        return NoteEventReviewResult(event_draft_id=str(draft.id), status=draft.review_status)
    event = commit_event_draft(db, draft)
    db.commit()
    return NoteEventReviewResult(
        event_draft_id=str(draft.id), status=draft.review_status, canonical_event_id=str(event.id)
    )


@router.patch("/mentions/{mention_id}", response_model=NoteEntityMentionRead)
def update_note_mention(mention_id: UUID, payload: NoteMentionUpdate, db: DbSession) -> NoteEntityMentionRead:
    mention = db.scalar(select(NoteEntityMention).where(NoteEntityMention.id == mention_id))
    if mention is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note mention not found")
    mention.entity_type = payload.entity_type
    mention.raw_text = payload.raw_text
    mention.normalized_text = normalize_mention_text(payload.normalized_text or payload.raw_text)
    mention.evidence_text = payload.evidence_text
    mention.review_status = "Pending"
    db.execute(delete(NoteMatchCandidate).where(NoteMatchCandidate.mention_id == mention.id))
    db.execute(delete(NoteReviewDecision).where(NoteReviewDecision.mention_id == mention.id))
    candidates = find_candidate_matches(db, mention.entity_type, mention.raw_text, mention.normalized_text)
    for rank, candidate in enumerate(candidates, start=1):
        db.add(
            NoteMatchCandidate(
                mention_id=mention.id,
                entity_type=candidate.entity_type,
                entity_id=candidate.entity_id,
                label=candidate.label,
                subtitle=candidate.subtitle,
                score=candidate.score,
                rationale=candidate.rationale,
                rank=rank,
            )
        )
    db.commit()
    return _serialize_mention(db, mention)


@router.post("/mentions/{mention_id}/match", response_model=NoteReviewDecisionRead)
def manually_match_note_mention(
    mention_id: UUID, payload: NoteManualMatchRequest, db: DbSession
) -> NoteReviewDecisionRead:
    mention = db.get(NoteEntityMention, mention_id)
    if mention is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note mention not found")
    if mention.entity_type != payload.entity_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Entity type does not match mention")
    model = {"Person": Person, "Organization": Organization, "Location": Location}[payload.entity_type]
    entity = db.get(model, payload.entity_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canonical entity not found")
    for candidate in db.scalars(select(NoteMatchCandidate).where(NoteMatchCandidate.mention_id == mention.id)):
        candidate.is_selected = candidate.entity_type == payload.entity_type and candidate.entity_id == payload.entity_id
    mention.review_status = "Accepted"
    decision = NoteReviewDecision(
        mention_id=mention.id,
        action="accept_match",
        matched_entity_type=payload.entity_type,
        matched_entity_id=payload.entity_id,
        notes="Manually selected existing entity",
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return NoteReviewDecisionRead.model_validate(decision)


@router.patch("/event-drafts/{draft_id}", response_model=NoteEventDraftRead)
def update_event_draft(draft_id: UUID, payload: NoteEventDraftUpdate, db: DbSession) -> NoteEventDraftRead:
    draft = db.get(NoteEventDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event draft not found")
    if draft.review_status == "Imported":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Imported event drafts cannot be edited")
    metadata = json.loads(draft.metadata_json or "{}")
    changes = payload.model_dump(exclude_unset=True)
    for field in ("title", "event_type", "started_on", "summary", "evidence_text"):
        if field in changes:
            setattr(draft, field, changes[field])
    if "started_on" in changes and changes["started_on"] is not None:
        metadata["occurred_on"] = changes["started_on"].isoformat()
    for field in ("title", "event_type", "summary", "evidence_text", "participant_refs", "organization_refs", "location_refs"):
        if field in changes:
            metadata[field] = changes[field]
    _validate_event_refs(db, draft, metadata)
    metadata["review_reasons"] = []
    draft.metadata_json = json.dumps(metadata, default=str)
    draft.review_status = "Ready" if not event_reference_summary(db, draft)["unresolved_refs"] else "Needs review"
    db.commit()
    return _serialize_event_draft(db, draft)


@router.post("/mentions/{mention_id}/create-canonical", response_model=NoteCanonicalCreateResult, status_code=status.HTTP_201_CREATED)
def create_canonical_from_note_mention(
    mention_id: UUID, payload: NoteCanonicalCreateRequest, db: DbSession
) -> NoteCanonicalCreateResult:
    mention = db.scalar(select(NoteEntityMention).where(NoteEntityMention.id == mention_id))
    if mention is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note mention not found")

    entity_type = payload.entity_type
    created_entity_id: UUID
    if entity_type == "Person":
        display_name = (payload.display_name or mention.normalized_text).strip()
        if not display_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="display_name is required")
        person = Person(
            display_name=display_name,
            given_name=payload.given_name,
            family_name=payload.family_name,
            primary_location=payload.primary_location,
            relationship_summary=payload.relationship_summary,
            how_we_met=payload.how_we_met,
            notes=payload.notes or mention.evidence_text,
        )
        db.add(person)
        db.flush()
        created_entity_id = person.id
    elif entity_type == "Organization":
        name = (payload.display_name or mention.normalized_text).strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="display_name is required")
        organization = Organization(
            name=name,
            type=payload.organization_type or "Other",
            industry=payload.industry,
            location=payload.primary_location,
            notes=payload.notes or mention.evidence_text,
        )
        db.add(organization)
        db.flush()
        created_entity_id = organization.id
    elif entity_type == "Location":
        location = Location(
            label=payload.location_label or mention.normalized_text,
            address_line=payload.location_address_line,
            city=payload.location_city,
            region=payload.location_region,
            country=payload.location_country,
            location_type=payload.location_type or "Other",
            notes=payload.notes or mention.evidence_text,
        )
        db.add(location)
        db.flush()
        created_entity_id = location.id
    else:
        title = (payload.event_title or mention.normalized_text).strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="event_title is required")
        event = InteractionEvent(
            title=title,
            type=payload.event_type or "Note",
            started_at=payload.event_started_at or datetime.now(timezone.utc),
            ended_at=payload.event_ended_at,
            summary=payload.event_summary or mention.evidence_text,
            notes=payload.notes,
        )
        if payload.selected_person_ids:
            event.people = list(db.scalars(select(Person).where(Person.id.in_(payload.selected_person_ids))))
        if payload.selected_organization_ids:
            event.organizations = list(
                db.scalars(select(Organization).where(Organization.id.in_(payload.selected_organization_ids)))
            )
        if payload.selected_location_ids:
            event.locations = list(db.scalars(select(Location).where(Location.id.in_(payload.selected_location_ids))))
        db.add(event)
        db.flush()
        created_entity_id = event.id

    mention.review_status = "Created"
    decision = NoteReviewDecision(
        mention_id=mention.id,
        action="create_new",
        matched_entity_type=entity_type,
        matched_entity_id=created_entity_id,
        notes=payload.notes,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return NoteCanonicalCreateResult(entity_type=entity_type, entity_id=created_entity_id, review_decision=NoteReviewDecisionRead.model_validate(decision))


def _create_mentions(
    db: DbSession,
    source: NoteSource,
    run: NoteExtractionRun,
    payload: NoteExtractionPayload,
) -> list[NoteEntityMention]:
    result: list[NoteEntityMention] = []
    entities = [
        ("Person", payload.people),
        ("Organization", payload.organizations),
        ("Location", payload.locations),
    ]
    for entity_type, drafts in entities:
        for draft in drafts:
            normalized = normalize_mention_text(draft.normalized_text or draft.raw_text)
            if not normalized:
                continue
            mention = NoteEntityMention(
                source_id=source.id,
                extraction_run_id=run.id,
                entity_type=entity_type,
                raw_text=draft.raw_text,
                normalized_text=normalized,
                evidence_text=draft.evidence_text,
                confidence=draft.confidence,
                metadata_json=json.dumps({"normalized_text": draft.normalized_text}),
            )
            db.add(mention)
            db.flush()
            candidates = find_candidate_matches(db, entity_type, draft.raw_text, normalized)
            for rank, candidate in enumerate(candidates, start=1):
                db.add(
                    NoteMatchCandidate(
                        mention_id=mention.id,
                        entity_type=candidate.entity_type,
                        entity_id=candidate.entity_id,
                        label=candidate.label,
                        subtitle=candidate.subtitle,
                        score=candidate.score,
                        rationale=candidate.rationale,
                        rank=rank,
                    )
                )
            result.append(mention)
    return result


def _create_event_drafts(
    db: DbSession,
    source: NoteSource,
    run: NoteExtractionRun,
    drafts: list[NoteEventDraftPayload],
) -> list[NoteEventDraft]:
    created: list[NoteEventDraft] = []
    for draft in drafts:
        event_draft = NoteEventDraft(
            source_id=source.id,
            extraction_run_id=run.id,
            title=draft.title,
            event_type=draft.event_type,
            summary=draft.summary,
            evidence_text=draft.evidence_text,
            started_on=draft.started_on,
            confidence=draft.confidence,
            metadata_json=draft.model_dump_json(),
        )
        db.add(event_draft)
        created.append(event_draft)
    return created


def _serialize_source_detail(db: DbSession, source: NoteSource) -> NoteSourceDetailRead:
    runs = list(
        db.scalars(select(NoteExtractionRun).where(NoteExtractionRun.source_id == source.id).order_by(NoteExtractionRun.created_at.desc()))
    )
    mentions = list(
        db.scalars(select(NoteEntityMention).where(NoteEntityMention.source_id == source.id).order_by(NoteEntityMention.entity_type, NoteEntityMention.created_at))
    )
    event_drafts = list(
        db.scalars(select(NoteEventDraft).where(NoteEventDraft.source_id == source.id).order_by(NoteEventDraft.created_at.desc()))
    )
    return NoteSourceDetailRead(
        **NoteSourceRead.model_validate(source).model_dump(),
        extraction_runs=[NoteExtractionRunRead.model_validate(run) for run in runs],
        mentions=[_serialize_mention(db, mention) for mention in mentions],
        event_drafts=[_serialize_event_draft(db, event_draft) for event_draft in event_drafts],
    )


def _serialize_mention(db: DbSession, mention: NoteEntityMention) -> NoteEntityMentionRead:
    candidates = list(
        db.scalars(select(NoteMatchCandidate).where(NoteMatchCandidate.mention_id == mention.id).order_by(NoteMatchCandidate.rank))
    )
    return NoteEntityMentionRead(
        **NoteEntityMentionRead.model_validate(mention).model_dump(exclude={"candidates"}),
        candidates=[NoteMatchCandidateRead.model_validate(candidate) for candidate in candidates],
    )


def _serialize_event_draft(db: DbSession, event_draft: NoteEventDraft) -> NoteEventDraftRead:
    return NoteEventDraftRead(
        **NoteEventDraftRead.model_validate(event_draft).model_dump(
            exclude={
                "participant_refs",
                "organization_refs",
                "location_refs",
                "review_reasons",
                "unresolved_refs",
                "canonical_event_id",
            }
        ),
        **event_reference_summary(db, event_draft),
    )


def _status_counts(db: DbSession, model: Any, source_ids: list[UUID]) -> dict[UUID, dict[str, int]]:
    counts: dict[UUID, dict[str, int]] = {}
    if not source_ids:
        return counts
    rows = db.execute(
        select(model.source_id, model.review_status, func.count())
        .where(model.source_id.in_(source_ids))
        .group_by(model.source_id, model.review_status)
    )
    for source_id, review_status, count in rows:
        counts.setdefault(source_id, {})[review_status] = count
    return counts


def _validate_event_refs(db: DbSession, draft: NoteEventDraft, metadata: dict[str, Any]) -> None:
    mention_types: dict[str, str] = {}
    mentions = db.scalars(
        select(NoteEntityMention).where(
            NoteEntityMention.source_id == draft.source_id,
            NoteEntityMention.extraction_run_id == draft.extraction_run_id,
        )
    )
    for mention in mentions:
        try:
            ref = json.loads(mention.metadata_json or "{}").get("ref")
        except json.JSONDecodeError:
            ref = None
        if ref:
            mention_types[str(ref)] = mention.entity_type
    expected = {
        "participant_refs": "Person",
        "organization_refs": "Organization",
        "location_refs": "Location",
    }
    for field, entity_type in expected.items():
        refs = metadata.get(field, [])
        if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid {field}")
        if len(refs) != len(set(refs)):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Duplicate {field}")
        invalid = [ref for ref in refs if mention_types.get(ref) != entity_type]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": f"Invalid {field}", "refs": invalid},
            )
