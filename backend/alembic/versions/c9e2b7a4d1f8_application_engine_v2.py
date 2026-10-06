"""application engine v2: applied_at and application_events

Milestone 15 (ADR-025): `applications.applied_at` (nullable) and the append-only
`application_events` history. Additive only: old application code ignores both. No data change;
no history is invented for existing applications.

Revision ID: c9e2b7a4d1f8
Revises: a3c7e9b1d5f2
Create Date: 2026-10-06 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c9e2b7a4d1f8"
down_revision: str | Sequence[str] | None = "a3c7e9b1d5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = (
    "saved",
    "applying",
    "applied",
    "interview",
    "offer",
    "accepted",
    "rejected",
    "withdrawn",
)
EVENT_TYPES = (
    "created",
    "status_changed",
    "next_action_changed",
    "interview_scheduled",
    "interview_updated",
    "note_added",
    "deadline_changed",
    "offer_received",
)


def _enum(values: Sequence[str], name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    op.add_column("applications", sa.Column("applied_at", sa.DateTime(timezone=True)))
    op.create_table(
        "application_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", _enum(EVENT_TYPES, "application_event_type"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("from_status", _enum(STATUSES, "application_event_from_status"), nullable=True),
        sa.Column("to_status", _enum(STATUSES, "application_event_to_status"), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(metadata_json::text) <= 2000", name="ck_application_events_metadata_bounded"
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_application_events_application_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_application_events"),
    )
    op.create_index(
        "ix_application_events_application_id", "application_events", ["application_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_application_events_application_id", table_name="application_events")
    op.drop_table("application_events")
    op.drop_column("applications", "applied_at")
