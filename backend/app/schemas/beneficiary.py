from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class BeneficiaryCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    mobile_number: str | None = Field(default=None, min_length=5, max_length=32)
    email_address: EmailStr | None = None
    country: str = Field(min_length=1, max_length=100)
    payout_currency: str = Field(min_length=3, max_length=10)
    relationship_to_sender: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_contact_detail(self):
        """FR-11: at least a mobile number or an email address is required."""
        if not self.mobile_number and not self.email_address:
            raise ValueError("Either mobile_number or email_address must be provided")
        return self


class BeneficiaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sender_id: str
    full_name: str
    mobile_number: str | None
    email_address: str | None
    country: str
    payout_currency: str
    relationship_to_sender: str
    linked_user_id: str | None
    wallet_provisioned: bool
    created_at: datetime
