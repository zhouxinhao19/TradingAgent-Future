"""
进度跟踪器（过渡期）：从新的 progress 子包提供导入路径，实际实现暂时委托给旧模块
- RedisProgressTracker
- get_progress_by_id
"""
from typing import Any, Dict, Optional

# 过渡期：从旧模块导入并重导出，保持现有行为不变
from app.services.redis_progress_tracker import (
    RedisProgressTracker as _RedisProgressTracker,
    get_progress_by_id as _get_progress_by_id,
)

RedisProgressTracker = _RedisProgressTracker  # type: ignore
get_progress_by_id = _get_progress_by_id  # type: ignore

