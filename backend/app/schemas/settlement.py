from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.settlement import SettlementMessageStatus


class SettlementMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    remittance_id: str
    status: SettlementMessageStatus
    attempts: int
    failure_reason: str | None
    created_at: datetime
    processed_at: datetime | None
