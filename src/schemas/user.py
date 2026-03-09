from uuid import UUID

from pydantic import BaseModel


class ProfileResponse(BaseModel):
    first_name: str
    last_name: str
    phone: str | None = None
    company_name: str | None = None
    avatar_url: str | None = None
    metadata: dict | None = None

    model_config = {"from_attributes": True}


class AgencyBrief(BaseModel):
    id: UUID
    name: str
    role_in_agency: str

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    id: UUID
    email: str
    role: str
    is_email_verified: bool
    profile_completed: bool
    profile: ProfileResponse | None = None
    agency: AgencyBrief | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserResponse | None = None


class ProfileCompleteRequest(BaseModel):
    first_name: str
    last_name: str
    phone: str | None = None
    company_name: str | None = None
    agency_id: str | None = None


class ProfileUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    company_name: str | None = None
