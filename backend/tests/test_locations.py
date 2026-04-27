from fastapi.testclient import TestClient

from app.main import app


def test_create_list_update_and_detail_location() -> None:
    client = TestClient(app)

    create_response = client.post(
        "/api/locations",
        json={
            "label": "Blue Bottle Mint Plaza",
            "address_line": "66 Mint St",
            "city": "San Francisco",
            "region": "CA",
            "country": "USA",
            "location_type": "Cafe",
            "notes": "Quiet seating in the back",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["address_line"] == "66 Mint St"

    list_response = client.get("/api/locations", params={"q": "Mint", "city": "San Francisco"})
    assert list_response.status_code == 200
    assert any(item["id"] == created["id"] for item in list_response.json())

    detail_response = client.get(f"/api/locations/{created['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["label"] == "Blue Bottle Mint Plaza"
    assert detail["linked_people"] == []
    assert detail["linked_organizations"] == []
    assert detail["recent_events"] == []

    update_response = client.patch(
        f"/api/locations/{created['id']}",
        json={"label": "Blue Bottle Coffee - Mint Plaza", "notes": "Good for founder catchups"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["label"] == "Blue Bottle Coffee - Mint Plaza"
    assert updated["notes"] == "Good for founder catchups"


def test_location_detail_collects_linked_entities_and_events() -> None:
    client = TestClient(app)

    location_response = client.post(
        "/api/locations",
        json={
            "label": "Fort Mason",
            "city": "San Francisco",
            "country": "USA",
            "location_type": "Venue",
        },
    )
    person_response = client.post(
        "/api/people",
        json={"display_name": "Dana Chen", "contact_methods": [], "external_profiles": []},
    )
    organization_response = client.post(
        "/api/organizations",
        json={"name": "Harbor Collective", "type": "Community"},
    )

    assert location_response.status_code == 201
    assert person_response.status_code == 201
    assert organization_response.status_code == 201

    location_id = location_response.json()["id"]
    person_id = person_response.json()["id"]
    organization_id = organization_response.json()["id"]

    person_location_response = client.post(
        f"/api/people/{person_id}/locations",
        json={
            "location": {
                "label": "Fort Mason",
                "city": "San Francisco",
                "country": "USA",
                "location_type": "Venue",
            },
            "is_primary": False,
            "notes": "Met there often",
        },
    )
    organization_location_response = client.post(
        f"/api/organizations/{organization_id}/locations",
        json={
            "location": {
                "label": "Fort Mason",
                "city": "San Francisco",
                "country": "USA",
                "location_type": "Venue",
            },
            "is_primary": True,
            "notes": "Operates from this venue",
        },
    )
    event_response = client.post(
        "/api/events",
        json={
            "title": "Harbor salon",
            "type": "Event attendance",
            "started_at": "2026-04-21T18:30:00Z",
            "person_ids": [person_id],
            "organization_ids": [organization_id],
            "location_ids": [location_id],
        },
    )

    assert person_location_response.status_code == 201
    assert organization_location_response.status_code == 201
    assert event_response.status_code == 201

    detail_response = client.get(f"/api/locations/{location_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["recent_events"][0]["title"] == "Harbor salon"

    events_response = client.get("/api/events", params={"location_id": location_id})
    assert events_response.status_code == 200
    assert any(item["title"] == "Harbor salon" for item in events_response.json())


def test_global_search_returns_locations() -> None:
    client = TestClient(app)

    create_response = client.post(
        "/api/locations",
        json={
            "label": "Union Square Apple Store",
            "city": "San Francisco",
            "country": "USA",
            "location_type": "Store",
        },
    )
    assert create_response.status_code == 201

    search_response = client.get("/api/search", params={"q": "Union Square"})
    assert search_response.status_code == 200
    payload = search_response.json()
    assert any(item["title"] == "Union Square Apple Store" for item in payload["locations"])


def test_people_and_organizations_can_link_existing_location_by_id() -> None:
    client = TestClient(app)

    location_response = client.post(
        "/api/locations",
        json={
            "label": "Salesforce Park",
            "city": "San Francisco",
            "country": "USA",
            "location_type": "Park",
        },
    )
    person_response = client.post(
        "/api/people",
        json={"display_name": "Yuna Park", "contact_methods": [], "external_profiles": []},
    )
    organization_response = client.post(
        "/api/organizations",
        json={"name": "Garden Studio", "type": "Community"},
    )

    assert location_response.status_code == 201
    assert person_response.status_code == 201
    assert organization_response.status_code == 201

    location_id = location_response.json()["id"]
    person_id = person_response.json()["id"]
    organization_id = organization_response.json()["id"]

    person_link_response = client.post(
        f"/api/people/{person_id}/locations",
        json={"location_id": location_id, "is_primary": True, "notes": "Frequent meetup spot"},
    )
    organization_link_response = client.post(
        f"/api/organizations/{organization_id}/locations",
        json={"location_id": location_id, "is_primary": True, "notes": "Hosts community events here"},
    )

    assert person_link_response.status_code == 201
    assert organization_link_response.status_code == 201
    person_payload = person_link_response.json()
    organization_payload = organization_link_response.json()
    assert person_payload["locations"][0]["location_id"] == location_id
    assert organization_payload["locations"][0]["location_id"] == location_id
    assert person_payload["primary_location"] == "San Francisco, USA"
    assert organization_payload["location"] == "San Francisco, USA"
