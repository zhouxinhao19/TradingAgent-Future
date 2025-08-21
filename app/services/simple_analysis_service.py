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

# 初始化TradingAgents日志系统
from tradingagents.utils.logging_init import init_logging
init_logging()

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
from app.services.redis_progress_tracker import RedisProgressTracker, get_progress_by_id
from app.services.progress_log_handler import register_analysis_tracker, unregister_analysis_tracker

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
        # 进度跟踪器缓存
        self._progress_trackers: Dict[str, RedisProgressTracker] = {}

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
        progress_tracker = None
        try:
            logger.info(f"🚀 开始后台执行分析任务: {task_id}")

            # 创建Redis进度跟踪器
            progress_tracker = RedisProgressTracker(
                task_id=task_id,
                analysts=request.parameters.selected_analysts or ["market", "fundamentals"],
                research_depth=request.parameters.research_depth or "标准",
                llm_provider="dashscope"
            )

            # 缓存进度跟踪器
            self._progress_trackers[task_id] = progress_tracker

            # 注册到日志监控
            register_analysis_tracker(task_id, progress_tracker)

            # 初始化进度
            progress_tracker.update_progress("🚀 开始股票分析")

            # 更新状态为运行中
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=10,
                message="分析开始...",
                current_step="initialization"
            )

            # 数据准备阶段
            progress_tracker.update_progress("🔧 检查环境配置")
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=20,
                message="准备分析数据...",
                current_step="data_preparation"
            )

            # 执行实际的分析
            result = await self._execute_analysis_sync(task_id, user_id, request, progress_tracker)

            # 标记进度跟踪器完成
            progress_tracker.mark_completed("✅ 分析完成")

            # 保存分析结果到文件和数据库
            try:
                logger.info(f"💾 开始保存分析结果: {task_id}")
                await self._save_analysis_results_complete(task_id, result)
                logger.info(f"✅ 分析结果保存完成: {task_id}")
            except Exception as save_error:
                logger.error(f"❌ 保存分析结果失败: {task_id} - {save_error}")
                # 保存失败不影响分析完成状态

            # 🔍 调试：检查即将保存到内存的result
            logger.info(f"🔍 [DEBUG] 即将保存到内存的result键: {list(result.keys())}")
            logger.info(f"🔍 [DEBUG] 即将保存到内存的decision: {bool(result.get('decision'))}")
            if result.get('decision'):
                logger.info(f"🔍 [DEBUG] 即将保存的decision内容: {result['decision']}")

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

            # 标记进度跟踪器失败
            if progress_tracker:
                progress_tracker.mark_failed(str(e))

            # 更新状态为失败
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.FAILED,
                progress=0,
                message="分析失败",
                current_step="failed",
                error_message=str(e)
            )
        finally:
            # 清理进度跟踪器缓存
            if task_id in self._progress_trackers:
                del self._progress_trackers[task_id]

            # 从日志监控中注销
            unregister_analysis_tracker(task_id)

    async def _execute_analysis_sync(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest,
        progress_tracker: Optional[RedisProgressTracker] = None
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
                request,
                progress_tracker
            )
        return result

    def _run_analysis_sync(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest,
        progress_tracker: Optional[RedisProgressTracker] = None
    ) -> Dict[str, Any]:
        """同步执行分析的具体实现"""
        try:
            # 在线程中重新初始化日志系统
            from tradingagents.utils.logging_init import init_logging, get_logger
            init_logging()
            thread_logger = get_logger('analysis_thread')

            thread_logger.info(f"🔄 [线程池] 开始执行分析: {task_id} - {request.stock_code}")
            logger.info(f"🔄 [线程池] 开始执行分析: {task_id} - {request.stock_code}")

            # 如果有进度跟踪器，更新进度
            if progress_tracker:
                progress_tracker.update_progress("⚙️ 配置分析参数")

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
            if progress_tracker:
                progress_tracker.update_progress("⚙️ 配置分析参数")
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
            if progress_tracker:
                progress_tracker.update_progress("🚀 初始化AI分析引擎")
            update_progress_sync(40, "初始化分析引擎...", "engine_initialization")
            trading_graph = self._get_trading_graph(config)

            # 开始分析
            if progress_tracker:
                progress_tracker.update_progress("📊 开始智能体分析")
            update_progress_sync(50, "开始股票分析...", "analysis_execution")
            start_time = datetime.now()
            analysis_date = datetime.now().strftime("%Y-%m-%d")

            # 调用分析方法 - 添加进度模拟
            if progress_tracker:
                progress_tracker.update_progress("🤖 执行多智能体协作分析")
            update_progress_sync(60, "执行智能体分析...", "agent_analysis")

            # 启动一个异步任务来模拟进度更新
            import threading
            import time

            def simulate_progress():
                """模拟TradingAgents内部进度"""
                try:
                    if not progress_tracker:
                        return

                    # 分析师阶段 - 根据选择的分析师数量动态调整
                    analysts = request.parameters.selected_analysts if request.parameters else ["market", "fundamentals"]

                    # 模拟分析师执行
                    for i, analyst in enumerate(analysts):
                        time.sleep(15)  # 每个分析师大约15秒
                        if analyst == "market":
                            progress_tracker.update_progress("📊 市场分析师正在分析")
                        elif analyst == "fundamentals":
                            progress_tracker.update_progress("💼 基本面分析师正在分析")
                        elif analyst == "news":
                            progress_tracker.update_progress("📰 新闻分析师正在分析")
                        elif analyst == "social":
                            progress_tracker.update_progress("💬 社交媒体分析师正在分析")

                    # 研究团队阶段
                    time.sleep(10)
                    progress_tracker.update_progress("🐂 看涨研究员构建论据")

                    time.sleep(8)
                    progress_tracker.update_progress("🐻 看跌研究员识别风险")

                    # 辩论阶段
                    research_depth = request.parameters.research_depth if request.parameters else "快速"
                    debate_rounds = 1 if research_depth == "快速" else (2 if research_depth == "标准" else 3)

                    for round_num in range(debate_rounds):
                        time.sleep(12)
                        progress_tracker.update_progress(f"🎯 研究辩论 第{round_num+1}轮")

                    time.sleep(8)
                    progress_tracker.update_progress("👔 研究经理形成共识")

                    # 交易员阶段
                    time.sleep(10)
                    progress_tracker.update_progress("💼 交易员制定策略")

                    # 风险管理阶段
                    time.sleep(8)
                    progress_tracker.update_progress("🔥 激进风险评估")

                    time.sleep(6)
                    progress_tracker.update_progress("🛡️ 保守风险评估")

                    time.sleep(6)
                    progress_tracker.update_progress("⚖️ 中性风险评估")

                    time.sleep(8)
                    progress_tracker.update_progress("🎯 风险经理制定策略")

                    # 最终阶段
                    time.sleep(5)
                    progress_tracker.update_progress("📡 信号处理")

                except Exception as e:
                    logger.warning(f"⚠️ 进度模拟失败: {e}")

            # 启动进度模拟线程
            progress_thread = threading.Thread(target=simulate_progress, daemon=True)
            progress_thread.start()

            # 执行实际分析
            state, decision = trading_graph.propagate(request.stock_code, analysis_date)

            # 🔍 调试：检查decision的结构
            logger.info(f"🔍 [DEBUG] Decision类型: {type(decision)}")
            logger.info(f"🔍 [DEBUG] Decision内容: {decision}")
            if isinstance(decision, dict):
                logger.info(f"🔍 [DEBUG] Decision键: {list(decision.keys())}")
            elif hasattr(decision, '__dict__'):
                logger.info(f"🔍 [DEBUG] Decision属性: {list(vars(decision).keys())}")

            # 处理结果
            if progress_tracker:
                progress_tracker.update_progress("📊 处理分析结果")
            update_progress_sync(90, "处理分析结果...", "result_processing")

            execution_time = (datetime.now() - start_time).total_seconds()

            # 从state中提取reports字段
            reports = {}
            try:
                # 定义所有可能的报告字段
                report_fields = [
                    'market_report',
                    'sentiment_report',
                    'news_report',
                    'fundamentals_report',
                    'investment_plan',
                    'trader_investment_plan',
                    'final_trade_decision'
                ]

                # 从state中提取报告内容
                for field in report_fields:
                    if hasattr(state, field):
                        value = getattr(state, field, "")
                    elif isinstance(state, dict) and field in state:
                        value = state[field]
                    else:
                        value = ""

                    if isinstance(value, str) and len(value.strip()) > 10:  # 只保存有实际内容的报告
                        reports[field] = value.strip()

                # 处理复杂的辩论状态报告
                if hasattr(state, 'investment_debate_state') or (isinstance(state, dict) and 'investment_debate_state' in state):
                    debate_state = getattr(state, 'investment_debate_state', None) if hasattr(state, 'investment_debate_state') else state.get('investment_debate_state')
                    if debate_state:
                        if hasattr(debate_state, 'judge_decision'):
                            decision_content = getattr(debate_state, 'judge_decision', "")
                        elif isinstance(debate_state, dict) and 'judge_decision' in debate_state:
                            decision_content = debate_state['judge_decision']
                        else:
                            decision_content = str(debate_state)

                        if decision_content and len(decision_content.strip()) > 10:
                            reports['research_team_decision'] = decision_content.strip()

                if hasattr(state, 'risk_debate_state') or (isinstance(state, dict) and 'risk_debate_state' in state):
                    risk_state = getattr(state, 'risk_debate_state', None) if hasattr(state, 'risk_debate_state') else state.get('risk_debate_state')
                    if risk_state:
                        if hasattr(risk_state, 'judge_decision'):
                            risk_decision = getattr(risk_state, 'judge_decision', "")
                        elif isinstance(risk_state, dict) and 'judge_decision' in risk_state:
                            risk_decision = risk_state['judge_decision']
                        else:
                            risk_decision = str(risk_state)

                        if risk_decision and len(risk_decision.strip()) > 10:
                            reports['risk_management_decision'] = risk_decision.strip()

                logger.info(f"📊 从state中提取到 {len(reports)} 个报告: {list(reports.keys())}")

            except Exception as e:
                logger.warning(f"⚠️ 提取reports时出错: {e}")
                # 降级到从detailed_analysis提取
                try:
                    if isinstance(decision, dict):
                        for key, value in decision.items():
                            if isinstance(value, str) and len(value) > 50:
                                reports[key] = value
                        logger.info(f"📊 降级：从decision中提取到 {len(reports)} 个报告")
                except Exception as fallback_error:
                    logger.warning(f"⚠️ 降级提取也失败: {fallback_error}")

            # 🔥 格式化decision数据（参考web目录的实现）
            formatted_decision = {}
            try:
                if isinstance(decision, dict):
                    # 处理目标价格
                    target_price = decision.get('target_price')
                    if target_price is not None and target_price != 'N/A':
                        try:
                            if isinstance(target_price, str):
                                # 移除货币符号和空格
                                clean_price = target_price.replace('$', '').replace('¥', '').replace('￥', '').strip()
                                target_price = float(clean_price) if clean_price and clean_price != 'None' else None
                            elif isinstance(target_price, (int, float)):
                                target_price = float(target_price)
                            else:
                                target_price = None
                        except (ValueError, TypeError):
                            target_price = None
                    else:
                        target_price = None

                    # 将英文投资建议转换为中文
                    action_translation = {
                        'BUY': '买入',
                        'SELL': '卖出',
                        'HOLD': '持有',
                        'buy': '买入',
                        'sell': '卖出',
                        'hold': '持有'
                    }
                    action = decision.get('action', '持有')
                    chinese_action = action_translation.get(action, action)

                    formatted_decision = {
                        'action': chinese_action,
                        'confidence': decision.get('confidence', 0.5),
                        'risk_score': decision.get('risk_score', 0.3),
                        'target_price': target_price,
                        'reasoning': decision.get('reasoning', '暂无分析推理')
                    }

                    logger.info(f"🎯 [DEBUG] 格式化后的decision: {formatted_decision}")
                else:
                    # 处理其他类型
                    formatted_decision = {
                        'action': '持有',
                        'confidence': 0.5,
                        'risk_score': 0.3,
                        'target_price': None,
                        'reasoning': '暂无分析推理'
                    }
                    logger.warning(f"⚠️ Decision不是字典类型: {type(decision)}")
            except Exception as e:
                logger.error(f"❌ 格式化decision失败: {e}")
                formatted_decision = {
                    'action': '持有',
                    'confidence': 0.5,
                    'risk_score': 0.3,
                    'target_price': None,
                    'reasoning': '暂无分析推理'
                }

            # 🔥 按照web目录的方式生成summary和recommendation
            summary = ""
            recommendation = ""

            # 1. 优先从reports中的final_trade_decision提取summary（与web目录保持一致）
            if isinstance(reports, dict) and 'final_trade_decision' in reports:
                final_decision_content = reports['final_trade_decision']
                if isinstance(final_decision_content, str) and len(final_decision_content) > 50:
                    # 提取前200个字符作为摘要（与web目录完全一致）
                    summary = final_decision_content[:200].replace('#', '').replace('*', '').strip()
                    if len(final_decision_content) > 200:
                        summary += "..."
                    logger.info(f"📝 [SUMMARY] 从final_trade_decision提取摘要: {len(summary)}字符")

            # 2. 如果没有final_trade_decision，从state中提取
            if not summary and isinstance(state, dict):
                final_decision = state.get('final_trade_decision', '')
                if isinstance(final_decision, str) and len(final_decision) > 50:
                    summary = final_decision[:200].replace('#', '').replace('*', '').strip()
                    if len(final_decision) > 200:
                        summary += "..."
                    logger.info(f"📝 [SUMMARY] 从state.final_trade_decision提取摘要: {len(summary)}字符")

            # 3. 生成recommendation（从decision的reasoning）
            if isinstance(formatted_decision, dict):
                action = formatted_decision.get('action', '持有')
                target_price = formatted_decision.get('target_price')
                reasoning = formatted_decision.get('reasoning', '')

                # 生成投资建议
                recommendation = f"投资建议：{action}。"
                if target_price:
                    recommendation += f"目标价格：{target_price}元。"
                if reasoning:
                    recommendation += f"决策依据：{reasoning}"
                logger.info(f"💡 [RECOMMENDATION] 生成投资建议: {len(recommendation)}字符")

            # 4. 如果还是没有，从其他报告中提取
            if not summary and isinstance(reports, dict):
                # 尝试从其他报告中提取摘要
                for report_name, content in reports.items():
                    if isinstance(content, str) and len(content) > 100:
                        summary = content[:200].replace('#', '').replace('*', '').strip()
                        if len(content) > 200:
                            summary += "..."
                        logger.info(f"📝 [SUMMARY] 从{report_name}提取摘要: {len(summary)}字符")
                        break

            # 5. 最后的备用方案
            if not summary:
                summary = f"对{request.stock_code}的分析已完成，请查看详细报告。"
                logger.warning(f"⚠️ [SUMMARY] 使用备用摘要")

            if not recommendation:
                recommendation = f"请参考详细分析报告做出投资决策。"
                logger.warning(f"⚠️ [RECOMMENDATION] 使用备用建议")

            # 构建结果
            result = {
                "analysis_id": str(uuid.uuid4()),
                "stock_code": request.stock_code,
                "stock_symbol": request.stock_code,  # 添加stock_symbol字段以保持兼容性
                "analysis_date": analysis_date,
                "summary": summary,
                "recommendation": recommendation,
                "confidence_score": formatted_decision.get("confidence", 0.0) if isinstance(formatted_decision, dict) else 0.0,
                "risk_level": "中等",  # 可以根据risk_score计算
                "key_points": [],  # 可以从reasoning中提取关键点
                "detailed_analysis": decision,
                "execution_time": execution_time,
                "tokens_used": decision.get("tokens_used", 0) if isinstance(decision, dict) else 0,
                "state": state,
                # 添加分析师信息
                "analysts": request.parameters.selected_analysts if request.parameters else [],
                "research_depth": request.parameters.research_depth if request.parameters else "快速",
                # 添加提取的报告内容
                "reports": reports,
                # 🔥 关键修复：添加格式化后的decision字段！
                "decision": formatted_decision
            }

            logger.info(f"✅ [线程池] 分析完成: {task_id} - 耗时{execution_time:.2f}秒")

            # 🔍 调试：检查返回的result结构
            logger.info(f"🔍 [DEBUG] 返回result的键: {list(result.keys())}")
            logger.info(f"🔍 [DEBUG] 返回result中有decision: {bool(result.get('decision'))}")
            if result.get('decision'):
                decision = result['decision']
                logger.info(f"🔍 [DEBUG] 返回decision内容: {decision}")

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

            # 🔍 调试：检查从内存获取的result_data
            result_data = result.get('result_data')
            logger.info(f"🔍 [GET_STATUS] result_data存在: {bool(result_data)}")
            if result_data:
                logger.info(f"🔍 [GET_STATUS] result_data键: {list(result_data.keys())}")
                logger.info(f"🔍 [GET_STATUS] result_data中有decision: {bool(result_data.get('decision'))}")
                if result_data.get('decision'):
                    logger.info(f"🔍 [GET_STATUS] decision内容: {result_data['decision']}")
            else:
                logger.warning(f"⚠️ [GET_STATUS] result_data为空或不存在")

            # 优先从Redis获取详细进度信息
            redis_progress = get_progress_by_id(task_id)
            if redis_progress:
                logger.info(f"📊 [Redis进度] 获取到详细进度: {task_id}")
                # 合并Redis进度数据
                result.update({
                    'progress': redis_progress.get('progress_percentage', result.get('progress', 0)),
                    'current_step': redis_progress.get('current_step_name', result.get('current_step', '')),
                    'message': redis_progress.get('last_message', result.get('message', '')),
                    'elapsed_time': redis_progress.get('elapsed_time', 0),
                    'remaining_time': redis_progress.get('remaining_time', 0),
                    'steps': redis_progress.get('steps', []),
                    'start_time': result.get('start_time'),  # 保持原有格式
                    'last_update': redis_progress.get('last_update', result.get('start_time'))
                })
            else:
                # 如果Redis中没有，尝试从内存中的进度跟踪器获取
                if task_id in self._progress_trackers:
                    progress_tracker = self._progress_trackers[task_id]
                    progress_data = progress_tracker.to_dict()

                    # 合并进度跟踪器的详细信息
                    result.update({
                        'progress': progress_data['progress'],
                        'current_step': progress_data['current_step'],
                        'message': progress_data['message'],
                        'elapsed_time': progress_data['elapsed_time'],
                        'remaining_time': progress_data['remaining_time'],
                        'estimated_total_time': progress_data.get('estimated_total_time', 0),
                        'steps': progress_data['steps'],
                        'start_time': progress_data['start_time'],
                        'last_update': progress_data['last_update']
                    })
                    logger.info(f"📊 合并内存进度跟踪器数据: {task_id}")
                else:
                    logger.info(f"⚠️ 未找到进度信息: {task_id}")
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
        """保存分析结果 - 采用web目录的方式，保存到analysis_reports集合"""
        try:
            db = get_mongo_db()

            # 生成分析ID（与web目录保持一致）
            from datetime import datetime
            timestamp = datetime.utcnow()
            stock_symbol = result.get('stock_symbol') or result.get('stock_code', 'UNKNOWN')
            analysis_id = f"{stock_symbol}_{timestamp.strftime('%Y%m%d_%H%M%S')}"

            # 处理reports字段 - 从state中提取所有分析报告
            reports = {}
            if 'state' in result:
                try:
                    state = result['state']

                    # 定义所有可能的报告字段
                    report_fields = [
                        'market_report',
                        'sentiment_report',
                        'news_report',
                        'fundamentals_report',
                        'investment_plan',
                        'trader_investment_plan',
                        'final_trade_decision'
                    ]

                    # 从state中提取报告内容
                    for field in report_fields:
                        if hasattr(state, field):
                            value = getattr(state, field, "")
                        elif isinstance(state, dict) and field in state:
                            value = state[field]
                        else:
                            value = ""

                        if isinstance(value, str) and len(value.strip()) > 10:  # 只保存有实际内容的报告
                            reports[field] = value.strip()

                    # 处理复杂的辩论状态报告
                    if hasattr(state, 'investment_debate_state') or (isinstance(state, dict) and 'investment_debate_state' in state):
                        debate_state = getattr(state, 'investment_debate_state', None) if hasattr(state, 'investment_debate_state') else state.get('investment_debate_state')
                        if debate_state:
                            if hasattr(debate_state, 'judge_decision'):
                                decision_content = getattr(debate_state, 'judge_decision', "")
                            elif isinstance(debate_state, dict) and 'judge_decision' in debate_state:
                                decision_content = debate_state['judge_decision']
                            else:
                                decision_content = str(debate_state)

                            if decision_content and len(decision_content.strip()) > 10:
                                reports['research_team_decision'] = decision_content.strip()

                    if hasattr(state, 'risk_debate_state') or (isinstance(state, dict) and 'risk_debate_state' in state):
                        risk_state = getattr(state, 'risk_debate_state', None) if hasattr(state, 'risk_debate_state') else state.get('risk_debate_state')
                        if risk_state:
                            if hasattr(risk_state, 'judge_decision'):
                                risk_decision = getattr(risk_state, 'judge_decision', "")
                            elif isinstance(risk_state, dict) and 'judge_decision' in risk_state:
                                risk_decision = risk_state['judge_decision']
                            else:
                                risk_decision = str(risk_state)

                            if risk_decision and len(risk_decision.strip()) > 10:
                                reports['risk_management_decision'] = risk_decision.strip()

                    logger.info(f"📊 从state中提取到 {len(reports)} 个报告: {list(reports.keys())}")

                except Exception as e:
                    logger.warning(f"⚠️ 处理state中的reports时出错: {e}")
                    # 降级到从detailed_analysis提取
                    if 'detailed_analysis' in result:
                        try:
                            detailed_analysis = result['detailed_analysis']
                            if isinstance(detailed_analysis, dict):
                                for key, value in detailed_analysis.items():
                                    if isinstance(value, str) and len(value) > 50:
                                        reports[key] = value
                                logger.info(f"📊 降级：从detailed_analysis中提取到 {len(reports)} 个报告")
                        except Exception as fallback_error:
                            logger.warning(f"⚠️ 降级提取也失败: {fallback_error}")

            # 构建文档（与web目录的MongoDBReportManager保持一致）
            document = {
                "analysis_id": analysis_id,
                "stock_symbol": stock_symbol,
                "analysis_date": timestamp.strftime('%Y-%m-%d'),
                "timestamp": timestamp,
                "status": "completed",
                "source": "api",

                # 分析结果摘要
                "summary": result.get("summary", ""),
                "analysts": result.get("analysts", []),
                "research_depth": result.get("research_depth", 1),

                # 报告内容
                "reports": reports,

                # 🔥 关键修复：添加格式化后的decision字段！
                "decision": result.get("decision", {}),

                # 元数据
                "created_at": timestamp,
                "updated_at": timestamp,

                # API特有字段
                "task_id": task_id,
                "recommendation": result.get("recommendation", ""),
                "confidence_score": result.get("confidence_score", 0.0),
                "risk_level": result.get("risk_level", "中等"),
                "key_points": result.get("key_points", []),
                "execution_time": result.get("execution_time", 0),
                "tokens_used": result.get("tokens_used", 0)
            }

            # 保存到analysis_reports集合（与web目录保持一致）
            result_insert = await db.analysis_reports.insert_one(document)

            if result_insert.inserted_id:
                logger.info(f"✅ 分析报告已保存到MongoDB analysis_reports: {analysis_id}")

                # 同时更新analysis_tasks集合中的result字段，保持API兼容性
                await db.analysis_tasks.update_one(
                    {"task_id": task_id},
                    {"$set": {"result": {
                        "analysis_id": analysis_id,
                        "stock_symbol": stock_symbol,
                        "stock_code": result.get('stock_code', stock_symbol),
                        "analysis_date": result.get('analysis_date'),
                        "summary": result.get("summary", ""),
                        "recommendation": result.get("recommendation", ""),
                        "confidence_score": result.get("confidence_score", 0.0),
                        "risk_level": result.get("risk_level", "中等"),
                        "key_points": result.get("key_points", []),
                        "detailed_analysis": result.get("detailed_analysis", {}),
                        "execution_time": result.get("execution_time", 0),
                        "tokens_used": result.get("tokens_used", 0),
                        "reports": reports,  # 包含提取的报告内容
                        # 🔥 关键修复：添加格式化后的decision字段！
                        "decision": result.get("decision", {})
                    }}}
                )
                logger.info(f"💾 分析结果已保存 (web风格): {task_id}")
            else:
                logger.error("❌ MongoDB插入失败")

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
            # 调试：打印result中的所有键
            logger.info(f"🔍 [调试] result中的所有键: {list(result.keys())}")
            logger.info(f"🔍 [调试] stock_code: {result.get('stock_code', 'NOT_FOUND')}")
            logger.info(f"🔍 [调试] stock_symbol: {result.get('stock_symbol', 'NOT_FOUND')}")

            # 优先使用stock_symbol，如果没有则使用stock_code
            stock_symbol = result.get('stock_symbol') or result.get('stock_code', 'UNKNOWN')
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
