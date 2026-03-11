"""Messaging API routes — REST + WebSocket."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.dependencies import get_current_user
from src.core.security import decode_token
from src.core.websocket_manager import ws_manager
from src.db.mongo import get_db
from src.schemas.messaging import CreateThreadRequest, MarkReadRequest, SendMessageRequest
from src.services import messaging_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["messaging"])


# ── REST endpoints ──────────────────────────────────────────────────

@router.post("/threads")
async def create_thread(
    body: CreateThreadRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    thread = await messaging_service.create_thread(
        db,
        creator=user,
        thread_type=body.thread_type,
        participant_ids=body.participant_ids,
        subject=body.subject,
        declaration_id=body.declaration_id,
        declaration_name=body.declaration_name,
    )
    return thread


@router.get("/threads")
async def list_threads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    return await messaging_service.list_threads(
        db, user=user, page=page, page_size=page_size,
    )


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    return await messaging_service.get_thread_detail(
        db, thread_id=thread_id, user=user,
    )


@router.post("/threads/{thread_id}/messages")
async def send_message(
    thread_id: str,
    body: SendMessageRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    result = await messaging_service.send_message(
        db,
        thread_id=thread_id,
        sender=user,
        content=body.content,
        message_type=body.message_type,
        file_url=body.file_url,
        file_name=body.file_name,
    )

    # Broadcast via WebSocket to other participants
    msg_data = result["message"]
    participant_ids = result["participant_ids"]
    user_id = str(user["_id"])
    await ws_manager.broadcast_to_thread(
        participant_ids,
        {"type": "new_message", "data": msg_data},
        exclude_id=user_id,
    )

    return msg_data


@router.post("/threads/{thread_id}/read")
async def mark_read(
    thread_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    return await messaging_service.mark_thread_read(
        db, thread_id=thread_id, user=user,
    )


# ── WebSocket endpoint ─────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(...)):
    """WebSocket connection. Client connects with ?token=<JWT>."""
    try:
        payload = decode_token(token)
    except Exception:
        await ws.close(code=4001, reason="Invalid token")
        return

    user_id = payload.get("sub", "")
    await ws_manager.connect(ws, user_id)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"error": "Invalid JSON"}))
                continue

            action = data.get("action")

            if action == "send_message":
                thread_id = data.get("thread_id")
                content = data.get("content", "").strip()
                if not thread_id or not content:
                    await ws.send_text(json.dumps({"error": "thread_id and content required"}))
                    continue

                try:
                    from src.db.mongo import get_db as _get_db
                    db = _get_db()

                    from bson import ObjectId
                    sender = await db.users.find_one({"_id": ObjectId(user_id)})
                    if not sender:
                        await ws.send_text(json.dumps({"error": "User not found"}))
                        continue

                    send_result = await messaging_service.send_message(
                        db,
                        thread_id=thread_id,
                        sender=sender,
                        content=content,
                        message_type=data.get("message_type", "text"),
                    )

                    msg_data = send_result["message"]
                    participant_ids = send_result["participant_ids"]

                    # Send confirmation to sender
                    await ws.send_text(json.dumps({"type": "message_sent", "data": msg_data}))

                    # Broadcast to others
                    await ws_manager.broadcast_to_thread(
                        participant_ids,
                        {"type": "new_message", "data": msg_data},
                        exclude_id=user_id,
                    )
                except Exception as e:
                    logger.error("WS send_message error: %s", e)
                    await ws.send_text(json.dumps({"error": str(e)}))

            elif action == "mark_read":
                thread_id = data.get("thread_id")
                if not thread_id:
                    await ws.send_text(json.dumps({"error": "thread_id required"}))
                    continue

                try:
                    from src.db.mongo import get_db as _get_db
                    db = _get_db()

                    from bson import ObjectId
                    sender = await db.users.find_one({"_id": ObjectId(user_id)})
                    if sender:
                        await messaging_service.mark_thread_read(
                            db, thread_id=thread_id, user=sender,
                        )
                        await ws.send_text(json.dumps({"type": "read_confirmed", "thread_id": thread_id}))
                except Exception as e:
                    logger.error("WS mark_read error: %s", e)

            elif action == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))

            else:
                await ws.send_text(json.dumps({"error": f"Unknown action: {action}"}))

    except WebSocketDisconnect:
        ws_manager.disconnect(ws, user_id)
    except Exception as e:
        logger.error("WS error for user %s: %s", user_id, e)
        ws_manager.disconnect(ws, user_id)
