from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import re


TOP_LEVEL_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(slots=True)
class ParsedNoteSection:
    section_key: str
    heading: str
    note_date: date | None
    body_text: str
    content_hash: str


def parse_note_sections(markdown: str) -> list[ParsedNoteSection]:
    matches = list(TOP_LEVEL_HEADING_RE.finditer(markdown))
    if not matches:
        body_text = markdown.strip()
        if not body_text:
            return []
        return [
            ParsedNoteSection(
                section_key="section-1",
                heading="Untitled",
                note_date=None,
                body_text=body_text,
                content_hash=_hash_text(body_text),
            )
        ]

    sections: list[ParsedNoteSection] = []
    for index, match in enumerate(matches, start=1):
        body_start = match.end()
        body_end = matches[index].start() if index < len(matches) else len(markdown)
        body_text = markdown[body_start:body_end].strip()
        if not body_text:
            continue
        heading = match.group(1).strip()
        sections.append(
            ParsedNoteSection(
                section_key=f"section-{index}",
                heading=heading,
                note_date=_parse_note_date(heading),
                body_text=body_text,
                content_hash=_hash_text(f"{heading}\n{body_text}"),
            )
        )
    return sections


def normalize_mention_text(value: str) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact.strip(" ,.;:!?()[]{}\"'")


def _parse_note_date(heading: str) -> date | None:
    if ISO_DATE_RE.match(heading):
        return date.fromisoformat(heading)
    return None


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
