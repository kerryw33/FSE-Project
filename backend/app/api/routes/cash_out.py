from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_current_user, require_admin, require_approved_kyc
from app.core.money import to_decimal
from app.database import get_db
from app.models.cash_out import CashOutRequest, CashOutStatus
from app.models.fee_config import FeeConfig
from app.models.user import User
from app.schemas.cash_out import CashOutOut, CashOutRequestCreate
from app.services.cash_out import SUPPORTED_FIAT_CURRENCIES, build_cash_out_quote
from app.services.recipient_wallet import get_or_create_wallet_row

router = APIRouter(prefix="/cash-outs", tags=["cash-out"])


def _get_fee_config(db: DBSession) -> FeeConfig:
    config = db.query(FeeConfig).first()
    if config is None:
        raise RuntimeError("Fee configuration is not seeded")
    return config


@router.post("", response_model=CashOutOut, status_code=status.HTTP_201_CREATED)
def request_cash_out(
    payload: CashOutRequestCreate,
    current_user: User = Depends(require_approved_kyc),
    db: DBSession = Depends(get_db),
):
    """FR-09a: a recipient needs approved KYC to cash out (they may still
    hold RLUSD without it). FR-30: request a cash-out to USD or a
    supported local fiat currency. FR-31: the fiat payout is calculated
    up front from the applicable rate and cash-out fee. The RLUSD amount
    is reserved (debited) immediately to prevent overdrawing the balance
    via concurrent requests, and refunded if the request is later failed.
    """
    if payload.fiat_currency not in SUPPORTED_FIAT_CURRENCIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported fiat currency. Supported: {sorted(SUPPORTED_FIAT_CURRENCIES)}",
        )

    wallet_row = get_or_create_wallet_row(db, current_user.id)
    available = to_decimal(wallet_row.balance)
    if payload.rlusd_amount > available:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Insufficient balance: available {available}, requested {payload.rlusd_amount}",
        )

    fee_config = _get_fee_config(db)
    quote = build_cash_out_quote(payload.rlusd_amount, payload.fiat_currency, fee_config)

    wallet_row.balance = available - payload.rlusd_amount
    db.add(wallet_row)

    cash_out = CashOutRequest(
        user_id=current_user.id,
        rlusd_amount=payload.rlusd_amount,
        fiat_currency=payload.fiat_currency,
        exchange_rate=quote.exchange_rate,
        cash_out_fee_percentage=quote.fee_percentage,
        fee_amount_rlusd=quote.fee_amount_rlusd,
        fiat_payout_amount=quote.fiat_payout_amount,
    )
    db.add(cash_out)
    db.commit()
    db.refresh(cash_out)
    return cash_out


@router.get("/me", response_model=list[CashOutOut])
def list_my_cash_outs(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    return (
        db.query(CashOutRequest)
        .filter(CashOutRequest.user_id == current_user.id)
        .order_by(CashOutRequest.created_at.desc())
        .all()
    )


@router.get("", response_model=list[CashOutOut])
def list_all_cash_outs(
    cash_out_status: CashOutStatus | None = None,
    _admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """FR-35: admin interface for actioning simulated cash-out requests."""
    query = db.query(CashOutRequest)
    if cash_out_status is not None:
        query = query.filter(CashOutRequest.status == cash_out_status)
    return query.order_by(CashOutRequest.created_at.desc()).all()


@router.post("/{cash_out_id}/approve", response_model=CashOutOut)
def approve_cash_out(cash_out_id: str, admin: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    """FR-32/FR-35: requested -> approved."""
    cash_out = db.query(CashOutRequest).filter(CashOutRequest.id == cash_out_id).first()
    if cash_out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cash-out request not found")
    if cash_out.status != CashOutStatus.REQUESTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a requested cash-out can be approved")

    cash_out.status = CashOutStatus.APPROVED
    cash_out.actioned_at = datetime.now(timezone.utc)
    cash_out.actioned_by = admin.id
    db.add(cash_out)
    db.commit()
    db.refresh(cash_out)
    return cash_out


@router.post("/{cash_out_id}/complete", response_model=CashOutOut)
def complete_cash_out(cash_out_id: str, admin: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    """FR-32/FR-35: approved -> completed. The cash-out itself is
    simulated (per FR-32), so this is a status transition representing
    the fiat payout having been delivered - no further RLUSD movement,
    since it was already reserved out of the balance at request time."""
    cash_out = db.query(CashOutRequest).filter(CashOutRequest.id == cash_out_id).first()
    if cash_out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cash-out request not found")
    if cash_out.status != CashOutStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only an approved cash-out can be completed")

    cash_out.status = CashOutStatus.COMPLETED
    cash_out.completed_at = datetime.now(timezone.utc)
    db.add(cash_out)
    db.commit()
    db.refresh(cash_out)
    return cash_out


@router.post("/{cash_out_id}/fail", response_model=CashOutOut)
def fail_cash_out(cash_out_id: str, admin: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    """FR-32/FR-35: requested or approved -> failed, refunding the
    reserved RLUSD back to the recipient's balance."""
    cash_out = db.query(CashOutRequest).filter(CashOutRequest.id == cash_out_id).first()
    if cash_out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cash-out request not found")
    if cash_out.status not in (CashOutStatus.REQUESTED, CashOutStatus.APPROVED):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot fail a completed cash-out")

    wallet_row = get_or_create_wallet_row(db, cash_out.user_id)
    wallet_row.balance = to_decimal(wallet_row.balance) + cash_out.rlusd_amount
    db.add(wallet_row)

    cash_out.status = CashOutStatus.FAILED
    cash_out.actioned_at = datetime.now(timezone.utc)
    cash_out.actioned_by = admin.id
    db.add(cash_out)
    db.commit()
    db.refresh(cash_out)
    return cash_out
