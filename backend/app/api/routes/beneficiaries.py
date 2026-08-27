from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_current_user, require_approved_kyc
from app.database import get_db
from app.models.beneficiary import Beneficiary
from app.models.user import User
from app.schemas.beneficiary import BeneficiaryCreate, BeneficiaryOut
from app.services.beneficiary_linking import try_link_beneficiary

router = APIRouter(prefix="/beneficiaries", tags=["beneficiaries"])


@router.post("", response_model=BeneficiaryOut, status_code=status.HTTP_201_CREATED)
def add_beneficiary(
    payload: BeneficiaryCreate,
    current_user: User = Depends(require_approved_kyc),
    db: DBSession = Depends(get_db),
):
    """FR-10/FR-11: an approved sender adds a beneficiary record."""
    beneficiary = Beneficiary(sender_id=current_user.id, **payload.model_dump())
    db.add(beneficiary)
    db.commit()
    db.refresh(beneficiary)

    try_link_beneficiary(db, beneficiary)  # FR-12a/FR-12b/FR-12c
    db.commit()
    db.refresh(beneficiary)

    return beneficiary


@router.get("", response_model=list[BeneficiaryOut])
def list_my_beneficiaries(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """FR-12: a sender views the list of beneficiaries they have added."""
    return (
        db.query(Beneficiary)
        .filter(Beneficiary.sender_id == current_user.id)
        .order_by(Beneficiary.created_at.desc())
        .all()
    )
