"""
股票数据提供器基类
定义统一的接口规范，所有SDK适配器必须继承此基类
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, date
import pandas as pd
import logging


class BaseStockDataProvider(ABC):
    """
    股票数据提供器基类
    
    所有股票数据SDK适配器都必须继承此基类并实现抽象方法
    提供统一的接口规范，确保数据获取的一致性
    """
    
    def __init__(self, name: str = None):
        self.name = name or self.__class__.__name__
        self.logger = logging.getLogger(f"{__name__}.{self.name}")
        self.connected = False
        self.last_error = None
    
    # ==================== 连接管理 ====================
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        连接到数据源
        
        Returns:
            bool: 连接是否成功
        """
        pass
    
    async def disconnect(self):
        """断开连接"""
        self.connected = False
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.connected
    
    # ==================== 基础信息接口 ====================
    
    @abstractmethod
    async def get_stock_basic_info(self, symbol: str = None) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """
        获取股票基础信息
        
        Args:
            symbol: 股票代码，为None时获取所有股票
            
        Returns:
            Dict[str, Any] | List[Dict[str, Any]] | None: 股票基础信息
        """
        pass
    
    @abstractmethod
    async def get_stock_list(self, market: str = None) -> Optional[List[Dict[str, Any]]]:
        """
        获取股票列表
        
        Args:
            market: 市场标识 (CN/HK/US)
            
        Returns:
            List[Dict[str, Any]] | None: 股票列表
        """
        pass
    
    # ==================== 行情数据接口 ====================
    
    @abstractmethod
    async def get_stock_quotes(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取实时行情
        
        Args:
            symbol: 股票代码
            
        Returns:
            Dict[str, Any] | None: 实时行情数据
        """
        pass
    
    @abstractmethod
    async def get_historical_data(
        self, 
        symbol: str, 
        start_date: Union[str, date], 
        end_date: Union[str, date] = None,
        period: str = "daily"
    ) -> Optional[pd.DataFrame]:
        """
        获取历史数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期，默认为今天
            period: 数据周期 (daily/weekly/monthly)
            
        Returns:
            pd.DataFrame | None: 历史数据
        """
        pass
    
    # ==================== 财务数据接口 ====================
    
    async def get_financial_data(
        self, 
        symbol: str, 
        report_type: str = "annual"
    ) -> Optional[Dict[str, Any]]:
        """
        获取财务数据 (可选实现)
        
        Args:
            symbol: 股票代码
            report_type: 报告类型 (annual/quarterly)
            
        Returns:
            Dict[str, Any] | None: 财务数据
        """
        self.logger.warning(f"{self.name} 未实现财务数据接口")
        return None
    
    async def get_balance_sheet(self, symbol: str) -> Optional[pd.DataFrame]:
        """获取资产负债表 (可选实现)"""
        return None
    
    async def get_income_statement(self, symbol: str) -> Optional[pd.DataFrame]:
        """获取利润表 (可选实现)"""
        return None
    
    async def get_cashflow_statement(self, symbol: str) -> Optional[pd.DataFrame]:
        """获取现金流量表 (可选实现)"""
        return None
    
    # ==================== 新闻数据接口 ====================
    
    async def get_stock_news(
        self, 
        symbol: str = None, 
        limit: int = 10
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取股票新闻 (可选实现)
        
        Args:
            symbol: 股票代码，为None时获取市场新闻
            limit: 返回数量限制
            
        Returns:
            List[Dict[str, Any]] | None: 新闻列表
        """
        return None
    
    # ==================== 数据标准化方法 ====================
    
    def standardize_basic_info(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化股票基础信息
        子类可以重写此方法以适配不同的数据格式
        
        Args:
            raw_data: 原始数据
            
        Returns:
            Dict[str, Any]: 标准化后的数据
        """
        return {
            # 必需字段
            "code": self._normalize_stock_code(raw_data.get("symbol", raw_data.get("code", ""))),
            "name": raw_data.get("name", ""),
            "symbol": self._normalize_stock_code(raw_data.get("symbol", raw_data.get("code", ""))),
            "full_symbol": self._generate_full_symbol(raw_data.get("symbol", raw_data.get("code", ""))),
            
            # 市场信息
            "market_info": self._determine_market_info(raw_data.get("symbol", raw_data.get("code", ""))),
            
            # 可选字段
            "industry": raw_data.get("industry"),
            "area": raw_data.get("area", raw_data.get("region")),
            "list_date": self._format_date(raw_data.get("list_date")),
            "total_mv": self._convert_to_float(raw_data.get("market_cap", raw_data.get("total_mv"))),
            "circ_mv": self._convert_to_float(raw_data.get("float_cap", raw_data.get("circ_mv"))),
            
            # 财务指标
            "pe": self._convert_to_float(raw_data.get("pe")),
            "pb": self._convert_to_float(raw_data.get("pb")),
            "roe": self._convert_to_float(raw_data.get("roe")),
            
            # 元数据
            "data_source": self.name.lower(),
            "data_version": 1,
            "updated_at": datetime.utcnow()
        }
    
    def standardize_quotes(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化实时行情数据
        
        Args:
            raw_data: 原始行情数据
            
        Returns:
            Dict[str, Any]: 标准化后的行情数据
        """
        symbol = raw_data.get("symbol", raw_data.get("code", ""))
        
        return {
            # 必需字段
            "code": self._normalize_stock_code(symbol),
            "symbol": self._normalize_stock_code(symbol),
            "full_symbol": self._generate_full_symbol(symbol),
            "market": self._determine_market(symbol),
            
            # 价格数据
            "close": self._convert_to_float(raw_data.get("close", raw_data.get("price"))),
            "current_price": self._convert_to_float(raw_data.get("current_price", raw_data.get("close", raw_data.get("price")))),
            "open": self._convert_to_float(raw_data.get("open")),
            "high": self._convert_to_float(raw_data.get("high")),
            "low": self._convert_to_float(raw_data.get("low")),
            "pre_close": self._convert_to_float(raw_data.get("pre_close", raw_data.get("prev_close"))),
            
            # 变动数据
            "change": self._calculate_change(raw_data),
            "pct_chg": self._convert_to_float(raw_data.get("pct_chg", raw_data.get("change_percent"))),
            
            # 成交数据
            "volume": self._convert_to_float(raw_data.get("volume")),
            "amount": self._convert_to_float(raw_data.get("amount", raw_data.get("turnover"))),
            
            # 时间数据
            "trade_date": self._format_trade_date(raw_data.get("trade_date", raw_data.get("date"))),
            "timestamp": self._parse_timestamp(raw_data.get("timestamp")),
            
            # 元数据
            "data_source": self.name.lower(),
            "data_version": 1,
            "updated_at": datetime.utcnow()
        }
    
    # ==================== 辅助方法 ====================
    
    def _normalize_stock_code(self, symbol: str) -> str:
        """标准化股票代码"""
        if not symbol:
            return ""
        
        # 移除后缀
        symbol = symbol.split('.')[0]
        
        # A股代码补齐到6位
        if symbol.isdigit() and len(symbol) <= 6:
            return symbol.zfill(6)
        
        return symbol.upper()
    
    def _generate_full_symbol(self, symbol: str) -> str:
        """生成完整股票代码"""
        code = self._normalize_stock_code(symbol)
        
        if not code:
            return ""
        
        # A股代码
        if code.isdigit() and len(code) == 6:
            if code.startswith(('60', '68', '90')):
                return f"{code}.SS"  # 上交所
            else:
                return f"{code}.SZ"  # 深交所
        
        # 港股代码
        if code.isdigit() and len(code) <= 5:
            return f"{code}.HK"
        
        # 美股代码
        return f"{code}.US"
    
    def _determine_market(self, symbol: str) -> str:
        """确定市场标识"""
        return self._determine_market_info(symbol)["market"]
    
    def _determine_market_info(self, symbol: str) -> Dict[str, Any]:
        """确定市场信息"""
        code = self._normalize_stock_code(symbol)
        
        if code.isdigit() and len(code) == 6:
            # A股
            if code.startswith(('60', '68', '90')):
                return {
                    "market": "CN",
                    "exchange": "SSE",
                    "exchange_name": "上海证券交易所",
                    "currency": "CNY",
                    "timezone": "Asia/Shanghai"
                }
            else:
                return {
                    "market": "CN",
                    "exchange": "SZSE", 
                    "exchange_name": "深圳证券交易所",
                    "currency": "CNY",
                    "timezone": "Asia/Shanghai"
                }
        elif code.isdigit() and len(code) <= 5:
            # 港股
            return {
                "market": "HK",
                "exchange": "SEHK",
                "exchange_name": "香港证券交易所",
                "currency": "HKD",
                "timezone": "Asia/Hong_Kong"
            }
        else:
            # 美股
            return {
                "market": "US",
                "exchange": "NYSE",  # 默认纽交所
                "exchange_name": "纽约证券交易所",
                "currency": "USD",
                "timezone": "America/New_York"
            }
    
    def _convert_to_float(self, value: Any) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _format_date(self, date_value: Any) -> Optional[str]:
        """格式化日期"""
        if not date_value:
            return None
        
        if isinstance(date_value, int):
            # 处理YYYYMMDD格式
            date_str = str(date_value)
            if len(date_str) == 8:
                return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        
        return str(date_value)
    
    def _format_trade_date(self, date_value: Any) -> Optional[str]:
        """格式化交易日期"""
        return self._format_date(date_value)
    
    def _parse_timestamp(self, timestamp_value: Any) -> Optional[datetime]:
        """解析时间戳"""
        if not timestamp_value:
            return None
        
        if isinstance(timestamp_value, datetime):
            return timestamp_value
        
        try:
            if isinstance(timestamp_value, (int, float)):
                return datetime.fromtimestamp(timestamp_value)
            else:
                return datetime.fromisoformat(str(timestamp_value))
        except (ValueError, TypeError):
            return None
    
    def _calculate_change(self, raw_data: Dict[str, Any]) -> Optional[float]:
        """计算涨跌额"""
        current = self._convert_to_float(raw_data.get("close", raw_data.get("price")))
        prev = self._convert_to_float(raw_data.get("pre_close", raw_data.get("prev_close")))
        
        if current is not None and prev is not None:
            return current - prev
        
        return self._convert_to_float(raw_data.get("change"))
    
    # ==================== 错误处理 ====================
    
    def _handle_error(self, error: Exception, context: str = ""):
        """统一错误处理"""
        self.last_error = error
        self.logger.error(f"{context}: {error}")
    
    def get_last_error(self) -> Optional[Exception]:
        """获取最后一次错误"""
        return self.last_error
