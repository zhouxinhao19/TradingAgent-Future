"""
通知数据模型（MongoDB + Pydantic）
"""
from datetime import datetime
from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, Field
from bson import ObjectId
from app.utils.timezone import now_tz

# 简单工具：ObjectId -> str

def to_str_id(v: Any) -> str:
    try:
        if isinstance(v, ObjectId):
            return str(v)
        return str(v)
    except Exception:
        return ""


NotificationType = Literal['analysis', 'alert', 'system']
NotificationStatus = Literal['unread', 'read']


class NotificationCreate(BaseModel):
    user_id: str
    type: NotificationType
    title: str
    content: Optional[str] = None
    link: Optional[str] = None
    source: Optional[str] = None
    severity: Optional[Literal['info','success','warning','error']] = None
    metadata: Optional[Dict[str, Any]] = None


class NotificationDB(BaseModel):
    id: Optional[str] = Field(default=None)
    user_id: str
    type: NotificationType
    title: str
    content: Optional[str] = None
    link: Optional[str] = None
    source: Optional[str] = None
    severity: Optional[Literal['info','success','warning','error']] = 'info'
    status: NotificationStatus = 'unread'
    created_at: datetime = Field(default_factory=now_tz)
    metadata: Optional[Dict[str, Any]] = None


class NotificationOut(BaseModel):
    id: str
    type: NotificationType
    title: str
    content: Optional[str] = None
    link: Optional[str] = None
    source: Optional[str] = None
    status: NotificationStatus
    created_at: datetime


class NotificationList(BaseModel):
    items: List[NotificationOut]
    total: int = 0
    page: int = 1
    page_size: int = 20


