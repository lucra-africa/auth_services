"""Messaging service — MongoDB version. Threads embed participants; messages are separate."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core import AuthorizationError, NotFoundError, ValidationError


# ── Contact discovery ───────────────────────────────────────────────

async def get_contacts(
    db: AsyncIOMotorDatabase,
    *,
    caller_id,
    caller_role: str,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Return users the caller is allowed to message, based on role and agency."""
    if isinstance(caller_id, str):
        caller_id = ObjectId(caller_id)

    # Build the user query filter based on role
    user_filter = await _build_contact_filter(db, caller_id, caller_role)
    if user_filter is None:
        return {"items": [], "total": 0}

    # Apply search filter
    if search:
        safe = re.escape(search)
        search_cond = {"$or": [
            {"email": {"$regex": safe, "$options": "i"}},
            {"profile.first_name": {"$regex": safe, "$options": "i"}},
            {"profile.last_name": {"$regex": safe, "$options": "i"}},
        ]}
        user_filter = {"$and": [user_filter, search_cond]}

    total = await db.users.count_documents(user_filter)

    cursor = (
        db.users.find(user_filter, {"email": 1, "role": 1, "profile": 1})
        .sort("email", 1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    users = await cursor.to_list(length=page_size)

    # Batch-resolve agency names for these users
    user_ids = [u["_id"] for u in users]
    agency_map = await _resolve_agency_names(db, user_ids)

    items = []
    for u in users:
        profile = u.get("profile") or {}
        name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        items.append({
            "id": str(u["_id"]),
            "name": name or u["email"],
            "email": u["email"],
            "role": u.get("role", ""),
            "agency_name": agency_map.get(u["_id"]),
        })

    return {"items": items, "total": total}


async def _build_contact_filter(
    db: AsyncIOMotorDatabase, caller_id: ObjectId, caller_role: str,
) -> dict | None:
    """Return a MongoDB filter for users the caller can contact, or None if none."""
    base = {"is_active": True, "_id": {"$ne": caller_id}}

    if caller_role in ("government_rra", "government_rsb", "admin"):
        return base

    if caller_role == "inspector":
        return {**base, "role": {"$in": ["agent", "importer", "government_rra", "government_rsb"]}}

    # For importer, agent, agency_manager — scope by agency membership
    agency = await db.agencies.find_one(
        {"members.user_id": caller_id},
        {"members": 1, "name": 1},
    )
    if not agency:
        return None  # not in any agency — no contacts

    member_ids = [
        m["user_id"] for m in agency.get("members", [])
        if m["user_id"] != caller_id
    ]

    if caller_role == "importer":
        # Only agents in the same agency
        agent_ids = [
            m["user_id"] for m in agency.get("members", [])
            if m["user_id"] != caller_id and m.get("role_in_agency") == "agent"
        ]
        # Also include the agency manager(s)
        manager_ids = [
            m["user_id"] for m in agency.get("members", [])
            if m["user_id"] != caller_id and m.get("role_in_agency") == "manager"
        ]
        allowed_ids = agent_ids + manager_ids
        if not allowed_ids:
            return None
        return {"_id": {"$in": allowed_ids}, "is_active": True}

    if caller_role == "agent":
        # All members of the same agency (agents, managers, importers)
        if not member_ids:
            return None
        return {"_id": {"$in": member_ids}, "is_active": True}

    if caller_role == "agency_manager":
        # Agency members + other agency managers across platform
        return {"$or": [
            {"_id": {"$in": member_ids}, "is_active": True},
            {"role": "agency_manager", "_id": {"$ne": caller_id}, "is_active": True},
        ]}

    return base


async def _resolve_agency_names(
    db: AsyncIOMotorDatabase, user_ids: list[ObjectId],
) -> dict[ObjectId, str | None]:
    """Map user ObjectIds to their agency name (if any)."""
    if not user_ids:
        return {}
    cursor = db.agencies.find(
        {"members.user_id": {"$in": user_ids}},
        {"name": 1, "members.user_id": 1},
    )
    result: dict[ObjectId, str | None] = {}
    async for agency in cursor:
        for m in agency.get("members", []):
            if m["user_id"] in user_ids:
                result[m["user_id"]] = agency.get("name")
    return result


async def _get_allowed_contact_ids(
    db: AsyncIOMotorDatabase, caller_id: ObjectId, caller_role: str,
) -> set[ObjectId] | None:
    """Return the set of user IDs the caller can contact, or None for 'everyone'."""
    if caller_role in ("government_rra", "government_rsb", "admin"):
        return None  # no restriction

    if caller_role == "inspector":
        cursor = db.users.find(
            {"role": {"$in": ["agent", "importer", "government_rra", "government_rsb"]}, "is_active": True},
            {"_id": 1},
        )
        return {u["_id"] async for u in cursor}

    filt = await _build_contact_filter(db, caller_id, caller_role)
    if filt is None:
        return set()
    cursor = db.users.find(filt, {"_id": 1})
    return {u["_id"] async for u in cursor}


# ── Thread operations ───────────────────────────────────────────────

async def create_thread(
    db: AsyncIOMotorDatabase,
    *,
    creator: dict,
    thread_type: str,
    participant_ids: list,
    subject: str | None = None,
    declaration_id: str | None = None,
    declaration_name: str | None = None,
) -> dict:
    """Create a new thread and add participants (including the creator)."""
    all_ids = set()
    for pid in participant_ids:
        all_ids.add(ObjectId(pid) if isinstance(pid, str) else pid)
    all_ids.add(creator["_id"])

    # Validate participants exist
    found_count = await db.users.count_documents({"_id": {"$in": list(all_ids)}})
    if found_count != len(all_ids):
        raise ValidationError("One or more users not found")

    # Validate contact permissions
    other_ids = all_ids - {creator["_id"]}
    allowed = await _get_allowed_contact_ids(db, creator["_id"], creator.get("role", ""))
    if allowed is not None:  # None means no restriction
        denied = other_ids - allowed
        if denied:
            raise AuthorizationError("You cannot message one or more of the selected users")

    # Duplicate direct thread detection
    if thread_type == "direct" and len(all_ids) == 2:
        existing = await db.threads.find_one({
            "thread_type": "direct",
            "participant_ids": {"$all": list(all_ids), "$size": 2},
        })
        if existing:
            return await _build_thread_response(db, existing, creator["_id"])

    now = datetime.now(timezone.utc)

    # Build participants array
    participants = []
    for uid in all_ids:
        participants.append({
            "user_id": uid,
            "last_read_at": now if uid == creator["_id"] else None,
        })

    thread_doc = {
        "thread_type": thread_type,
        "subject": subject,
        "declaration_id": declaration_id,
        "declaration_name": declaration_name,
        "is_closed": False,
        "participant_ids": list(all_ids),
        "participants": participants,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.threads.insert_one(thread_doc)
    thread_doc["_id"] = result.inserted_id

    return await _build_thread_response(db, thread_doc, creator["_id"])


async def list_threads(
    db: AsyncIOMotorDatabase,
    *,
    user: dict,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List threads the user participates in, ordered by last update."""
    user_id = user["_id"]

    total = await db.threads.count_documents({"participant_ids": user_id})

    cursor = (
        db.threads.find({"participant_ids": user_id})
        .sort("updated_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    threads = await cursor.to_list(length=page_size)

    items = []
    for t in threads:
        items.append(await _build_thread_response(db, t, user_id))

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
    }


async def get_thread_detail(
    db: AsyncIOMotorDatabase,
    *,
    thread_id,
    user: dict,
) -> dict:
    """Get a single thread with all messages. User must be a participant."""
    if isinstance(thread_id, str):
        thread_id = ObjectId(thread_id)

    thread = await db.threads.find_one({"_id": thread_id})
    if not thread:
        raise NotFoundError("Thread not found")

    user_id = user["_id"]
    if user_id not in thread.get("participant_ids", []):
        raise AuthorizationError("Not a participant of this thread")

    # Mark as read
    now = datetime.now(timezone.utc)
    await db.threads.update_one(
        {"_id": thread_id, "participants.user_id": user_id},
        {"$set": {"participants.$.last_read_at": now}},
    )

    resp = await _build_thread_response(db, thread, user_id)

    # Get all messages for this thread
    msg_cursor = db.messages.find({"thread_id": thread_id}).sort("created_at", 1)
    messages = await msg_cursor.to_list(length=None)

    resp["messages"] = [await _build_message_response(db, m) for m in messages]
    return resp


# ── Message operations ──────────────────────────────────────────────

async def send_message(
    db: AsyncIOMotorDatabase,
    *,
    thread_id,
    sender: dict,
    content: str,
    message_type: str = "text",
    file_url: str | None = None,
    file_name: str | None = None,
) -> dict:
    """Send a message in a thread. Sender must be a participant."""
    if isinstance(thread_id, str):
        thread_id = ObjectId(thread_id)

    thread = await db.threads.find_one({"_id": thread_id})
    if not thread:
        raise NotFoundError("Thread not found")

    sender_id = sender["_id"]
    participant_ids = thread.get("participant_ids", [])
    if sender_id not in participant_ids:
        raise AuthorizationError("Not a participant of this thread")

    if thread.get("is_closed"):
        raise ValidationError("Thread is closed")

    now = datetime.now(timezone.utc)
    msg_doc = {
        "thread_id": thread_id,
        "sender_id": sender_id,
        "message_type": message_type,
        "content": content,
        "file_url": file_url,
        "file_name": file_name,
        "created_at": now,
    }
    result = await db.messages.insert_one(msg_doc)
    msg_doc["_id"] = result.inserted_id

    # Update sender's last_read_at and thread's updated_at
    await db.threads.update_one(
        {"_id": thread_id, "participants.user_id": sender_id},
        {"$set": {"participants.$.last_read_at": now, "updated_at": now}},
    )

    return {
        "message": await _build_message_response(db, msg_doc),
        "participant_ids": [str(uid) for uid in participant_ids],
    }


async def mark_thread_read(
    db: AsyncIOMotorDatabase,
    *,
    thread_id,
    user: dict,
) -> dict:
    """Mark all messages in a thread as read for the user."""
    if isinstance(thread_id, str):
        thread_id = ObjectId(thread_id)

    thread = await db.threads.find_one({"_id": thread_id})
    if not thread:
        raise NotFoundError("Thread not found")

    user_id = user["_id"]
    if user_id not in thread.get("participant_ids", []):
        raise AuthorizationError("Not a participant of this thread")

    now = datetime.now(timezone.utc)
    await db.threads.update_one(
        {"_id": thread_id, "participants.user_id": user_id},
        {"$set": {"participants.$.last_read_at": now}},
    )

    return {"message": "Marked as read"}


# ── Internal helpers ────────────────────────────────────────────────

async def _build_thread_response(db: AsyncIOMotorDatabase, thread: dict, viewer_id) -> dict:
    """Build a thread response dict with unread count and last message info."""
    viewer_last_read = None
    for p in thread.get("participants", []):
        if p["user_id"] == viewer_id:
            viewer_last_read = p.get("last_read_at")
            break

    # Get last message and count unread
    last_msg = await db.messages.find_one(
        {"thread_id": thread["_id"]},
        sort=[("created_at", -1)],
    )

    unread_query: dict = {"thread_id": thread["_id"], "sender_id": {"$ne": viewer_id}}
    if viewer_last_read:
        unread_query["created_at"] = {"$gt": viewer_last_read}
    unread = await db.messages.count_documents(unread_query)

    last_msg_content = ""
    last_msg_time = None
    if last_msg:
        last_msg_content = last_msg.get("content", "")
        last_msg_time = last_msg.get("created_at")

    # Build participants with user info
    participants = []
    for p in thread.get("participants", []):
        u = await db.users.find_one({"_id": p["user_id"]}, {"email": 1, "role": 1, "profile": 1})
        if not u:
            continue
        name = u["email"]
        profile = u.get("profile")
        if profile:
            full_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
            if full_name:
                name = full_name
        participants.append({
            "id": str(p["user_id"]),
            "user_id": str(p["user_id"]),
            "name": name,
            "email": u["email"],
            "role": u.get("role", ""),
            "last_read_at": p["last_read_at"].isoformat() if p.get("last_read_at") else None,
        })

    return {
        "id": str(thread["_id"]),
        "thread_type": thread.get("thread_type", ""),
        "subject": thread.get("subject"),
        "declaration_id": thread.get("declaration_id"),
        "declaration_name": thread.get("declaration_name"),
        "is_closed": thread.get("is_closed", False),
        "participants": participants,
        "last_message": last_msg_content,
        "last_message_time": last_msg_time.isoformat() if last_msg_time else None,
        "unread_count": unread,
        "created_at": thread["created_at"].isoformat(),
    }


async def _build_message_response(db: AsyncIOMotorDatabase, msg: dict) -> dict:
    sender_name = ""
    sender_role = ""

    msg_type = msg.get("message_type", "text")

    if msg.get("sender_id"):
        sender = await db.users.find_one({"_id": msg["sender_id"]}, {"email": 1, "role": 1, "profile": 1})
        if sender:
            profile = sender.get("profile")
            if profile:
                sender_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
            sender_name = sender_name or sender["email"]
            sender_role = sender.get("role", "")
    elif msg_type == "system":
        sender_name = "System"
        sender_role = "system"

    return {
        "id": str(msg["_id"]),
        "thread_id": str(msg["thread_id"]),
        "sender_id": str(msg["sender_id"]) if msg.get("sender_id") else None,
        "sender_name": sender_name,
        "sender_role": sender_role,
        "message_type": msg_type,
        "content": msg.get("content", ""),
        "file_url": msg.get("file_url"),
        "file_name": msg.get("file_name"),
        "created_at": msg["created_at"].isoformat(),
    }
