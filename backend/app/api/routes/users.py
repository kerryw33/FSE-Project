from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """FR-04a: view own basic profile information."""
    return current_user


@router.patch("/me", response_model=UserOut)
def update_my_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """FR-04a: update own basic profile information (full name, email, mobile)."""
    if payload.email is not None and payload.email != current_user.email:
        if db.query(User).filter(User.email == payload.email, User.id != current_user.id).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
        current_user.email = payload.email

    if payload.mobile_number is not None and payload.mobile_number != current_user.mobile_number:
        if (
            db.query(User)
            .filter(User.mobile_number == payload.mobile_number, User.id != current_user.id)
            .first()
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Mobile number is already registered")
        current_user.mobile_number = payload.mobile_number

    if payload.full_name is not None:
        current_user.full_name = payload.full_name

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user
