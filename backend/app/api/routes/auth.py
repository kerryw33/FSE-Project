from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_current_session
from app.core.security import create_session, hash_password, revoke_session, verify_password
from app.database import get_db
from app.models.session import Session as SessionModel
from app.models.user import User
from app.schemas.user import TokenResponse, UserLogin, UserOut, UserRegister
from app.services.beneficiary_linking import link_pending_beneficiaries_for_new_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: DBSession = Depends(get_db)):
    """FR-01/FR-03: register a new account; email and mobile number must be unique."""
    if db.query(User).filter(User.email == payload.email).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
    if db.query(User).filter(User.mobile_number == payload.mobile_number).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Mobile number is already registered")

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        mobile_number=payload.mobile_number,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    link_pending_beneficiaries_for_new_user(db, user)  # FR-12c

    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: DBSession = Depends(get_db)):
    """FR-02: log in with registered credentials."""
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    session = create_session(db, user.id)
    return TokenResponse(access_token=session.token, expires_at=session.expires_at, user=user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    session: SessionModel = Depends(get_current_session),
    db: DBSession = Depends(get_db),
):
    """FR-02a: log out, terminating the current session."""
    revoke_session(db, session)
