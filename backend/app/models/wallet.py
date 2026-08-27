import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class RecipientWallet(Base):
    """FR-12b/FR-27 stub: one custodial wallet per recipient user.

    This is a placeholder record only, marking that provisioning has
    happened for a user. Real XRPL account generation, the TrustSet to the
    RLUSD issuer, and balance/transaction tracking belong to the XRPL
    Testnet Integration requirements (FR-27-FR-29) and are not implemented
    yet - xrpl_address stays null until that module exists.
    """

    __tablename__ = "recipient_wallets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    xrpl_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User")
