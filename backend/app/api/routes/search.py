from fastapi import APIRouter, Query
from sqlalchemy import ColumnElement, or_, select, text
from typing import cast

from app.api.deps import DbSession
from app.models import EntityTag, EntityLocation, InteractionEvent, Location, Organization, Person, PersonOrganization, Reminder, Tag
from app.schemas.search import SearchResponse, SearchResult

router = APIRouter(prefix="/search", tags=["search"])


def text_search_clause(columns: list[str], pattern: str, query: str, dialect: str) -> ColumnElement[bool]:
    if dialect == "postgresql":
        joined = " || ' ' || ".join(f"coalesce({column}, '')" for column in columns)
        return cast(
            ColumnElement[bool],
            text(f"to_tsvector('simple', {joined}) @@ plainto_tsquery('simple', :query)").bindparams(query=query),
        )
    return or_(
        *[text(f"lower(coalesce({column}, '')) like lower(:pattern)").bindparams(pattern=pattern) for column in columns]
    )


@router.get("", response_model=SearchResponse)
def search(
    db: DbSession,
    q: str = Query(min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
) -> SearchResponse:
    pattern = f"%{q}%"
    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"

    people = list(
        db.scalars(
            select(Person)
            .where(
                Person.deleted_at.is_(None),
                or_(
                    text_search_clause(
                        [
                            "people.display_name",
                            "people.primary_location",
                            "people.relationship_summary",
                            "people.how_we_met",
                            "people.notes",
                        ],
                        pattern,
                        q,
                        dialect,
                    ),
                    Person.id.in_(
                        select(EntityTag.entity_id)
                        .join(Tag, Tag.id == EntityTag.tag_id)
                        .where(EntityTag.entity_type == "Person", Tag.name.ilike(pattern))
                    ),
                    Person.id.in_(
                        select(PersonOrganization.person_id)
                        .join(Organization, Organization.id == PersonOrganization.organization_id)
                        .where(Organization.name.ilike(pattern))
                    ),
                ),
            )
            .order_by(Person.display_name)
            .limit(limit)
        )
    )
    organizations = list(
        db.scalars(
            select(Organization)
            .where(
                Organization.deleted_at.is_(None),
                or_(
                    text_search_clause(
                        [
                            "organizations.name",
                            "organizations.industry",
                            "organizations.location",
                            "organizations.notes",
                        ],
                        pattern,
                        q,
                        dialect,
                    ),
                    Organization.id.in_(
                        select(EntityTag.entity_id)
                        .join(Tag, Tag.id == EntityTag.tag_id)
                        .where(EntityTag.entity_type == "Organization", Tag.name.ilike(pattern))
                    ),
                ),
            )
            .order_by(Organization.name)
            .limit(limit)
        )
    )
    events = list(
        db.scalars(
            select(InteractionEvent)
            .where(
                InteractionEvent.deleted_at.is_(None),
                text_search_clause(
                    [
                        "interaction_events.title",
                        "interaction_events.context",
                        "interaction_events.summary",
                        "interaction_events.notes",
                    ],
                    pattern,
                    q,
                    dialect,
                ),
            )
            .order_by(InteractionEvent.started_at.desc())
            .limit(limit)
        )
    )
    locations = list(
        db.scalars(
            select(Location)
            .where(
                or_(
                    text_search_clause(
                        [
                            "locations.label",
                            "locations.city",
                            "locations.region",
                            "locations.country",
                            "locations.address_line",
                            "locations.notes",
                        ],
                        pattern,
                        q,
                        dialect,
                    ),
                    Location.id.in_(
                        select(EntityLocation.location_id)
                        .join(Person, Person.id == EntityLocation.entity_id)
                        .where(EntityLocation.entity_type == "Person", Person.display_name.ilike(pattern))
                    ),
                    Location.id.in_(
                        select(EntityLocation.location_id)
                        .join(Organization, Organization.id == EntityLocation.entity_id)
                        .where(EntityLocation.entity_type == "Organization", Organization.name.ilike(pattern))
                    ),
                )
            )
            .order_by(Location.country, Location.city, Location.label)
            .limit(limit)
        )
    )
    reminders = list(
        db.scalars(
            select(Reminder)
            .where(
                Reminder.deleted_at.is_(None),
                text_search_clause(["reminders.title", "reminders.notes"], pattern, q, dialect),
            )
            .order_by(Reminder.due_at)
            .limit(limit)
        )
    )

    return SearchResponse(
        people=[
            SearchResult(
                entity_type="Person",
                id=person.id,
                title=person.display_name,
                subtitle=person.primary_location or person.relationship_summary,
            )
            for person in people
        ],
        organizations=[
            SearchResult(
                entity_type="Organization",
                id=organization.id,
                title=organization.name,
                subtitle=organization.industry or organization.location,
            )
            for organization in organizations
        ],
        locations=[
            SearchResult(
                entity_type="Location",
                id=location.id,
                title=location.label or location.address_line or location.city or "Untitled location",
                subtitle=", ".join(part for part in [location.city, location.region, location.country] if part) or location.location_type,
            )
            for location in locations
        ],
        events=[
            SearchResult(
                entity_type="Event",
                id=event.id,
                title=event.title,
                subtitle=event.summary or event.context,
            )
            for event in events
        ],
        reminders=[
            SearchResult(
                entity_type="Reminder",
                id=reminder.id,
                title=reminder.title,
                subtitle=reminder.notes,
            )
            for reminder in reminders
        ],
    )
