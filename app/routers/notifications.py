"""
通知API与SSE（方案B）
"""
import asyncio
import json
import logging
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.responses import StreamingResponse

from app.routers.auth import get_current_user
from app.core.response import ok
from app.core.database import get_redis_client
from app.services.notifications_service import get_notifications_service
from app.services.auth_service import AuthService

router = APIRouter()
logger = logging.getLogger("webapi.notifications")

# 🔥 全局 SSE 连接管理器：限制每个用户只能有一个活跃的 SSE 连接
_active_sse_connections: Dict[str, asyncio.Event] = {}
_sse_connections_lock = asyncio.Lock()


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


@router.get("/notifications/debug/redis_pool")
async def debug_redis_pool(user: dict = Depends(get_current_user)):
    """调试端点：查看 Redis 连接池状态"""
    try:
        r = get_redis_client()
        pool = r.connection_pool

        # 获取连接池信息
        pool_info = {
            "max_connections": pool.max_connections,
            "connection_class": str(pool.connection_class),
            "available_connections": len(pool._available_connections) if hasattr(pool, '_available_connections') else "N/A",
            "in_use_connections": len(pool._in_use_connections) if hasattr(pool, '_in_use_connections') else "N/A",
        }

        # 获取 Redis 服务器信息
        info = await r.info("clients")
        redis_info = {
            "connected_clients": info.get("connected_clients", "N/A"),
            "client_recent_max_input_buffer": info.get("client_recent_max_input_buffer", "N/A"),
            "client_recent_max_output_buffer": info.get("client_recent_max_output_buffer", "N/A"),
            "blocked_clients": info.get("blocked_clients", "N/A"),
        }

        # 🔥 新增：获取 PubSub 频道信息
        try:
            pubsub_info = await r.execute_command("PUBSUB", "CHANNELS", "notifications:*")
            pubsub_channels = {
                "active_channels": len(pubsub_info) if pubsub_info else 0,
                "channels": pubsub_info if pubsub_info else []
            }
        except Exception as e:
            logger.warning(f"获取 PubSub 频道信息失败: {e}")
            pubsub_channels = {"error": str(e)}

        return ok(data={
            "pool": pool_info,
            "redis_server": redis_info,
            "pubsub": pubsub_channels
        })
    except Exception as e:
        logger.error(f"获取 Redis 连接池信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# SSE: 实时通知流
async def notifications_stream_generator(user_id: str):
    """
    SSE 通知流生成器

    注意：确保在所有情况下都正确释放 Redis PubSub 连接

    🔥 连接管理策略：
    - 每个用户只能有一个活跃的 SSE 连接
    - 新连接到来时，旧连接会被自动关闭
    - 这样可以防止 PubSub 连接泄漏
    """
    r = get_redis_client()
    pubsub = None
    channel = f"notifications:{user_id}"
    disconnect_event = None

    # 🔥 检查是否已有活跃连接
    async with _sse_connections_lock:
        if user_id in _active_sse_connections:
            # 通知旧连接断开
            old_event = _active_sse_connections[user_id]
            old_event.set()
            logger.info(f"🔄 [SSE] 用户 {user_id} 已有活跃连接，将关闭旧连接")
            # 等待一小段时间让旧连接清理
            await asyncio.sleep(0.1)

        # 创建新的断开事件
        disconnect_event = asyncio.Event()
        _active_sse_connections[user_id] = disconnect_event
        logger.info(f"✅ [SSE] 注册新连接: user={user_id}, 当前活跃连接数={len(_active_sse_connections)}")

    try:
        # 🔥 修复：在创建 PubSub 之前检查连接池状态
        try:
            pool = r.connection_pool
            logger.debug(f"📊 [SSE] Redis 连接池状态: max={pool.max_connections}, "
                        f"available={len(pool._available_connections) if hasattr(pool, '_available_connections') else 'N/A'}, "
                        f"in_use={len(pool._in_use_connections) if hasattr(pool, '_in_use_connections') else 'N/A'}")
        except Exception as e:
            logger.warning(f"⚠️ [SSE] 无法获取连接池状态: {e}")

        # 创建 PubSub 连接
        pubsub = r.pubsub()
        logger.info(f"📡 [SSE] 创建 PubSub 连接: user={user_id}, channel={channel}")

        # 订阅频道（这里可能失败，需要确保 pubsub 被清理）
        try:
            await pubsub.subscribe(channel)
            logger.info(f"✅ [SSE] 订阅频道成功: {channel}")
            yield f"event: connected\ndata: {{\"channel\": \"{channel}\"}}\n\n"
        except Exception as subscribe_error:
            # 🔥 订阅失败时立即清理 pubsub 连接
            logger.error(f"❌ [SSE] 订阅频道失败: {subscribe_error}")
            try:
                await pubsub.close()
                logger.info(f"🧹 [SSE] 订阅失败后已关闭 PubSub 连接")
            except Exception as close_error:
                logger.error(f"❌ [SSE] 关闭 PubSub 连接失败: {close_error}")
            # 重新抛出异常，让外层 except 处理
            raise

        idle = 0
        message_count = 0  # 统计发送的消息数量
        while True:
            # 🔥 检查是否需要断开（新连接到来）
            if disconnect_event and disconnect_event.is_set():
                logger.info(f"🔄 [SSE] 检测到新连接，关闭当前连接: user={user_id}")
                break

            try:
                msg = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=10)
                if msg and msg.get('type') == 'message':
                    idle = 0
                    data = msg.get('data')
                    message_count += 1
                    # data 已经是JSON字符串
                    logger.debug(f"📨 [SSE] 发送通知消息 #{message_count}: user={user_id}")
                    yield f"event: notification\ndata: {data}\n\n"
                else:
                    # 没有消息时等待一段时间，避免空转
                    await asyncio.sleep(10)
                    idle += 1
                    if idle % 3 == 0:  # 每 30 秒发送一次心跳
                        message_count += 1
                        logger.debug(f"💓 [SSE] 发送心跳 #{message_count}: user={user_id}, idle={idle}")
                        yield f"event: heartbeat\ndata: {{\"ts\": {asyncio.get_event_loop().time()} }}\n\n"
            except asyncio.TimeoutError:
                idle += 1
                if idle % 3 == 0:  # 每 30 秒发送一次心跳
                    message_count += 1
                    logger.debug(f"💓 [SSE] 发送心跳(超时) #{message_count}: user={user_id}, idle={idle}")
                    yield f"event: heartbeat\ndata: {{\"ts\": {asyncio.get_event_loop().time()} }}\n\n"
            except asyncio.CancelledError:
                # 客户端断开连接
                logger.info(f"🔌 [SSE] 客户端断开连接: user={user_id}, 已发送 {message_count} 条消息")
                raise  # 重新抛出 CancelledError 以确保正确的异步取消行为
            except Exception as e:
                logger.error(f"❌ [SSE] 消息处理错误: {e}, 已发送 {message_count} 条消息", exc_info=True)
                break

    except Exception as e:
        logger.error(f"❌ [SSE] 连接错误: {e}", exc_info=True)
        yield f"event: error\ndata: {{\"error\": \"{str(e)}\"}}\n\n"
    finally:
        # 🔥 从连接管理器中移除
        async with _sse_connections_lock:
            if user_id in _active_sse_connections and _active_sse_connections[user_id] == disconnect_event:
                del _active_sse_connections[user_id]
                logger.info(f"🗑️ [SSE] 从连接管理器中移除: user={user_id}, 剩余活跃连接数={len(_active_sse_connections)}")

        # 确保在所有情况下都释放连接
        if pubsub:
            logger.info(f"🧹 [SSE] 清理 PubSub 连接: user={user_id}")

            # 分步骤关闭，确保即使 unsubscribe 失败也能关闭连接
            try:
                await pubsub.unsubscribe(channel)
                logger.debug(f"✅ [SSE] 已取消订阅频道: {channel}")
            except Exception as e:
                logger.warning(f"⚠️ [SSE] 取消订阅失败（将继续关闭连接）: {e}")

            try:
                await pubsub.close()
                logger.info(f"✅ [SSE] PubSub 连接已关闭: user={user_id}")
            except Exception as e:
                logger.error(f"❌ [SSE] 关闭 PubSub 连接失败: {e}", exc_info=True)
                # 即使关闭失败，也尝试重置连接
                try:
                    await pubsub.reset()
                    logger.info(f"🔄 [SSE] PubSub 连接已重置: user={user_id}")
                except Exception as reset_error:
                    logger.error(f"❌ [SSE] 重置 PubSub 连接也失败: {reset_error}")


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

