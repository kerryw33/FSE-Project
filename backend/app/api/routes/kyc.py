from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_current_user, require_admin
from app.database import get_db
from app.models.kyc import KYCApplication, KYCStatus
from app.models.user import User
from app.schemas.kyc import KYCOut, KYCReview, KYCStatusOut, KYCSubmit

router = APIRouter(prefix="/kyc", tags=["kyc"])


@router.post("", response_model=KYCOut, status_code=status.HTTP_201_CREATED)
def submit_kyc(
    payload: KYCSubmit,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """FR-05/FR-06: submit a completed KYC application for review.

    A user with no prior application creates one; a user whose application
    was rejected (or is still pending) may resubmit, which overwrites the
    details and resets the application to PENDING.
    """
    application = current_user.kyc_application
    if application is not None and application.status == KYCStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="KYC application is already approved"
        )

    if application is None:
        application = KYCApplication(user_id=current_user.id)

    for field, value in payload.model_dump().items():
        setattr(application, field, value)

    application.status = KYCStatus.PENDING
    application.rejection_reason = None
    application.submitted_at = datetime.now(timezone.utc)
    application.reviewed_at = None
    application.reviewed_by = None

    db.add(application)
    db.commit()
    db.refresh(application)
    return application


@router.get("/me/status", response_model=KYCStatusOut)
def get_my_kyc_status(current_user: User = Depends(get_current_user)):
    """FR-08a: view own current KYC status."""
    application = current_user.kyc_application
    if application is None:
        return KYCStatusOut(status=KYCStatus.NOT_SUBMITTED)
    return application


@router.get("/me", response_model=KYCOut)
def get_my_kyc_application(current_user: User = Depends(get_current_user)):
    """View the full detail of the caller's own KYC application."""
    application = current_user.kyc_application
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No KYC application submitted yet")
    return application


@router.get("", response_model=list[KYCOut])
def list_kyc_applications(
    kyc_status: KYCStatus | None = None,
    _admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """FR-07/FR-33: admin interface for reviewing submitted KYC applications."""
    query = db.query(KYCApplication)
    if kyc_status is not None:
        query = query.filter(KYCApplication.status == kyc_status)
    return query.order_by(KYCApplication.submitted_at.desc()).all()


@router.get("/{application_id}", response_model=KYCOut)
def get_kyc_application(
    application_id: str,
    _admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """FR-07: admin views a single submitted KYC application."""
    application = db.query(KYCApplication).filter(KYCApplication.id == application_id).first()
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="KYC application not found")
    return application


@router.post("/{application_id}/approve", response_model=KYCOut)
def approve_kyc_application(
    application_id: str,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """FR-08/FR-33: admin approves a submitted KYC application."""
    application = db.query(KYCApplication).filter(KYCApplication.id == application_id).first()
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="KYC application not found")
    if application.status != KYCStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only a pending application can be approved"
        )

    application.status = KYCStatus.APPROVED
    application.rejection_reason = None
    application.reviewed_at = datetime.now(timezone.utc)
    application.reviewed_by = admin.id
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


@router.post("/{application_id}/reject", response_model=KYCOut)
def reject_kyc_application(
    application_id: str,
    payload: KYCReview,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """FR-08/FR-33: admin rejects a submitted KYC application."""
    application = db.query(KYCApplication).filter(KYCApplication.id == application_id).first()
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="KYC application not found")
    if application.status != KYCStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only a pending application can be rejected"
        )

    application.status = KYCStatus.REJECTED
    application.rejection_reason = payload.rejection_reason
    application.reviewed_at = datetime.now(timezone.utc)
    application.reviewed_by = admin.id
    db.add(application)
    db.commit()
    db.refresh(application)
    return application
