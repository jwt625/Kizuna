from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.models import ExternalProfile, Person, SourceLink


CARD_MARKER = '<li class="mn-connection-card artdeco-list">'
LINK_RE = re.compile(r'<a href="([^"]+)"[^>]*class="[^"]*mn-connection-card__(?:picture|link)[^"]*"')
NAME_RE = re.compile(r'<span class="mn-connection-card__name[^"]*">\s*(.*?)\s*</span>', re.S)
OCCUPATION_RE = re.compile(r'<span class="mn-connection-card__occupation[^"]*">\s*(.*?)\s*</span>', re.S)
TIME_RE = re.compile(r'<time class="time-badge[^"]*">\s*(.*?)\s*</time>', re.S)
IMAGE_RE = re.compile(r'<img [^>]*src="([^"]+)"[^>]*alt="([^"]*)"', re.S)


@dataclass
class LinkedInConnection:
    display_name: str
    profile_url: str
    headline: str | None
    connected_text: str | None
    avatar_url: str | None
    avatar_alt: str | None


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    return html.unescape(re.sub(r"\s+", " ", value)).strip() or None


def canonical_linkedin_url(href: str) -> str:
    href = html.unescape(href).strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href.rstrip("/")
    return f"https://www.linkedin.com{href}".rstrip("/")


def split_name(display_name: str) -> tuple[str | None, str | None]:
    parts = [part for part in display_name.split() if part]
    if len(parts) < 2:
        return None, None
    return parts[0], " ".join(parts[1:])


def parse_connections(html_text: str) -> list[LinkedInConnection]:
    connections: list[LinkedInConnection] = []
    for block in html_text.split(CARD_MARKER)[1:]:
        href_match = LINK_RE.search(block)
        name_match = NAME_RE.search(block)
        if not href_match or not name_match:
            continue

        occupation_match = OCCUPATION_RE.search(block)
        time_match = TIME_RE.search(block)
        image_match = IMAGE_RE.search(block)

        connections.append(
            LinkedInConnection(
                display_name=clean_text(name_match.group(1)) or "Unknown",
                profile_url=canonical_linkedin_url(href_match.group(1)),
                headline=clean_text(occupation_match.group(1)) if occupation_match else None,
                connected_text=clean_text(time_match.group(1)) if time_match else None,
                avatar_url=clean_text(image_match.group(1)) if image_match else None,
                avatar_alt=clean_text(image_match.group(2)) if image_match else None,
            )
        )
    return connections


def build_notes(connection: LinkedInConnection, html_path: Path, snapshot_date: date) -> str:
    note_parts = [
        f"Imported from LinkedIn connections page snapshot {html_path.name} on {snapshot_date.isoformat()}.",
    ]
    if connection.headline:
        note_parts.append(f"LinkedIn headline: {connection.headline}")
    if connection.connected_text:
        note_parts.append(connection.connected_text)
    if connection.avatar_url:
        note_parts.append(f"Avatar URL: {connection.avatar_url}")
    if connection.avatar_alt and connection.avatar_alt != connection.display_name:
        note_parts.append(f"Avatar alt text: {connection.avatar_alt}")
    return "\n".join(note_parts)


def ensure_source_link(person_id, profile_url: str, html_path: Path, snapshot_date: date, headline: str | None) -> SourceLink:
    notes = f"Imported from {html_path.name} on {snapshot_date.isoformat()}."
    if headline:
        notes = f"{notes}\nHeadline at import: {headline}"
    return SourceLink(
        entity_type="Person",
        entity_id=person_id,
        source_type="LinkedIn",
        url_or_reference=profile_url,
        label="LinkedIn connection import",
        notes=notes,
    )


def normalize_imported_person(person: Person, connection: LinkedInConnection, html_path: Path, snapshot_date: date) -> None:
    person.short_bio = connection.headline
    if person.relationship_summary == connection.headline:
        person.relationship_summary = None
    if person.how_we_met in {None, "", "Imported from LinkedIn connections page."}:
        person.how_we_met = "LinkedIn connection import"
    person.notes = build_notes(connection, html_path, snapshot_date)


def import_connections(html_path: Path, snapshot_date: date, dry_run: bool = False) -> dict[str, int]:
    html_text = html_path.read_text()
    parsed = parse_connections(html_text)
    seen_profile_urls: set[str] = set()
    created = 0
    skipped = 0
    updated = 0

    session = SessionLocal()
    try:
        existing_profiles = {
            profile.url_or_handle: profile
            for profile in session.scalars(
                select(ExternalProfile).where(ExternalProfile.platform == "LinkedIn")
            ).all()
        }

        for connection in parsed:
            if connection.profile_url in seen_profile_urls:
                skipped += 1
                continue
            existing_profile = existing_profiles.get(connection.profile_url)
            if existing_profile:
                person = existing_profile.person
                if person is not None:
                    normalize_imported_person(person, connection, html_path, snapshot_date)
                    updated += 1
                seen_profile_urls.add(connection.profile_url)
                skipped += 1
                continue

            given_name, family_name = split_name(connection.display_name)
            person = Person(
                display_name=connection.display_name,
                given_name=given_name,
                family_name=family_name,
                short_bio=connection.headline,
                relationship_summary=None,
                how_we_met="LinkedIn connection import",
                notes=build_notes(connection, html_path, snapshot_date),
            )
            person.external_profiles = [
                ExternalProfile(
                    platform="LinkedIn",
                    url_or_handle=connection.profile_url,
                    label="Imported profile",
                    notes=f"Imported from {html_path.name} on {snapshot_date.isoformat()}.",
                )
            ]
            session.add(person)
            session.flush()
            session.add(ensure_source_link(person.id, connection.profile_url, html_path, snapshot_date, connection.headline))

            seen_profile_urls.add(connection.profile_url)
            created += 1

        if dry_run:
            session.rollback()
        else:
            session.commit()
    finally:
        session.close()

    return {"parsed": len(parsed), "created": created, "updated": updated, "skipped": skipped}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import LinkedIn connections from a saved HTML page.")
    parser.add_argument("html_path", type=Path, help="Path to the saved LinkedIn connections HTML file.")
    parser.add_argument(
        "--snapshot-date",
        type=date.fromisoformat,
        default=date.today(),
        help="Snapshot date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and report without committing any changes.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = import_connections(args.html_path, args.snapshot_date, dry_run=args.dry_run)
    print(result)


if __name__ == "__main__":
    main()
