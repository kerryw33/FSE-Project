import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SettlementMessageStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


def _uuid() -> str:
    return str(uuid.uuid4())


class SettlementMessage(Base):
    """FR-21: a queued settlement instruction, placed once a remittance's
    ZAR cash-in is confirmed.

    Implemented as a DB-backed queue table rather than RabbitMQ/Redis
    Streams/Kafka - neither was available to stand up in this environment
    (no Redis/RabbitMQ installed, Docker daemon not running). Enqueue/
    claim/ack semantics are the same as a real broker, so swapping one in
    later means replacing this table's producer/consumer (see
    app.services.settlement), not any caller.

    FR-25: the unique constraint on remittance_id means a given remittance
    can never have more than one message queued for it - the first line
    of defence against a duplicate crediting the recipient twice. The
    second line is in app.services.settlement.process_settlement_message,
    which is a no-op on a message that's already COMPLETED.
    """

    __tablename__ = "settlement_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    remittance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("remittances.id"), unique=True, nullable=False
    )
    status: Mapped[SettlementMessageStatus] = mapped_column(
        Enum(SettlementMessageStatus), default=SettlementMessageStatus.PENDING, nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    remittance: Mapped["Remittance"] = relationship("Remittance")
