from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.deps import require_approved_kyc
from app.database import get_db
from app.models.beneficiary import Beneficiary
from app.models.fee_config import FeeConfig
from app.models.remittance import Remittance
from app.models.user import User
from app.schemas.remittance import RemittanceOut, RemittanceQuoteRequest
from app.services.exchange_rate import get_usd_zar_rate
from app.services.limits import get_tier_limits, tier_for_user, usage_this_month, usage_today
from app.services.quote import build_quote

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
