from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.beneficiary import Beneficiary
from app.models.cash_out import CashOutRequest
from app.models.remittance import Remittance, RemittanceStatus
from app.models.user import User
from app.schemas.wallet import CashOutSummaryOut, IncomingTransferOut, WalletOut
from app.services.recipient_wallet import get_or_create_wallet_row

router = APIRouter(prefix="/wallet", tags=["wallet"])

_VISIBLE_INCOMING_STATUSES = [
    RemittanceStatus.SETTLEMENT_QUEUED,
    RemittanceStatus.SETTLED,
    RemittanceStatus.SETTLEMENT_FAILED,
]


@router.get("/me", response_model=WalletOut)
def get_my_wallet(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    """FR-27/FR-28: the recipient's custodial wallet - available RLUSD
    balance, incoming transfers (with status/date/XRPL tx hash), and
    cash-out history."""
    wallet_row = get_or_create_wallet_row(db, current_user.id)

    incoming = (
        db.query(Remittance)
        .join(Beneficiary, Remittance.beneficiary_id == Beneficiary.id)
        .filter(Beneficiary.linked_user_id == current_user.id)
        .filter(Remittance.status.in_(_VISIBLE_INCOMING_STATUSES))
        .order_by(Remittance.created_at.desc())
        .all()
    )
    cash_outs = (
        db.query(CashOutRequest)
        .filter(CashOutRequest.user_id == current_user.id)
        .order_by(CashOutRequest.created_at.desc())
        .all()
    )

    return WalletOut(
        balance_rlusd=wallet_row.balance,
        xrpl_address=wallet_row.xrpl_address,
        incoming_transfers=[
            IncomingTransferOut(
                remittance_id=r.id,
                rlusd_amount=r.rlusd_amount,
                status=r.status.value,
                xrpl_tx_hash=r.xrpl_settlement_tx_hash,
                settled_at=r.settled_at,
                created_at=r.created_at,
            )
            for r in incoming
        ],
        cash_out_transactions=[
            CashOutSummaryOut(
                id=c.id,
                rlusd_amount=c.rlusd_amount,
                fiat_currency=c.fiat_currency,
                fiat_payout_amount=c.fiat_payout_amount,
                status=c.status.value,
                created_at=c.created_at,
                completed_at=c.completed_at,
            )
            for c in cash_outs
        ],
    )
