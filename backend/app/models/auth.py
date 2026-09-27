import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class AuthUser(IdMixin, TimestampMixin, Base):
    """The owner account (single-user, ADR-007). Created only by the CLI, never by the API."""

    __tablename__ = "auth_users"

    username: Mapped[str] = mapped_column(String(64), unique=True)
    # Argon2id PHC string from pwdlib. Never the password.
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class AuthSession(IdMixin, Base):
    """A server-side login session. Only the SHA-256 of the opaque cookie token is stored."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[AuthUser] = relationship(back_populates="sessions")
