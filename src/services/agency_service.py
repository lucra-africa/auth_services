"""Agency management business logic — MongoDB version."""

import math
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core import AuthorizationError, ConflictError, NotFoundError, ValidationError
from src.models.enums import AuthAction
from src.services.log_service import log_action


async def create_agency(
    db: AsyncIOMotorDatabase,
    user: dict,
    name: str,
    registration_number: str,
    address: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    if user["role"] not in ("agency_manager", "admin"):
        raise AuthorizationError("Only agency managers and admins can create agencies")

    existing = await db.agencies.find_one({"registration_number": registration_number})
    if existing:
        raise ConflictError("An agency with this registration number already exists")

    now = datetime.now(timezone.utc)
    agency_doc = {
        "name": name,
        "registration_number": registration_number,
        "address": address,
        "phone": phone,
        "email": email,
        "created_by": user["_id"],
        "is_active": True,
        "members": [],
        "created_at": now,
        "updated_at": now,
    }
    result = await db.agencies.insert_one(agency_doc)
    agency_id = result.inserted_id

    await log_action(
        db, AuthAction.AGENCY_CREATED,
        user_id=str(user["_id"]), email=user["email"],
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"agency_id": str(agency_id), "name": name},
    )

    return {
        "id": str(agency_id),
        "name": name,
        "registration_number": registration_number,
        "address": address,
        "phone": phone,
        "email": email,
        "is_active": True,
        "created_at": now.isoformat(),
    }


async def list_agencies(
    db: AsyncIOMotorDatabase,
    user: dict,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
) -> dict:
    query: dict = {}

    if user["role"] in ("agency_manager", "agent"):
        # If profile not yet completed, show all agencies so user can pick one
        if user.get("profile_completed"):
            query["members.user_id"] = user["_id"]
    elif user["role"] not in ("admin", "government_rra", "government_rsb"):
        raise AuthorizationError("No permission to list agencies")

    if search:
        query["name"] = {"$regex": search, "$options": "i"}

    total = await db.agencies.count_documents(query)

    offset = (page - 1) * page_size
    cursor = db.agencies.find(query).sort("created_at", -1).skip(offset).limit(page_size)
    agencies = await cursor.to_list(length=page_size)

    return {
        "items": [
            {
                "id": str(a["_id"]),
                "name": a["name"],
                "registration_number": a["registration_number"],
                "is_active": a.get("is_active", True),
                "created_at": a["created_at"].isoformat() if a.get("created_at") else None,
            }
            for a in agencies
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


async def get_agency(db: AsyncIOMotorDatabase, user: dict, agency_id: str) -> dict:
    try:
        agency_oid = ObjectId(agency_id)
    except Exception:
        raise NotFoundError("Agency not found")

    agency = await db.agencies.find_one({"_id": agency_oid})
    if not agency:
        raise NotFoundError("Agency not found")

    # Permission check
    if user["role"] == "agency_manager":
        member_ids = {str(m["user_id"]) for m in agency.get("members", [])}
        if str(user["_id"]) not in member_ids:
            raise AuthorizationError("You can only view your own agency")

    # Build members with user email lookup
    members = []
    for m in agency.get("members", []):
        member_user = await db.users.find_one({"_id": m["user_id"]}, {"email": 1})
        members.append({
            "user_id": str(m["user_id"]),
            "email": member_user["email"] if member_user else None,
            "role_in_agency": m.get("role_in_agency"),
            "joined_at": m["joined_at"].isoformat() if m.get("joined_at") else None,
        })

    return {
        "id": str(agency["_id"]),
        "name": agency["name"],
        "registration_number": agency["registration_number"],
        "address": agency.get("address"),
        "phone": agency.get("phone"),
        "email": agency.get("email"),
        "is_active": agency.get("is_active", True),
        "created_at": agency["created_at"].isoformat() if agency.get("created_at") else None,
        "members": members,
    }


async def update_agency(
    db: AsyncIOMotorDatabase,
    user: dict,
    agency_id: str,
    data: dict,
    ip_address: str | None = None,
    user_agent_str: str | None = None,
) -> dict:
    try:
        agency_oid = ObjectId(agency_id)
    except Exception:
        raise NotFoundError("Agency not found")

    agency = await db.agencies.find_one({"_id": agency_oid})
    if not agency:
        raise NotFoundError("Agency not found")

    if user["role"] == "agency_manager":
        is_manager = any(
            m["user_id"] == user["_id"] and m.get("role_in_agency") == "manager"
            for m in agency.get("members", [])
        )
        if not is_manager:
            raise AuthorizationError("You can only update your own agency")

    changed = []
    update_fields = {}
    for field in ("name", "address", "phone", "email"):
        if field in data and data[field] is not None:
            update_fields[field] = data[field]
            changed.append(field)

    if "is_active" in data and data["is_active"] is not None:
        if user["role"] != "admin":
            raise AuthorizationError("Only admins can change agency active status")
        update_fields["is_active"] = data["is_active"]
        changed.append("is_active")

    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc)
        await db.agencies.update_one({"_id": agency_oid}, {"$set": update_fields})

    await log_action(
        db, AuthAction.AGENCY_UPDATED,
        user_id=str(user["_id"]), email=user["email"],
        ip_address=ip_address, user_agent=user_agent_str,
        metadata={"agency_id": agency_id, "fields_changed": changed},
    )

    agency = await db.agencies.find_one({"_id": agency_oid})
    return {
        "id": str(agency["_id"]),
        "name": agency["name"],
        "registration_number": agency["registration_number"],
        "address": agency.get("address"),
        "phone": agency.get("phone"),
        "email": agency.get("email"),
        "is_active": agency.get("is_active", True),
        "created_at": agency["created_at"].isoformat() if agency.get("created_at") else None,
    }
