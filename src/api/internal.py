"""Internal service-to-service API for poruta-backend user lookups."""

from fastapi import APIRouter, Depends, Header, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from src.config import settings
from src.core import AuthenticationError, NotFoundError
from src.core.security import ROLE_TO_BACKEND
from src.db.mongo import get_db
from src.schemas.internal import BatchUserRequest, UserLookupResponse

router = APIRouter(prefix="/internal", tags=["internal"])


async def _verify_service_key(
    x_service_key: str = Header(..., alias="X-Service-Key"),
) -> None:
    if not settings.service_api_key:
        raise AuthenticationError("Service API not configured")
    if x_service_key != settings.service_api_key:
        raise AuthenticationError("Invalid service key")


def _user_to_response(user: dict) -> dict:
    """Convert a MongoDB user document to the internal response format."""
    profile = user.get("profile") or {}
    agency_id = None
    if user.get("agency"):
        agency_id = str(user["agency"].get("agency_id", ""))

    role = user.get("role", "")
    return {
        "user_id": str(user["_id"]),
        "email": user.get("email", ""),
        "role": role,
        "backend_role": ROLE_TO_BACKEND.get(role, role.upper()),
        "first_name": profile.get("first_name"),
        "last_name": profile.get("last_name"),
        "phone_number": user.get("phone_number") or profile.get("phone_number") or profile.get("phone"),
        "address": user.get("address"),
        "agency_id": agency_id,
        "is_active": user.get("is_active", True),
        "is_email_verified": user.get("is_email_verified", False),
    }


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: None = Depends(_verify_service_key),
):
    """Look up a single user by ID. Requires X-Service-Key header."""
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise NotFoundError("Invalid user ID")

    user = await db.users.find_one({"_id": oid})
    if not user:
        raise NotFoundError("User not found")

    # Lookup agency membership
    agency_doc = await db.agencies.find_one(
        {"members.user_id": oid},
        {"name": 1, "members.$": 1},
    )
    if agency_doc and agency_doc.get("members"):
        user["agency"] = {
            "agency_id": agency_doc["_id"],
            "name": agency_doc.get("name"),
        }

    return _user_to_response(user)


@router.post("/users/batch")
async def batch_lookup(
    body: BatchUserRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: None = Depends(_verify_service_key),
):
    """Look up multiple users by IDs. Requires X-Service-Key header."""
    oids = []
    for uid in body.user_ids[:100]:  # Cap at 100
        try:
            oids.append(ObjectId(uid))
        except Exception:
            continue

    if not oids:
        return []

    users = await db.users.find({"_id": {"$in": oids}}).to_list(length=100)

    # Batch agency lookup
    agency_map: dict = {}
    agency_docs = await db.agencies.find(
        {"members.user_id": {"$in": oids}},
        {"name": 1, "members": 1},
    ).to_list(length=100)
    for agency_doc in agency_docs:
        for member in agency_doc.get("members", []):
            if member.get("user_id") in oids:
                agency_map[member["user_id"]] = {
                    "agency_id": agency_doc["_id"],
                    "name": agency_doc.get("name"),
                }

    results = []
    for user in users:
        if user["_id"] in agency_map:
            user["agency"] = agency_map[user["_id"]]
        results.append(_user_to_response(user))

    return results


@router.get("/users/by-role/{role}")
async def list_by_role(
    role: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: None = Depends(_verify_service_key),
):
    """List users by role. Requires X-Service-Key header."""
    valid_roles = set(ROLE_TO_BACKEND.keys())
    if role not in valid_roles:
        raise NotFoundError(f"Unknown role: {role}")

    query = {"role": role, "is_active": True}
    total = await db.users.count_documents(query)
    offset = (page - 1) * page_size
    users = await db.users.find(query).sort("created_at", -1).skip(offset).limit(page_size).to_list(length=page_size)

    return {
        "items": [_user_to_response(u) for u in users],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
