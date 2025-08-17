from fastapi import APIRouter, Depends
from webapi.routers.auth import get_current_user
from webapi.services.queue_service import get_queue_service, QueueService

router = APIRouter()

@router.get("/stats")
async def queue_stats(user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service)):
    stats = await svc.stats()
    return {"user": user["id"], **stats}