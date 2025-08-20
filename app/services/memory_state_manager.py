"""
内存状态管理器
类似于 analysis-engine 的实现，提供快速的状态读写
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class TaskState:
    """任务状态数据类"""
    task_id: str
    user_id: str
    stock_code: str
    status: TaskStatus
    progress: int = 0
    message: str = ""
    current_step: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    
    # 分析参数
    parameters: Optional[Dict[str, Any]] = None
    
    # 性能指标
    execution_time: Optional[float] = None
    tokens_used: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        # 处理枚举类型
        data['status'] = self.status.value
        # 处理时间格式
        if self.start_time:
            data['start_time'] = self.start_time.isoformat()
        if self.end_time:
            data['end_time'] = self.end_time.isoformat()
        return data

class MemoryStateManager:
    """内存状态管理器"""

    def __init__(self):
        self._tasks: Dict[str, TaskState] = {}
        self._lock = asyncio.Lock()
        self._websocket_manager = None

    def set_websocket_manager(self, websocket_manager):
        """设置 WebSocket 管理器"""
        self._websocket_manager = websocket_manager
        
    async def create_task(
        self, 
        task_id: str, 
        user_id: str, 
        stock_code: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> TaskState:
        """创建新任务"""
        async with self._lock:
            task_state = TaskState(
                task_id=task_id,
                user_id=user_id,
                stock_code=stock_code,
                status=TaskStatus.PENDING,
                start_time=datetime.now(),
                parameters=parameters or {},
                message="任务已创建，等待执行..."
            )
            self._tasks[task_id] = task_state
            logger.info(f"📝 创建任务状态: {task_id}")
            logger.info(f"📊 当前内存中任务数量: {len(self._tasks)}")
            logger.info(f"🔍 内存管理器实例ID: {id(self)}")
            return task_state
    
    async def update_task_status(
        self, 
        task_id: str, 
        status: TaskStatus,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        current_step: Optional[str] = None,
        result_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """更新任务状态"""
        async with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"⚠️ 任务不存在: {task_id}")
                return False
            
            task = self._tasks[task_id]
            task.status = status
            
            if progress is not None:
                task.progress = progress
            if message is not None:
                task.message = message
            if current_step is not None:
                task.current_step = current_step
            if result_data is not None:
                task.result_data = result_data
            if error_message is not None:
                task.error_message = error_message
                
            # 如果任务完成或失败，设置结束时间
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                task.end_time = datetime.now()
                if task.start_time:
                    task.execution_time = (task.end_time - task.start_time).total_seconds()
            
            logger.info(f"📊 更新任务状态: {task_id} -> {status.value} ({progress}%)")

            # 推送状态更新到 WebSocket
            if self._websocket_manager:
                try:
                    progress_update = {
                        "type": "progress_update",
                        "task_id": task_id,
                        "status": status.value,
                        "progress": task.progress,
                        "message": task.message,
                        "current_step": task.current_step,
                        "timestamp": datetime.now().isoformat()
                    }
                    # 异步推送，不等待完成
                    asyncio.create_task(
                        self._websocket_manager.send_progress_update(task_id, progress_update)
                    )
                except Exception as e:
                    logger.warning(f"⚠️ WebSocket 推送失败: {e}")

            return True
    
    async def get_task(self, task_id: str) -> Optional[TaskState]:
        """获取任务状态"""
        async with self._lock:
            logger.debug(f"🔍 查询任务: {task_id}")
            logger.debug(f"📊 当前内存中任务数量: {len(self._tasks)}")
            logger.debug(f"🔑 内存中的任务ID列表: {list(self._tasks.keys())}")
            task = self._tasks.get(task_id)
            if task:
                logger.debug(f"✅ 找到任务: {task_id}")
            else:
                logger.debug(f"❌ 未找到任务: {task_id}")
            return task
    
    async def get_task_dict(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态（字典格式）"""
        task = await self.get_task(task_id)
        return task.to_dict() if task else None
    
    async def list_user_tasks(
        self, 
        user_id: str, 
        status: Optional[TaskStatus] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """获取用户的任务列表"""
        async with self._lock:
            tasks = []
            for task in self._tasks.values():
                if task.user_id == user_id:
                    if status is None or task.status == status:
                        tasks.append(task.to_dict())
            
            # 按开始时间倒序排列
            tasks.sort(key=lambda x: x.get('start_time', ''), reverse=True)
            
            # 分页
            return tasks[offset:offset + limit]
    
    async def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        async with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                logger.info(f"🗑️ 删除任务: {task_id}")
                return True
            return False
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        async with self._lock:
            total_tasks = len(self._tasks)
            status_counts = {}
            
            for task in self._tasks.values():
                status = task.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total_tasks": total_tasks,
                "status_distribution": status_counts,
                "running_tasks": status_counts.get("running", 0),
                "completed_tasks": status_counts.get("completed", 0),
                "failed_tasks": status_counts.get("failed", 0)
            }
    
    async def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """清理旧任务"""
        async with self._lock:
            cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
            tasks_to_remove = []
            
            for task_id, task in self._tasks.items():
                if task.start_time and task.start_time.timestamp() < cutoff_time:
                    if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                        tasks_to_remove.append(task_id)
            
            for task_id in tasks_to_remove:
                del self._tasks[task_id]
            
            logger.info(f"🧹 清理了 {len(tasks_to_remove)} 个旧任务")
            return len(tasks_to_remove)

# 全局实例
_memory_state_manager = None

def get_memory_state_manager() -> MemoryStateManager:
    """获取内存状态管理器实例"""
    global _memory_state_manager
    if _memory_state_manager is None:
        _memory_state_manager = MemoryStateManager()
    return _memory_state_manager
