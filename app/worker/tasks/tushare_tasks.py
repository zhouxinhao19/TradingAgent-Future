"""
Tushare数据同步Celery任务
"""
from celery import Celery
from celery.schedules import crontab
from app.worker.tushare_sync_service import get_tushare_sync_service
import asyncio
import logging

logger = logging.getLogger(__name__)

# 创建Celery应用
app = Celery('tushare_sync')

# 配置Celery
app.conf.update(
    broker_url='redis://localhost:6379/0',
    result_backend='redis://localhost:6379/0',
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=True,
)


@app.task(bind=True, max_retries=3)
def sync_stock_basic_info_task(self, force_update: bool = False):
    """同步股票基础信息任务"""
    try:
        async def run_sync():
            service = await get_tushare_sync_service()
            return await service.sync_stock_basic_info(force_update)
        
        result = asyncio.run(run_sync())
        logger.info(f"✅ 股票基础信息同步完成: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ 股票基础信息同步任务失败: {e}")
        raise self.retry(countdown=60, exc=e)


@app.task(bind=True, max_retries=3)
def sync_realtime_quotes_task(self):
    """同步实时行情任务"""
    try:
        async def run_sync():
            service = await get_tushare_sync_service()
            return await service.sync_realtime_quotes()
        
        result = asyncio.run(run_sync())
        logger.info(f"✅ 实时行情同步完成: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ 实时行情同步任务失败: {e}")
        raise self.retry(countdown=30, exc=e)


@app.task(bind=True, max_retries=2)
def sync_historical_data_task(self, incremental: bool = True):
    """同步历史数据任务"""
    try:
        async def run_sync():
            service = await get_tushare_sync_service()
            return await service.sync_historical_data(incremental=incremental)
        
        result = asyncio.run(run_sync())
        logger.info(f"✅ 历史数据同步完成: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ 历史数据同步任务失败: {e}")
        raise self.retry(countdown=300, exc=e)


@app.task(bind=True, max_retries=2)
def sync_financial_data_task(self):
    """同步财务数据任务"""
    try:
        async def run_sync():
            service = await get_tushare_sync_service()
            return await service.sync_financial_data()
        
        result = asyncio.run(run_sync())
        logger.info(f"✅ 财务数据同步完成: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ 财务数据同步任务失败: {e}")
        raise self.retry(countdown=300, exc=e)


@app.task(bind=True)
def get_sync_status_task(self):
    """获取同步状态任务"""
    try:
        async def run_sync():
            service = await get_tushare_sync_service()
            return await service.get_sync_status()
        
        result = asyncio.run(run_sync())
        logger.info(f"✅ 同步状态获取完成: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ 获取同步状态失败: {e}")
        return {"error": str(e)}


# 定时任务配置
app.conf.beat_schedule = {
    # 每日凌晨2点同步基础信息
    'sync-basic-info-daily': {
        'task': 'app.worker.tasks.tushare_tasks.sync_stock_basic_info_task',
        'schedule': crontab(hour=2, minute=0),
        'args': (False,)  # 不强制更新
    },
    
    # 交易时间每5分钟同步行情 (工作日9:00-15:00)
    'sync-quotes-trading-hours': {
        'task': 'app.worker.tasks.tushare_tasks.sync_realtime_quotes_task',
        'schedule': crontab(minute='*/5', hour='9-15', day_of_week='1-5'),
    },
    
    # 每日收盘后同步历史数据 (工作日16:00)
    'sync-historical-daily': {
        'task': 'app.worker.tasks.tushare_tasks.sync_historical_data_task',
        'schedule': crontab(hour=16, minute=0, day_of_week='1-5'),
        'args': (True,)  # 增量同步
    },
    
    # 每周日凌晨3点同步财务数据
    'sync-financial-weekly': {
        'task': 'app.worker.tasks.tushare_tasks.sync_financial_data_task',
        'schedule': crontab(hour=3, minute=0, day_of_week=0),
    },
    
    # 每小时检查同步状态
    'check-sync-status-hourly': {
        'task': 'app.worker.tasks.tushare_tasks.get_sync_status_task',
        'schedule': crontab(minute=0),
    },
}

# 启动beat调度器
app.conf.beat_scheduler = 'django_celery_beat.schedulers:DatabaseScheduler'
