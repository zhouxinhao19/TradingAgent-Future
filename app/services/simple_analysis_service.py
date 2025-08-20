"""
简化的股票分析服务
直接调用现有的 TradingAgents 分析功能
"""

import asyncio
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from app.models.analysis import (
    AnalysisTask, AnalysisStatus, SingleAnalysisRequest, AnalysisParameters
)
from app.models.user import PyObjectId
from bson import ObjectId
from app.core.database import get_mongo_db
from app.services.config_service import ConfigService
from app.services.memory_state_manager import get_memory_state_manager, TaskStatus

# 设置日志
logger = logging.getLogger("app.services.simple_analysis_service")

# 配置服务实例
config_service = ConfigService()


async def get_provider_by_model_name(model_name: str) -> str:
    """
    根据模型名称从数据库配置中查找对应的供应商

    Args:
        model_name: 模型名称，如 'qwen-turbo', 'gpt-4' 等

    Returns:
        str: 供应商名称，如 'dashscope', 'openai' 等
    """
    try:
        # 从配置服务获取系统配置
        system_config = await config_service.get_system_config()
        if not system_config or not system_config.llm_configs:
            logger.warning(f"⚠️ 系统配置为空，使用默认供应商映射")
            return _get_default_provider_by_model(model_name)

        # 在LLM配置中查找匹配的模型
        for llm_config in system_config.llm_configs:
            if llm_config.model_name == model_name:
                provider = llm_config.provider.value if hasattr(llm_config.provider, 'value') else str(llm_config.provider)
                logger.info(f"✅ 从数据库找到模型 {model_name} 的供应商: {provider}")
                return provider

        # 如果数据库中没有找到，使用默认映射
        logger.warning(f"⚠️ 数据库中未找到模型 {model_name}，使用默认映射")
        return _get_default_provider_by_model(model_name)

    except Exception as e:
        logger.error(f"❌ 查找模型供应商失败: {e}")
        return _get_default_provider_by_model(model_name)


def _get_default_provider_by_model(model_name: str) -> str:
    """
    根据模型名称返回默认的供应商映射
    这是一个后备方案，当数据库查询失败时使用
    """
    # 模型名称到供应商的默认映射
    model_provider_map = {
        # 阿里百炼 (DashScope)
        'qwen-turbo': 'dashscope',
        'qwen-plus': 'dashscope',
        'qwen-max': 'dashscope',
        'qwen-plus-latest': 'dashscope',
        'qwen-max-longcontext': 'dashscope',

        # OpenAI
        'gpt-3.5-turbo': 'openai',
        'gpt-4': 'openai',
        'gpt-4-turbo': 'openai',
        'gpt-4o': 'openai',
        'gpt-4o-mini': 'openai',

        # Google
        'gemini-pro': 'google',
        'gemini-2.0-flash': 'google',
        'gemini-2.0-flash-thinking-exp': 'google',

        # DeepSeek
        'deepseek-chat': 'deepseek',
        'deepseek-coder': 'deepseek',

        # 智谱AI
        'glm-4': 'zhipu',
        'glm-3-turbo': 'zhipu',
        'chatglm3-6b': 'zhipu'
    }

    provider = model_provider_map.get(model_name, 'dashscope')  # 默认使用阿里百炼
    logger.info(f"🔧 使用默认映射: {model_name} -> {provider}")
    return provider


def create_analysis_config(
    research_depth: str,
    selected_analysts: list,
    quick_model: str,
    deep_model: str,
    llm_provider: str,
    market_type: str = "A股"
) -> dict:
    """
    创建分析配置 - 完全复制web目录的配置逻辑

    Args:
        research_depth: 研究深度 ("快速", "标准", "深度")
        selected_analysts: 选中的分析师列表
        quick_model: 快速分析模型
        deep_model: 深度分析模型
        llm_provider: LLM供应商
        market_type: 市场类型

    Returns:
        dict: 完整的分析配置
    """
    # 从DEFAULT_CONFIG开始，完全复制web目录的逻辑
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = llm_provider
    config["deep_think_llm"] = deep_model
    config["quick_think_llm"] = quick_model

    # 根据研究深度调整配置 - 方案C：自定义映射
    if research_depth == "快速":
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 1
        config["memory_enabled"] = True
        config["online_tools"] = True
        logger.info(f"🔧 [快速分析] {market_type}使用统一工具，确保数据源正确和稳定性")

        # 根据供应商优化模型选择
        if llm_provider == "dashscope":
            config["quick_think_llm"] = "qwen-turbo"  # 使用最快模型
            config["deep_think_llm"] = "qwen-plus"
        elif llm_provider == "deepseek":
            config["quick_think_llm"] = "deepseek-chat"
            config["deep_think_llm"] = "deepseek-chat"

    elif research_depth == "标准":
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 2
        config["memory_enabled"] = True
        config["online_tools"] = True

        if llm_provider == "dashscope":
            config["quick_think_llm"] = "qwen-plus"
            config["deep_think_llm"] = "qwen-max"
        elif llm_provider == "deepseek":
            config["quick_think_llm"] = "deepseek-chat"
            config["deep_think_llm"] = "deepseek-chat"

    elif research_depth == "深度":
        config["max_debate_rounds"] = 2
        config["max_risk_discuss_rounds"] = 3
        config["memory_enabled"] = True
        config["online_tools"] = True

        if llm_provider == "dashscope":
            config["quick_think_llm"] = "qwen-max"
            config["deep_think_llm"] = "qwen-max"
        elif llm_provider == "deepseek":
            config["quick_think_llm"] = "deepseek-chat"
            config["deep_think_llm"] = "deepseek-chat"

    # 根据LLM提供商设置后端URL
    if llm_provider == "dashscope":
        config["backend_url"] = "https://dashscope.aliyuncs.com/api/v1"
    elif llm_provider == "deepseek":
        config["backend_url"] = "https://api.deepseek.com"
    elif llm_provider == "openai":
        config["backend_url"] = "https://api.openai.com/v1"
    elif llm_provider == "google":
        config["backend_url"] = "https://generativelanguage.googleapis.com/v1"
    elif llm_provider == "qianfan":
        config["backend_url"] = "https://aip.baidubce.com"

    # 添加分析师配置
    config["selected_analysts"] = selected_analysts
    config["debug"] = False

    logger.info(f"📋 创建分析配置完成:")
    logger.info(f"   研究深度: {research_depth}")
    logger.info(f"   辩论轮次: {config['max_debate_rounds']}")
    logger.info(f"   风险讨论轮次: {config['max_risk_discuss_rounds']}")
    logger.info(f"   LLM供应商: {llm_provider}")
    logger.info(f"   快速模型: {config['quick_think_llm']}")
    logger.info(f"   深度模型: {config['deep_think_llm']}")

    return config


class SimpleAnalysisService:
    """简化的股票分析服务类"""

    def __init__(self):
        self._trading_graph_cache = {}
        self.memory_manager = get_memory_state_manager()

        logger.info(f"🔧 [服务初始化] SimpleAnalysisService 实例ID: {id(self)}")
        logger.info(f"🔧 [服务初始化] 内存管理器实例ID: {id(self.memory_manager)}")

        # 设置 WebSocket 管理器
        try:
            from app.services.websocket_manager import get_websocket_manager
            self.memory_manager.set_websocket_manager(get_websocket_manager())
        except ImportError:
            logger.warning("⚠️ WebSocket 管理器不可用")
    
    def _convert_user_id(self, user_id: str) -> PyObjectId:
        """将字符串用户ID转换为PyObjectId"""
        try:
            logger.info(f"🔄 开始转换用户ID: {user_id} (类型: {type(user_id)})")
            
            # 如果是admin用户，使用固定的ObjectId
            if user_id == "admin":
                admin_object_id = ObjectId("507f1f77bcf86cd799439011")
                logger.info(f"🔄 转换admin用户ID: {user_id} -> {admin_object_id}")
                return PyObjectId(admin_object_id)
            else:
                # 尝试将字符串转换为ObjectId
                object_id = ObjectId(user_id)
                logger.info(f"🔄 转换用户ID: {user_id} -> {object_id}")
                return PyObjectId(object_id)
        except Exception as e:
            logger.error(f"❌ 用户ID转换失败: {user_id} -> {e}")
            # 如果转换失败，生成一个新的ObjectId
            new_object_id = ObjectId()
            logger.warning(f"⚠️ 生成新的用户ID: {new_object_id}")
            return PyObjectId(new_object_id)
    
    def _get_trading_graph(self, config: Dict[str, Any]) -> TradingAgentsGraph:
        """获取或创建TradingAgents实例 - 完全复制web目录的创建方式"""
        config_key = str(sorted(config.items()))

        if config_key not in self._trading_graph_cache:
            logger.info(f"创建新的TradingAgents实例...")

            # 直接使用完整配置，不再合并DEFAULT_CONFIG（因为create_analysis_config已经处理了）
            # 这与web目录的方式一致
            self._trading_graph_cache[config_key] = TradingAgentsGraph(
                selected_analysts=config.get("selected_analysts", ["market", "fundamentals"]),
                debug=config.get("debug", False),
                config=config
            )

            logger.info(f"✅ TradingAgents实例创建成功")

        return self._trading_graph_cache[config_key]

    async def create_analysis_task(
        self,
        user_id: str,
        request: SingleAnalysisRequest
    ) -> Dict[str, Any]:
        """创建分析任务（立即返回，不执行分析）"""
        try:
            # 生成任务ID
            task_id = str(uuid.uuid4())

            logger.info(f"📝 创建分析任务: {task_id} - {request.stock_code}")
            logger.info(f"🔍 内存管理器实例ID: {id(self.memory_manager)}")

            # 在内存中创建任务状态
            task_state = await self.memory_manager.create_task(
                task_id=task_id,
                user_id=user_id,
                stock_code=request.stock_code,
                parameters=request.parameters.model_dump() if request.parameters else {}
            )

            logger.info(f"✅ 任务状态已创建: {task_state.task_id}")

            # 立即验证任务是否可以查询到
            verify_task = await self.memory_manager.get_task(task_id)
            if verify_task:
                logger.info(f"✅ 任务创建验证成功: {verify_task.task_id}")
            else:
                logger.error(f"❌ 任务创建验证失败: 无法查询到刚创建的任务 {task_id}")

            return {
                "task_id": task_id,
                "status": "pending",
                "message": "任务已创建，等待执行"
            }

        except Exception as e:
            logger.error(f"❌ 创建分析任务失败: {e}")
            raise

    async def execute_analysis_background(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest
    ):
        """在后台执行分析任务"""
        try:
            logger.info(f"🚀 开始后台执行分析任务: {task_id}")

            # 更新状态为运行中
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=10,
                message="分析开始...",
                current_step="initialization"
            )

            # 数据准备阶段
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=20,
                message="准备分析数据...",
                current_step="data_preparation"
            )

            # 执行实际的分析
            result = await self._execute_analysis_sync(task_id, user_id, request)

            # 更新状态为完成
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="分析完成",
                current_step="completed",
                result_data=result
            )

            logger.info(f"✅ 后台分析任务完成: {task_id}")

        except Exception as e:
            logger.error(f"❌ 后台分析任务失败: {task_id} - {e}")

            # 更新状态为失败
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.FAILED,
                progress=0,
                message="分析失败",
                current_step="failed",
                error_message=str(e)
            )

    async def _execute_analysis_sync(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest
    ) -> Dict[str, Any]:
        """同步执行分析（在线程池中运行）"""
        import concurrent.futures

        # 在线程池中执行同步分析
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            result = await loop.run_in_executor(
                executor,
                self._run_analysis_sync,
                task_id,
                user_id,
                request
            )
        return result

    def _run_analysis_sync(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest
    ) -> Dict[str, Any]:
        """同步执行分析的具体实现"""
        try:
            logger.info(f"🔄 [线程池] 开始执行分析: {task_id} - {request.stock_code}")

            # 异步更新进度（在线程池中调用）
            def update_progress_sync(progress: int, message: str, step: str):
                """在线程池中同步更新进度"""
                try:
                    # 创建新的事件循环来执行异步操作
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(
                            self.memory_manager.update_task_status(
                                task_id=task_id,
                                status=TaskStatus.RUNNING,
                                progress=progress,
                                message=message,
                                current_step=step
                            )
                        )
                    finally:
                        loop.close()
                except Exception as e:
                    logger.warning(f"⚠️ 进度更新失败: {e}")

            # 配置阶段
            update_progress_sync(30, "配置分析参数...", "configuration")

            # 创建分析配置
            config = create_analysis_config(
                research_depth=request.parameters.research_depth if request.parameters else 2,
                selected_analysts=request.parameters.selected_analysts if request.parameters else ["market", "fundamentals"],
                quick_model="qwen-turbo",
                deep_model="qwen-plus",
                llm_provider="dashscope",
                market_type="A股"
            )

            # 初始化分析引擎
            update_progress_sync(40, "初始化分析引擎...", "engine_initialization")
            trading_graph = self._get_trading_graph(config)

            # 开始分析
            update_progress_sync(50, "开始股票分析...", "analysis_execution")
            start_time = datetime.now()
            analysis_date = datetime.now().strftime("%Y-%m-%d")

            # 调用分析方法
            update_progress_sync(60, "执行智能体分析...", "agent_analysis")
            state, decision = trading_graph.propagate(request.stock_code, analysis_date)

            # 处理结果
            update_progress_sync(90, "处理分析结果...", "result_processing")

            execution_time = (datetime.now() - start_time).total_seconds()

            # 构建结果
            result = {
                "analysis_id": str(uuid.uuid4()),
                "stock_code": request.stock_code,
                "analysis_date": analysis_date,
                "summary": decision.get("summary", ""),
                "recommendation": decision.get("recommendation", ""),
                "confidence_score": decision.get("confidence_score", 0.0),
                "risk_level": decision.get("risk_level", "中等"),
                "key_points": decision.get("key_points", []),
                "detailed_analysis": decision,
                "execution_time": execution_time,
                "tokens_used": decision.get("tokens_used", 0),
                "state": state
            }

            logger.info(f"✅ [线程池] 分析完成: {task_id} - 耗时{execution_time:.2f}秒")
            return result

        except Exception as e:
            logger.error(f"❌ [线程池] 分析执行失败: {task_id} - {e}")
            raise

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        logger.info(f"🔍 查询任务状态: {task_id}")
        logger.info(f"🔍 当前服务实例ID: {id(self)}")
        logger.info(f"🔍 内存管理器实例ID: {id(self.memory_manager)}")

        # 强制使用全局内存管理器实例（临时解决方案）
        global_memory_manager = get_memory_state_manager()
        logger.info(f"🔍 全局内存管理器实例ID: {id(global_memory_manager)}")

        # 获取统计信息
        stats = await global_memory_manager.get_statistics()
        logger.info(f"📊 内存中任务统计: {stats}")

        result = await global_memory_manager.get_task_dict(task_id)
        if result:
            logger.info(f"✅ 找到任务: {task_id} - 状态: {result.get('status')}")
        else:
            logger.warning(f"❌ 未找到任务: {task_id}")

        return result

    async def list_user_tasks(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """获取用户任务列表"""
        task_status = None
        if status:
            try:
                task_status = TaskStatus(status)
            except ValueError:
                pass

        return await self.memory_manager.list_user_tasks(
            user_id=user_id,
            status=task_status,
            limit=limit,
            offset=offset
        )

    async def submit_single_analysis(
        self, 
        user_id: str, 
        request: SingleAnalysisRequest
    ) -> Dict[str, Any]:
        """提交单股分析任务"""
        try:
            logger.info(f"📝 开始提交单股分析任务")
            logger.info(f"👤 用户ID: {user_id}")
            logger.info(f"📊 股票代码: {request.stock_code}")
            logger.info(f"⚙️ 分析参数: {request.parameters}")
            
            # 生成任务ID
            task_id = str(uuid.uuid4())
            logger.info(f"🆔 生成任务ID: {task_id}")
            
            # 转换用户ID
            converted_user_id = self._convert_user_id(user_id)
            
            # 创建分析任务
            task = AnalysisTask(
                task_id=task_id,
                user_id=converted_user_id,
                stock_code=request.stock_code,
                parameters=request.parameters or AnalysisParameters(),
                status=AnalysisStatus.PENDING
            )
            
            # 保存任务到数据库
            logger.info(f"💾 保存任务到数据库...")
            db = get_mongo_db()
            task_dict = task.model_dump(by_alias=True)
            await db.analysis_tasks.insert_one(task_dict)
            logger.info(f"✅ 任务已保存到数据库")
            
            # 直接执行分析（异步）
            logger.info(f"🚀 开始直接执行单股分析...")
            asyncio.create_task(self._execute_analysis_async(task))
            
            logger.info(f"🎉 单股分析任务提交完成: {task_id} - {request.stock_code}")
            
            return {
                "task_id": task_id,
                "stock_code": request.stock_code,
                "status": AnalysisStatus.PENDING,
                "message": "任务已提交，正在后台执行"
            }
            
        except Exception as e:
            logger.error(f"❌ 提交单股分析任务失败: {e}")
            raise
    
    async def _execute_analysis_async(self, task: AnalysisTask):
        """异步执行分析任务"""
        try:
            logger.info(f"🔄 开始执行分析任务: {task.task_id} - {task.stock_code}")
            
            # 更新任务状态为处理中
            await self._update_task_status(task.task_id, AnalysisStatus.PROCESSING, 10)
            
            # 准备分析配置
            # 根据研究深度选择不同的模型配置
            research_depth = task.parameters.research_depth or "3 级 - 标准分析"

            # 从任务参数中获取模型配置（前端传递），如果没有则从系统配置获取
            from app.core.unified_config import unified_config

            quick_model = getattr(task.parameters, 'quick_analysis_model', None) or unified_config.get_quick_analysis_model()
            deep_model = getattr(task.parameters, 'deep_analysis_model', None) or unified_config.get_deep_analysis_model()

            # 根据模型名称动态查找供应商
            llm_provider = await get_provider_by_model_name(quick_model)

            # 使用标准配置函数创建完整配置 - 完全复制web目录的逻辑
            config = create_analysis_config(
                research_depth=research_depth,
                selected_analysts=task.parameters.selected_analysts or ["market", "fundamentals"],
                quick_model=quick_model,
                deep_model=deep_model,
                llm_provider=llm_provider,
                market_type=task.parameters.market_type or "A股"
            )

            logger.info(f"📋 分析配置: {config}")
            
            # 获取TradingAgents实例
            trading_graph = self._get_trading_graph(config)
            
            # 更新进度
            await self._update_task_status(task.task_id, AnalysisStatus.PROCESSING, 30)
            
            # 执行分析
            logger.info(f"📈 开始执行股票分析: {task.stock_code}")
            analysis_date = task.parameters.analysis_date or datetime.now().strftime("%Y-%m-%d")
            
            # 调用TradingAgents的propagate方法
            logger.info(f"🔍 开始调用 trading_graph.propagate({task.stock_code}, {analysis_date})")
            logger.info(f"🔍 选中的分析师: {config.get('selected_analysts', [])}")
            logger.info(f"🔍 预期分析流程: 分析师 → 研究员辩论 → 交易员 → 风险评估 → 信号处理")

            start_time = datetime.utcnow()
            final_state, decision = trading_graph.propagate(task.stock_code, analysis_date)
            execution_time = (datetime.utcnow() - start_time).total_seconds()

            logger.info(f"🔍 propagate 执行完成，总耗时: {execution_time:.2f}秒")
            logger.info(f"🔍 返回的 final_state 类型: {type(final_state)}")
            logger.info(f"🔍 返回的 decision 类型: {type(decision)}")
            if isinstance(decision, dict):
                logger.info(f"🔍 decision 内容: {decision}")
            else:
                logger.info(f"🔍 decision 内容: {str(decision)[:200]}...")
            
            # 更新进度
            await self._update_task_status(task.task_id, AnalysisStatus.PROCESSING, 80)
            
            # 处理分析结果 - 完全采用web目录的结构
            result = {
                'stock_symbol': task.stock_code,
                'analysis_date': analysis_date,
                'analysts': task.parameters.selected_analysts,
                'research_depth': task.parameters.research_depth,
                'llm_provider': config.get("llm_provider"),
                'llm_model': config.get("quick_think_llm"),
                'state': final_state,
                'decision': decision,
                'success': True,
                'error': None,
                'task_id': task.task_id
            }

            # 保存结果 - 完全采用web目录的双重保存方式
            await self._save_analysis_results_complete(task.task_id, result)
            
            # 更新任务状态为完成
            await self._update_task_status(task.task_id, AnalysisStatus.COMPLETED, 100)
            
            logger.info(f"✅ 分析任务完成: {task.task_id}")
            
        except Exception as e:
            logger.error(f"❌ 分析任务失败: {task.task_id} - {e}")
            # 更新任务状态为失败
            await self._update_task_status(task.task_id, AnalysisStatus.FAILED, 0, str(e))
    
    async def _update_task_status(
        self, 
        task_id: str, 
        status: AnalysisStatus, 
        progress: int, 
        error_message: str = None
    ):
        """更新任务状态"""
        try:
            db = get_mongo_db()
            update_data = {
                "status": status,
                "progress": progress,
                "updated_at": datetime.utcnow()
            }
            
            if status == AnalysisStatus.PROCESSING and progress == 10:
                update_data["started_at"] = datetime.utcnow()
            elif status == AnalysisStatus.COMPLETED:
                update_data["completed_at"] = datetime.utcnow()
            elif status == AnalysisStatus.FAILED:
                update_data["last_error"] = error_message
                update_data["completed_at"] = datetime.utcnow()
            
            await db.analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": update_data}
            )
            
            logger.debug(f"📊 任务状态已更新: {task_id} -> {status} ({progress}%)")
            
        except Exception as e:
            logger.error(f"❌ 更新任务状态失败: {task_id} - {e}")
    
    async def _save_analysis_result(self, task_id: str, result: Dict[str, Any]):
        """保存分析结果（原始方法）"""
        try:
            db = get_mongo_db()
            await db.analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": {"result": result}}
            )
            logger.debug(f"💾 分析结果已保存: {task_id}")
        except Exception as e:
            logger.error(f"❌ 保存分析结果失败: {task_id} - {e}")

    async def _save_analysis_result_web_style(self, task_id: str, result: Dict[str, Any]):
        """保存分析结果 - 采用web目录的方式，避免序列化问题"""
        try:
            db = get_mongo_db()

            # 创建可序列化的结果副本
            serializable_result = {}

            # 复制基本字段
            for key, value in result.items():
                if key in ['stock_symbol', 'analysis_date', 'analysts', 'research_depth',
                          'llm_provider', 'llm_model', 'success', 'error', 'task_id']:
                    serializable_result[key] = value

            # 处理state和decision - 转换为字符串或提取关键信息
            if 'state' in result:
                try:
                    # 尝试提取state中的关键信息
                    state = result['state']
                    if hasattr(state, '__dict__'):
                        # 如果是对象，提取其字典表示
                        serializable_result['state_summary'] = str(state)
                    else:
                        serializable_result['state_summary'] = str(state)
                except Exception as e:
                    logger.warning(f"⚠️ 处理state时出错: {e}")
                    serializable_result['state_summary'] = "分析状态处理失败"

            if 'decision' in result:
                try:
                    # decision通常是字典，直接保存
                    decision = result['decision']
                    if isinstance(decision, dict):
                        serializable_result['decision'] = decision
                    else:
                        serializable_result['decision'] = str(decision)
                except Exception as e:
                    logger.warning(f"⚠️ 处理decision时出错: {e}")
                    serializable_result['decision'] = "决策信息处理失败"

            # 添加时间戳
            serializable_result['completed_at'] = datetime.utcnow().isoformat()

            # 保存到数据库
            await db.analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": {"result": serializable_result}}
            )
            logger.info(f"💾 分析结果已保存 (web风格): {task_id}")

        except Exception as e:
            logger.error(f"❌ 保存分析结果失败: {task_id} - {e}")
            # 降级到简单保存
            try:
                simple_result = {
                    'task_id': task_id,
                    'success': result.get('success', True),
                    'error': str(e),
                    'completed_at': datetime.utcnow().isoformat()
                }
                await db.analysis_tasks.update_one(
                    {"task_id": task_id},
                    {"$set": {"result": simple_result}}
                )
                logger.info(f"💾 使用简化结果保存: {task_id}")
            except Exception as fallback_error:
                logger.error(f"❌ 简化保存也失败: {task_id} - {fallback_error}")

    async def _save_analysis_results_complete(self, task_id: str, result: Dict[str, Any]):
        """完整的分析结果保存 - 完全采用web目录的双重保存方式"""
        try:
            stock_symbol = result.get('stock_symbol', 'UNKNOWN')
            logger.info(f"💾 开始完整保存分析结果: {stock_symbol}")

            # 1. 保存分模块报告到本地目录
            logger.info(f"📁 [本地保存] 开始保存分模块报告到本地目录")
            local_files = await self._save_modular_reports_to_data_dir(result, stock_symbol)
            if local_files:
                logger.info(f"✅ [本地保存] 已保存 {len(local_files)} 个本地报告文件")
                for module, path in local_files.items():
                    logger.info(f"  - {module}: {path}")
            else:
                logger.warning(f"⚠️ [本地保存] 本地报告文件保存失败")

            # 2. 保存分析报告到数据库
            logger.info(f"🗄️ [数据库保存] 开始保存分析报告到数据库")
            await self._save_analysis_result_web_style(task_id, result)
            logger.info(f"✅ [数据库保存] 分析报告已成功保存到数据库")

            # 3. 记录保存结果
            if local_files:
                logger.info(f"✅ 分析报告已保存到数据库和本地文件")
            else:
                logger.warning(f"⚠️ 数据库保存成功，但本地文件保存失败")

        except Exception as save_error:
            logger.error(f"❌ [完整保存] 保存分析报告时发生错误: {str(save_error)}")
            # 降级到仅数据库保存
            try:
                await self._save_analysis_result_web_style(task_id, result)
                logger.info(f"💾 降级保存成功 (仅数据库): {task_id}")
            except Exception as fallback_error:
                logger.error(f"❌ 降级保存也失败: {task_id} - {fallback_error}")

    async def _save_modular_reports_to_data_dir(self, result: Dict[str, Any], stock_symbol: str) -> Dict[str, str]:
        """保存分模块报告到data目录 - 完全采用web目录的文件结构"""
        try:
            import os
            from pathlib import Path
            from datetime import datetime
            import json

            # 获取项目根目录
            project_root = Path(__file__).parent.parent.parent

            # 确定results目录路径 - 与web目录保持一致
            results_dir_env = os.getenv("TRADINGAGENTS_RESULTS_DIR")
            if results_dir_env:
                if not os.path.isabs(results_dir_env):
                    results_dir = project_root / results_dir_env
                else:
                    results_dir = Path(results_dir_env)
            else:
                # 默认使用data目录而不是results目录
                results_dir = project_root / "data" / "analysis_results"

            # 创建股票专用目录 - 完全按照web目录的结构
            analysis_date_raw = result.get('analysis_date', datetime.now())

            # 确保 analysis_date 是字符串格式
            if isinstance(analysis_date_raw, datetime):
                analysis_date_str = analysis_date_raw.strftime('%Y-%m-%d')
            elif isinstance(analysis_date_raw, str):
                # 如果已经是字符串，检查格式
                try:
                    # 尝试解析日期字符串，确保格式正确
                    parsed_date = datetime.strptime(analysis_date_raw, '%Y-%m-%d')
                    analysis_date_str = analysis_date_raw
                except ValueError:
                    # 如果格式不正确，使用当前日期
                    analysis_date_str = datetime.now().strftime('%Y-%m-%d')
            else:
                # 其他类型，使用当前日期
                analysis_date_str = datetime.now().strftime('%Y-%m-%d')

            stock_dir = results_dir / stock_symbol / analysis_date_str
            reports_dir = stock_dir / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            # 创建message_tool.log文件 - 与web目录保持一致
            log_file = stock_dir / "message_tool.log"
            log_file.touch(exist_ok=True)

            logger.info(f"📁 创建分析结果目录: {reports_dir}")
            logger.info(f"🔍 [调试] analysis_date_raw 类型: {type(analysis_date_raw)}, 值: {analysis_date_raw}")
            logger.info(f"🔍 [调试] analysis_date_str: {analysis_date_str}")
            logger.info(f"🔍 [调试] 完整路径: {os.path.normpath(str(reports_dir))}")

            state = result.get('state', {})
            saved_files = {}

            # 定义报告模块映射 - 完全按照web目录的定义
            report_modules = {
                'market_report': {
                    'filename': 'market_report.md',
                    'title': f'{stock_symbol} 股票技术分析报告',
                    'state_key': 'market_report'
                },
                'sentiment_report': {
                    'filename': 'sentiment_report.md',
                    'title': f'{stock_symbol} 市场情绪分析报告',
                    'state_key': 'sentiment_report'
                },
                'news_report': {
                    'filename': 'news_report.md',
                    'title': f'{stock_symbol} 新闻事件分析报告',
                    'state_key': 'news_report'
                },
                'fundamentals_report': {
                    'filename': 'fundamentals_report.md',
                    'title': f'{stock_symbol} 基本面分析报告',
                    'state_key': 'fundamentals_report'
                },
                'investment_plan': {
                    'filename': 'investment_plan.md',
                    'title': f'{stock_symbol} 投资决策报告',
                    'state_key': 'investment_plan'
                },
                'trader_investment_plan': {
                    'filename': 'trader_investment_plan.md',
                    'title': f'{stock_symbol} 交易计划报告',
                    'state_key': 'trader_investment_plan'
                },
                'final_trade_decision': {
                    'filename': 'final_trade_decision.md',
                    'title': f'{stock_symbol} 最终投资决策',
                    'state_key': 'final_trade_decision'
                },
                'investment_debate_state': {
                    'filename': 'research_team_decision.md',
                    'title': f'{stock_symbol} 研究团队决策报告',
                    'state_key': 'investment_debate_state'
                },
                'risk_debate_state': {
                    'filename': 'risk_management_decision.md',
                    'title': f'{stock_symbol} 风险管理团队决策报告',
                    'state_key': 'risk_debate_state'
                }
            }

            # 保存各模块报告 - 完全按照web目录的方式
            for module_key, module_info in report_modules.items():
                try:
                    state_key = module_info['state_key']
                    if state_key in state:
                        # 提取模块内容
                        module_content = state[state_key]
                        if isinstance(module_content, str):
                            report_content = module_content
                        else:
                            report_content = str(module_content)

                        # 保存到文件 - 使用web目录的文件名
                        file_path = reports_dir / module_info['filename']
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(report_content)

                        saved_files[module_key] = str(file_path)
                        logger.info(f"✅ 保存模块报告: {file_path}")

                except Exception as e:
                    logger.warning(f"⚠️ 保存模块 {module_key} 失败: {e}")

            # 保存最终决策报告 - 完全按照web目录的方式
            decision = result.get('decision', {})
            if decision:
                decision_content = f"# {stock_symbol} 最终投资决策\n\n"

                if isinstance(decision, dict):
                    decision_content += f"## 投资建议\n\n"
                    decision_content += f"**行动**: {decision.get('action', 'N/A')}\n\n"
                    decision_content += f"**置信度**: {decision.get('confidence', 0):.1%}\n\n"
                    decision_content += f"**风险评分**: {decision.get('risk_score', 0):.1%}\n\n"
                    decision_content += f"**目标价位**: {decision.get('target_price', 'N/A')}\n\n"
                    decision_content += f"## 分析推理\n\n{decision.get('reasoning', '暂无分析推理')}\n\n"
                else:
                    decision_content += f"{str(decision)}\n\n"

                decision_file = reports_dir / "final_trade_decision.md"
                with open(decision_file, 'w', encoding='utf-8') as f:
                    f.write(decision_content)

                saved_files['final_trade_decision'] = str(decision_file)
                logger.info(f"✅ 保存最终决策: {decision_file}")

            # 保存分析元数据文件 - 完全按照web目录的方式
            metadata = {
                'stock_symbol': stock_symbol,
                'analysis_date': analysis_date_str,
                'timestamp': datetime.now().isoformat(),
                'research_depth': result.get('research_depth', 1),
                'analysts': result.get('analysts', []),
                'status': 'completed',
                'reports_count': len(saved_files),
                'report_types': list(saved_files.keys())
            }

            metadata_file = reports_dir.parent / "analysis_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ 保存分析元数据: {metadata_file}")
            logger.info(f"✅ 分模块报告保存完成，共保存 {len(saved_files)} 个文件")
            logger.info(f"📁 保存目录: {os.path.normpath(str(reports_dir))}")

            return saved_files

        except Exception as e:
            logger.error(f"❌ 保存分模块报告失败: {e}")
            import traceback
            logger.error(f"❌ 详细错误: {traceback.format_exc()}")
            return {}
    
# 重复的 get_task_status 方法已删除，使用第469行的内存版本


# 全局服务实例
_analysis_service = None

def get_simple_analysis_service() -> SimpleAnalysisService:
    """获取分析服务实例"""
    global _analysis_service
    if _analysis_service is None:
        logger.info("🔧 [单例] 创建新的 SimpleAnalysisService 实例")
        _analysis_service = SimpleAnalysisService()
    else:
        logger.info(f"🔧 [单例] 返回现有的 SimpleAnalysisService 实例: {id(_analysis_service)}")
    return _analysis_service
