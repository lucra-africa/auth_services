from pydantic import BaseModel


class AddressResponse(BaseModel):
    street: str | None = None
    city: str | None = None
    province: str | None = None
    country: str | None = None


class ProfileResponse(BaseModel):
    first_name: str
    last_name: str
    phone: str | None = None
    phone_number: str | None = None
    company_name: str | None = None
    avatar_url: str | None = None
    address: AddressResponse | None = None
    metadata: dict | None = None


class AgencyBrief(BaseModel):
    id: str
    name: str
    role_in_agency: str


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_email_verified: bool
    profile_completed: bool
    profile: ProfileResponse | None = None
    agency: AgencyBrief | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserResponse | None = None


class AddressInput(BaseModel):
    street: str | None = None
    city: str | None = None
    province: str | None = None
    country: str | None = None


class ProfileCompleteRequest(BaseModel):
    first_name: str
    last_name: str
    phone: str | None = None
    phone_number: str | None = None
    company_name: str | None = None
    agency_id: str | None = None
    address: AddressInput | None = None


class ProfileUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    phone_number: str | None = None
    company_name: str | None = None
    address: AddressInput | None = None
