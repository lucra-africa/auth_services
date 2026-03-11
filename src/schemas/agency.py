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
    user_id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role_in_agency: str
    joined_at: str


class AgencyResponse(BaseModel):
    id: str
    name: str
    registration_number: str
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    is_active: bool
    created_at: str
    member_count: int = 0


class AgencyDetailResponse(AgencyResponse):
    members: list[AgencyMemberResponse] = []


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int
