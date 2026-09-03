import csv
from io import StringIO
import json

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import false, or_, select

from app.api.deps import DbSession
from app.models import ContactMethod, Person
from app.schemas.imports import NoteJsonlImportResult, NoteJsonlRecord, PeopleImportResult
from app.services.note_jsonl import stage_jsonl_record

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/people-csv", response_model=PeopleImportResult, status_code=status.HTTP_201_CREATED)
async def import_people_csv(file: UploadFile, db: DbSession) -> PeopleImportResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV file required")

    raw = await file.read()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text))

    created = 0
    skipped = 0
    errors: list[str] = []
    seen_display_names: set[str] = set()
    seen_emails: set[str] = set()

    for index, row in enumerate(reader, start=2):
        display_name = (row.get("display_name") or row.get("name") or "").strip()
        if not display_name:
            errors.append(f"Row {index}: missing display_name")
            continue

        email = (row.get("email") or "").strip()
        if display_name in seen_display_names or (email and email in seen_emails):
            skipped += 1
            continue
        duplicate = db.scalar(
            select(Person)
            .outerjoin(ContactMethod, ContactMethod.person_id == Person.id)
            .where(
                Person.deleted_at.is_(None),
                or_(
                    Person.display_name == display_name,
                    ContactMethod.value == email if email else false(),
                ),
            )
            .limit(1)
        )
        if duplicate:
            skipped += 1
            continue

        person = Person(
            display_name=display_name,
            given_name=(row.get("given_name") or "").strip() or None,
            family_name=(row.get("family_name") or "").strip() or None,
            primary_location=(row.get("primary_location") or row.get("location") or "").strip() or None,
            relationship_summary=(row.get("relationship_summary") or "").strip() or None,
            how_we_met=(row.get("how_we_met") or "").strip() or None,
            notes=(row.get("notes") or "").strip() or None,
        )
        if email:
            person.contact_methods = [ContactMethod(type="Email", value=email, label="Imported", is_primary=True)]
        db.add(person)
        db.flush()
        seen_display_names.add(display_name)
        if email:
            seen_emails.add(email)
        created += 1

    db.commit()
    return PeopleImportResult(created=created, skipped=skipped, errors=errors)


@router.get("/notes-jsonl/schema")
def note_jsonl_schema() -> dict[str, object]:
    return NoteJsonlRecord.model_json_schema()


@router.post("/notes-jsonl", response_model=NoteJsonlImportResult, status_code=status.HTTP_201_CREATED)
async def import_notes_jsonl(file: UploadFile, db: DbSession) -> NoteJsonlImportResult:
    if not file.filename or not file.filename.lower().endswith(".jsonl"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSONL file required")
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="JSONL file exceeds 10 MiB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSONL file must be UTF-8") from exc

    lines = [(line_number, line) for line_number, line in enumerate(text.splitlines(), start=1) if line.strip()]
    staged = 0
    skipped = 0
    errors: list[str] = []
    source_ids: list[str] = []
    for line_number, line in lines:
        try:
            payload = NoteJsonlRecord.model_validate(json.loads(line))
            with db.begin_nested():
                source, was_staged = stage_jsonl_record(db, payload)
                source_ids.append(str(source.id))
                if was_staged:
                    staged += 1
                else:
                    skipped += 1
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            errors.append(f"Line {line_number}: {exc}")
    db.commit()
    return NoteJsonlImportResult(
        lines_received=len(lines), staged=staged, skipped=skipped, errors=errors, source_ids=source_ids
    )
