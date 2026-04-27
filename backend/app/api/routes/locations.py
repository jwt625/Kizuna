from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession
from app.models import EntityLocation, InteractionEvent, Location, Organization, Person
from app.schemas.event import EventRead
from app.schemas.location import LocationDetailRead, LocationLinkRead, LocationUpdate
from app.schemas.metadata import LocationCreate, LocationRead

router = APIRouter(prefix="/locations", tags=["locations"])


def location_statement() -> Select[tuple[Location]]:
    return select(Location)


def serialize_event(event: InteractionEvent) -> EventRead:
    return EventRead.model_validate(
        {
            **event.__dict__,
            "person_ids": [person.id for person in event.people],
            "organization_ids": [organization.id for organization in event.organizations],
            "location_ids": [location.id for location in event.locations],
        }
    )


def build_location_detail(location: Location, db: DbSession) -> LocationDetailRead:
    person_links = list(
        db.execute(
            select(EntityLocation, Person)
            .join(Person, Person.id == EntityLocation.entity_id)
            .where(
                EntityLocation.entity_type == "Person",
                EntityLocation.location_id == location.id,
                Person.deleted_at.is_(None),
            )
            .order_by(EntityLocation.is_primary.desc(), Person.display_name)
        )
    )
    organization_links = list(
        db.execute(
            select(EntityLocation, Organization)
            .join(Organization, Organization.id == EntityLocation.entity_id)
            .where(
                EntityLocation.entity_type == "Organization",
                EntityLocation.location_id == location.id,
                Organization.deleted_at.is_(None),
            )
            .order_by(EntityLocation.is_primary.desc(), Organization.name)
        )
    )
    recent_events = list(
        db.scalars(
            select(InteractionEvent)
            .where(
                InteractionEvent.deleted_at.is_(None),
                InteractionEvent.locations.any(Location.id == location.id),
            )
            .options(
                selectinload(InteractionEvent.people),
                selectinload(InteractionEvent.organizations),
                selectinload(InteractionEvent.locations),
            )
            .order_by(InteractionEvent.started_at.desc())
            .limit(25)
        )
    )
    return LocationDetailRead.model_validate(
        {
            **LocationRead.model_validate(location).model_dump(),
            "linked_people": [
                LocationLinkRead.model_validate(
                    {
                        "id": entity_location.id,
                        "entity_type": "Person",
                        "entity_id": person.id,
                        "title": person.display_name,
                        "subtitle": person.relationship_summary or person.primary_location,
                        "is_primary": entity_location.is_primary,
                        "notes": entity_location.notes,
                        "created_at": entity_location.created_at,
                        "updated_at": entity_location.updated_at,
                    }
                )
                for entity_location, person in person_links
            ],
            "linked_organizations": [
                LocationLinkRead.model_validate(
                    {
                        "id": entity_location.id,
                        "entity_type": "Organization",
                        "entity_id": organization.id,
                        "title": organization.name,
                        "subtitle": organization.industry or organization.location,
                        "is_primary": entity_location.is_primary,
                        "notes": entity_location.notes,
                        "created_at": entity_location.created_at,
                        "updated_at": entity_location.updated_at,
                    }
                )
                for entity_location, organization in organization_links
            ],
            "recent_events": [serialize_event(event) for event in recent_events],
            "last_event_at": recent_events[0].started_at if recent_events else None,
        }
    )


@router.get("", response_model=list[LocationRead])
def list_locations(
    db: DbSession,
    response: Response,
    q: str | None = Query(default=None),
    city: str | None = None,
    country: str | None = None,
    location_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Location]:
    statement = location_statement()
    count_statement = select(func.count()).select_from(Location)
    if q:
        pattern = f"%{q}%"
        search_filter = or_(
            Location.label.ilike(pattern),
            Location.city.ilike(pattern),
            Location.region.ilike(pattern),
            Location.country.ilike(pattern),
            Location.address_line.ilike(pattern),
            Location.notes.ilike(pattern),
        )
        statement = statement.where(search_filter)
        count_statement = count_statement.where(search_filter)
    if city:
        city_filter = Location.city.ilike(f"%{city}%")
        statement = statement.where(city_filter)
        count_statement = count_statement.where(city_filter)
    if country:
        country_filter = Location.country.ilike(f"%{country}%")
        statement = statement.where(country_filter)
        count_statement = count_statement.where(country_filter)
    if location_type:
        type_filter = Location.location_type.ilike(f"%{location_type}%")
        statement = statement.where(type_filter)
        count_statement = count_statement.where(type_filter)
    response.headers["X-Total-Count"] = str(db.scalar(count_statement) or 0)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)
    statement = statement.order_by(Location.country, Location.city, Location.label).limit(limit).offset(offset)
    return list(db.scalars(statement))


@router.post("", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
def create_location(payload: LocationCreate, db: DbSession) -> Location:
    location = Location(**payload.model_dump())
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@router.get("/{location_id}", response_model=LocationDetailRead)
def get_location(location_id: UUID, db: DbSession) -> LocationDetailRead:
    location = db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return build_location_detail(location, db)


@router.patch("/{location_id}", response_model=LocationDetailRead)
def update_location(location_id: UUID, payload: LocationUpdate, db: DbSession) -> LocationDetailRead:
    location = db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(location, field, value)
    db.commit()
    db.refresh(location)
    return get_location(location.id, db)
