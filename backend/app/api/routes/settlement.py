from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.deps import require_admin
from app.database import get_db
from app.models.remittance import RemittanceStatus
from app.models.settlement import SettlementMessage, SettlementMessageStatus
from app.models.user import User
from app.schemas.settlement import SettlementMessageOut
from app.services.settlement import process_pending_settlements

router = APIRouter(prefix="/admin/settlement", tags=["settlement"])


@router.post("/run", response_model=list[SettlementMessageOut])
def run_settlement_worker(_admin: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    """FR-22: manually trigger one pass of the settlement worker - the
    same function scripts/run_settlement_worker.py runs as a standalone
    process. Exposed here so settlement can be demonstrated via the API
    without needing a second long-lived process during development.
    """
    return process_pending_settlements(db)


@router.get("", response_model=list[SettlementMessageOut])
def list_settlement_messages(
    message_status: SettlementMessageStatus | None = None,
    _admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    query = db.query(SettlementMessage)
    if message_status is not None:
        query = query.filter(SettlementMessage.status == message_status)
    return query.order_by(SettlementMessage.created_at.desc()).all()


@router.post("/{message_id}/retry", response_model=SettlementMessageOut)
def retry_settlement_message(
    message_id: str, _admin: User = Depends(require_admin), db: DBSession = Depends(get_db)
):
    """No FR mandates automatic retry, but FR-24's failure handling is
    only useful in practice if a failed settlement can be tried again."""
    message = db.query(SettlementMessage).filter(SettlementMessage.id == message_id).first()
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settlement message not found")
    if message.status != SettlementMessageStatus.FAILED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a failed message can be retried")

    message.status = SettlementMessageStatus.PENDING
    message.failure_reason = None
    db.add(message)

    message.remittance.status = RemittanceStatus.SETTLEMENT_QUEUED
    message.remittance.settlement_failure_reason = None
    db.add(message.remittance)

    db.commit()
    db.refresh(message)
    return message
