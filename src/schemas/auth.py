import re
from typing import Literal, Optional

from pydantic import BaseModel, field_validator


class AddressSchema(BaseModel):
    street: str | None = None
    city: str | None = None
    province: str | None = None
    country: str | None = None


class SignupRequest(BaseModel):
    email: str
    password: str
    role: Literal["importer", "agency_manager"]
    phone_number: str | None = None
    address: AddressSchema | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, v):
            raise ValueError("Invalid email address")
        return v.lower().strip()


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()


class RefreshRequest(BaseModel):
    refresh_token: str


class InviteRequest(BaseModel):
    email: str
    role: Literal["importer", "agent", "agency_manager", "inspector", "government_rra", "government_rsb"]
    agency_id: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()


class InvitedSignupRequest(BaseModel):
    token: str
    password: str
    first_name: str
    last_name: str
    phone: str | None = None
    phone_number: str | None = None
    address: AddressSchema | None = None


class BulkInviteRequest(BaseModel):
    invitations: list[InviteRequest]

    @field_validator("invitations")
    @classmethod
    def validate_length(cls, v: list) -> list:
        if len(v) == 0:
            raise ValueError("At least one invitation is required")
        if len(v) > 20:
            raise ValueError("Maximum 20 invitations per batch")
        return v


class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
