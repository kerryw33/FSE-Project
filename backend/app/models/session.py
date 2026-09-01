import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _token() -> str:
    return secrets.token_urlsafe(48)


class Session(Base):
    """An opaque bearer session token (FR-02/FR-02a).

    Assumption: neither functional_requirements.pdf nor project_brief.pdf
    mandates a specific token mechanism - FR-02/FR-02a just require login
    with credentials and a logout that "terminates their session." JWT
    would satisfy the letter of that, but not really the spirit: a JWT is
    stateless by design, so the server never holds a copy of it and has
    nothing to delete on logout - the token stays cryptographically valid
    until it expires no matter what the server does. Making logout actually
    revoke access would mean adding a blacklist table (revoked token IDs)
    or a per-user token-version counter, either of which is a row the
    server tracks and can invalidate - i.e. the same shape as this table,
    just with JWT's signing/claims/expiry machinery layered on top. That
    machinery earns its keep when multiple independent services need to
    verify a token without calling back to the auth service; this project
    is a single FastAPI backend, so there's no second verifier to benefit.

    An opaque token looked up against this table gets the same security
    properties (unguessable, revocable, expiring) with logout being a
    single UPDATE (revoked_at = now()) instead of token-blacklist upkeep.
    """

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True, default=_token)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="sessions")

    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            # SQLite drops tz-awareness on round-trip; the value was always
            # written as UTC (see create_session), so reattach it here.
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) <= expires_at
