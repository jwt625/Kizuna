from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import TimestampedSchema
from app.schemas.event import EventRead
from app.schemas.metadata import LocationRead


class LocationUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=160)
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    address_line: str | None = Field(default=None, max_length=500)
    latitude: float | None = None
    longitude: float | None = None
    location_type: str | None = Field(default=None, max_length=80)
    notes: str | None = None


class LocationLinkRead(TimestampedSchema):
    entity_type: str
    entity_id: UUID
    title: str
    subtitle: str | None = None
    is_primary: bool = False
    notes: str | None = None


class LocationDetailRead(LocationRead):
    linked_people: list[LocationLinkRead]
    linked_organizations: list[LocationLinkRead]
    recent_events: list[EventRead]
    last_event_at: datetime | None = None
