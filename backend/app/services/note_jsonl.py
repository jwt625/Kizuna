from __future__ import annotations

from datetime import datetime, time, timezone
from hashlib import sha256
import json
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

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
    SourceLink,
)
from app.schemas.imports import NoteJsonlEvent, NoteJsonlRecord
from app.services.note_parsing import normalize_mention_text
from app.services.note_retrieval import find_candidate_matches
from app.services.relationship_scoring import recompute_people_relationships


AUTO_MATCH_CONFIDENCE = 0.85


def stage_jsonl_record(db: Session, record: NoteJsonlRecord) -> tuple[NoteSource, bool]:
    serialized = record.model_dump_json(exclude_none=True)
    content_hash = sha256(serialized.encode()).hexdigest()
    file_path = f"jsonl:{record.source.key}"
    source = db.scalar(
        select(NoteSource).where(NoteSource.file_path == file_path, NoteSource.section_key == record.source.key)
    )
    if source and source.content_hash == content_hash:
        return source, False
    if source:
        imported = db.scalar(
            select(NoteEventDraft.id).where(
                NoteEventDraft.source_id == source.id,
                NoteEventDraft.review_status == "Imported",
            )
        )
        if imported:
            raise ValueError("source has imported events; use a new source key for revised content")
        _clear_staged_source(db, source)
        source.heading = record.source.heading
        source.note_date = record.source.note_date
        source.body_text = _evidence_text(record)
        source.content_hash = content_hash
        source.scan_status = "Imported"
        source.extraction_status = "Completed"
    else:
        source = NoteSource(
            file_path=file_path,
            section_key=record.source.key,
            heading=record.source.heading,
            note_date=record.source.note_date,
            body_text=_evidence_text(record),
            content_hash=content_hash,
            source_type="Daily note JSONL",
            scan_status="Imported",
            extraction_status="Completed",
        )
        db.add(source)
        db.flush()

    run = NoteExtractionRun(
        source_id=source.id,
        provider_name="external-jsonl",
        model_name=None,
        prompt_version=record.schema_version,
        status="Completed",
        raw_response_json=serialized,
    )
    db.add(run)
    db.flush()

    mentions: dict[str, NoteEntityMention] = {}
    for draft in record.mentions:
        normalized = normalize_mention_text(draft.normalized_text or draft.raw_text)
        mention = NoteEntityMention(
            source_id=source.id,
            extraction_run_id=run.id,
            entity_type=draft.entity_type,
            raw_text=draft.raw_text,
            normalized_text=normalized,
            evidence_text=draft.evidence_text,
            confidence=draft.confidence,
            review_status="Pending",
            metadata_json=json.dumps({"ref": draft.ref}),
        )
        db.add(mention)
        db.flush()
        candidates = find_candidate_matches(db, draft.entity_type, draft.raw_text, normalized)
        candidate_rows: list[NoteMatchCandidate] = []
        for rank, candidate in enumerate(candidates, start=1):
            row = NoteMatchCandidate(
                mention_id=mention.id,
                entity_type=candidate.entity_type,
                entity_id=candidate.entity_id,
                label=candidate.label,
                subtitle=candidate.subtitle,
                score=candidate.score,
                rationale=candidate.rationale,
                rank=rank,
            )
            db.add(row)
            candidate_rows.append(row)
        exact = [candidate for candidate in candidate_rows if candidate.score == 1.0]
        if draft.confidence >= AUTO_MATCH_CONFIDENCE and len(exact) == 1:
            exact[0].is_selected = True
            mention.review_status = "Auto matched"
            db.add(
                NoteReviewDecision(
                    mention_id=mention.id,
                    action="accept_match",
                    matched_entity_type=exact[0].entity_type,
                    matched_entity_id=exact[0].entity_id,
                    notes="Unique exact match",
                )
            )
        mentions[draft.ref] = mention

    for event in record.events:
        refs = event.participant_refs + event.organization_refs + event.location_refs
        all_resolved = all(mentions[ref].review_status == "Auto matched" for ref in refs)
        review_status = "Ready" if event.confidence >= AUTO_MATCH_CONFIDENCE and all_resolved else "Needs review"
        db.add(
            NoteEventDraft(
                source_id=source.id,
                extraction_run_id=run.id,
                title=event.title,
                event_type=event.event_type,
                summary=event.summary,
                evidence_text=event.evidence_text,
                started_on=event.occurred_on,
                confidence=event.confidence,
                review_status=review_status,
                metadata_json=event.model_dump_json(exclude_none=True),
            )
        )
    return source, True


def commit_event_draft(db: Session, draft: NoteEventDraft) -> InteractionEvent:
    metadata = json.loads(draft.metadata_json or "{}")
    existing_id = metadata.get("canonical_event_id")
    if existing_id:
        existing = db.get(InteractionEvent, UUID(existing_id))
        if existing:
            return existing
    event_payload = NoteJsonlEvent.model_validate(metadata)
    mentions = list(
        db.scalars(
            select(NoteEntityMention).where(
                NoteEntityMention.source_id == draft.source_id,
                NoteEntityMention.extraction_run_id == draft.extraction_run_id,
            )
        )
    )
    mentions_by_ref = {_mention_ref(mention): mention for mention in mentions}
    resolved: dict[str, tuple[str, UUID]] = {}
    unresolved: list[str] = []
    typed_refs = [
        *((ref, "Person") for ref in event_payload.participant_refs),
        *((ref, "Organization") for ref in event_payload.organization_refs),
        *((ref, "Location") for ref in event_payload.location_refs),
    ]
    for ref, expected_type in typed_refs:
        mention = mentions_by_ref.get(ref)
        decision = _latest_resolution(db, mention) if mention else None
        if not decision or decision.matched_entity_type != expected_type or not decision.matched_entity_id:
            unresolved.append(ref)
        else:
            resolved[ref] = (decision.matched_entity_type, decision.matched_entity_id)
    if unresolved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Resolve referenced mentions before committing", "unresolved_refs": unresolved},
        )

    started_at = event_payload.occurred_at or datetime.combine(event_payload.occurred_on, time.min, tzinfo=timezone.utc)
    event = InteractionEvent(
        title=event_payload.title,
        type=event_payload.event_type,
        started_at=started_at,
        summary=event_payload.summary,
        notes=event_payload.evidence_text,
    )
    person_ids = [resolved[ref][1] for ref in event_payload.participant_refs]
    organization_ids = [resolved[ref][1] for ref in event_payload.organization_refs]
    location_ids = [resolved[ref][1] for ref in event_payload.location_refs]
    event.people = list(db.scalars(select(Person).where(Person.id.in_(person_ids)))) if person_ids else []
    event.organizations = (
        list(db.scalars(select(Organization).where(Organization.id.in_(organization_ids)))) if organization_ids else []
    )
    event.locations = list(db.scalars(select(Location).where(Location.id.in_(location_ids)))) if location_ids else []
    if (
        len(event.people) != len(set(person_ids))
        or len(event.organizations) != len(set(organization_ids))
        or len(event.locations) != len(set(location_ids))
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A resolved canonical entity no longer exists")
    db.add(event)
    db.flush()
    source = db.get(NoteSource, draft.source_id)
    if source:
        db.add(
            SourceLink(
                entity_type="Event",
                entity_id=event.id,
                source_type="Daily note JSONL",
                url_or_reference=source.file_path.removeprefix("jsonl:"),
                label=source.heading[:160],
            )
        )
    recompute_people_relationships(db, {person.id for person in event.people})
    metadata["canonical_event_id"] = str(event.id)
    draft.metadata_json = json.dumps(metadata)
    draft.review_status = "Imported"
    return event


def reject_event_draft(draft: NoteEventDraft) -> None:
    draft.review_status = "Rejected"


def event_reference_summary(db: Session, draft: NoteEventDraft) -> dict[str, object]:
    metadata = json.loads(draft.metadata_json or "{}")
    refs = (
        metadata.get("participant_refs", []) + metadata.get("organization_refs", []) + metadata.get("location_refs", [])
    )
    mentions = list(
        db.scalars(
            select(NoteEntityMention).where(
                NoteEntityMention.source_id == draft.source_id,
                NoteEntityMention.extraction_run_id == draft.extraction_run_id,
            )
        )
    )
    mentions_by_ref = {_mention_ref(mention): mention for mention in mentions}
    unresolved = []
    for ref in refs:
        mention = mentions_by_ref.get(ref)
        if not mention or not _latest_resolution(db, mention):
            unresolved.append(ref)
    return {
        "participant_refs": metadata.get("participant_refs", []),
        "organization_refs": metadata.get("organization_refs", []),
        "location_refs": metadata.get("location_refs", []),
        "review_reasons": metadata.get("review_reasons", []),
        "unresolved_refs": unresolved,
        "canonical_event_id": metadata.get("canonical_event_id"),
    }


def _clear_staged_source(db: Session, source: NoteSource) -> None:
    mention_ids = select(NoteEntityMention.id).where(NoteEntityMention.source_id == source.id)
    db.execute(delete(NoteMatchCandidate).where(NoteMatchCandidate.mention_id.in_(mention_ids)))
    db.execute(delete(NoteReviewDecision).where(NoteReviewDecision.mention_id.in_(mention_ids)))
    db.execute(delete(NoteEntityMention).where(NoteEntityMention.source_id == source.id))
    db.execute(delete(NoteEventDraft).where(NoteEventDraft.source_id == source.id))
    db.execute(delete(NoteExtractionRun).where(NoteExtractionRun.source_id == source.id))


def _evidence_text(record: NoteJsonlRecord) -> str:
    snippets = [item.evidence_text for item in record.mentions if item.evidence_text]
    snippets.extend(item.evidence_text for item in record.events if item.evidence_text)
    return "\n\n".join(dict.fromkeys(snippets))


def _mention_ref(mention: NoteEntityMention) -> str:
    try:
        return str(json.loads(mention.metadata_json or "{}").get("ref", ""))
    except json.JSONDecodeError:
        return ""


def _latest_resolution(db: Session, mention: NoteEntityMention | None) -> NoteReviewDecision | None:
    if not mention or mention.review_status not in {"Auto matched", "Accepted", "Created"}:
        return None
    decision = db.scalar(
        select(NoteReviewDecision)
        .where(NoteReviewDecision.mention_id == mention.id)
        .order_by(NoteReviewDecision.created_at.desc())
        .limit(1)
    )
    if decision and decision.action in {"accept_match", "create_new"} and decision.matched_entity_id is not None:
        return decision
    return None
