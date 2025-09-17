"""
Base classes and shared typing for data source adapters
"""
from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd


class DataSourceAdapter(ABC):
    """数据源适配器基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """数据源名称"""
        raise NotImplementedError

    @property
    @abstractmethod
    def priority(self) -> int:
        """数据源优先级（数字越小优先级越高）"""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """检查数据源是否可用"""
        raise NotImplementedError

    @abstractmethod
    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """获取股票列表"""
        raise NotImplementedError

    @abstractmethod
    def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """获取每日基础财务数据"""
        raise NotImplementedError

    @abstractmethod
    def find_latest_trade_date(self) -> Optional[str]:
        """查找最新交易日期"""
        raise NotImplementedError

