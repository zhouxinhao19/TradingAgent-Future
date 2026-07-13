"""
大宗商品数据提供器基类
镜像 BaseStockDataProvider 设计,便于 Phase 5 整体替换
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, date
import logging
import pandas as pd


class BaseCommodityDataProvider(ABC):
    """大宗商品数据提供器基类"""

    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        self.connected = False
        self.logger = logging.getLogger(f"{__name__}.{provider_name}")

    @abstractmethod
    async def connect(self) -> bool:
        """连接到数据源"""
        pass

    async def disconnect(self):
        """断开连接"""
        self.connected = False
        self.logger.info(f"✅ {self.provider_name} 连接已断开")

    def is_available(self) -> bool:
        """检查数据源是否可用"""
        return self.connected

    @abstractmethod
    async def get_commodity_basic_info(
        self, full_symbol: str = None
    ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """
        获取大宗商品基础信息

        Args:
            full_symbol: 完整代码,如 CU2501.SHF。空则返回列表

        Returns:
            单个商品信息字典或商品列表
        """
        pass

    @abstractmethod
    async def get_commodity_quotes(self, full_symbol: str) -> Optional[Dict[str, Any]]:
        """获取大宗商品实时行情"""
        pass

    @abstractmethod
    async def get_historical_data(
        self,
        full_symbol: str,
        start_date: Union[str, date],
        end_date: Union[str, date] = None,
    ) -> Optional[pd.DataFrame]:
        """获取历史 K 线数据"""
        pass

    # ----- 标准化方法(子类可重写) -----

    def standardize_basic_info(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化商品基础信息"""
        return {
            "code": raw_data.get("code", ""),
            "symbol": raw_data.get("symbol", ""),
            "full_symbol": raw_data.get("full_symbol", ""),
            "name": raw_data.get("name", ""),
            "exchange": raw_data.get("exchange", ""),
            "category": raw_data.get("category", "unknown"),
            "underlying": raw_data.get("underlying", ""),
            "currency": raw_data.get("currency", "CNY"),
            "data_source": self.provider_name.lower(),
            "data_version": 1,
            "updated_at": datetime.utcnow(),
        }

    def standardize_quotes(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化实时行情"""
        return {
            "full_symbol": raw_data.get("full_symbol", ""),
            "close": self._to_float(raw_data.get("close")),
            "current_price": self._to_float(raw_data.get("current_price", raw_data.get("close"))),
            "open": self._to_float(raw_data.get("open")),
            "high": self._to_float(raw_data.get("high")),
            "low": self._to_float(raw_data.get("low")),
            "pre_close": self._to_float(raw_data.get("pre_close")),
            "settlement_price": self._to_float(raw_data.get("settlement_price")),
            "change": self._to_float(raw_data.get("change")),
            "pct_chg": self._to_float(raw_data.get("pct_chg")),
            "volume": self._to_float(raw_data.get("volume")),
            "open_interest": self._to_float(raw_data.get("open_interest")),
            "trade_date": raw_data.get("trade_date", ""),
            "data_source": self.provider_name.lower(),
            "updated_at": datetime.utcnow(),
        }

    def _to_float(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _format_date(self, value: Any) -> Optional[str]:
        if not value:
            return None
        s = str(value)
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        if isinstance(value, (date, datetime)):
            return value.strftime("%Y-%m-%d")
        return s

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    def __repr__(self):
        return f"<{self.__class__.__name__}(name='{self.provider_name}', connected={self.connected})>"
