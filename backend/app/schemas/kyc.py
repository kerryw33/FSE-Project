from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.kyc import KYCStatus


class KYCSubmit(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    date_of_birth: date
    nationality: str = Field(min_length=1, max_length=100)
    identification_number: str = Field(min_length=1, max_length=100)
    residential_address: str = Field(min_length=1, max_length=1000)
    mobile_number: str = Field(min_length=5, max_length=32)
    email_address: EmailStr
    source_of_funds: str = Field(min_length=1, max_length=500)


class KYCStatusOut(BaseModel):
    status: KYCStatus
    rejection_reason: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None


class KYCOut(BaseModel):
    """Full application detail - never includes the raw identification number
    over the API beyond what the owner/admin needs (NFR-08a still applies:
    it's decrypted only for the authorised viewer at request time)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    full_name: str
    date_of_birth: date
    nationality: str
    identification_number: str
    residential_address: str
    mobile_number: str
    email_address: str
    source_of_funds: str
    status: KYCStatus
    rejection_reason: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None


class KYCReview(BaseModel):
    rejection_reason: str | None = Field(default=None, max_length=1000)
