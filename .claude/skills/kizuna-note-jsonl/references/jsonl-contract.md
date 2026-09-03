# Kizuna note extraction JSONL v1

Each physical line is one complete source-unit record. Unknown optional values should be omitted, not emitted as empty guesses.

```json
{"schema_version":"kizuna.note-extraction.v1","source":{"key":"journal.md#2026-01-15","heading":"2026-01-15","note_date":"2026-01-15"},"mentions":[{"ref":"person-1","entity_type":"Person","raw_text":"Taylor Morgan","normalized_text":"Taylor Morgan","evidence_text":"Met Taylor at Riverside Cafe.","confidence":0.98},{"ref":"org-1","entity_type":"Organization","raw_text":"Northstar Labs","normalized_text":"Northstar Labs","confidence":0.93},{"ref":"location-1","entity_type":"Location","raw_text":"Riverside Cafe","normalized_text":"Riverside Cafe","confidence":0.96}],"events":[{"ref":"event-1","title":"Coffee with Taylor","event_type":"One-on-one","occurred_on":"2026-01-15","date_precision":"date","summary":"Discussed a possible collaboration with Northstar Labs.","evidence_text":"Met Taylor at Riverside Cafe to discuss a possible collaboration.","confidence":0.96,"participant_refs":["person-1"],"organization_refs":["org-1"],"location_refs":["location-1"],"review_reasons":[]}]}
```

## Record fields

- `schema_version`: exactly `kizuna.note-extraction.v1`.
- `source.key`: stable relative locator, 1-180 characters.
- `source.heading`: source section label, 1-500 characters.
- `source.note_date`: ISO date used to interpret the source unit.
- `mentions`: zero or more locally referenced entities.
- `events`: zero or more past interaction drafts.

## Mention fields

- `ref`: 1-80 ASCII letters, digits, `.`, `_`, or `-`; starts with a letter or digit.
- `entity_type`: `Person`, `Organization`, or `Location`.
- `raw_text`: shortest identifying text from the source.
- `normalized_text`: optional conservative spelling/casing normalization.
- `evidence_text`: optional shortest supporting source fragment.
- `confidence`: number from 0 through 1.

Do not include Kizuna IDs. Matching is deterministic and happens after upload.

## Event fields

- `ref`: same syntax and uniqueness rule as mention refs.
- `title`: concise factual title, at most 240 characters.
- `event_type`: one of `Meeting`, `One-on-one`, `Group meeting`, `Call`, `Email`, `Message`, `Intro`, `Meal`, `Conference`, `Event attendance`, `Work session`, `Supplier discussion`, `Personal milestone`, `Note`, or `Other`.
- `occurred_on`: ISO date; required.
- `occurred_at`: optional ISO 8601 datetime with timezone, only when supported by the note.
- `date_precision`: `date`, `datetime`, or `approximate`.
- `summary`, `evidence_text`: optional strings.
- `confidence`: number from 0 through 1.
- `participant_refs`: refs whose mention type is `Person`.
- `organization_refs`: refs whose mention type is `Organization`.
- `location_refs`: refs whose mention type is `Location`.
- `review_reasons`: short machine-readable reason strings; empty when none.

Mention and event refs must be unique within their respective arrays. Every referenced mention must exist on the same line and have the corresponding entity type.
