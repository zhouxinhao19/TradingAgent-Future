"""
大宗商品数据提供器基类
镜像 BaseStockDataProvider 设计,便于 Phase 5 整体替换

设计原则:
- 3 个核心方法标记为 @abstractmethod(connect / get_commodity_basic_info /
  get_commodity_quotes / get_historical_data)
- 扩展接口(费用、库存、基差等)定义为普通方法 + 抛 NotImplementedError,
  Phase 2+ 的 provider 逐步实现,避免改动后让现有 provider 失效
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

    # ==================== 生命周期(强制) ====================

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

    # ==================== 核心数据接口(强制) ====================

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
        adjustment_mode: str = "none",
    ) -> Optional[pd.DataFrame]:
        """
        获取历史 K 线(日线)。

        Args:
            full_symbol: 完整标的代码(如 CU2501.SHF / CU0.SHF)
            start_date: 开始日期
            end_date: 结束日期(默认到今天)
            adjustment_mode: 复权模式
                "none" — 原始数据，含 rollover_date 换月标记列
                "back" — 后复权(向前调整)
                "forward" — 前复权(向后调整)
        """

    # ==================== 扩展接口(可选,需要时由子类实现) ====================
    # 新版期货数据接口:费用、库存、基差、展期、持仓、合约信息、交易日历。
    # 这些方法不在基类中强制,默认抛 NotImplementedError。

    async def get_fees_and_margin(
        self,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        date: Optional[str] = None,
    ) -> Optional[Union[List[Dict[str, Any]], Dict[str, Any]]]:
        """
        获取期货手续费 / 保证金 (AKShare: futures_comm_info / futures_comm_js /
        futures_fees_info / futures_settle)
        返回按合约+日期的费率表,具体字段视 provider 实现而定。
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_fees_and_margin"
        )

    async def get_inventory(
        self,
        symbol: str,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
    ) -> Optional[pd.DataFrame]:
        """
        获取库存数据(AKShare: futures_inventory_99 / futures_inventory_em /
        futures_stock_shfe_js)。
        返回 DataFrame,列应包含 [date, inventory, change_pct]。
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_inventory"
        )

    async def get_warehouse_receipt(
        self,
        exchange: str,
        date: Union[str, date],
    ) -> Optional[Dict[str, pd.DataFrame]]:
        """
        获取仓单日报(AKShare: futures_warehouse_receipt_czce/dce/shfe/gfex)
        返回 {品种代码: DataFrame} 的字典。
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_warehouse_receipt"
        )

    async def get_position_rank(
        self,
        exchange: str,
        date: Union[str, date],
        vars_list: Optional[List[str]] = None,
    ) -> Optional[Dict[str, pd.DataFrame]]:
        """
        获取会员持仓排名(AKShare: futures_dce_position_rank /
        futures_gfex_position_rank / get_shfe_rank_table / get_cffex_rank_table /
        get_rank_table_czce)
        返回 {合约代码: DataFrame} 的字典。
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_position_rank"
        )

    async def get_registered_receipt(
        self,
        start_date: Union[str, date],
        end_date: Union[str, date],
        vars_list: List[str],
    ) -> Optional[pd.DataFrame]:
        """
        获取注册仓单(AKShare: get_receipt)。
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_registered_receipt"
        )

    async def get_spot_price(
        self,
        date: Union[str, date],
    ) -> Optional[pd.DataFrame]:
        """
        获取某交易日现货价格 + 基差(AKShare: futures_spot_price)。
        列应包含 symbol / spot_price / near_contract / near_basis /
        dom_contract / dom_basis / near_basis_rate / dom_basis_rate。
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_spot_price"
        )

    async def get_basis_history(
        self,
        start_day: Union[str, date],
        end_day: Union[str, date],
        vars_list: List[str],
    ) -> Optional[pd.DataFrame]:
        """
        获取历史基差数据(AKShare: futures_spot_price_daily)。
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_basis_history"
        )

    async def get_basis_spot_previous(
        self,
        date: Union[str, date],
    ) -> Optional[pd.DataFrame]:
        """
        获取历史某交易日基差汇总(AKShare: futures_spot_price_previous),
        含品种 / 现货 / 主力 / 主力基差 / 180 日内主力基差最高最低等列。
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_basis_spot_previous"
        )

    async def get_roll_yield(
        self,
        type_method: str,
        var: Optional[str] = None,
        date: Optional[Union[str, date]] = None,
        start_day: Optional[Union[str, date]] = None,
        end_day: Optional[Union[str, date]] = None,
        symbol1: Optional[str] = None,
        symbol2: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """
        获取展期收益率(AKShare: get_roll_yield_bar / get_roll_yield)。

        type_method 取值:
        - "date": 某品种在多个日期的主力/次主力价差
        - "symbol": 某品种在某天的所有交割月合约价格
        - "var": 某交易日所有品种的主力/次主力展期收益率
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_roll_yield"
        )

    async def get_contract_info(
        self,
        exchange: str,
        date: Union[str, date],
    ) -> Optional[pd.DataFrame]:
        """
        获取合约信息(AKShare: futures_contract_info_shfe/ine/dce/czce/gfex/cffex)。
        列含合约代码 / 上市日 / 到期日 / 开始交割日 / 最后交割日 / 挂牌基准价 等。
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_contract_info"
        )

    async def get_trading_calendar(
        self,
        date: Union[str, date],
    ) -> Optional[pd.DataFrame]:
        """
        获取交易日历的合约参数表(AKShare: futures_rule)。
        列含交易所 / 品种 / 交易保证金比例 / 涨跌停板幅度 / 合约乘数 /
        最小变动价位 / 限价单最大下单手数等。
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_trading_calendar"
        )

    async def get_realtime_quote(
        self,
        symbols: Union[str, List[str]],
        market: str = "CF",
    ) -> Optional[pd.DataFrame]:
        """
        获取期货实时行情(AKShare: futures_zh_spot / futures_zh_realtime)。

        market 取值:
        - "CF": 商品期货
        - "FF": 金融期货
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_realtime_quote"
        )

    async def get_minute_kline(
        self,
        symbol: str,
        period: int = 1,
    ) -> Optional[pd.DataFrame]:
        """
        获取分时 K 线(AKShare: futures_zh_minute_sina)。
        period: 1/5/15/30/60 分钟。
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_minute_kline"
        )

    async def get_delivery_info(
        self,
        exchange: str,
        date: Union[str, date],
    ) -> Optional[pd.DataFrame]:
        """
        获取交割统计(AKShare: futures_delivery_dce/czce/shfe)
        或期转现数据(futures_to_spot_dce/czce/shfe)
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_delivery_info"
        )

    async def get_holding_position(
        self,
        symbol: str,
        indicator: str = "成交量",
        date: Union[str, date] = None,
    ) -> Optional[pd.DataFrame]:
        """
        获取期货成交持仓(AKShare: futures_hold_pos_sina)。

        indicator 取值: "成交量" / "多单持仓" / "空单持仓"
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_holding_position"
        )

    async def get_futures_news(
        self,
        category: str = "all",
        limit: int = 50,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取期货市场资讯(新闻 + 情感 + 重要度,供给 agent 用作"基本面叙事"输入)。

        Args:
            category: 资讯分类,默认 "all"
                - "all": 全部
                - "metal": 有色金属(总)
                - "copper": 铜 / "aluminum": 铝 / "lead": 铅 / "zinc": 锌
                - "nickel": 镍 / "tin": 锡
                - "precious": 贵金属 / "minor": 小金属
                - "headline": 要闻 / "vip": VIP / "finance": 财经
            limit: 最多返回条数

        Returns:
            新闻列表,每条含 published_at / title / content / category /
            sentiment / sentiment_score / source / url。

        注意:不同 provider 覆盖的范围不同。
        - AKShare futures_news_shmet: 仅覆盖有色金属 + 贵金属 + 小金属 + 财经快讯;
          化工/能源/农产品/金融期货暂无信息源,需另接。
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_futures_news"
        )

    async def get_active_contract_history(
        self,
        symbol: str,
        start_date: Union[str, date],
        end_date: Union[str, date] = None,
    ) -> Optional[pd.DataFrame]:
        """
        获取每日主力合约代码历史序列。

        Args:
            symbol: 品种代码(如 CU / RB / A),纯字母代码
            start_date: 开始日期
            end_date: 结束日期(默认到今天)

        Returns:
            DataFrame: [date, active_contract, exchange, days_to_expiry, last_delivery_date]
        """
        raise NotImplementedError(
            f"{self.provider_name} 未实现 get_active_contract_history"
        )

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
