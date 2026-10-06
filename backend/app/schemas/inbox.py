"""Action Inbox response (ADR-020). Contract shared by the backend and frontend."""

import datetime as dt
import uuid

from pydantic import BaseModel


class InboxItem(BaseModel):
    """Minimal on purpose: where to go (id), what it is, why it is here, and the date that
    matters. `id` is an opportunity ID, or a source ID in the source-warnings section."""

    id: uuid.UUID
    title: str
    organization: str
    reason: str
    date: dt.date | None = None
    # ADR-025: for application items, why (follow_up_overdue, follow_up_due, interview, stale).
    kind: str | None = None


class InboxSection(BaseModel):
    total: int
    items: list[InboxItem]


class InboxResponse(BaseModel):
    today: dt.date
    new_high_fit: InboxSection
    closing_soon: InboxSection
    pending_requirement_review: InboxSection
    source_warnings: InboxSection
    program_verify_by: InboxSection
    applications: InboxSection
