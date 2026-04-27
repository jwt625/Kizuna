from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.main import app
from app.schemas.notes import NoteEventDraftPayload, NoteExtractionPayload, NoteMentionDraft, NoteProviderStatus
from app.services.note_parsing import parse_note_sections


class StubNotesProvider:
    def provider_name(self) -> str:
        return "stub-local"

    def model_name(self) -> str | None:
        return "stub-qwen3"

    def extract(self, heading: str, note_date: str | None, body_text: str) -> NoteExtractionPayload:
        assert heading == "2026-04-01"
        assert note_date == "2026-04-01"
        assert "Met with Ming" in body_text
        return NoteExtractionPayload(
            people=[
                NoteMentionDraft(
                    raw_text="Ming",
                    normalized_text="Ming",
                    evidence_text="Met with Ming at Blue Bottle in San Francisco",
                    confidence=0.92,
                )
            ],
            organizations=[
                NoteMentionDraft(
                    raw_text="Flux",
                    normalized_text="Flux",
                    evidence_text="Talked about Flux roadmap",
                    confidence=0.83,
                )
            ],
            locations=[
                NoteMentionDraft(
                    raw_text="Blue Bottle",
                    normalized_text="Blue Bottle",
                    evidence_text="Met with Ming at Blue Bottle in San Francisco",
                    confidence=0.88,
                )
            ],
            events=[
                NoteEventDraftPayload(
                    title="Coffee with Ming",
                    event_type="One-on-one",
                    summary="Talked about Flux roadmap",
                    evidence_text="Met with Ming at Blue Bottle in San Francisco. Talked about Flux roadmap.",
                    started_on="2026-04-01",
                    confidence=0.81,
                    people=["Ming"],
                    organizations=["Flux"],
                    locations=["Blue Bottle"],
                )
            ],
        )

    def healthcheck(self) -> NoteProviderStatus:
        return NoteProviderStatus(
            provider_name="stub-local",
            configured=True,
            reachable=True,
            model_name="stub-qwen3",
            detail="stub provider",
        )

    def fallback_healthcheck(self) -> None:
        return None


def test_parse_note_sections_splits_top_level_headings() -> None:
    sections = parse_note_sections(
        """
# 2026-04-01

Met with Ming at Blue Bottle.

# TODO

- follow up with Flux
""".strip()
    )

    assert len(sections) == 2
    assert sections[0].heading == "2026-04-01"
    assert sections[0].note_date is not None
    assert "Met with Ming" in sections[0].body_text
    assert sections[1].heading == "TODO"


def test_scan_extract_and_review_notes_flow(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    client = TestClient(app)

    note_dir = tmp_path / "daily-notes"
    note_dir.mkdir()
    note_file = note_dir / "2026-04.md"
    note_file.write_text(
        """
# 2026-04-01

Met with Ming at Blue Bottle in San Francisco.
Talked about Flux roadmap.
""".strip(),
        encoding="utf-8",
    )

    person_response = client.post(
        "/api/people",
        json={"display_name": "Ming", "primary_location": "San Francisco", "contact_methods": [], "external_profiles": []},
    )
    organization_response = client.post(
        "/api/organizations",
        json={"name": "Flux", "industry": "Energy"},
    )
    assert person_response.status_code == 201
    assert organization_response.status_code == 201

    location_host = client.post(
        f"/api/people/{person_response.json()['id']}/locations",
        json={
            "location": {"label": "Blue Bottle", "city": "San Francisco", "region": "CA", "country": "USA", "location_type": "Cafe"},
            "is_primary": True,
        },
    )
    assert location_host.status_code == 201

    scan_response = client.post("/api/notes/scan", json={"root_path": str(note_dir), "recursive": True})
    assert scan_response.status_code == 201
    payload = scan_response.json()
    assert payload["files_seen"] == 1
    assert payload["sections_seen"] == 1
    source_id = payload["sources"][0]["id"]

    import app.api.routes.notes as notes_route

    monkeypatch.setattr(notes_route, "get_note_extraction_provider", lambda: StubNotesProvider())

    extract_response = client.post(f"/api/notes/sources/{source_id}/extract")
    assert extract_response.status_code == 201
    extracted = extract_response.json()
    assert extracted["run"]["status"] == "Completed"
    assert extracted["mentions"][0]["raw_text"] == "Ming"
    assert extracted["event_drafts"][0]["title"] == "Coffee with Ming"

    detail_response = client.get(f"/api/notes/sources/{source_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert len(detail["mentions"]) == 3

    person_mention = next(item for item in detail["mentions"] if item["entity_type"] == "Person")
    assert person_mention["candidates"][0]["label"] == "Ming"
    assert person_mention["candidates"][0]["score"] >= 0.75

    review_response = client.post(
        f"/api/notes/mentions/{person_mention['id']}/review",
        json={"action": "accept_match", "selected_candidate_id": person_mention["candidates"][0]["id"]},
    )
    assert review_response.status_code == 200
    assert review_response.json()["action"] == "accept_match"

    refreshed = client.get(f"/api/notes/sources/{source_id}")
    refreshed_person = next(item for item in refreshed.json()["mentions"] if item["entity_type"] == "Person")
    assert refreshed_person["review_status"] == "Accepted"


def test_note_mention_can_change_type_and_create_canonical_entity(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    client = TestClient(app)

    note_dir = tmp_path / "daily-notes"
    note_dir.mkdir()
    note_file = note_dir / "2026-04.md"
    note_file.write_text(
        """
# 2026-04-01

Met with Dan at Chinese supplier office in San Francisco.
""".strip(),
        encoding="utf-8",
    )

    scan_response = client.post("/api/notes/scan", json={"root_path": str(note_dir), "recursive": True})
    assert scan_response.status_code == 201
    source_id = scan_response.json()["sources"][0]["id"]

    import app.api.routes.notes as notes_route

    class AmbiguousProvider:
        def provider_name(self) -> str:
            return "stub-local"

        def model_name(self) -> str | None:
            return "stub-qwen3"

        def extract(self, heading: str, note_date: str | None, body_text: str) -> NoteExtractionPayload:
            assert heading == "2026-04-01"
            assert note_date == "2026-04-01"
            assert "Chinese supplier office" in body_text
            return NoteExtractionPayload(
                organizations=[
                    NoteMentionDraft(
                        raw_text="Chinese supplier",
                        normalized_text="Chinese supplier",
                        evidence_text="Met with Dan at Chinese supplier office in San Francisco.",
                        confidence=0.61,
                    )
                ]
            )

        def healthcheck(self) -> NoteProviderStatus:
            return NoteProviderStatus(
                provider_name="stub-local",
                configured=True,
                reachable=True,
                model_name="stub-qwen3",
                detail="stub provider",
            )

        def fallback_healthcheck(self) -> None:
            return None

    monkeypatch.setattr(notes_route, "get_note_extraction_provider", lambda: AmbiguousProvider())

    extract_response = client.post(f"/api/notes/sources/{source_id}/extract")
    assert extract_response.status_code == 201
    mention = extract_response.json()["mentions"][0]
    assert mention["entity_type"] == "Organization"

    update_response = client.patch(
        f"/api/notes/mentions/{mention['id']}",
        json={
            "entity_type": "Person",
            "raw_text": "Dan",
            "normalized_text": "Dan",
            "evidence_text": "Met with Dan at Chinese supplier office in San Francisco.",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["entity_type"] == "Person"
    assert updated["raw_text"] == "Dan"

    create_response = client.post(
        f"/api/notes/mentions/{mention['id']}/create-canonical",
        json={
            "entity_type": "Person",
            "display_name": "Dan",
            "primary_location": "San Francisco",
            "notes": "Created from note review",
        },
    )
    assert create_response.status_code == 201

    person_id = create_response.json()["entity_id"]
    person_response = client.get(f"/api/people/{person_id}")
    assert person_response.status_code == 200
    assert person_response.json()["display_name"] == "Dan"

    refreshed = client.get(f"/api/notes/sources/{source_id}")
    refreshed_mention = refreshed.json()["mentions"][0]
    assert refreshed_mention["review_status"] == "Created"

def test_note_mention_can_create_canonical_event_with_optional_end_date_from_scanned_source(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    client = TestClient(app)

    person_response = client.post(
        "/api/people",
        json={"display_name": "Ming", "contact_methods": [], "external_profiles": []},
    )
    assert person_response.status_code == 201
    person_id = person_response.json()["id"]

    note_dir = tmp_path / "daily-notes"
    note_dir.mkdir()
    note_file = note_dir / "2026-04.md"
    note_file.write_text(
        """
# 2026-04-01

Met with Ming for coffee.
""".strip(),
        encoding="utf-8",
    )

    scan_response = client.post("/api/notes/scan", json={"root_path": str(note_dir), "recursive": True})
    assert scan_response.status_code == 201
    source_id = scan_response.json()["sources"][0]["id"]

    import app.api.routes.notes as notes_route

    class EventProvider:
        def provider_name(self) -> str:
            return "stub-local"

        def model_name(self) -> str | None:
            return "stub-qwen3"

        def extract(self, heading: str, note_date: str | None, body_text: str) -> NoteExtractionPayload:
            assert heading == "2026-04-01"
            assert note_date == "2026-04-01"
            assert "Met with Ming" in body_text
            return NoteExtractionPayload(
                people=[
                    NoteMentionDraft(
                        raw_text="Coffee with Ming",
                        normalized_text="Coffee with Ming",
                        evidence_text="Met with Ming for coffee.",
                        confidence=0.93,
                    )
                ],
                events=[
                    NoteEventDraftPayload(
                        title="Coffee with Ming",
                        event_type="One-on-one",
                        summary="Met with Ming for coffee",
                        evidence_text="Met with Ming for coffee.",
                        started_on="2026-04-01",
                        confidence=0.93,
                        people=["Ming"],
                        organizations=[],
                        locations=[],
                    )
                ],
            )

        def healthcheck(self) -> NoteProviderStatus:
            return NoteProviderStatus(
                provider_name="stub-local",
                configured=True,
                reachable=True,
                model_name="stub-qwen3",
                detail="stub provider",
            )

        def fallback_healthcheck(self) -> None:
            return None

    monkeypatch.setattr(notes_route, "get_note_extraction_provider", lambda: EventProvider())

    extract_response = client.post(f"/api/notes/sources/{source_id}/extract")
    assert extract_response.status_code == 201

    event_mention_response = client.patch(
        f"/api/notes/mentions/{extract_response.json()['mentions'][0]['id']}",
        json={
            "entity_type": "Event",
            "raw_text": "Coffee with Ming",
            "normalized_text": "Coffee with Ming",
            "evidence_text": "Met with Ming for coffee.",
        },
    )
    assert event_mention_response.status_code == 200
    mention_id = event_mention_response.json()["id"]

    create_response = client.post(
        f"/api/notes/mentions/{mention_id}/create-canonical",
        json={
            "entity_type": "Event",
            "event_title": "Coffee with Ming",
            "event_type": "One-on-one",
            "event_summary": "Met with Ming for coffee",
            "event_started_at": "2026-04-01T10:00:00Z",
            "event_ended_at": "2026-04-01T11:30:00Z",
            "selected_person_ids": [person_id],
        },
    )
    assert create_response.status_code == 201

    event_id = create_response.json()["entity_id"]
    event_response = client.get(f"/api/events/{event_id}")
    assert event_response.status_code == 200
    event = event_response.json()
    assert event["started_at"].startswith("2026-04-01T10:00:00")
    assert event["ended_at"].startswith("2026-04-01T11:30:00")
    assert event["person_ids"] == [person_id]
