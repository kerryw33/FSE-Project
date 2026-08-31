from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_current_user, require_admin, require_approved_kyc
from app.database import get_db
from app.models.beneficiary import Beneficiary
from app.models.fee_config import FeeConfig
from app.models.remittance import Remittance, RemittanceStatus
from app.models.user import User
from app.schemas.remittance import CashInInitiateRequest, RemittanceOut, RemittanceQuoteRequest
from app.services.exchange_rate import get_usd_zar_rate
from app.services.limits import get_tier_limits, tier_for_user, usage_this_month, usage_today
from app.services.quote import build_quote
from app.services.settlement import enqueue_settlement

router = APIRouter(prefix="/remittances", tags=["remittances"])


def _get_fee_config(db: DBSession) -> FeeConfig:
    config = db.query(FeeConfig).first()
    if config is None:
        raise RuntimeError("Fee configuration is not seeded")
    return config


@router.post("", response_model=RemittanceOut, status_code=status.HTTP_201_CREATED)
def create_remittance_quote(
    payload: RemittanceQuoteRequest,
    current_user: User = Depends(require_approved_kyc),
    db: DBSession = Depends(get_db),
):
    """FR-13/FR-14: create a remittance quote for a ZAR amount, locking in
    the exchange rate and fee breakdown. FR-16/FR-17: rejected if it would
    push the sender over their daily or monthly limit.
    """
    beneficiary = (
        db.query(Beneficiary)
        .filter(Beneficiary.id == payload.beneficiary_id, Beneficiary.sender_id == current_user.id)
        .first()
    )
    if beneficiary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Beneficiary not found")

    tier_key = tier_for_user(current_user)
    tier = get_tier_limits(db, tier_key)

    used_today = usage_today(db, current_user.id)
    used_this_month = usage_this_month(db, current_user.id)
    daily_limit = Decimal(str(tier.daily_limit_zar))
    monthly_limit = Decimal(str(tier.monthly_limit_zar))

    if used_today + payload.zar_amount > daily_limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"This remittance would exceed your daily limit of {daily_limit} ZAR "
                f"(already sent {used_today} ZAR today)"
            ),
        )
    if used_this_month + payload.zar_amount > monthly_limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"This remittance would exceed your monthly limit of {monthly_limit} ZAR "
                f"(already sent {used_this_month} ZAR this month)"
            ),
        )

    fee_config = _get_fee_config(db)
    base_rate = get_usd_zar_rate()
    quote = build_quote(payload.zar_amount, base_rate, fee_config)

    remittance = Remittance(
        sender_id=current_user.id,
        beneficiary_id=beneficiary.id,
        zar_amount=payload.zar_amount,
        exchange_rate=quote.exchange_rate,
        fx_margin_percentage=quote.fx_margin_percentage,
        transaction_fee_zar=quote.transaction_fee_zar,
        rlusd_amount=quote.rlusd_amount,
        cash_out_fee_percentage=quote.cash_out_fee_percentage,
        estimated_cash_out_fee=quote.estimated_cash_out_fee,
        estimated_recipient_payout=quote.estimated_recipient_payout,
    )
    db.add(remittance)
    db.commit()
    db.refresh(remittance)
    return remittance


@router.get("/me", response_model=list[RemittanceOut])
def list_my_remittances(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    """FR-28a: sender views the status and history of remittances they've
    sent - quote details, cash-in status, settlement status, and the XRPL
    transaction hash where applicable."""
    return (
        db.query(Remittance)
        .filter(Remittance.sender_id == current_user.id)
        .order_by(Remittance.created_at.desc())
        .all()
    )


@router.get("", response_model=list[RemittanceOut])
def list_remittances(
    remittance_status: RemittanceStatus | None = None,
    _admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """FR-34: admin interface for finding remittances awaiting cash-in
    confirmation (typically filtered to cash_in_pending)."""
    query = db.query(Remittance)
    if remittance_status is not None:
        query = query.filter(Remittance.status == remittance_status)
    return query.order_by(Remittance.created_at.desc()).all()


@router.post("/{remittance_id}/cash-in", response_model=RemittanceOut)
def initiate_cash_in(
    remittance_id: str,
    payload: CashInInitiateRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """FR-18: the sender initiates a simulated ZAR cash-in payment for
    their own quote, via one supported method."""
    remittance = (
        db.query(Remittance)
        .filter(Remittance.id == remittance_id, Remittance.sender_id == current_user.id)
        .first()
    )
    if remittance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remittance not found")
    if remittance.status != RemittanceStatus.QUOTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cash-in can only be initiated from status 'quoted' (current: '{remittance.status.value}')",
        )

    remittance.cash_in_method = payload.method
    remittance.cash_in_initiated_at = datetime.now(timezone.utc)
    remittance.status = RemittanceStatus.CASH_IN_PENDING
    db.add(remittance)
    db.commit()
    db.refresh(remittance)
    return remittance


@router.post("/{remittance_id}/confirm-cash-in", response_model=RemittanceOut)
def confirm_cash_in(
    remittance_id: str,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """FR-19/FR-34: admin (standing in for a mock payment service) confirms
    a simulated ZAR cash-in has been received.

    FR-20/FR-21: confirming immediately enqueues the settlement message -
    no settlement can happen before cash-in is confirmed, since this is
    the only place a message is ever created.
    """
    remittance = db.query(Remittance).filter(Remittance.id == remittance_id).first()
    if remittance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remittance not found")
    if remittance.status != RemittanceStatus.CASH_IN_PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cash-in can only be confirmed from status 'cash_in_pending' "
                f"(current: '{remittance.status.value}')"
            ),
        )

    remittance.status = RemittanceStatus.CASH_IN_CONFIRMED
    remittance.cash_in_confirmed_at = datetime.now(timezone.utc)
    remittance.cash_in_confirmed_by = admin.id
    db.add(remittance)
    db.commit()
    db.refresh(remittance)

    enqueue_settlement(db, remittance)
    db.refresh(remittance)
    return remittance
