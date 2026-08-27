import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.database import Base


class KYCStatus(str, enum.Enum):
    """FR-08a: not_submitted is the implicit status before a user ever submits."""

    NOT_SUBMITTED = "not_submitted"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def _uuid() -> str:
    return str(uuid.uuid4())


class KYCApplication(Base):
    """FR-05/FR-06: the KYC application a user submits for review.

    One row per user - a rejected user resubmits by updating and
    re-submitting the same application (status moves back to PENDING),
    keeping a single current record rather than an unbounded history.
    """

    __tablename__ = "kyc_applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, nullable=False)

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    nationality: Mapped[str] = mapped_column(String(100), nullable=False)
    identification_number: Mapped[str] = mapped_column(EncryptedString(500), nullable=False)
    residential_address: Mapped[str] = mapped_column(Text, nullable=False)
    mobile_number: Mapped[str] = mapped_column(String(32), nullable=False)
    email_address: Mapped[str] = mapped_column(String(255), nullable=False)
    source_of_funds: Mapped[str] = mapped_column(String(500), nullable=False)

    status: Mapped[KYCStatus] = mapped_column(Enum(KYCStatus), default=KYCStatus.NOT_SUBMITTED, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship("User", back_populates="kyc_application", foreign_keys=[user_id])
