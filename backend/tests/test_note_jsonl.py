import json
from typing import Any

from fastapi.testclient import TestClient
from httpx import Response

from app.main import app


def _record(*, key: str = "notes/2026-01#2026-01-15", confidence: float = 0.95) -> dict[str, Any]:
    return {
        "schema_version": "kizuna.note-extraction.v1",
        "source": {"key": key, "heading": "2026-01-15", "note_date": "2026-01-15"},
        "mentions": [
            {
                "ref": "person-1",
                "entity_type": "Person",
                "raw_text": "Alex Rivera",
                "normalized_text": "Alex Rivera",
                "evidence_text": "Met Alex for coffee.",
                "confidence": confidence,
            },
            {
                "ref": "org-1",
                "entity_type": "Organization",
                "raw_text": "Example Labs",
                "normalized_text": "Example Labs",
                "confidence": 0.98,
            },
            {
                "ref": "location-1",
                "entity_type": "Location",
                "raw_text": "Harbor Cafe",
                "normalized_text": "Harbor Cafe",
                "confidence": 0.98,
            },
        ],
        "events": [
            {
                "ref": "event-1",
                "title": "Coffee catch-up",
                "event_type": "One-on-one",
                "occurred_on": "2026-01-15",
                "date_precision": "date",
                "summary": "Discussed a possible collaboration.",
                "evidence_text": "Met Alex for coffee.",
                "confidence": confidence,
                "participant_refs": ["person-1"],
                "organization_refs": ["org-1"],
                "location_refs": ["location-1"],
                "review_reasons": [],
            }
        ],
    }


def _upload(client: TestClient, records: list[dict[str, Any] | str]) -> Response:
    content = "\n".join(item if isinstance(item, str) else json.dumps(item) for item in records)
    return client.post("/api/imports/notes-jsonl", files={"file": ("notes.jsonl", content, "application/x-ndjson")})


def _create_canonical_matches(client: TestClient) -> None:
    assert client.post("/api/people", json={"display_name": "Alex Rivera"}).status_code == 201
    assert client.post("/api/organizations", json={"name": "Example Labs", "type": "Company"}).status_code == 201
    assert (
        client.post(
            "/api/locations", json={"label": "Harbor Cafe", "city": "Bay City", "location_type": "Venue"}
        ).status_code
        == 201
    )


def test_jsonl_auto_matches_exact_entities_and_commits_linked_event() -> None:
    client = TestClient(app)
    _create_canonical_matches(client)

    upload = _upload(client, [_record()])

    assert upload.status_code == 201
    assert upload.json()["staged"] == 1
    detail = client.get(f"/api/notes/sources/{upload.json()['source_ids'][0]}").json()
    assert {mention["review_status"] for mention in detail["mentions"]} == {"Auto matched"}
    draft = detail["event_drafts"][0]
    assert draft["review_status"] == "Ready"
    assert draft["unresolved_refs"] == []

    commit = client.post(f"/api/notes/event-drafts/{draft['id']}/review", json={"action": "commit"})

    assert commit.status_code == 200
    event = client.get(f"/api/events/{commit.json()['canonical_event_id']}").json()
    assert event["title"] == "Coffee catch-up"
    assert len(event["person_ids"]) == len(event["organization_ids"]) == len(event["location_ids"]) == 1


def test_jsonl_low_confidence_match_requires_review_before_commit() -> None:
    client = TestClient(app)
    person_response = client.post("/api/people", json={"display_name": "Alex Rivera"})
    assert person_response.status_code == 201
    record = _record(key="notes/2026-01#2026-01-16", confidence=0.5)
    record["source"]["heading"] = "2026-01-16"
    record["source"]["note_date"] = "2026-01-16"
    event = record["events"][0]
    event["occurred_on"] = "2026-01-16"
    event["participant_refs"] = ["person-1"]
    event["organization_refs"] = []
    event["location_refs"] = []
    record["mentions"] = record["mentions"][:1]

    upload = _upload(client, [record])
    detail = client.get(f"/api/notes/sources/{upload.json()['source_ids'][0]}").json()
    mention = detail["mentions"][0]
    draft = detail["event_drafts"][0]
    assert mention["review_status"] == "Pending"
    assert mention["candidates"][0]["score"] == 1.0
    assert draft["review_status"] == "Needs review"
    assert client.post(f"/api/notes/event-drafts/{draft['id']}/review", json={"action": "commit"}).status_code == 409

    reviewed = client.post(
        f"/api/notes/mentions/{mention['id']}/match",
        json={"entity_type": "Person", "entity_id": person_response.json()["id"]},
    )
    assert reviewed.status_code == 200
    assert client.post(f"/api/notes/event-drafts/{draft['id']}/review", json={"action": "commit"}).status_code == 200


def test_jsonl_review_summary_and_event_edit() -> None:
    client = TestClient(app)
    record = _record(key="notes/2026-01#2026-01-19", confidence=0.5)
    record["source"]["heading"] = "2026-01-19"
    record["source"]["note_date"] = "2026-01-19"
    event = record["events"][0]
    event["occurred_on"] = "2026-01-19"
    event["organization_refs"] = []
    event["location_refs"] = []
    record["mentions"] = record["mentions"][:1]
    upload = _upload(client, [record])
    source_id = upload.json()["source_ids"][0]
    detail = client.get(f"/api/notes/sources/{source_id}").json()
    draft = detail["event_drafts"][0]

    summary = client.get("/api/notes/review-summary").json()["items"]
    source_summary = next(item for item in summary if item["id"] == source_id)
    assert source_summary["review_status"] == "Needs review"
    assert source_summary["pending_mentions"] == 1
    assert source_summary["needs_review_events"] == 1
    update = client.patch(
        f"/api/notes/event-drafts/{draft['id']}",
        json={"title": "Corrected interaction", "participant_refs": []},
    )
    assert update.status_code == 200
    assert update.json()["title"] == "Corrected interaction"
    assert update.json()["review_status"] == "Ready"
    assert update.json()["unresolved_refs"] == []
    rejected = client.post(f"/api/notes/event-drafts/{draft['id']}/review", json={"action": "reject"})
    assert rejected.status_code == 200
    summary = client.get("/api/notes/review-summary").json()["items"]
    assert next(item for item in summary if item["id"] == source_id)["review_status"] == "Rejected"


def test_jsonl_import_is_idempotent_and_reports_invalid_lines() -> None:
    client = TestClient(app)
    record = _record(key="notes/2026-01#2026-01-17")

    first = _upload(client, ["not json", record])
    second = _upload(client, [record])

    assert first.status_code == 201
    assert first.json()["lines_received"] == 2
    assert first.json()["staged"] == 1
    assert len(first.json()["errors"]) == 1
    assert second.status_code == 201
    assert second.json()["skipped"] == 1


def test_jsonl_rejects_cross_type_or_missing_refs() -> None:
    client = TestClient(app)
    record = _record(key="notes/2026-01#2026-01-18")
    event = record["events"][0]
    event["participant_refs"] = ["org-1"]

    response = _upload(client, [record])

    assert response.status_code == 201
    assert response.json()["staged"] == 0
    assert "wrong-type mention" in response.json()["errors"][0]
