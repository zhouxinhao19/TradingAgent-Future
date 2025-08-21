"""
Redis进度跟踪器
基于web目录的实现，支持Redis和文件双重存储
"""

import json
import os
import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger("app.services.redis_progress_tracker")


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
    
    def _generate_dynamic_steps(self) -> List[AnalysisStep]:
        """根据分析师数量和研究深度动态生成分析步骤"""
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

    def update_progress(self, message: str, step: Optional[int] = None):
        """更新进度状态"""
        current_time = time.time()
        elapsed_time = current_time - self.progress_data['start_time']

        # 自动检测步骤
        if step is None:
            step = self._detect_current_step(message)

        # 更新当前步骤
        if step is not None and 0 <= step < len(self.analysis_steps):
            # 标记之前的步骤为完成
            for i in range(step):
                if self.analysis_steps[i].status in ["pending", "current"]:
                    self.analysis_steps[i].status = "completed"
                    if self.analysis_steps[i].end_time is None:
                        self.analysis_steps[i].end_time = current_time

            # 清除其他步骤的current状态
            for i in range(len(self.analysis_steps)):
                if i != step and self.analysis_steps[i].status == "current":
                    self.analysis_steps[i].status = "completed"
                    if self.analysis_steps[i].end_time is None:
                        self.analysis_steps[i].end_time = current_time

            # 设置当前步骤
            if self.analysis_steps[step].status == "pending":
                self.analysis_steps[step].status = "current"
                self.analysis_steps[step].start_time = current_time

            self.progress_data['current_step'] = step
            self.progress_data['current_step_name'] = self.analysis_steps[step].name
            self.progress_data['current_step_description'] = self.analysis_steps[step].description

        # 计算进度百分比 - 使用固定的基础时间估算
        completed_weight = sum(step.weight for step in self.analysis_steps if step.status == "completed")
        current_weight = 0

        # 找到当前正在执行的步骤
        current_step_obj = None
        for step_obj in self.analysis_steps:
            if step_obj.status == "current":
                current_step_obj = step_obj
                break

        if current_step_obj and current_step_obj.start_time:
            # 根据当前步骤的执行时间估算部分完成度
            step_elapsed = current_time - current_step_obj.start_time
            estimated_step_time = self._estimate_step_time(current_step_obj)
            step_progress = min(step_elapsed / estimated_step_time, 0.95) if estimated_step_time > 0 else 0
            current_weight = current_step_obj.weight * step_progress

        self.progress_data['progress_percentage'] = (completed_weight + current_weight) * 100

        # 使用统一的时间计算逻辑
        elapsed_time, remaining_time, estimated_total_time = self._calculate_time_estimates()

        # 更新时间信息
        self.progress_data['elapsed_time'] = elapsed_time
        self.progress_data['remaining_time'] = remaining_time
        self.progress_data['estimated_total_time'] = estimated_total_time
        self.progress_data['last_message'] = message
        self.progress_data['last_update'] = current_time

        # 更新步骤数据
        self.progress_data['steps'] = [asdict(step) for step in self.analysis_steps]

        # 保存进度
        self._save_progress()

        logger.info(f"📊 [Redis进度] 更新: {self.task_id} -> {message} ({self.progress_data['progress_percentage']:.1f}%)")

    def _detect_current_step(self, message: str) -> Optional[int]:
        """根据消息内容检测当前步骤"""
        message_lower = message.lower()

        # 定义消息模式到步骤的映射
        patterns = {
            "准备阶段": 0,
            "环境检查": 1,
            "成本估算": 2,
            "参数设置": 3,
            "启动引擎": 4,
            "市场分析": self._find_step_by_name("📊 市场分析师"),
            "基本面分析": self._find_step_by_name("💼 基本面分析师"),
            "新闻分析": self._find_step_by_name("📰 新闻分析师"),
            "社交媒体": self._find_step_by_name("💬 社交媒体分析师"),
            "看涨研究": self._find_step_by_name("🐂 看涨研究员"),
            "看跌研究": self._find_step_by_name("🐻 看跌研究员"),
            "研究辩论": self._find_step_by_pattern("🎯 研究辩论"),
            "研究经理": self._find_step_by_name("👔 研究经理"),
            "交易员": self._find_step_by_name("💼 交易员决策"),
            "激进风险": self._find_step_by_name("🔥 激进风险评估"),
            "保守风险": self._find_step_by_name("🛡️ 保守风险评估"),
            "中性风险": self._find_step_by_name("⚖️ 中性风险评估"),
            "风险经理": self._find_step_by_name("🎯 风险经理"),
            "信号处理": self._find_step_by_name("📡 信号处理"),
            "生成报告": self._find_step_by_name("📊 生成报告"),
        }

        for pattern, step_index in patterns.items():
            if pattern in message_lower and step_index is not None:
                return step_index

        return None

    def _find_step_by_name(self, name: str) -> Optional[int]:
        """根据步骤名称查找步骤索引"""
        for i, step in enumerate(self.analysis_steps):
            if step.name == name:
                return i
        return None

    def _find_step_by_pattern(self, pattern: str) -> Optional[int]:
        """根据模式查找步骤索引"""
        for i, step in enumerate(self.analysis_steps):
            if pattern in step.name:
                return i
        return None

    def _estimate_step_time(self, step: AnalysisStep) -> float:
        """估算步骤执行时间（秒）"""
        # 基于步骤权重和总体预估时间
        total_time = self._get_base_total_time()
        return total_time * step.weight

    def _get_base_total_time(self) -> float:
        """根据分析师数量、研究深度、模型类型预估总时长（秒）"""
        # 基础时间（秒）- 环境准备、配置等
        base_time = 60

        # 将研究深度字符串转换为数字
        depth_map = {"快速": 1, "标准": 2, "深度": 3}
        research_depth_num = depth_map.get(self.research_depth, 2)

        # 每个分析师的实际耗时（基于真实测试数据）
        analyst_base_time = {
            1: 180,  # 快速分析：每个分析师约3分钟
            2: 360,  # 标准分析：每个分析师约6分钟
            3: 600   # 深度分析：每个分析师约10分钟
        }.get(research_depth_num, 360)

        analyst_time = len(self.analysts) * analyst_base_time

        # 模型速度影响（基于实际测试）
        model_multiplier = {
            'dashscope': 1.0,  # 阿里百炼速度适中
            'deepseek': 0.7,   # DeepSeek较快
            'google': 1.3      # Google较慢
        }.get(self.llm_provider, 1.0)

        # 研究深度额外影响（工具调用复杂度）
        depth_multiplier = {
            1: 0.8,  # 快速分析，较少工具调用
            2: 1.0,  # 标准分析，标准工具调用
            3: 1.3   # 深度分析，更多工具调用和推理
        }.get(research_depth_num, 1.0)

        total_time = (base_time + analyst_time) * model_multiplier * depth_multiplier
        return total_time

    def _calculate_time_estimates(self) -> tuple[float, float, float]:
        """统一的时间计算逻辑，返回 (已用时间, 剩余时间, 预计总时长)"""
        # 计算实时已用时间
        current_time = time.time()
        start_time = self.progress_data.get('start_time', current_time)
        elapsed_time = current_time - start_time

        # 获取当前进度
        progress_percentage = self.progress_data.get('progress_percentage', 0)
        progress = progress_percentage / 100

        # 获取基础预估时间
        base_estimated_total = self._get_base_total_time()

        # 计算预计总时长（采用web目录的逻辑）
        if progress_percentage >= 100:
            # 任务已完成，总时长就是已用时间
            estimated_total_time = elapsed_time
            remaining_time = 0
        else:
            # 优先使用基础预估时间
            estimated_total_time = base_estimated_total
            remaining_time = max(0, estimated_total_time - elapsed_time)

            # 如果已经超过预估时间，根据当前进度动态调整
            if remaining_time <= 0 and progress > 0:
                estimated_total_time = elapsed_time / progress
                remaining_time = max(0, estimated_total_time - elapsed_time)

        return elapsed_time, remaining_time, estimated_total_time

    @staticmethod
    def _calculate_static_time_estimates(progress_data: dict) -> dict:
        """静态方法：为已有的进度数据计算时间估算"""
        if 'start_time' not in progress_data or not progress_data['start_time']:
            return progress_data

        # 计算实时已用时间
        current_time = time.time()
        elapsed_time = current_time - progress_data['start_time']
        progress_data['elapsed_time'] = elapsed_time

        # 获取当前进度
        progress_percentage = progress_data.get('progress_percentage', 0)

        # 计算预计总时长和剩余时间（采用web目录的逻辑）
        progress = progress_percentage / 100

        if progress_percentage >= 100:
            # 任务已完成
            estimated_total_time = elapsed_time
            remaining_time = 0
        else:
            # 优先使用原有的预估时间或默认值
            estimated_total_time = progress_data.get('estimated_total_time', 300)  # 默认5分钟
            remaining_time = max(0, estimated_total_time - elapsed_time)

            # 如果已经超过预估时间，根据当前进度动态调整
            if remaining_time <= 0 and progress > 0:
                estimated_total_time = elapsed_time / progress
                remaining_time = max(0, estimated_total_time - elapsed_time)

        progress_data['estimated_total_time'] = estimated_total_time
        progress_data['remaining_time'] = remaining_time

        return progress_data

    def _save_progress(self):
        """保存进度到Redis或文件"""
        try:
            if self.use_redis:
                # 保存到Redis（安全序列化）
                key = f"progress:{self.task_id}"
                safe_data = safe_serialize(self.progress_data)
                data_json = json.dumps(safe_data, ensure_ascii=False)
                self.redis_client.setex(key, 3600, data_json)  # 1小时过期

                logger.debug(f"📊 [Redis写入] {self.task_id} -> {self.progress_data['progress_percentage']:.1f}%")
            else:
                # 保存到文件（安全序列化）
                progress_dir = "./data/progress"
                os.makedirs(progress_dir, exist_ok=True)
                progress_file = os.path.join(progress_dir, f"{self.task_id}.json")

                safe_data = safe_serialize(self.progress_data)
                with open(progress_file, 'w', encoding='utf-8') as f:
                    json.dump(safe_data, f, ensure_ascii=False, indent=2)

                logger.debug(f"📊 [文件写入] {self.task_id} -> {self.progress_data['progress_percentage']:.1f}%")

        except Exception as e:
            logger.error(f"📊 [Redis进度] 保存失败: {e}")
            # 尝试备用存储方式
            try:
                if self.use_redis:
                    # Redis失败，尝试文件存储
                    logger.warning(f"📊 [Redis进度] Redis保存失败，尝试文件存储")
                    backup_file = f"./data/progress_{self.task_id}.json"
                    os.makedirs(os.path.dirname(backup_file), exist_ok=True)
                    safe_data = safe_serialize(self.progress_data)
                    with open(backup_file, 'w', encoding='utf-8') as f:
                        json.dump(safe_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"📊 [备用存储] 文件保存成功: {backup_file}")
            except Exception as backup_error:
                logger.error(f"📊 [Redis进度] 备用存储也失败: {backup_error}")

    def mark_completed(self, message: str = "分析完成"):
        """标记分析完成"""
        # 标记所有步骤为完成
        current_time = time.time()
        for step in self.analysis_steps:
            if step.status != "completed":
                step.status = "completed"
                if step.end_time is None:
                    step.end_time = current_time

        self.progress_data['status'] = 'completed'
        self.progress_data['progress_percentage'] = 100.0
        self.progress_data['current_step'] = len(self.analysis_steps) - 1
        self.progress_data['current_step_name'] = "分析完成"
        self.progress_data['current_step_description'] = "所有分析步骤已完成"
        self.progress_data['last_message'] = message
        self.progress_data['last_update'] = current_time
        self.progress_data['remaining_time'] = 0
        self.progress_data['steps'] = [asdict(step) for step in self.analysis_steps]

        self._save_progress()
        logger.info(f"📊 [Redis进度] 分析完成: {self.task_id}")

    def mark_failed(self, error_message: str):
        """标记分析失败"""
        current_time = time.time()

        # 标记当前步骤为失败
        if self.progress_data['current_step'] < len(self.analysis_steps):
            current_step = self.analysis_steps[self.progress_data['current_step']]
            current_step.status = "failed"
            current_step.end_time = current_time

        self.progress_data['status'] = 'failed'
        self.progress_data['last_message'] = f"分析失败: {error_message}"
        self.progress_data['last_update'] = current_time
        self.progress_data['remaining_time'] = 0
        self.progress_data['steps'] = [asdict(step) for step in self.analysis_steps]

        self._save_progress()
        logger.error(f"📊 [Redis进度] 分析失败: {self.task_id}, 错误: {error_message}")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（兼容原有接口）"""
        # 使用统一的时间计算逻辑
        elapsed_time, remaining_time, estimated_total_time = self._calculate_time_estimates()

        return {
            'progress': self.progress_data['progress_percentage'],
            'current_step': self.progress_data['current_step_name'],
            'message': self.progress_data['last_message'],
            'elapsed_time': elapsed_time,  # 使用统一计算的已用时间
            'remaining_time': remaining_time,  # 使用统一计算的剩余时间
            'estimated_total_time': estimated_total_time,  # 使用统一计算的预计总时长
            'steps': self.progress_data['steps'],
            'start_time': datetime.fromtimestamp(self.progress_data['start_time']).isoformat(),
            'last_update': datetime.fromtimestamp(self.progress_data['last_update']).isoformat()
        }


def get_progress_by_id(task_id: str) -> Optional[Dict[str, Any]]:
    """根据任务ID获取进度"""
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
                    # 使用统一的时间计算逻辑
                    progress_data = cls._calculate_static_time_estimates(progress_data)
                    return progress_data
            except Exception as e:
                logger.debug(f"📊 [Redis进度] Redis读取失败: {e}")

        # 尝试从文件读取
        progress_file = f"./data/progress/{task_id}.json"
        if os.path.exists(progress_file):
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
                # 使用统一的时间计算逻辑
                progress_data = cls._calculate_static_time_estimates(progress_data)
                return progress_data

        # 尝试备用文件位置
        backup_file = f"./data/progress_{task_id}.json"
        if os.path.exists(backup_file):
            with open(backup_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
                # 使用统一的时间计算逻辑
                progress_data = cls._calculate_static_time_estimates(progress_data)
                return progress_data

        return None

    except Exception as e:
        logger.error(f"📊 [Redis进度] 获取进度失败: {task_id} - {e}")
        return None
