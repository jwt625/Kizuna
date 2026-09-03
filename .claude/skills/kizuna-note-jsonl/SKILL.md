---
name: kizuna-note-jsonl
description: Convert one day or month of free-form Markdown notes into versioned Kizuna JSONL interaction drafts. Use when preparing note-derived people, organizations, locations, and past interactions for Kizuna's staged importer; do not use for direct database writes or general note summarization.
---

# Kizuna Note JSONL

Produce a `.jsonl` file that Kizuna can validate, match against canonical entities, and present for human review. Read [references/jsonl-contract.md](references/jsonl-contract.md) before producing output.

## Scope

- Accept a Markdown file plus either a single day/section or a month-sized range.
- Emit one JSON object per source day or coherent dated section, on one physical line. A month is multiple lines.
- Extract only past, relationship-relevant interactions involving the note author: meetings, calls, messages, meals, introductions, shared work, event attendance, and meaningful personal milestones.
- Exclude research facts, copied material, passive observations, private reflection without an interaction, future plans, reminders, and TODOs. Do not turn a person merely mentioned in hearsay or an article into a participant.
- Do not infer demographic, contact, employment, or relationship facts that the source does not support.

## Extraction

Resolve dates from explicit ISO headings first, then document date ranges and weekday context. Preserve uncertainty: use `date_precision: "approximate"` and add a review reason instead of fabricating precision. Set `occurred_at` only when both the time and timezone are supported; otherwise omit it.

Create a mention only when an emitted event references it. Give each mention a short stable local `ref`, unique within that JSONL line. Reuse the same ref across events in the source unit when it clearly denotes the same entity. Preserve ambiguous identity as written; never invent a surname or expand an alias without evidence.

Use concise factual titles and summaries. Keep opinions, sensitive anecdotes, and unrelated details out of summaries. Evidence should be the shortest source fragment that supports the interaction and identity references.

Calibrate confidence as evidence quality, not prose fluency:

- `0.95-1.0`: explicit identity, interaction, and date.
- `0.85-0.94`: clear interaction with only minor normalization.
- `0.60-0.84`: an alias, inferred date, uncertain entity type, or other material ambiguity.
- Below `0.60`: omit unless preserving the candidate for review is clearly valuable.

Add machine-readable `review_reasons` such as `ambiguous_identity`, `inferred_date`, `approximate_date`, `ambiguous_location`, or `low_confidence`. The importer, not this skill, owns database matching and canonical IDs.

## Output and validation

Write UTF-8 JSONL with no Markdown fences, comments, preamble, or trailing summary. Use a relative, portable `source.key`; never put an absolute filesystem path in output. The key must remain stable across reruns, for example `<document-name>#<date-or-section>`.

Treat the validated JSONL as a retained user artifact, not temporary scratch data:

- Honor a user-specified output path.
- Otherwise, when operating in a Kizuna checkout, write one final file under its ignored `import/` directory using a descriptive source-and-scope name such as `<source-stem>-<date-or-month>.jsonl`.
- Otherwise, write beside the source note unless that location is unsuitable or the user directs another location.
- Parallel extraction may use temporary shards, but merge them into one final file and retain the final file.
- Do not delete or overwrite a successful final JSONL after validation or ingestion unless the user explicitly requests it. For a rerun, obtain confirmation before replacing an existing output or choose a clearly versioned name.
- Keep note-derived JSONL out of Git by default. If the chosen path is tracked or not ignored, warn the user before writing because the file may contain private data.

Before finishing:

1. Parse every nonblank output line as JSON.
2. Verify every line has `schema_version: "kizuna.note-extraction.v1"`.
3. Verify all event refs exist in the same line and have the required entity type.
4. Verify every event type is one of the contract values.
5. From the Kizuna repository, run `cd backend && PYTHONPATH=. uv run python scripts/validate_note_jsonl.py <output-path>` and correct every reported error.
6. Confirm the retained file still exists after any ingestion step.
7. Report the output path and counts only; do not echo note-derived contents unless asked.
