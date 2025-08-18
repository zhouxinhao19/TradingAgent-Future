"""
股票分析服务
将现有的TradingAgents分析功能包装成API服务
"""

import asyncio
import uuid
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from app.models.analysis import (
    AnalysisParameters, AnalysisResult, AnalysisTask, AnalysisBatch,
    AnalysisStatus, BatchStatus, SingleAnalysisRequest, BatchAnalysisRequest
)
from app.core.database import get_mongo_db
from app.core.redis_client import get_redis_service, RedisKeys
from app.services.queue_service import QueueService
from app.core.database import get_redis_client

import logging
logger = logging.getLogger(__name__)


class AnalysisService:
    """股票分析服务类"""
    
    def __init__(self):
        # 获取Redis客户端
        redis_client = get_redis_client()
        self.queue_service = QueueService(redis_client)
        self._trading_graph_cache = {}
    
    def _get_trading_graph(self, config: Dict[str, Any]) -> TradingAgentsGraph:
        """获取或创建TradingAgents图实例（带缓存）"""
        config_key = json.dumps(config, sort_keys=True)
        
        if config_key not in self._trading_graph_cache:
            # 创建自定义配置
            custom_config = DEFAULT_CONFIG.copy()
            custom_config.update(config)
            
            # 创建TradingAgents实例
            self._trading_graph_cache[config_key] = TradingAgentsGraph(
                debug=False,
                config=custom_config
            )
            
            logger.info(f"创建新的TradingAgents实例: {custom_config.get('llm_provider', 'default')}")
        
        return self._trading_graph_cache[config_key]
    
    async def submit_single_analysis(
        self, 
        user_id: str, 
        request: SingleAnalysisRequest
    ) -> Dict[str, Any]:
        """提交单股分析任务"""
        try:
            # 生成任务ID
            task_id = str(uuid.uuid4())
            
            # 创建分析任务
            task = AnalysisTask(
                task_id=task_id,
                user_id=user_id,
                stock_code=request.stock_code,
                parameters=request.parameters or AnalysisParameters(),
                status=AnalysisStatus.PENDING
            )
            
            # 保存任务到数据库
            db = get_mongo_db()
            await db.analysis_tasks.insert_one(task.dict(by_alias=True))
            
            # 提交到队列
            await self.queue_service.enqueue_task(task)
            
            logger.info(f"单股分析任务已提交: {task_id} - {request.stock_code}")
            
            return {
                "task_id": task_id,
                "stock_code": request.stock_code,
                "status": AnalysisStatus.PENDING,
                "message": "任务已提交到队列"
            }
            
        except Exception as e:
            logger.error(f"提交单股分析任务失败: {e}")
            raise
    
    async def submit_batch_analysis(
        self, 
        user_id: str, 
        request: BatchAnalysisRequest
    ) -> Dict[str, Any]:
        """提交批量分析任务"""
        try:
            # 生成批次ID
            batch_id = str(uuid.uuid4())
            
            # 创建批次记录
            batch = AnalysisBatch(
                batch_id=batch_id,
                user_id=user_id,
                title=request.title,
                description=request.description,
                total_tasks=len(request.stock_codes),
                parameters=request.parameters or AnalysisParameters(),
                status=BatchStatus.PENDING
            )
            
            # 创建任务列表
            tasks = []
            for stock_code in request.stock_codes:
                task_id = str(uuid.uuid4())
                task = AnalysisTask(
                    task_id=task_id,
                    batch_id=batch_id,
                    user_id=user_id,
                    stock_code=stock_code,
                    parameters=batch.parameters,
                    status=AnalysisStatus.PENDING
                )
                tasks.append(task)
            
            # 保存到数据库
            db = get_mongo_db()
            await db.analysis_batches.insert_one(batch.dict(by_alias=True))
            await db.analysis_tasks.insert_many([task.dict(by_alias=True) for task in tasks])
            
            # 提交任务到队列
            for task in tasks:
                await self.queue_service.enqueue_task(task)
            
            logger.info(f"批量分析任务已提交: {batch_id} - {len(tasks)}个股票")
            
            return {
                "batch_id": batch_id,
                "total_tasks": len(tasks),
                "status": BatchStatus.PENDING,
                "message": f"已提交{len(tasks)}个分析任务到队列"
            }
            
        except Exception as e:
            logger.error(f"提交批量分析任务失败: {e}")
            raise
    
    async def execute_analysis_task(
        self, 
        task: AnalysisTask,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> AnalysisResult:
        """执行单个分析任务"""
        try:
            logger.info(f"开始执行分析任务: {task.task_id} - {task.stock_code}")
            
            # 更新任务状态
            await self._update_task_status(task.task_id, AnalysisStatus.PROCESSING, 0)
            
            if progress_callback:
                progress_callback(10, "初始化分析引擎...")
            
            # 准备配置
            config = {
                "llm_provider": task.parameters.selected_analysts[0] if task.parameters.selected_analysts else "google",
                "research_depth": task.parameters.research_depth,
                "max_debate_rounds": 1 if task.parameters.research_depth == "快速" else 2,
                "online_tools": True
            }
            
            if progress_callback:
                progress_callback(30, "创建分析图...")
            
            # 获取TradingAgents实例
            trading_graph = self._get_trading_graph(config)
            
            if progress_callback:
                progress_callback(50, "执行股票分析...")
            
            # 执行分析
            start_time = datetime.utcnow()
            analysis_date = task.parameters.analysis_date or datetime.now().strftime("%Y-%m-%d")
            
            # 调用现有的分析方法
            _, decision = trading_graph.propagate(task.stock_code, analysis_date)
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            if progress_callback:
                progress_callback(80, "处理分析结果...")
            
            # 构建结果
            result = AnalysisResult(
                analysis_id=str(uuid.uuid4()),
                summary=decision.get("summary", ""),
                recommendation=decision.get("recommendation", ""),
                confidence_score=decision.get("confidence_score", 0.0),
                risk_level=decision.get("risk_level", "中等"),
                key_points=decision.get("key_points", []),
                detailed_analysis=decision,
                execution_time=execution_time,
                tokens_used=decision.get("tokens_used", 0)
            )
            
            if progress_callback:
                progress_callback(100, "分析完成")
            
            # 更新任务状态
            await self._update_task_status(task.task_id, AnalysisStatus.COMPLETED, 100, result)
            
            logger.info(f"分析任务完成: {task.task_id} - 耗时{execution_time:.2f}秒")
            
            return result
            
        except Exception as e:
            logger.error(f"执行分析任务失败: {task.task_id} - {e}")
            
            # 更新任务状态为失败
            error_result = AnalysisResult(error_message=str(e))
            await self._update_task_status(task.task_id, AnalysisStatus.FAILED, 0, error_result)
            
            raise
    
    async def _update_task_status(
        self, 
        task_id: str, 
        status: AnalysisStatus, 
        progress: int,
        result: Optional[AnalysisResult] = None
    ):
        """更新任务状态"""
        try:
            db = get_mongo_db()
            redis_service = get_redis_service()
            
            # 准备更新数据
            update_data = {
                "status": status,
                "progress": progress,
                "updated_at": datetime.utcnow()
            }
            
            if status == AnalysisStatus.PROCESSING and "started_at" not in update_data:
                update_data["started_at"] = datetime.utcnow()
            elif status in [AnalysisStatus.COMPLETED, AnalysisStatus.FAILED]:
                update_data["completed_at"] = datetime.utcnow()
                if result:
                    update_data["result"] = result.dict()
            
            # 更新数据库
            await db.analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": update_data}
            )
            
            # 更新Redis缓存
            progress_key = RedisKeys.TASK_PROGRESS.format(task_id=task_id)
            await redis_service.set_json(progress_key, {
                "task_id": task_id,
                "status": status,
                "progress": progress,
                "updated_at": datetime.utcnow().isoformat()
            }, ttl=3600)
            
        except Exception as e:
            logger.error(f"更新任务状态失败: {task_id} - {e}")
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        try:
            # 先从Redis缓存获取
            redis_service = get_redis_service()
            progress_key = RedisKeys.TASK_PROGRESS.format(task_id=task_id)
            cached_status = await redis_service.get_json(progress_key)
            
            if cached_status:
                return cached_status
            
            # 从数据库获取
            db = get_mongo_db()
            task = await db.analysis_tasks.find_one({"task_id": task_id})
            
            if task:
                return {
                    "task_id": task_id,
                    "status": task.get("status"),
                    "progress": task.get("progress", 0),
                    "updated_at": task.get("updated_at", "").isoformat() if task.get("updated_at") else None
                }
            
            return None
            
        except Exception as e:
            logger.error(f"获取任务状态失败: {task_id} - {e}")
            return None
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            # 更新任务状态
            await self._update_task_status(task_id, AnalysisStatus.CANCELLED, 0)
            
            # 从队列中移除（如果还在队列中）
            await self.queue_service.remove_task(task_id)
            
            logger.info(f"任务已取消: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"取消任务失败: {task_id} - {e}")
            return False


# 全局分析服务实例（延迟初始化）
analysis_service: Optional[AnalysisService] = None


def get_analysis_service() -> AnalysisService:
    """获取分析服务实例（延迟初始化）"""
    global analysis_service
    if analysis_service is None:
        analysis_service = AnalysisService()
    return analysis_service
