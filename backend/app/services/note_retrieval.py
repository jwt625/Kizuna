from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Location, Organization, Person


@dataclass(slots=True)
class CandidateMatch:
    entity_type: str
    entity_id: UUID | None
    label: str
    subtitle: str | None
    score: float
    rationale: str


def find_candidate_matches(db: Session, entity_type: str, raw_text: str, normalized_text: str) -> list[CandidateMatch]:
    if entity_type == "Person":
        return _rank_people(db, raw_text, normalized_text)
    if entity_type == "Organization":
        return _rank_organizations(db, raw_text, normalized_text)
    if entity_type == "Location":
        return _rank_locations(db, raw_text, normalized_text)
    return []


def _rank_people(db: Session, raw_text: str, normalized_text: str) -> list[CandidateMatch]:
    pattern = f"%{normalized_text}%"
    broad_people = list(
        db.scalars(
            select(Person)
            .where(
                Person.deleted_at.is_(None),
                or_(
                    Person.display_name.ilike(pattern),
                    Person.given_name.ilike(pattern),
                    Person.family_name.ilike(pattern),
                    Person.nickname.ilike(pattern),
                ),
            )
            .limit(25)
        )
    )
    people = _filter_people_broadly(broad_people, raw_text, normalized_text)
    return _score_entities(
        "Person",
        people,
        raw_text,
        normalized_text,
        lambda person: person.display_name,
        lambda person: person.primary_location or person.relationship_summary,
    )


def _rank_organizations(db: Session, raw_text: str, normalized_text: str) -> list[CandidateMatch]:
    pattern = f"%{normalized_text}%"
    broad_organizations = list(
        db.scalars(
            select(Organization)
            .where(
                Organization.deleted_at.is_(None),
                or_(
                    Organization.name.ilike(pattern),
                    Organization.industry.ilike(pattern),
                    Organization.location.ilike(pattern),
                ),
            )
            .limit(25)
        )
    )
    organizations = _filter_organizations_broadly(broad_organizations, raw_text, normalized_text)
    return _score_entities(
        "Organization",
        organizations,
        raw_text,
        normalized_text,
        lambda organization: organization.name,
        lambda organization: organization.industry or organization.location,
    )


def _rank_locations(db: Session, raw_text: str, normalized_text: str) -> list[CandidateMatch]:
    pattern = f"%{normalized_text}%"
    broad_locations = list(
        db.scalars(
            select(Location)
            .where(
                or_(
                    Location.label.ilike(pattern),
                    Location.city.ilike(pattern),
                    Location.region.ilike(pattern),
                    Location.country.ilike(pattern),
                    Location.address_line.ilike(pattern),
                )
            )
            .limit(25)
        )
    )
    locations = _filter_locations_broadly(broad_locations, raw_text, normalized_text)
    return _score_entities(
        "Location",
        locations,
        raw_text,
        normalized_text,
        lambda location: location.label or location.city or location.address_line or "Unknown location",
        lambda location: ", ".join(part for part in [location.city, location.region, location.country] if part) or None,
    )


def _score_entities(
    entity_type: str,
    entities: list[Any],
    raw_text: str,
    normalized_text: str,
    label_getter: Any,
    subtitle_getter: Any,
) -> list[CandidateMatch]:
    raw_lower = raw_text.casefold()
    normalized_lower = normalized_text.casefold()
    ranked: list[CandidateMatch] = []
    for entity in entities:
        label = label_getter(entity)
        label_lower = label.casefold()
        subtitle = subtitle_getter(entity)
        if label_lower == normalized_lower or label_lower == raw_lower:
            score = 1.0
            rationale = "Exact normalized name match"
        elif label_lower.startswith(normalized_lower):
            score = 0.9
            rationale = "Prefix match"
        elif normalized_lower in label_lower:
            score = 0.75
            rationale = "Substring match"
        else:
            score = 0.55
            rationale = "Related text match"
        ranked.append(
            CandidateMatch(
                entity_type=entity_type,
                entity_id=entity.id,
                label=label,
                subtitle=subtitle,
                score=score,
                rationale=rationale,
            )
        )
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:5]


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def _tokenize(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", value.casefold()) if token}


def _filter_people_broadly(people: list[Person], raw_text: str, normalized_text: str) -> list[Person]:
    normalized_compact = _compact(normalized_text)
    raw_tokens = _tokenize(raw_text)
    results: list[Person] = []
    for person in people:
        fields = [person.display_name, person.given_name, person.family_name, person.nickname]
        compact_fields = [_compact(field) for field in fields]
        token_fields = [_tokenize(field or "") for field in fields]
        if any(normalized_compact and normalized_compact in field for field in compact_fields):
            results.append(person)
            continue
        if any(raw_tokens & field_tokens for field_tokens in token_fields):
            results.append(person)
    return results[:10]


def _filter_organizations_broadly(organizations: list[Organization], raw_text: str, normalized_text: str) -> list[Organization]:
    normalized_compact = _compact(normalized_text)
    raw_tokens = _tokenize(raw_text)
    results: list[Organization] = []
    for organization in organizations:
        fields = [organization.name, organization.industry, organization.location]
        compact_fields = [_compact(field) for field in fields]
        token_fields = [_tokenize(field or "") for field in fields]
        if any(normalized_compact and normalized_compact in field for field in compact_fields):
            results.append(organization)
            continue
        if any(raw_tokens & field_tokens for field_tokens in token_fields):
            results.append(organization)
    return results[:10]


def _filter_locations_broadly(locations: list[Location], raw_text: str, normalized_text: str) -> list[Location]:
    normalized_compact = _compact(normalized_text)
    raw_tokens = _tokenize(raw_text)
    results: list[Location] = []
    for location in locations:
        label = location.label or location.city or location.address_line or ""
        fields = [label, location.city, location.region, location.country, location.address_line]
        compact_fields = [_compact(field) for field in fields]
        token_fields = [_tokenize(field or "") for field in fields]
        if any(normalized_compact and normalized_compact in field for field in compact_fields):
            results.append(location)
            continue
        if any(raw_tokens & field_tokens for field_tokens in token_fields):
            results.append(location)
    return results[:10]
