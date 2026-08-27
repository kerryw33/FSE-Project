from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.deps import require_admin
from app.database import get_db
from app.models.fee_config import FeeConfig
from app.models.limit_tier import LimitTier, LimitTierKey
from app.models.user import User
from app.schemas.admin_config import FeeConfigOut, FeeConfigUpdate, LimitTierOut, LimitTierUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/fee-config", response_model=FeeConfigOut)
def get_fee_config(_admin: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    """FR-15a: admin views the configurable fee parameters."""
    config = db.query(FeeConfig).first()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Fee configuration is not seeded"
        )
    return config


@router.put("/fee-config", response_model=FeeConfigOut)
def update_fee_config(
    payload: FeeConfigUpdate,
    _admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """FR-15a: admin updates the configurable fee parameters."""
    config = db.query(FeeConfig).first()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Fee configuration is not seeded"
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(config, field, value)

    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.get("/limit-tiers", response_model=list[LimitTierOut])
def list_limit_tiers(_admin: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    """FR-16b: admin views the daily/monthly limit tiers."""
    return db.query(LimitTier).all()


@router.put("/limit-tiers/{tier_key}", response_model=LimitTierOut)
def update_limit_tier(
    tier_key: LimitTierKey,
    payload: LimitTierUpdate,
    _admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """FR-16b: admin updates a limit tier's daily/monthly caps."""
    tier = db.query(LimitTier).filter(LimitTier.tier_key == tier_key).first()
    if tier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Limit tier not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tier, field, value)

    db.add(tier)
    db.commit()
    db.refresh(tier)
    return tier
