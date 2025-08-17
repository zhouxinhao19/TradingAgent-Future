from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List
from webapi.routers.auth import get_current_user
from webapi.services.queue_service import get_queue_service, QueueService

router = APIRouter()

class SingleAnalyzeRequest(BaseModel):
    symbol: str
    parameters: dict = Field(default_factory=dict)

class BatchAnalyzeRequest(BaseModel):
    symbols: List[str]
    parameters: dict = Field(default_factory=dict)

@router.post("/analyze")
async def analyze_single(req: SingleAnalyzeRequest, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service)):
    task_id = await svc.enqueue_task(user_id=user["id"], symbol=req.symbol, params=req.parameters)
    return {"task_id": task_id, "status": "queued"}

@router.post("/analyze/batch")
async def analyze_batch(req: BatchAnalyzeRequest, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service)):
    batch_id, submitted = await svc.create_batch(user_id=user["id"], symbols=req.symbols, params=req.parameters)
    return {"batch_id": batch_id, "submitted": submitted}

@router.get("/batches/{batch_id}")
async def get_batch(batch_id: str, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service)):
    b = await svc.get_batch(batch_id)
    if not b or b.get("user") != user["id"]:
        raise HTTPException(status_code=404, detail="batch not found")
    return b

@router.get("/tasks/{task_id}")
async def get_task(task_id: str, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service)):
    t = await svc.get_task(task_id)
    if not t or t.get("user") != user["id"]:
        raise HTTPException(status_code=404, detail="task not found")
    return t