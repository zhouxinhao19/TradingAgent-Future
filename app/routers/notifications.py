"""
通知API与SSE（方案B）
"""
import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.responses import StreamingResponse

from app.routers.auth import get_current_user
from app.core.response import ok
from app.core.database import get_redis_client
from app.services.notifications_service import get_notifications_service
from app.services.auth_service import AuthService

router = APIRouter()
logger = logging.getLogger("webapi.notifications")


@router.get("/notifications")
async def list_notifications(
    status: Optional[str] = Query(None, description="状态: unread|read|all"),
    type: Optional[str] = Query(None, description="类型: analysis|alert|system"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user)
):
    svc = get_notifications_service()
    s = status if status in ("read","unread") else None
    t = type if type in ("analysis","alert","system") else None
    data = await svc.list(user_id=user["id"], status=s, ntype=t, page=page, page_size=page_size)
    return ok(data=data.model_dump(), message="ok")


@router.get("/notifications/unread_count")
async def get_unread_count(user: dict = Depends(get_current_user)):
    svc = get_notifications_service()
    cnt = await svc.unread_count(user_id=user["id"])
    return ok(data={"count": cnt})


@router.post("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, user: dict = Depends(get_current_user)):
    svc = get_notifications_service()
    ok_flag = await svc.mark_read(user_id=user["id"], notif_id=notif_id)
    if not ok_flag:
        raise HTTPException(status_code=404, detail="Notification not found")
    return ok()


@router.post("/notifications/read_all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    svc = get_notifications_service()
    n = await svc.mark_all_read(user_id=user["id"])
    return ok(data={"updated": n})


# SSE: 实时通知流
async def notifications_stream_generator(user_id: str):
    r = get_redis_client()
    pubsub = r.pubsub()
    channel = f"notifications:{user_id}"
    try:
        await pubsub.subscribe(channel)
        yield f"event: connected\ndata: {{\"channel\": \"{channel}\"}}\n\n"
        idle = 0
        while True:
            try:
                msg = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=10)
                if msg and msg.get('type') == 'message':
                    idle = 0
                    data = msg.get('data')
                    # data 已经是JSON字符串
                    yield f"event: notification\ndata: {data}\n\n"
                else:
                    idle += 1
                    if idle % 3 == 0:  # 心跳
                        yield f"event: heartbeat\ndata: {{\"ts\": {asyncio.get_event_loop().time()} }}\n\n"
            except asyncio.TimeoutError:
                idle += 1
                if idle % 3 == 0:
                    yield f"event: heartbeat\ndata: {{\"ts\": {asyncio.get_event_loop().time()} }}\n\n"
    except Exception as e:
        logger.exception(f"SSE error: {e}")
        yield f"event: error\ndata: {{\"error\": \"{str(e)}\"}}\n\n"
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        except Exception:
            pass


@router.get("/notifications/stream")
async def stream_notifications(token: Optional[str] = Query(None), authorization: Optional[str] = Header(default=None)):
    """SSE端点：优先从Authorization头获取；若无则支持token查询参数。"""
    user_id = None
    if authorization and authorization.lower().startswith("bearer "):
        token_val = authorization.split(" ", 1)[1]
        token_data = AuthService.verify_token(token_val)
        if token_data:
            user_id = "admin"
    elif token:
        token_data = AuthService.verify_token(token)
        if token_data:
            user_id = "admin"

    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return StreamingResponse(
        notifications_stream_generator(user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

