"""
进度跟踪器（过渡期）
- 暂时从旧模块导入 RedisProgressTracker 类
- 在本模块内提供 get_progress_by_id 的实现（与旧实现一致，修正 cls 引用）
"""
from typing import Any, Dict, Optional, List
import json
import os
import logging
import time


# 过渡期：从旧模块导入类，保持现有行为不变
from app.services.redis_progress_tracker import (
    RedisProgressTracker as _RedisProgressTracker,
)

RedisProgressTracker = _RedisProgressTracker  # type: ignore

logger = logging.getLogger("app.services.redis_progress_tracker")

from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class AnalysisStep:
    """分析步骤数据类"""
    name: str
    description: str
    status: str = "pending"  # pending, current, completed, failed
    weight: float = 0.1  # 权重，用于计算进度
    start_time: Optional[float] = None
    end_time: Optional[float] = None


def safe_serialize(data):
    """安全序列化，处理不可序列化的对象"""
    if isinstance(data, dict):
        return {k: safe_serialize(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [safe_serialize(item) for item in data]
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    elif hasattr(data, '__dict__'):
        return safe_serialize(data.__dict__)
    else:
        return str(data)



class RedisProgressTracker:
    """Redis进度跟踪器"""

    def __init__(self, task_id: str, analysts: List[str], research_depth: str, llm_provider: str):
        self.task_id = task_id
        self.analysts = analysts
        self.research_depth = research_depth
        self.llm_provider = llm_provider

        # Redis连接
        self.redis_client = None
        self.use_redis = self._init_redis()

        # 进度数据
        self.progress_data = {
            'task_id': task_id,
            'status': 'running',
            'progress_percentage': 0.0,
            'current_step': 0,
            'total_steps': 0,
            'current_step_name': '初始化',
            'current_step_description': '准备开始分析',
            'last_message': '分析任务已启动',
            'start_time': time.time(),
            'last_update': time.time(),
            'elapsed_time': 0.0,
            'remaining_time': 0.0,
            'steps': []
        }

        # 生成分析步骤
        self.analysis_steps = self._generate_dynamic_steps()
        self.progress_data['total_steps'] = len(self.analysis_steps)
        self.progress_data['steps'] = [asdict(step) for step in self.analysis_steps]

        # 保存初始状态
        self._save_progress()

        logger.info(f"📊 [Redis进度] 初始化完成: {task_id}, 步骤数: {len(self.analysis_steps)}")

    def _init_redis(self) -> bool:
        """初始化Redis连接"""
        try:
            # 检查REDIS_ENABLED环境变量
            redis_enabled = os.getenv('REDIS_ENABLED', 'false').lower() == 'true'
            if not redis_enabled:
                logger.info(f"📊 [Redis进度] Redis未启用，使用文件存储")
                return False

            import redis

            # 从环境变量获取Redis配置
            redis_host = os.getenv('REDIS_HOST', 'localhost')
            redis_port = int(os.getenv('REDIS_PORT', 6379))
            redis_password = os.getenv('REDIS_PASSWORD', None)
            redis_db = int(os.getenv('REDIS_DB', 0))

            # 创建Redis连接
            if redis_password:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    password=redis_password,
                    db=redis_db,
                    decode_responses=True
                )
            else:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=True
                )

            # 测试连接
            self.redis_client.ping()
            logger.info(f"📊 [Redis进度] Redis连接成功: {redis_host}:{redis_port}")
            return True
        except Exception as e:
            logger.warning(f"📊 [Redis进度] Redis连接失败，使用文件存储: {e}")
            return False



def get_progress_by_id(task_id: str) -> Optional[Dict[str, Any]]:
    def _generate_dynamic_steps(self) -> List[AnalysisStep]:
        """根据分析师数量和研究深度动态生成分析步骤"""
        steps = []

        # 1. 基础准备阶段 (10%)
        steps.extend([
            AnalysisStep("📋 准备阶段", "验证股票代码，检查数据源可用性", "pending", 0.03),
            AnalysisStep("🔧 环境检查", "检查API密钥配置，确保数据获取正常", "pending", 0.02),
            AnalysisStep("💰 成本估算", "根据分析深度预估API调用成本", "pending", 0.01),
            AnalysisStep("⚙️ 参数设置", "配置分析参数和AI模型选择", "pending", 0.02),
            AnalysisStep("🚀 启动引擎", "初始化AI分析引擎，准备开始分析", "pending", 0.02),
        ])

        # 2. 分析师团队阶段 (35%) - 并行执行
        analyst_weight = 0.35 / len(self.analysts)
        for analyst in self.analysts:
            analyst_info = self._get_analyst_step_info(analyst)
            steps.append(AnalysisStep(
                analyst_info["name"],
                analyst_info["description"],
                "pending",
                analyst_weight
            ))

        # 3. 研究团队辩论阶段 (25%)
        debate_rounds = self._get_debate_rounds()
        debate_weight = 0.25 / (3 + debate_rounds)  # 多头+空头+经理+辩论轮次

        steps.extend([
            AnalysisStep("🐂 看涨研究员", "基于分析师报告构建买入论据", "pending", debate_weight),
            AnalysisStep("🐻 看跌研究员", "识别潜在风险和问题", "pending", debate_weight),
        ])

        # 根据研究深度添加辩论轮次
        for i in range(debate_rounds):
            steps.append(AnalysisStep(f"🎯 研究辩论 第{i+1}轮", "多头空头研究员深度辩论", "pending", debate_weight))

        steps.append(AnalysisStep("👔 研究经理", "综合辩论结果，形成研究共识", "pending", debate_weight))

        # 4. 交易团队阶段 (8%)
        steps.append(AnalysisStep("💼 交易员决策", "基于研究结果制定具体交易策略", "pending", 0.08))

        # 5. 风险管理团队阶段 (15%)
        risk_weight = 0.15 / 4
        steps.extend([
            AnalysisStep("🔥 激进风险评估", "从激进角度评估投资风险", "pending", risk_weight),
            AnalysisStep("🛡️ 保守风险评估", "从保守角度评估投资风险", "pending", risk_weight),
            AnalysisStep("⚖️ 中性风险评估", "从中性角度评估投资风险", "pending", risk_weight),
            AnalysisStep("🎯 风险经理", "综合风险评估，制定风险控制策略", "pending", risk_weight),
        ])

        # 6. 最终决策阶段 (7%)
        steps.extend([
            AnalysisStep("📡 信号处理", "处理所有分析结果，生成交易信号", "pending", 0.04),
            AnalysisStep("📊 生成报告", "整理分析结果，生成完整报告", "pending", 0.03),
        ])

        return steps

    def _get_debate_rounds(self) -> int:
        """根据研究深度获取辩论轮次"""
        if self.research_depth == "快速":
            return 1
        elif self.research_depth == "标准":
            return 2
        else:  # 深度
            return 3

    def _get_analyst_step_info(self, analyst: str) -> Dict[str, str]:
        """获取分析师步骤信息（名称和描述）"""
        analyst_info = {
            'market': {
                "name": "📊 市场分析师",
                "description": "分析股价走势、成交量、技术指标等市场表现"
            },
            'fundamentals': {
                "name": "💼 基本面分析师",
                "description": "分析公司财务状况、盈利能力、成长性等基本面"
            },
            'news': {
                "name": "📰 新闻分析师",
                "description": "分析相关新闻、公告、行业动态对股价的影响"
            },
            'social': {
                "name": "💬 社交媒体分析师",
                "description": "分析社交媒体讨论、网络热度、散户情绪等"
            }
        }
        return analyst_info.get(analyst, {
            "name": f"🔍 {analyst}分析师",
            "description": f"进行{analyst}相关的专业分析"
        })

    """根据任务ID获取进度（过渡期实现，保持与旧实现一致）"""
    try:
        # 检查REDIS_ENABLED环境变量
        redis_enabled = os.getenv('REDIS_ENABLED', 'false').lower() == 'true'

        # 如果Redis启用，先尝试Redis
        if redis_enabled:
            try:
                import redis

                # 从环境变量获取Redis配置
                redis_host = os.getenv('REDIS_HOST', 'localhost')
                redis_port = int(os.getenv('REDIS_PORT', 6379))
                redis_password = os.getenv('REDIS_PASSWORD', None)
                redis_db = int(os.getenv('REDIS_DB', 0))

                # 创建Redis连接
                if redis_password:
                    redis_client = redis.Redis(
                        host=redis_host,
                        port=redis_port,
                        password=redis_password,
                        db=redis_db,
                        decode_responses=True
                    )
                else:
                    redis_client = redis.Redis(
                        host=redis_host,
                        port=redis_port,
                        db=redis_db,
                        decode_responses=True
                    )

                key = f"progress:{task_id}"
                data = redis_client.get(key)
                if data:
                    progress_data = json.loads(data)
                    # 使用统一的时间计算逻辑（修正对 cls 的引用）
                    progress_data = RedisProgressTracker._calculate_static_time_estimates(progress_data)
                    return progress_data
            except Exception as e:
                logger.debug(f"📊 [Redis进度] Redis读取失败: {e}")

        # 尝试从文件读取
        progress_file = f"./data/progress/{task_id}.json"
        if os.path.exists(progress_file):
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
                # 使用统一的时间计算逻辑
                progress_data = RedisProgressTracker._calculate_static_time_estimates(progress_data)
                return progress_data

        # 尝试备用文件位置
        backup_file = f"./data/progress_{task_id}.json"
        if os.path.exists(backup_file):
            with open(backup_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
                # 使用统一的时间计算逻辑
                progress_data = RedisProgressTracker._calculate_static_time_estimates(progress_data)
                return progress_data

        return None

    except Exception as e:
        logger.error(f"📊 [Redis进度] 获取进度失败: {task_id} - {e}")
        return None



def get_progress_by_id(task_id: str) -> Optional[Dict[str, Any]]:
    """根据任务ID获取进度（与旧实现一致，修正 cls 引用）"""
    try:
        # 检查REDIS_ENABLED环境变量
        redis_enabled = os.getenv('REDIS_ENABLED', 'false').lower() == 'true'

        # 如果Redis启用，先尝试Redis
        if redis_enabled:
            try:
                import redis

                # 从环境变量获取Redis配置
                redis_host = os.getenv('REDIS_HOST', 'localhost')
                redis_port = int(os.getenv('REDIS_PORT', 6379))
                redis_password = os.getenv('REDIS_PASSWORD', None)
                redis_db = int(os.getenv('REDIS_DB', 0))

                # 创建Redis连接
                if redis_password:
                    redis_client = redis.Redis(
                        host=redis_host,
                        port=redis_port,
                        password=redis_password,
                        db=redis_db,
                        decode_responses=True
                    )
                else:
                    redis_client = redis.Redis(
                        host=redis_host,
                        port=redis_port,
                        db=redis_db,
                        decode_responses=True
                    )

                key = f"progress:{task_id}"
                data = redis_client.get(key)
                if data:
                    progress_data = json.loads(data)
                    progress_data = RedisProgressTracker._calculate_static_time_estimates(progress_data)
                    return progress_data
            except Exception as e:
                logger.debug(f"📊 [Redis进度] Redis读取失败: {e}")

        # 尝试从文件读取
        progress_file = f"./data/progress/{task_id}.json"
        if os.path.exists(progress_file):
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
                progress_data = RedisProgressTracker._calculate_static_time_estimates(progress_data)
                return progress_data

        # 尝试备用文件位置
        backup_file = f"./data/progress_{task_id}.json"
        if os.path.exists(backup_file):
            with open(backup_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
                progress_data = RedisProgressTracker._calculate_static_time_estimates(progress_data)
                return progress_data

        return None

    except Exception as e:
        logger.error(f"📊 [Redis进度] 获取进度失败: {task_id} - {e}")
        return None
