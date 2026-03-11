"""Schemas for internal service-to-service API."""

from pydantic import BaseModel


class UserLookupResponse(BaseModel):
    user_id: str
    email: str
    role: str
    backend_role: str
    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None
    address: dict | None = None
    agency_id: str | None = None
    is_active: bool = True
    is_email_verified: bool = False


class BatchUserRequest(BaseModel):
    user_ids: list[str]
