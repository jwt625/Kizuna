"""add_note_ingestion_staging_tables

Revision ID: 7fbe6fdb6d2c
Revises: 0faf33ae7a64
Create Date: 2026-04-25 14:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7fbe6fdb6d2c"
down_revision: Union[str, Sequence[str], None] = "0faf33ae7a64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "note_sources",
        sa.Column("file_path", sa.String(length=1000), nullable=False),
        sa.Column("section_key", sa.String(length=200), nullable=False),
        sa.Column("heading", sa.String(length=500), nullable=False),
        sa.Column("note_date", sa.Date(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("scan_status", sa.String(length=40), nullable=False),
        sa.Column("extraction_status", sa.String(length=40), nullable=False),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_note_sources")),
    )
    op.create_index(op.f("ix_note_sources_content_hash"), "note_sources", ["content_hash"], unique=False)
    op.create_index(op.f("ix_note_sources_extraction_status"), "note_sources", ["extraction_status"], unique=False)
    op.create_index(op.f("ix_note_sources_file_path"), "note_sources", ["file_path"], unique=False)
    op.create_index(op.f("ix_note_sources_last_extracted_at"), "note_sources", ["last_extracted_at"], unique=False)
    op.create_index(op.f("ix_note_sources_last_scanned_at"), "note_sources", ["last_scanned_at"], unique=False)
    op.create_index(op.f("ix_note_sources_note_date"), "note_sources", ["note_date"], unique=False)
    op.create_index(op.f("ix_note_sources_scan_status"), "note_sources", ["scan_status"], unique=False)
    op.create_index(op.f("ix_note_sources_section_key"), "note_sources", ["section_key"], unique=False)
    op.create_index(op.f("ix_note_sources_source_type"), "note_sources", ["source_type"], unique=False)

    op.create_table(
        "note_extraction_runs",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("raw_response_json", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["note_sources.id"], name=op.f("fk_note_extraction_runs_source_id_note_sources"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_note_extraction_runs")),
    )
    op.create_index(op.f("ix_note_extraction_runs_provider_name"), "note_extraction_runs", ["provider_name"], unique=False)
    op.create_index(op.f("ix_note_extraction_runs_source_id"), "note_extraction_runs", ["source_id"], unique=False)
    op.create_index(op.f("ix_note_extraction_runs_status"), "note_extraction_runs", ["status"], unique=False)

    op.create_table(
        "note_entity_mentions",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("raw_text", sa.String(length=300), nullable=False),
        sa.Column("normalized_text", sa.String(length=300), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("review_status", sa.String(length=40), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"],
            ["note_extraction_runs.id"],
            name=op.f("fk_note_entity_mentions_extraction_run_id_note_extraction_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["note_sources.id"], name=op.f("fk_note_entity_mentions_source_id_note_sources"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_note_entity_mentions")),
    )
    op.create_index(op.f("ix_note_entity_mentions_entity_type"), "note_entity_mentions", ["entity_type"], unique=False)
    op.create_index(op.f("ix_note_entity_mentions_extraction_run_id"), "note_entity_mentions", ["extraction_run_id"], unique=False)
    op.create_index(op.f("ix_note_entity_mentions_normalized_text"), "note_entity_mentions", ["normalized_text"], unique=False)
    op.create_index(op.f("ix_note_entity_mentions_raw_text"), "note_entity_mentions", ["raw_text"], unique=False)
    op.create_index(op.f("ix_note_entity_mentions_review_status"), "note_entity_mentions", ["review_status"], unique=False)
    op.create_index(op.f("ix_note_entity_mentions_source_id"), "note_entity_mentions", ["source_id"], unique=False)

    op.create_table(
        "note_event_drafts",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("started_on", sa.Date(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("review_status", sa.String(length=40), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"], ["note_extraction_runs.id"], name=op.f("fk_note_event_drafts_extraction_run_id_note_extraction_runs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["note_sources.id"], name=op.f("fk_note_event_drafts_source_id_note_sources"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_note_event_drafts")),
    )
    op.create_index(op.f("ix_note_event_drafts_event_type"), "note_event_drafts", ["event_type"], unique=False)
    op.create_index(op.f("ix_note_event_drafts_extraction_run_id"), "note_event_drafts", ["extraction_run_id"], unique=False)
    op.create_index(op.f("ix_note_event_drafts_review_status"), "note_event_drafts", ["review_status"], unique=False)
    op.create_index(op.f("ix_note_event_drafts_source_id"), "note_event_drafts", ["source_id"], unique=False)
    op.create_index(op.f("ix_note_event_drafts_started_on"), "note_event_drafts", ["started_on"], unique=False)
    op.create_index(op.f("ix_note_event_drafts_title"), "note_event_drafts", ["title"], unique=False)

    op.create_table(
        "note_match_candidates",
        sa.Column("mention_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("subtitle", sa.String(length=500), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("is_selected", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["mention_id"], ["note_entity_mentions.id"], name=op.f("fk_note_match_candidates_mention_id_note_entity_mentions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_note_match_candidates")),
    )
    op.create_index(op.f("ix_note_match_candidates_entity_id"), "note_match_candidates", ["entity_id"], unique=False)
    op.create_index(op.f("ix_note_match_candidates_entity_type"), "note_match_candidates", ["entity_type"], unique=False)
    op.create_index(op.f("ix_note_match_candidates_is_selected"), "note_match_candidates", ["is_selected"], unique=False)
    op.create_index(op.f("ix_note_match_candidates_mention_id"), "note_match_candidates", ["mention_id"], unique=False)

    op.create_table(
        "note_review_decisions",
        sa.Column("mention_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("matched_entity_type", sa.String(length=40), nullable=True),
        sa.Column("matched_entity_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["mention_id"], ["note_entity_mentions.id"], name=op.f("fk_note_review_decisions_mention_id_note_entity_mentions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_note_review_decisions")),
    )
    op.create_index(op.f("ix_note_review_decisions_action"), "note_review_decisions", ["action"], unique=False)
    op.create_index(op.f("ix_note_review_decisions_matched_entity_id"), "note_review_decisions", ["matched_entity_id"], unique=False)
    op.create_index(op.f("ix_note_review_decisions_matched_entity_type"), "note_review_decisions", ["matched_entity_type"], unique=False)
    op.create_index(op.f("ix_note_review_decisions_mention_id"), "note_review_decisions", ["mention_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_note_review_decisions_mention_id"), table_name="note_review_decisions")
    op.drop_index(op.f("ix_note_review_decisions_matched_entity_type"), table_name="note_review_decisions")
    op.drop_index(op.f("ix_note_review_decisions_matched_entity_id"), table_name="note_review_decisions")
    op.drop_index(op.f("ix_note_review_decisions_action"), table_name="note_review_decisions")
    op.drop_table("note_review_decisions")

    op.drop_index(op.f("ix_note_match_candidates_mention_id"), table_name="note_match_candidates")
    op.drop_index(op.f("ix_note_match_candidates_is_selected"), table_name="note_match_candidates")
    op.drop_index(op.f("ix_note_match_candidates_entity_type"), table_name="note_match_candidates")
    op.drop_index(op.f("ix_note_match_candidates_entity_id"), table_name="note_match_candidates")
    op.drop_table("note_match_candidates")

    op.drop_index(op.f("ix_note_event_drafts_title"), table_name="note_event_drafts")
    op.drop_index(op.f("ix_note_event_drafts_started_on"), table_name="note_event_drafts")
    op.drop_index(op.f("ix_note_event_drafts_source_id"), table_name="note_event_drafts")
    op.drop_index(op.f("ix_note_event_drafts_review_status"), table_name="note_event_drafts")
    op.drop_index(op.f("ix_note_event_drafts_extraction_run_id"), table_name="note_event_drafts")
    op.drop_index(op.f("ix_note_event_drafts_event_type"), table_name="note_event_drafts")
    op.drop_table("note_event_drafts")

    op.drop_index(op.f("ix_note_entity_mentions_source_id"), table_name="note_entity_mentions")
    op.drop_index(op.f("ix_note_entity_mentions_review_status"), table_name="note_entity_mentions")
    op.drop_index(op.f("ix_note_entity_mentions_raw_text"), table_name="note_entity_mentions")
    op.drop_index(op.f("ix_note_entity_mentions_normalized_text"), table_name="note_entity_mentions")
    op.drop_index(op.f("ix_note_entity_mentions_extraction_run_id"), table_name="note_entity_mentions")
    op.drop_index(op.f("ix_note_entity_mentions_entity_type"), table_name="note_entity_mentions")
    op.drop_table("note_entity_mentions")

    op.drop_index(op.f("ix_note_extraction_runs_status"), table_name="note_extraction_runs")
    op.drop_index(op.f("ix_note_extraction_runs_source_id"), table_name="note_extraction_runs")
    op.drop_index(op.f("ix_note_extraction_runs_provider_name"), table_name="note_extraction_runs")
    op.drop_table("note_extraction_runs")

    op.drop_index(op.f("ix_note_sources_source_type"), table_name="note_sources")
    op.drop_index(op.f("ix_note_sources_section_key"), table_name="note_sources")
    op.drop_index(op.f("ix_note_sources_scan_status"), table_name="note_sources")
    op.drop_index(op.f("ix_note_sources_note_date"), table_name="note_sources")
    op.drop_index(op.f("ix_note_sources_last_scanned_at"), table_name="note_sources")
    op.drop_index(op.f("ix_note_sources_last_extracted_at"), table_name="note_sources")
    op.drop_index(op.f("ix_note_sources_file_path"), table_name="note_sources")
    op.drop_index(op.f("ix_note_sources_extraction_status"), table_name="note_sources")
    op.drop_index(op.f("ix_note_sources_content_hash"), table_name="note_sources")
    op.drop_table("note_sources")
