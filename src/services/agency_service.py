"""Agency management business logic."""

import math
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core import AuthorizationError, ConflictError, NotFoundError, ValidationError
from src.models.agency import Agency, UserAgency
from src.models.enums import AgencyRole, AuthAction, UserRole
from src.models.user import User
from src.services.log_service import log_action


async def create_agency(
    db: AsyncSession,
    user: User,
    name: str,
    registration_number: str,
    address: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    if user.role not in (UserRole.AGENCY_MANAGER, UserRole.ADMIN):
        raise AuthorizationError("Only agency managers and admins can create agencies")

    result = await db.execute(
        select(Agency).where(Agency.registration_number == registration_number)
    )
    if result.scalar_one_or_none():
        raise ConflictError("An agency with this registration number already exists")

    agency = Agency(
        name=name,
        registration_number=registration_number,
        address=address,
        phone=phone,
        email=email,
        created_by=user.id,
        is_active=True,
    )
    db.add(agency)
    await db.flush()

    await log_action(
        db, AuthAction.AGENCY_CREATED,
        user_id=str(user.id), email=user.email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"agency_id": str(agency.id), "name": name},
    )

    return {
        "id": str(agency.id),
        "name": agency.name,
        "registration_number": agency.registration_number,
        "address": agency.address,
        "phone": agency.phone,
        "email": agency.email,
        "is_active": agency.is_active,
        "created_at": agency.created_at.isoformat() if agency.created_at else None,
    }


async def list_agencies(
    db: AsyncSession,
    user: User,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
) -> dict:
    query = select(Agency)

    if user.role == UserRole.AGENCY_MANAGER:
        # Only show own agencies
        subq = select(UserAgency.agency_id).where(UserAgency.user_id == user.id)
        query = query.where(Agency.id.in_(subq))
    elif user.role not in (UserRole.ADMIN, UserRole.GOVERNMENT):
        raise AuthorizationError("No permission to list agencies")

    if search:
        query = query.where(Agency.name.ilike(f"%{search}%"))

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Agency.created_at.desc()).offset(offset).limit(page_size)
    )
    agencies = result.scalars().all()

    return {
        "items": [
            {
                "id": str(a.id),
                "name": a.name,
                "registration_number": a.registration_number,
                "is_active": a.is_active,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in agencies
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


async def get_agency(db: AsyncSession, user: User, agency_id: str) -> dict:
    result = await db.execute(
        select(Agency)
        .options(selectinload(Agency.members).selectinload(UserAgency.user))
        .where(Agency.id == agency_id)
    )
    agency = result.scalar_one_or_none()
    if not agency:
        raise NotFoundError("Agency not found")

    # Permission check
    if user.role == UserRole.AGENCY_MANAGER:
        member_ids = {str(m.user_id) for m in agency.members}
        if str(user.id) not in member_ids:
            raise AuthorizationError("You can only view your own agency")

    members = []
    for m in agency.members:
        u = m.user
        members.append({
            "user_id": str(m.user_id),
            "email": u.email if u else None,
            "role_in_agency": m.role_in_agency.value,
            "joined_at": m.joined_at.isoformat() if m.joined_at else None,
        })

    return {
        "id": str(agency.id),
        "name": agency.name,
        "registration_number": agency.registration_number,
        "address": agency.address,
        "phone": agency.phone,
        "email": agency.email,
        "is_active": agency.is_active,
        "created_at": agency.created_at.isoformat() if agency.created_at else None,
        "members": members,
    }


async def update_agency(
    db: AsyncSession,
    user: User,
    agency_id: str,
    data: dict,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    result = await db.execute(select(Agency).where(Agency.id == agency_id))
    agency = result.scalar_one_or_none()
    if not agency:
        raise NotFoundError("Agency not found")

    if user.role == UserRole.AGENCY_MANAGER:
        result = await db.execute(
            select(UserAgency).where(
                UserAgency.user_id == user.id,
                UserAgency.agency_id == agency.id,
                UserAgency.role_in_agency == AgencyRole.MANAGER,
            )
        )
        if not result.scalar_one_or_none():
            raise AuthorizationError("You can only update your own agency")

    changed = []
    for field in ("name", "address", "phone", "email"):
        if field in data and data[field] is not None:
            setattr(agency, field, data[field])
            changed.append(field)

    # Only admin can toggle is_active
    if "is_active" in data and data["is_active"] is not None:
        if user.role != UserRole.ADMIN:
            raise AuthorizationError("Only admins can change agency active status")
        agency.is_active = data["is_active"]
        changed.append("is_active")

    await db.flush()

    await log_action(
        db, AuthAction.AGENCY_UPDATED,
        user_id=str(user.id), email=user.email,
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"agency_id": str(agency.id), "fields_changed": changed},
    )

    return {
        "id": str(agency.id),
        "name": agency.name,
        "registration_number": agency.registration_number,
        "address": agency.address,
        "phone": agency.phone,
        "email": agency.email,
        "is_active": agency.is_active,
        "created_at": agency.created_at.isoformat() if agency.created_at else None,
    }
