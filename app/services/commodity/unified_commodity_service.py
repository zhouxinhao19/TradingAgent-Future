"""
大宗商品统一服务
- 协调多个 provider(akshare / yfinance)
- Phase 1:只接入 akshare_futures,实时调用
- Phase 2+ 接入 MongoDB 缓存
"""
import asyncio
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


class UnifiedCommodityService:
    """大宗商品统一服务(单例)"""

    def __init__(self):
        self._providers = {}
        self._initialized = False

    async def initialize(self) -> None:
        """初始化 provider(懒加载)"""
        if self._initialized:
            return
        try:
            from tradingagents.dataflows.providers.commodity.akshare_futures import (
                AkshareFuturesProvider,
            )
            ak_provider = AkshareFuturesProvider()
            await ak_provider.connect()
            self._providers["akshare_futures"] = ak_provider
            logger.info("✅ UnifiedCommodityService 初始化完成(akshare_futures)")
        except Exception as e:
            logger.error(f"❌ UnifiedCommodityService 初始化失败: {e}")
        self._initialized = True

    async def get_basic_info(self, full_symbol: str) -> Optional[Dict[str, Any]]:
        """获取商品基础信息"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        return await provider.get_commodity_basic_info(full_symbol)

    async def get_quotes(self, full_symbol: str) -> Optional[Dict[str, Any]]:
        """获取实时行情"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        return await provider.get_commodity_quotes(full_symbol)

    async def get_historical(
        self,
        full_symbol: str,
        start_date: str,
        end_date: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        获取历史 K 线(返回 dict 而非 DataFrame,便于 JSON 序列化)

        返回结构:
        {
          "full_symbol": "...",
          "rows": [
            {"date": "2024-01-16", "open": 67350.0, "high": ..., "low": ..., "close": ..., "volume": 7, "open_interest": 5, "settlement": 67260.0},
            ...
          ],
          "count": 242,
          "start_date": "2024-01-16",
          "end_date": "2025-01-15"
        }
        """
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None

        df = await provider.get_historical_data(full_symbol, start_date, end_date)
        if df is None or df.empty:
            return {"full_symbol": full_symbol, "rows": [], "count": 0, "start_date": start_date, "end_date": end_date or ""}

        rows = []
        for _, r in df.iterrows():
            rows.append({
                "date": str(r.get("日期", "")),
                "open": float(r.get("开盘价", 0) or 0),
                "high": float(r.get("最高价", 0) or 0),
                "low": float(r.get("最低价", 0) or 0),
                "close": float(r.get("收盘价", 0) or 0),
                "volume": int(r.get("成交量", 0) or 0),
                "open_interest": int(r.get("持仓量", 0) or 0),
                "settlement": float(r.get("动态结算价", 0) or 0),
            })

        return {
            "full_symbol": full_symbol,
            "rows": rows,
            "count": len(rows),
            "start_date": str(df["日期"].min()) if not df.empty else start_date,
            "end_date": str(df["日期"].max()) if not df.empty else (end_date or ""),
        }

    async def get_categories(self) -> List[Dict[str, Any]]:
        """返回商品品类列表(用于前端筛选)"""
        return [
            {"code": "precious", "name": "贵金属"},
            {"code": "metal", "name": "有色金属"},
            {"code": "energy", "name": "能源"},
            {"code": "chemical", "name": "化工"},
            {"code": "agricultural", "name": "农产品"},
            {"code": "financial", "name": "金融"},
        ]

    async def get_exchanges(self) -> List[Dict[str, Any]]:
        """返回交易所列表"""
        return [
            {"code": "SHF", "name": "上海期货交易所"},
            {"code": "DCE", "name": "大连商品交易所"},
            {"code": "CZC", "name": "郑州商品交易所"},
            {"code": "INE", "name": "上海国际能源交易中心"},
            {"code": "GFEX", "name": "广州期货交易所"},
        ]


# 全局单例
service = UnifiedCommodityService()
