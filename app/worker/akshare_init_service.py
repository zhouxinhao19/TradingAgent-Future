"""
AKShare数据初始化服务
用于首次部署时的完整数据初始化，包括基础数据、历史数据、财务数据等
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from app.core.database import get_mongo_db
from app.worker.akshare_sync_service import get_akshare_sync_service

logger = logging.getLogger(__name__)


@dataclass
class AKShareInitializationStats:
    """AKShare初始化统计信息"""
    started_at: datetime
    finished_at: Optional[datetime] = None
    total_steps: int = 0
    completed_steps: int = 0
    current_step: str = ""
    basic_info_count: int = 0
    historical_records: int = 0
    financial_records: int = 0
    quotes_count: int = 0
    errors: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class AKShareInitService:
    """
    AKShare数据初始化服务
    
    负责首次部署时的完整数据初始化：
    1. 检查数据库状态
    2. 初始化股票基础信息
    3. 同步历史数据（可配置时间范围）
    4. 同步财务数据
    5. 同步最新行情数据
    6. 验证数据完整性
    """
    
    def __init__(self):
        self.db = None
        self.sync_service = None
        self.stats = None
    
    async def initialize(self):
        """初始化服务"""
        self.db = get_mongo_db()
        self.sync_service = await get_akshare_sync_service()
        logger.info("✅ AKShare初始化服务准备完成")
    
    async def run_full_initialization(
        self,
        historical_days: int = 365,
        skip_if_exists: bool = True,
        batch_size: int = 100
    ) -> Dict[str, Any]:
        """
        运行完整的数据初始化
        
        Args:
            historical_days: 历史数据天数（默认1年）
            skip_if_exists: 如果数据已存在是否跳过
            batch_size: 批处理大小
            
        Returns:
            初始化结果统计
        """
        logger.info("🚀 开始AKShare数据完整初始化...")
        
        self.stats = AKShareInitializationStats(
            started_at=datetime.utcnow(),
            total_steps=6
        )
        
        try:
            # 步骤1: 检查数据库状态
            await self._step_check_database_status(skip_if_exists)
            
            # 步骤2: 初始化股票基础信息
            await self._step_initialize_basic_info()
            
            # 步骤3: 同步历史数据
            await self._step_initialize_historical_data(historical_days)
            
            # 步骤4: 同步财务数据
            await self._step_initialize_financial_data()
            
            # 步骤5: 同步最新行情
            await self._step_initialize_quotes()
            
            # 步骤6: 验证数据完整性
            await self._step_verify_data_integrity()
            
            self.stats.finished_at = datetime.utcnow()
            duration = (self.stats.finished_at - self.stats.started_at).total_seconds()
            
            logger.info(f"🎉 AKShare数据初始化完成！耗时: {duration:.2f}秒")
            
            return self._get_initialization_summary()
            
        except Exception as e:
            logger.error(f"❌ AKShare数据初始化失败: {e}")
            self.stats.errors.append({
                "step": self.stats.current_step,
                "error": str(e),
                "timestamp": datetime.utcnow()
            })
            return self._get_initialization_summary()
    
    async def _step_check_database_status(self, skip_if_exists: bool):
        """步骤1: 检查数据库状态"""
        self.stats.current_step = "检查数据库状态"
        logger.info(f"📊 {self.stats.current_step}...")
        
        # 检查各集合的数据量
        basic_count = await self.db.stock_basic_info.count_documents({})
        quotes_count = await self.db.market_quotes.count_documents({})
        
        logger.info(f"  当前数据状态:")
        logger.info(f"    股票基础信息: {basic_count}条")
        logger.info(f"    行情数据: {quotes_count}条")
        
        if skip_if_exists and basic_count > 0:
            logger.info("⚠️ 检测到已有数据，跳过初始化（可通过skip_if_exists=False强制初始化）")
            raise Exception("数据已存在，跳过初始化")
        
        self.stats.completed_steps += 1
        logger.info(f"✅ {self.stats.current_step}完成")
    
    async def _step_initialize_basic_info(self):
        """步骤2: 初始化股票基础信息"""
        self.stats.current_step = "初始化股票基础信息"
        logger.info(f"📋 {self.stats.current_step}...")
        
        # 强制更新所有基础信息
        result = await self.sync_service.sync_stock_basic_info(force_update=True)
        
        if result:
            self.stats.basic_info_count = result.get("success_count", 0)
            logger.info(f"✅ 基础信息初始化完成: {self.stats.basic_info_count}只股票")
        else:
            raise Exception("基础信息初始化失败")
        
        self.stats.completed_steps += 1
    
    async def _step_initialize_historical_data(self, historical_days: int):
        """步骤3: 同步历史数据"""
        self.stats.current_step = f"同步历史数据({historical_days}天)"
        logger.info(f"📊 {self.stats.current_step}...")
        
        # 计算日期范围
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=historical_days)).strftime('%Y-%m-%d')
        
        logger.info(f"  历史数据范围: {start_date} 到 {end_date}")
        
        # 同步历史数据
        result = await self.sync_service.sync_historical_data(
            start_date=start_date,
            end_date=end_date,
            incremental=False  # 全量同步
        )
        
        if result:
            self.stats.historical_records = result.get("total_records", 0)
            logger.info(f"✅ 历史数据初始化完成: {self.stats.historical_records}条记录")
        else:
            logger.warning("⚠️ 历史数据初始化部分失败，继续后续步骤")
        
        self.stats.completed_steps += 1
    
    async def _step_initialize_financial_data(self):
        """步骤4: 同步财务数据"""
        self.stats.current_step = "同步财务数据"
        logger.info(f"💰 {self.stats.current_step}...")
        
        try:
            result = await self.sync_service.sync_financial_data()
            
            if result:
                self.stats.financial_records = result.get("success_count", 0)
                logger.info(f"✅ 财务数据初始化完成: {self.stats.financial_records}条记录")
            else:
                logger.warning("⚠️ 财务数据初始化失败")
        except Exception as e:
            logger.warning(f"⚠️ 财务数据初始化失败: {e}（继续后续步骤）")
        
        self.stats.completed_steps += 1
    
    async def _step_initialize_quotes(self):
        """步骤5: 同步最新行情"""
        self.stats.current_step = "同步最新行情"
        logger.info(f"📈 {self.stats.current_step}...")
        
        try:
            result = await self.sync_service.sync_realtime_quotes()
            
            if result:
                self.stats.quotes_count = result.get("success_count", 0)
                logger.info(f"✅ 最新行情初始化完成: {self.stats.quotes_count}只股票")
            else:
                logger.warning("⚠️ 最新行情初始化失败")
        except Exception as e:
            logger.warning(f"⚠️ 最新行情初始化失败: {e}（继续后续步骤）")
        
        self.stats.completed_steps += 1
    
    async def _step_verify_data_integrity(self):
        """步骤6: 验证数据完整性"""
        self.stats.current_step = "验证数据完整性"
        logger.info(f"🔍 {self.stats.current_step}...")
        
        # 检查最终数据状态
        basic_count = await self.db.stock_basic_info.count_documents({})
        quotes_count = await self.db.market_quotes.count_documents({})
        
        # 检查数据质量
        extended_count = await self.db.stock_basic_info.count_documents({
            "full_symbol": {"$exists": True},
            "market_info": {"$exists": True}
        })
        
        logger.info(f"  数据完整性验证:")
        logger.info(f"    股票基础信息: {basic_count}条")
        logger.info(f"    扩展字段覆盖: {extended_count}条 ({extended_count/basic_count*100:.1f}%)")
        logger.info(f"    行情数据: {quotes_count}条")
        
        if basic_count == 0:
            raise Exception("数据初始化失败：无基础数据")
        
        if extended_count / basic_count < 0.9:  # 90%以上应该有扩展字段
            logger.warning("⚠️ 扩展字段覆盖率较低，可能存在数据质量问题")
        
        self.stats.completed_steps += 1
        logger.info(f"✅ {self.stats.current_step}完成")
    
    def _get_initialization_summary(self) -> Dict[str, Any]:
        """获取初始化总结"""
        duration = 0
        if self.stats.finished_at:
            duration = (self.stats.finished_at - self.stats.started_at).total_seconds()
        
        return {
            "success": self.stats.completed_steps == self.stats.total_steps,
            "started_at": self.stats.started_at,
            "finished_at": self.stats.finished_at,
            "duration": duration,
            "completed_steps": self.stats.completed_steps,
            "total_steps": self.stats.total_steps,
            "progress": f"{self.stats.completed_steps}/{self.stats.total_steps}",
            "data_summary": {
                "basic_info_count": self.stats.basic_info_count,
                "historical_records": self.stats.historical_records,
                "financial_records": self.stats.financial_records,
                "quotes_count": self.stats.quotes_count
            },
            "errors": self.stats.errors,
            "current_step": self.stats.current_step
        }


# 全局初始化服务实例
_akshare_init_service = None

async def get_akshare_init_service() -> AKShareInitService:
    """获取AKShare初始化服务实例"""
    global _akshare_init_service
    if _akshare_init_service is None:
        _akshare_init_service = AKShareInitService()
        await _akshare_init_service.initialize()
    return _akshare_init_service


# APScheduler兼容的初始化任务函数
async def run_akshare_full_initialization(
    historical_days: int = 365,
    skip_if_exists: bool = True
):
    """APScheduler任务：运行完整的AKShare数据初始化"""
    try:
        service = await get_akshare_init_service()
        result = await service.run_full_initialization(
            historical_days=historical_days,
            skip_if_exists=skip_if_exists
        )
        logger.info(f"✅ AKShare完整初始化完成: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ AKShare完整初始化失败: {e}")
        raise
