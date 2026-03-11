"""Pydantic schemas for the messaging system."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ── Request schemas ─────────────────────────────────────────────────

class CreateThreadRequest(BaseModel):
    thread_type: str = Field(..., pattern="^(declaration|direct|inspection)$")
    subject: str | None = None
    declaration_id: str | None = None
    declaration_name: str | None = None
    participant_ids: list[str] = Field(..., min_length=1)


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    message_type: str = Field(default="text", pattern="^(text|system|file)$")
    file_url: str | None = None
    file_name: str | None = None


class MarkReadRequest(BaseModel):
    thread_id: str


# ── Response schemas ────────────────────────────────────────────────

class ParticipantResponse(BaseModel):
    id: str
    user_id: str
    name: str
    email: str
    role: str
    last_read_at: datetime | None = None


class MessageResponse(BaseModel):
    id: str
    thread_id: str
    sender_id: str | None = None
    sender_name: str = ""
    sender_role: str = ""
    message_type: str
    content: str
    file_url: str | None = None
    file_name: str | None = None
    created_at: datetime


class ThreadResponse(BaseModel):
    id: str
    thread_type: str
    subject: str | None = None
    declaration_id: str | None = None
    declaration_name: str | None = None
    is_closed: bool
    participants: list[ParticipantResponse] = []
    last_message: str = ""
    last_message_time: datetime | None = None
    unread_count: int = 0
    created_at: datetime


class ThreadDetailResponse(ThreadResponse):
    messages: list[MessageResponse] = []


# ── Contact schemas ─────────────────────────────────────────────────

class ContactResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    agency_name: str | None = None


class ContactListResponse(BaseModel):
    items: list[ContactResponse] = []
    total: int = 0
