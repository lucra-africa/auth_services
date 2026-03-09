from uuid import UUID

from pydantic import BaseModel


class AgencyCreateRequest(BaseModel):
    name: str
    registration_number: str
    address: str | None = None
    phone: str | None = None
    email: str | None = None


class AgencyUpdateRequest(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    is_active: bool | None = None


class AgencyMemberResponse(BaseModel):
    user_id: UUID
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role_in_agency: str
    joined_at: str

    model_config = {"from_attributes": True}


class AgencyResponse(BaseModel):
    id: UUID
    name: str
    registration_number: str
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    is_active: bool
    created_at: str
    member_count: int = 0

    model_config = {"from_attributes": True}


class AgencyDetailResponse(AgencyResponse):
    members: list[AgencyMemberResponse] = []


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int
