"""
AKShare 国内期货数据源
- 主力连续合约: futures_main_sina
- 历史日线: futures_zh_daily_sina
- 实时行情: 用最近日线数据近似(Phase 2 接入 futures_zh_spot)

Phase 1 最小实现,只支持国内期货(国际 + 现货在后续 Phase 扩展)
"""
import asyncio
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Union

import pandas as pd

from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.commodity_utils import (
    CommodityUtils, CommodityMarket,
)
from tradingagents.dataflows.providers.commodity.base_commodity_provider import (
    BaseCommodityDataProvider,
)
from tradingagents.dataflows.providers.commodity.commodity_metadata import (
    is_past_yymm,
    parse_contract_code,
    resolve_main_continuous,
)

logger = get_logger("default")


# 国内期货交易所后缀映射(AKShare 接口不识别后缀)
_CHINA_FUTURES_EXCHANGES = ("SHF", "DCE", "CZC", "INE", "GFEX")

# 交易所中文名
_EXCHANGE_NAMES = {
    "SHF": "上海期货交易所",
    "DCE": "大连商品交易所",
    "CZC": "郑州商品交易所",
    "INE": "上海国际能源交易中心",
    "GFEX": "广州期货交易所",
}


class AkshareFuturesProvider(BaseCommodityDataProvider):
    """AKShare 国内期货数据源(主力 + 历史 K 线)"""

    def __init__(self):
        super().__init__("akshare_futures")
        self._ak = None

    async def connect(self) -> bool:
        """延迟加载 akshare(避免启动时强依赖)"""
        try:
            import akshare as ak
            self._ak = ak
            self.connected = True
            self.logger.info("✅ AkshareFuturesProvider 连接成功(懒加载)")
            return True
        except ImportError as e:
            self.logger.error(f"❌ akshare 未安装: {e}")
            return False

    # ==================== 核心数据接口 ====================

    async def get_commodity_basic_info(
        self, full_symbol: str = None
    ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """
        获取商品基础信息

        Args:
            full_symbol: 完整代码,如 CU2501.SHF。空则返回空列表(全列表由 Phase 2 实现)
        """
        if not full_symbol:
            return []
        return self._build_basic_info(full_symbol)

    async def get_commodity_quotes(self, full_symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取实时行情(Phase 1:用最近日线 close + 动态结算价作为快照)
        """
        if not self.connected:
            await self.connect()
        if not self._ak:
            return None

        symbol = self._strip_exchange(full_symbol)
        try:
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None, lambda: self._ak.futures_main_sina(symbol=symbol)
            )
        except Exception as e:
            self.logger.warning(f"获取 {full_symbol} 行情失败: {e}")
            return None

        if df is None or df.empty:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        info = self._build_basic_info(full_symbol) or {}
        close = float(last.get("收盘价", 0) or 0)
        pre_close = float(prev.get("收盘价", 0) or 0)
        settlement_price = float(last.get("动态结算价", 0) or 0)
        change = close - pre_close
        pct_chg = (change / pre_close * 100) if pre_close else 0.0

        return {
            "full_symbol": full_symbol,
            "code": info.get("code", full_symbol),
            "exchange": info.get("exchange", ""),
            "name": info.get("name", ""),
            "category": info.get("category", ""),
            "currency": info.get("currency", "CNY"),
            "unit": info.get("unit", "手"),
            "contract_size": info.get("contract_size", 1.0),
            "open": float(last.get("开盘价", 0) or 0),
            "high": float(last.get("最高价", 0) or 0),
            "low": float(last.get("最低价", 0) or 0),
            "close": close,
            "pre_close": pre_close,
            "current_price": close,
            "settlement_price": settlement_price,
            "change": change,
            "pct_chg": pct_chg,
            "volume": int(last.get("成交量", 0) or 0),
            "open_interest": int(last.get("持仓量", 0) or 0),
            "trade_date": str(last.get("日期", "")),
            "data_source": "akshare_futures",
            "updated_at": datetime.utcnow().isoformat(),
        }

    async def get_historical_data(
        self,
        full_symbol: str,
        start_date: Union[str, date],
        end_date: Union[str, date] = None,
    ) -> Optional[pd.DataFrame]:
        """获取历史 K 线(日线)"""
        if not self.connected:
            await self.connect()
        if not self._ak:
            return None

        symbol = self._strip_exchange(full_symbol)
        try:
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None, lambda: self._ak.futures_main_sina(symbol=symbol)
            )
        except Exception as e:
            self.logger.warning(f"获取 {full_symbol} 历史数据失败: {e}")
            return None

        if df is None or df.empty:
            return None

        df["日期"] = pd.to_datetime(df["日期"]).dt.date
        start = pd.to_datetime(start_date).date() if isinstance(start_date, str) else start_date
        if end_date is None:
            end = df["日期"].max()
        elif isinstance(end_date, str):
            end = pd.to_datetime(end_date).date()
        else:
            end = end_date

        df = df[(df["日期"] >= start) & (df["日期"] <= end)]
        df = df.sort_values("日期").reset_index(drop=True)
        return df

    # ==================== 辅助方法 ====================

    @staticmethod
    def _strip_exchange(full_symbol: str) -> str:
        """去掉交易所后缀(AKShare 接口不识别)"""
        for exch in _CHINA_FUTURES_EXCHANGES:
            suffix = f".{exch}"
            if full_symbol.upper().endswith(suffix):
                return full_symbol[: -len(suffix)]
        return full_symbol

    @staticmethod
    def _build_basic_info(full_symbol: str) -> Optional[Dict[str, Any]]:
        """从 full_symbol 构造基础信息(不依赖外部 API)"""
        market = CommodityUtils.identify_market(full_symbol)
        if market != CommodityMarket.CHINA_FUTURES:
            return None

        info = CommodityUtils.get_market_info(full_symbol)
        code, exchange = full_symbol.split(".") if "." in full_symbol else (full_symbol, "")

        underlying = info.get("underlying", "")
        year_month = code[len(underlying):] if len(code) > len(underlying) else ""
        yymm_str = ""
        if len(year_month) == 4 and year_month.isdigit():
            yymm_str = f"20{year_month[:2]}年{int(year_month[2:]):02d}月"

        name = f"{underlying}期货{yymm_str}合约" if yymm_str else f"{underlying}期货"

        return {
            "code": code,
            "full_symbol": full_symbol,
            "symbol": code,
            "name": name,
            "exchange": exchange,
            "exchange_name": _EXCHANGE_NAMES.get(exchange, "未知交易所"),
            "category": info.get("category", "unknown"),
            "underlying": underlying,
            "currency": info.get("currency", "CNY"),
            "unit": info.get("unit", "手"),
            "contract_size": info.get("contract_size", 1.0),
            "is_china_futures": True,
            "is_international": False,
            "is_spot_cn": False,
            "data_source": "akshare_futures",
            "data_version": 1,
            "updated_at": datetime.utcnow().isoformat(),
        }
