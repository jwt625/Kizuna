from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings
from app.schemas.notes import NoteExtractionPayload, NoteMentionDraft, NoteProviderStatus


PROMPT_VERSION = "notes-v1"


class NoteExtractionProvider(Protocol):
    def provider_name(self) -> str: ...

    def model_name(self) -> str | None: ...

    def extract(self, heading: str, note_date: str | None, body_text: str) -> NoteExtractionPayload: ...

    def healthcheck(self) -> NoteProviderStatus: ...


@dataclass(slots=True)
class OpenAICompatibleProvider:
    name: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    supports_structured_outputs: bool = True

    def provider_name(self) -> str:
        return self.name

    def model_name(self) -> str | None:
        return self.model

    def extract(self, heading: str, note_date: str | None, body_text: str) -> NoteExtractionPayload:
        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "note_extraction",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "people": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/mention"},
                        },
                        "organizations": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/mention"},
                        },
                        "locations": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/mention"},
                        },
                        "events": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "event_type": {"type": "string"},
                                    "summary": {"type": ["string", "null"]},
                                    "evidence_text": {"type": ["string", "null"]},
                                    "started_on": {"type": ["string", "null"]},
                                    "confidence": {"type": ["number", "null"]},
                                    "people": {"type": "array", "items": {"type": "string"}},
                                    "organizations": {"type": "array", "items": {"type": "string"}},
                                    "locations": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["title", "event_type", "summary", "evidence_text", "started_on", "confidence", "people", "organizations", "locations"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["people", "organizations", "locations", "events"],
                    "$defs": {
                        "mention": {
                            "type": "object",
                            "properties": {
                                "raw_text": {"type": "string"},
                                "normalized_text": {"type": ["string", "null"]},
                                "evidence_text": {"type": ["string", "null"]},
                                "confidence": {"type": ["number", "null"]},
                            },
                            "required": ["raw_text", "normalized_text", "evidence_text", "confidence"],
                            "additionalProperties": False,
                        }
                    },
                    "additionalProperties": False,
                },
            },
        }
        system_prompt = (
            "Extract explicit people, organizations, locations, and event candidates from a daily note. "
            "Prefer precision over recall. Do not invent surnames, companies, dates, or places. "
            "Use only entities explicitly present in the note text. "
            "Treat cafes, restaurants, offices, homes, airports, and meeting venues as locations unless the note clearly refers to the company itself. "
            "If the note explicitly says met, talked, called, had lunch, had coffee, attended, visited, or caught up, create an event candidate."
        )
        user_prompt = (
            f"Heading: {heading}\n"
            f"Note date: {note_date or 'unknown'}\n\n"
            f"Note text:\n{body_text}"
        )
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }
        if self.supports_structured_outputs:
            payload["response_format"] = schema
        else:
            payload["messages"] = [
                {
                    "role": "system",
                    "content": (
                        f"{system_prompt} Return a valid JSON object only. No markdown fences, no explanation. "
                        "Use keys people, organizations, locations, and events. "
                        "For missing arrays, return empty arrays. "
                        "Each person, organization, and location item should ideally be an object with raw_text, normalized_text, evidence_text, and confidence."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ]
        response = self._post_json("/chat/completions", payload)
        choices = cast(list[dict[str, Any]], response["choices"])
        message = cast(dict[str, Any], choices[0]["message"])
        content = cast(str, message["content"])
        return NoteExtractionPayload.model_validate(_normalize_payload(_parse_json_content(content)))

    def healthcheck(self) -> NoteProviderStatus:
        try:
            response = self._post_json("/models", method="GET")
            detail = "reachable"
            if isinstance(response, dict) and "data" in response:
                models = cast(list[dict[str, Any]], response["data"])
                detail = f"reachable ({len(models)} models listed)"
            return NoteProviderStatus(
                provider_name=self.name,
                configured=bool(self.base_url and self.model),
                reachable=True,
                model_name=self.model,
                detail=detail,
            )
        except Exception as exc:
            return NoteProviderStatus(
                provider_name=self.name,
                configured=bool(self.base_url and self.model),
                reachable=False,
                model_name=self.model,
                detail=str(exc),
            )

    def _post_json(self, path: str, payload: dict[str, object] | None = None, method: str = "POST") -> dict[str, object]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(f"{self.base_url.rstrip('/')}{path}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return cast(dict[str, object], json.loads(response.read().decode("utf-8")))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"{self.name} HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"{self.name} unreachable: {exc.reason}") from exc


@dataclass(slots=True)
class CompoundNoteProvider:
    primary: OpenAICompatibleProvider
    fallback: OpenAICompatibleProvider | None = None

    def provider_name(self) -> str:
        return self.primary.provider_name()

    def model_name(self) -> str | None:
        return self.primary.model_name()

    def extract(self, heading: str, note_date: str | None, body_text: str) -> NoteExtractionPayload:
        try:
            return self.primary.extract(heading, note_date, body_text)
        except Exception:
            if self.fallback is None:
                raise
            return self.fallback.extract(heading, note_date, body_text)

    def healthcheck(self) -> NoteProviderStatus:
        return self.primary.healthcheck()

    def fallback_healthcheck(self) -> NoteProviderStatus | None:
        if self.fallback is None:
            return None
        return self.fallback.healthcheck()


class FakeNotesProvider:
    def provider_name(self) -> str:
        return "fake"

    def model_name(self) -> str | None:
        return "fake-model"

    def extract(self, heading: str, note_date: str | None, body_text: str) -> NoteExtractionPayload:
        del heading, note_date
        words = [token.strip(" ,.;:!?()[]{}") for token in body_text.split()]
        people = [
            NoteMentionDraft(raw_text=token, normalized_text=token, evidence_text=token, confidence=0.3)
            for token in words
            if token[:1].isupper() and len(token) > 2
        ][:5]
        return NoteExtractionPayload(people=people)

    def healthcheck(self) -> NoteProviderStatus:
        return NoteProviderStatus(
            provider_name="fake",
            configured=True,
            reachable=True,
            model_name="fake-model",
            detail="test provider",
        )


def get_note_extraction_provider() -> CompoundNoteProvider:
    settings = get_settings()
    primary = OpenAICompatibleProvider(
        name=settings.notes_llm_provider_name,
        base_url=settings.notes_llm_base_url,
        api_key=settings.notes_llm_api_key,
        model=settings.notes_llm_model,
        timeout_seconds=settings.notes_llm_timeout_seconds,
    )
    fallback = None
    if settings.notes_llm_fallback_base_url and settings.notes_llm_fallback_model:
        fallback = OpenAICompatibleProvider(
            name=settings.notes_llm_fallback_provider_name,
            base_url=settings.notes_llm_fallback_base_url,
            api_key=settings.notes_llm_fallback_api_key,
            model=settings.notes_llm_fallback_model,
            timeout_seconds=settings.notes_llm_timeout_seconds,
            supports_structured_outputs=False,
        )
    return CompoundNoteProvider(primary=primary, fallback=fallback)


def _parse_json_content(content: str) -> dict[str, object]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        return cast(dict[str, object], json.loads(stripped))
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return cast(dict[str, object], json.loads(stripped[start : end + 1]))
        raise


def _normalize_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    for key in ["people", "organizations", "locations"]:
        values = payload.get(key, [])
        if not isinstance(values, list):
            normalized[key] = []
            continue
        normalized[key] = [
            value
            if isinstance(value, dict)
            else {
                "raw_text": str(value),
                "normalized_text": str(value),
                "evidence_text": None,
                "confidence": None,
            }
            for value in values
        ]
    event_values = payload.get("events", [])
    if not isinstance(event_values, list):
        normalized["events"] = []
    else:
        normalized["events"] = [_normalize_event(value) for value in event_values]
    return normalized


def _normalize_event(value: object) -> dict[str, object]:
    if isinstance(value, dict) and "title" in value:
        return dict(value)
    if isinstance(value, dict):
        raw_text = str(value.get("raw_text") or value.get("normalized_text") or "Untitled event")
        evidence_text = value.get("evidence_text")
        confidence = value.get("confidence")
        return {
            "title": raw_text[:240],
            "event_type": "One-on-one" if "met with" in raw_text.casefold() else "Note",
            "summary": evidence_text if isinstance(evidence_text, str) else raw_text,
            "evidence_text": evidence_text if isinstance(evidence_text, str) else raw_text,
            "started_on": None,
            "confidence": confidence,
            "people": [],
            "organizations": [],
            "locations": [],
        }
    raw_text = str(value)
    return {
        "title": raw_text[:240],
        "event_type": "Note",
        "summary": raw_text,
        "evidence_text": raw_text,
        "started_on": None,
        "confidence": None,
        "people": [],
        "organizations": [],
        "locations": [],
    }
