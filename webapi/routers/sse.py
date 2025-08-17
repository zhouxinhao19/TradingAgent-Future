from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json
import logging

from webapi.routers.auth import get_current_user
from webapi.core.database import get_redis_client
from webapi.services.queue_service import get_queue_service, QueueService

router = APIRouter()
logger = logging.getLogger("webapi.sse")


async def task_progress_generator(task_id: str, user_id: str):
    """Generate SSE events for task progress updates"""
    r = get_redis_client()
    pubsub = r.pubsub()
    
    try:
        # Subscribe to task progress updates
        await pubsub.subscribe(f"task_progress:{task_id}")
        
        # Send initial connection confirmation
        yield f"event: connected\ndata: {{\"task_id\": \"{task_id}\", \"message\": \"已连接进度流\"}}\n\n"
        
        # Listen for progress updates
        timeout_count = 0
        max_timeout = 300  # 5 minutes timeout
        
        while timeout_count < max_timeout:
            try:
                message = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=1.0)
                if message and message['type'] == 'message':
                    # Reset timeout counter on valid message
                    timeout_count = 0
                    try:
                        progress_data = json.loads(message['data'])
                        yield f"event: progress\ndata: {json.dumps(progress_data, ensure_ascii=False)}\n\n"
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in progress message: {message['data']}")
                else:
                    # Send heartbeat every few seconds during no updates
                    timeout_count += 1
                    if timeout_count % 10 == 0:
                        yield f"event: heartbeat\ndata: {{\"timestamp\": \"{asyncio.get_event_loop().time()}\"}}\n\n"
                        
            except asyncio.TimeoutError:
                timeout_count += 1
                continue
                
    except Exception as e:
        logger.exception(f"SSE error for task {task_id}: {e}")
        yield f"event: error\ndata: {{\"error\": \"连接异常: {str(e)}\"}}\n\n"
    finally:
        await pubsub.unsubscribe(f"task_progress:{task_id}")
        await pubsub.close()


async def batch_progress_generator(batch_id: str, user_id: str):
    """Generate SSE events for batch progress updates"""
    r = get_redis_client()
    svc = get_queue_service()
    
    try:
        # Send initial connection confirmation
        yield f"event: connected\ndata: {{\"batch_id\": \"{batch_id}\", \"message\": \"已连接批次进度流\"}}\n\n"
        
        timeout_count = 0
        max_timeout = 600  # 10 minutes timeout for batches
        
        while timeout_count < max_timeout:
            try:
                # Get current batch status
                batch_data = await svc.get_batch(batch_id)
                if not batch_data:
                    yield f"event: error\ndata: {{\"error\": \"批次不存在\"}}\n\n"
                    break
                    
                # Check if batch belongs to user
                if batch_data.get("user") != user_id:
                    yield f"event: error\ndata: {{\"error\": \"无权限访问此批次\"}}\n\n"
                    break
                
                # Calculate batch progress based on task statuses
                task_ids = batch_data.get("tasks", [])
                if not task_ids:
                    yield f"event: progress\ndata: {{\"batch_id\": \"{batch_id}\", \"message\": \"批次无任务\", \"progress\": 0}}\n\n"
                    await asyncio.sleep(2)
                    continue
                
                completed_count = 0
                failed_count = 0
                processing_count = 0
                
                for task_id in task_ids:
                    task_data = await svc.get_task(task_id)
                    if task_data:
                        status = task_data.get("status", "queued")
                        if status == "completed":
                            completed_count += 1
                        elif status == "failed":
                            failed_count += 1
                        elif status == "processing":
                            processing_count += 1
                
                total_tasks = len(task_ids)
                finished_tasks = completed_count + failed_count
                progress = round((finished_tasks / total_tasks) * 100, 1) if total_tasks > 0 else 0
                
                # Determine batch status
                if finished_tasks == total_tasks:
                    if failed_count == 0:
                        batch_status = "completed"
                        message = f"批次完成: {completed_count}/{total_tasks} 成功"
                    elif completed_count == 0:
                        batch_status = "failed"
                        message = f"批次失败: {failed_count}/{total_tasks} 失败"
                    else:
                        batch_status = "partial"
                        message = f"批次部分成功: {completed_count} 成功, {failed_count} 失败"
                elif processing_count > 0 or finished_tasks < total_tasks:
                    batch_status = "processing"
                    message = f"批次处理中: {finished_tasks}/{total_tasks} 已完成, {processing_count} 处理中"
                else:
                    batch_status = "queued"
                    message = f"批次排队中: {total_tasks} 任务待处理"
                
                progress_data = {
                    "batch_id": batch_id,
                    "status": batch_status,
                    "message": message,
                    "progress": progress,
                    "total_tasks": total_tasks,
                    "completed": completed_count,
                    "failed": failed_count,
                    "processing": processing_count,
                    "timestamp": asyncio.get_event_loop().time()
                }
                
                yield f"event: progress\ndata: {json.dumps(progress_data, ensure_ascii=False)}\n\n"
                
                # Break if batch is finished
                if batch_status in ["completed", "failed", "partial"]:
                    yield f"event: finished\ndata: {{\"batch_id\": \"{batch_id}\", \"final_status\": \"{batch_status}\"}}\n\n"
                    break
                
                # Wait before next update
                await asyncio.sleep(2)
                timeout_count += 1
                
            except Exception as e:
                logger.exception(f"Batch progress error: {e}")
                yield f"event: error\ndata: {{\"error\": \"获取批次状态失败: {str(e)}\"}}\n\n"
                break
                
    except Exception as e:
        logger.exception(f"SSE batch error for {batch_id}: {e}")
        yield f"event: error\ndata: {{\"error\": \"连接异常: {str(e)}\"}}\n\n"


@router.get("/tasks/{task_id}")
async def stream_task_progress(task_id: str, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service)):
    """Stream real-time progress updates for a specific task"""
    # Verify task exists and belongs to user
    task_data = await svc.get_task(task_id)
    if not task_data or task_data.get("user") != user["id"]:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return StreamingResponse(
        task_progress_generator(task_id, user["id"]), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get("/batches/{batch_id}")
async def stream_batch_progress(batch_id: str, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service)):
    """Stream real-time progress updates for a batch"""
    # Verify batch exists and belongs to user
    batch_data = await svc.get_batch(batch_id)
    if not batch_data or batch_data.get("user") != user["id"]:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    return StreamingResponse(
        batch_progress_generator(batch_id, user["id"]), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )