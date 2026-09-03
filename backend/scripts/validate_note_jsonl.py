from argparse import ArgumentParser
from pathlib import Path

from pydantic import ValidationError

from app.schemas.imports import NoteJsonlRecord


def main() -> int:
    parser = ArgumentParser(description="Validate Kizuna note extraction JSONL")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    errors: list[str] = []
    count = 0
    for line_number, line in enumerate(args.path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        count += 1
        try:
            NoteJsonlRecord.model_validate_json(line)
        except ValidationError as exc:
            errors.append(f"Line {line_number}: {exc}")
    if errors:
        print("\n".join(errors))
        return 1
    print(f"Valid Kizuna JSONL records: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
