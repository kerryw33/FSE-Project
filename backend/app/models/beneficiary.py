import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Beneficiary(Base):
    """FR-10: a beneficiary record a sender adds, describing who they want
    to pay out to.

    FR-12a/FR-12c: `linked_user_id` is populated once a registered account
    is found matching the beneficiary's mobile number or email address -
    either immediately on creation, or retroactively when that account
    registers later (see app.services.beneficiary_linking). Until linked,
    the beneficiary cannot receive a custodial wallet or settlement.
    """

    __tablename__ = "beneficiaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sender_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    mobile_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    payout_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    relationship_to_sender: Mapped[str] = mapped_column(String(100), nullable=False)

    linked_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    sender: Mapped["User"] = relationship("User", foreign_keys=[sender_id])
    linked_user: Mapped["User | None"] = relationship("User", foreign_keys=[linked_user_id])

    @property
    def wallet_provisioned(self) -> bool:
        """FR-12b: a wallet exists exactly when linking has happened -
        provisioning is triggered atomically at link time (see
        app.services.beneficiary_linking), so this never drifts from
        linked_user_id."""
        return self.linked_user_id is not None
