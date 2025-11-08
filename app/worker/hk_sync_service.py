#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
港股数据同步服务（支持多数据源）

功能：
1. 从 yfinance 同步港股基础信息和行情
2. 从 akshare 同步港股基础信息（备用数据源）
3. 支持多数据源存储：同一股票可有多个数据源记录
4. 使用 (code, source) 联合查询进行 upsert 操作

设计说明：
- 参考A股多数据源同步服务设计
- 每个数据源独立同步任务
- 批量更新操作提高性能
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Optional
from pymongo import UpdateOne

# 导入港股数据提供器
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.dataflows.providers.hk.hk_stock import HKStockProvider
from tradingagents.dataflows.providers.hk.improved_hk import ImprovedHKStockProvider

logger = logging.getLogger("worker")


class HKSyncService:
    """港股数据同步服务（支持多数据源）"""
    
    def __init__(self, db):
        self.db = db
        
        # 数据提供器映射
        self.providers = {
            "yfinance": HKStockProvider(),
            "akshare": ImprovedHKStockProvider(),
        }
        
        # 港股列表（主要港股标的）
        self.hk_stock_list = [
            "00700",  # 腾讯控股
            "09988",  # 阿里巴巴
            "03690",  # 美团
            "01810",  # 小米集团
            "00941",  # 中国移动
            "00762",  # 中国联通
            "00728",  # 中国电信
            "00939",  # 建设银行
            "01398",  # 工商银行
            "03988",  # 中国银行
            "00005",  # 汇丰控股
            "01299",  # 友邦保险
            "02318",  # 中国平安
            "02628",  # 中国人寿
            "00857",  # 中国石油
            "00386",  # 中国石化
            "01211",  # 比亚迪
            "02015",  # 理想汽车
            "09868",  # 小鹏汽车
            "09866",  # 蔚来汽车
        ]
    
    async def sync_basic_info_from_source(
        self, 
        source: str,
        force_update: bool = False
    ) -> Dict[str, int]:
        """
        从指定数据源同步港股基础信息
        
        Args:
            source: 数据源名称 (yfinance/akshare)
            force_update: 是否强制更新
        
        Returns:
            Dict: 同步统计信息 {updated: int, inserted: int, failed: int}
        """
        provider = self.providers.get(source)
        if not provider:
            logger.error(f"❌ 不支持的数据源: {source}")
            return {"updated": 0, "inserted": 0, "failed": 0}
        
        logger.info(f"🇭🇰 开始同步港股基础信息 (数据源: {source})")
        logger.info(f"📊 待同步股票数量: {len(self.hk_stock_list)}")
        
        operations = []
        failed_count = 0
        
        for stock_code in self.hk_stock_list:
            try:
                # 从数据源获取数据
                stock_info = provider.get_stock_info(stock_code)
                
                if not stock_info or not stock_info.get('name'):
                    logger.warning(f"⚠️ 跳过无效数据: {stock_code}")
                    failed_count += 1
                    continue
                
                # 标准化数据格式
                normalized_info = self._normalize_stock_info(stock_info, source)
                normalized_info["code"] = stock_code.lstrip('0').zfill(5)  # 标准化为5位代码
                normalized_info["source"] = source
                normalized_info["updated_at"] = datetime.now()
                
                # 批量更新操作
                operations.append(
                    UpdateOne(
                        {"code": normalized_info["code"], "source": source},  # 🔥 联合查询条件
                        {"$set": normalized_info},
                        upsert=True
                    )
                )
                
                logger.debug(f"✅ 准备同步: {stock_code} ({stock_info.get('name')}) from {source}")
                
            except Exception as e:
                logger.error(f"❌ 同步失败: {stock_code} from {source}: {e}")
                failed_count += 1
        
        # 执行批量操作
        result = {"updated": 0, "inserted": 0, "failed": failed_count}
        
        if operations:
            try:
                bulk_result = await self.db.stock_basic_info_hk.bulk_write(operations)
                result["updated"] = bulk_result.modified_count
                result["inserted"] = bulk_result.upserted_count
                
                logger.info(
                    f"✅ 港股基础信息同步完成 ({source}): "
                    f"更新 {result['updated']} 条, "
                    f"插入 {result['inserted']} 条, "
                    f"失败 {result['failed']} 条"
                )
            except Exception as e:
                logger.error(f"❌ 批量写入失败: {e}")
                result["failed"] += len(operations)
        
        return result
    
    def _normalize_stock_info(self, stock_info: Dict, source: str) -> Dict:
        """
        标准化股票信息格式
        
        Args:
            stock_info: 原始股票信息
            source: 数据源
        
        Returns:
            Dict: 标准化后的股票信息
        """
        # 提取通用字段
        normalized = {
            "name": stock_info.get("name", ""),
            "name_en": stock_info.get("name_en", ""),
            "currency": stock_info.get("currency", "HKD"),
            "exchange": stock_info.get("exchange", "HKG"),
            "market": "香港交易所",
            "area": "香港",
        }
        
        # 可选字段
        if "market_cap" in stock_info and stock_info["market_cap"]:
            # 转换为亿港币
            normalized["total_mv"] = stock_info["market_cap"] / 100000000
        
        if "sector" in stock_info:
            normalized["sector"] = stock_info["sector"]
        
        if "industry" in stock_info:
            normalized["industry"] = stock_info["industry"]
        
        return normalized
    
    async def sync_quotes_from_source(
        self,
        source: str = "yfinance"
    ) -> Dict[str, int]:
        """
        从指定数据源同步港股实时行情
        
        Args:
            source: 数据源名称 (默认 yfinance)
        
        Returns:
            Dict: 同步统计信息
        """
        provider = self.providers.get(source)
        if not provider:
            logger.error(f"❌ 不支持的数据源: {source}")
            return {"updated": 0, "inserted": 0, "failed": 0}
        
        logger.info(f"🇭🇰 开始同步港股实时行情 (数据源: {source})")
        
        operations = []
        failed_count = 0
        
        for stock_code in self.hk_stock_list:
            try:
                # 获取实时价格
                quote = provider.get_real_time_price(stock_code)
                
                if not quote or not quote.get('price'):
                    logger.warning(f"⚠️ 跳过无效行情: {stock_code}")
                    failed_count += 1
                    continue
                
                # 标准化行情数据
                normalized_quote = {
                    "code": stock_code.lstrip('0').zfill(5),
                    "close": float(quote.get('price', 0)),
                    "open": float(quote.get('open', 0)),
                    "high": float(quote.get('high', 0)),
                    "low": float(quote.get('low', 0)),
                    "volume": int(quote.get('volume', 0)),
                    "currency": "HKD",
                    "updated_at": datetime.now()
                }
                
                # 计算涨跌幅
                if normalized_quote["open"] > 0:
                    pct_chg = ((normalized_quote["close"] - normalized_quote["open"]) / normalized_quote["open"]) * 100
                    normalized_quote["pct_chg"] = round(pct_chg, 2)
                
                operations.append(
                    UpdateOne(
                        {"code": normalized_quote["code"]},
                        {"$set": normalized_quote},
                        upsert=True
                    )
                )
                
                logger.debug(f"✅ 准备同步行情: {stock_code} (价格: {normalized_quote['close']} HKD)")
                
            except Exception as e:
                logger.error(f"❌ 同步行情失败: {stock_code}: {e}")
                failed_count += 1
        
        # 执行批量操作
        result = {"updated": 0, "inserted": 0, "failed": failed_count}
        
        if operations:
            try:
                bulk_result = await self.db.market_quotes_hk.bulk_write(operations)
                result["updated"] = bulk_result.modified_count
                result["inserted"] = bulk_result.upserted_count
                
                logger.info(
                    f"✅ 港股行情同步完成: "
                    f"更新 {result['updated']} 条, "
                    f"插入 {result['inserted']} 条, "
                    f"失败 {result['failed']} 条"
                )
            except Exception as e:
                logger.error(f"❌ 批量写入失败: {e}")
                result["failed"] += len(operations)
        
        return result


# ==================== 同步任务函数 ====================

async def run_hk_yfinance_basic_info_sync(force_update: bool = False):
    """港股基础信息同步（yfinance）"""
    from app.core.database import get_mongo_db

    logger.info("🚀 开始执行港股基础信息同步任务 (yfinance)")

    try:
        db = get_mongo_db()
        service = HKSyncService(db)
        result = await service.sync_basic_info_from_source("yfinance", force_update)

        logger.info(f"✅ 港股基础信息同步任务完成 (yfinance): {result}")
        return result

    except Exception as e:
        logger.error(f"❌ 港股基础信息同步任务失败 (yfinance): {e}")
        raise


async def run_hk_akshare_basic_info_sync(force_update: bool = False):
    """港股基础信息同步（AKShare）"""
    from app.core.database import get_mongo_db

    logger.info("🚀 开始执行港股基础信息同步任务 (AKShare)")

    try:
        db = get_mongo_db()
        service = HKSyncService(db)
        result = await service.sync_basic_info_from_source("akshare", force_update)

        logger.info(f"✅ 港股基础信息同步任务完成 (AKShare): {result}")
        return result

    except Exception as e:
        logger.error(f"❌ 港股基础信息同步任务失败 (AKShare): {e}")
        raise


async def run_hk_yfinance_quotes_sync():
    """港股实时行情同步（yfinance）"""
    from app.core.database import get_mongo_db

    logger.info("🚀 开始执行港股实时行情同步任务 (yfinance)")

    try:
        db = get_mongo_db()
        service = HKSyncService(db)
        result = await service.sync_quotes_from_source("yfinance")

        logger.info(f"✅ 港股实时行情同步任务完成: {result}")
        return result

    except Exception as e:
        logger.error(f"❌ 港股实时行情同步任务失败: {e}")
        raise

