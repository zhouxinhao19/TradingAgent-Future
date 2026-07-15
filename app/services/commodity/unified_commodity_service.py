"""
大宗商品统一服务
- 协调多个 provider(akshare / yfinance)
- Phase 1:接入 akshare_futures,基础信息/行情/历史
- Phase 2:接入 13 扩展接口 + 6 类新闻 + 静态品种字典
- Phase 3a:所有 provider 方法都有对应 service 包装,DataFrame → JSON safe dict/list
"""
import asyncio
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


# DataFrame → JSON safe 辅助
def _df_to_records(df) -> Optional[List[Dict[str, Any]]]:
    """DataFrame → records,空表返回 []"""
    if df is None:
        return None
    try:
        if hasattr(df, "empty") and df.empty:
            return []
        # fillna NaN/NaT 成 None,JSON 可序列化
        cleaned = df.where(df.notna(), None)
        records = cleaned.to_dict(orient="records")
        return records
    except Exception as e:
        logger.warning(f"_df_to_records 失败: {e}")
        return None


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
        """获取历史 K 线(已存在,Phase 1 写)"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None

        df = await provider.get_historical_data(full_symbol, start_date, end_date)
        if df is None or df.empty:
            return {"full_symbol": full_symbol, "rows": [], "count": 0,
                    "start_date": start_date, "end_date": end_date or ""}

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
            {"code": "black", "name": "黑色"},
            {"code": "energy", "name": "能源"},
            {"code": "chemical", "name": "化工"},
            {"code": "agricultural", "name": "农产品"},
            {"code": "financial", "name": "金融"},
        ]

    async def get_exchanges(self) -> List[Dict[str, Any]]:
        """返回交易所列表"""
        return [
            {"code": "SHFE", "name": "上海期货交易所", "abbrev": "SHF"},
            {"code": "DCE", "name": "大连商品交易所", "abbrev": "DCE"},
            {"code": "CZCE", "name": "郑州商品交易所", "abbrev": "CZC"},
            {"code": "INE", "name": "上海国际能源交易中心", "abbrev": "INE"},
            {"code": "GFEX", "name": "广州期货交易所", "abbrev": "GFEX"},
            {"code": "CFFEX", "name": "中国金融期货交易所", "abbrev": "CFFEX"},
        ]

    # ============================================================
    # Phase 3a 新增:品种字典(静态,用于前端下拉/筛选)
    # ============================================================
    async def get_varieties(
        self,
        exchange: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        返回静态品种字典(80+ 条目)。

        Args:
            exchange: 过滤交易所 SHFE/DCE/...
            category: 过滤品类 metal/energy/...
        """
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return []
        result = await provider.list_all_varieties()
        if not result:
            return []
        if exchange:
            ex = exchange.upper()
            result = [v for v in result if v.get("exchange", "").upper() == ex]
        if category:
            result = [v for v in result if v.get("category", "").lower() == category.lower()]
        return result

    # ============================================================
    # Phase 3a 新增:13 扩展接口 + 1 期货新闻
    # ============================================================

    async def get_fees_and_margin(
        self,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        date: Optional[str] = None,
    ) -> Optional[Union[List[Dict[str, Any]], Dict[str, Any]]]:
        """手续费 / 保证金 / 涨跌停"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        return await provider.get_fees_and_margin(exchange=exchange, symbol=symbol, date=date)

    async def get_inventory(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """库存数据(EM 60 天,99 长期)"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_inventory(symbol, start_date, end_date)
        records = _df_to_records(df)
        if records is None:
            return None
        return {"symbol": symbol, "rows": records, "count": len(records)}

    async def get_warehouse_receipt(
        self,
        exchange: str,
        date: str,
    ) -> Optional[Dict[str, Any]]:
        """仓单日报"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        result = await provider.get_warehouse_receipt(exchange, date)
        if result is None:
            return None
        # 仓单可能是 dict{variety: DataFrame} 或 单 DataFrame
        if hasattr(result, "to_dict"):
            records = _df_to_records(result)
            return {"exchange": exchange, "date": date, "rows": records or [], "count": len(records) if records else 0}
        if isinstance(result, dict):
            # 各品种一张表
            rows = {}
            for var, df in result.items():
                if hasattr(df, "to_dict"):
                    rows[var] = _df_to_records(df) or []
                else:
                    rows[var] = df
            total = sum(len(v) if isinstance(v, list) else 1 for v in rows.values())
            return {"exchange": exchange, "date": date, "by_variety": rows, "count": total}
        return {"exchange": exchange, "date": date, "raw": str(result)[:500]}

    async def get_position_rank(
        self,
        exchange: str,
        date: str,
        vars_list: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """会员持仓排名"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        result = await provider.get_position_rank(exchange, date, vars_list)
        if result is None:
            return None
        if isinstance(result, dict):
            by_var = {}
            for var, df in result.items():
                by_var[var] = _df_to_records(df) or []
            total = sum(len(v) for v in by_var.values())
            return {"exchange": exchange, "date": date, "by_variety": by_var, "count": total}
        # 单表
        records = _df_to_records(result)
        return {"exchange": exchange, "date": date, "rows": records or [], "count": len(records) if records else 0}

    async def get_spot_price(
        self,
        date: str,
    ) -> Optional[Dict[str, Any]]:
        """当日现货价格 + 基差"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_spot_price(date)
        records = _df_to_records(df)
        if records is None:
            return None
        return {"date": date, "rows": records, "count": len(records)}

    async def get_basis_history(
        self,
        start_day: str,
        end_day: str,
        vars_list: List[str],
    ) -> Optional[Dict[str, Any]]:
        """历史基差"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_basis_history(start_day, end_day, vars_list)
        records = _df_to_records(df)
        if records is None:
            return None
        return {"vars_list": vars_list, "start_day": start_day, "end_day": end_day,
                "rows": records, "count": len(records)}

    async def get_basis_spot_previous(
        self,
        date: str,
    ) -> Optional[Dict[str, Any]]:
        """历史某日基差汇总"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_basis_spot_previous(date)
        records = _df_to_records(df)
        if records is None:
            return None
        return {"date": date, "rows": records, "count": len(records)}

    async def get_roll_yield(
        self,
        type_method: str,
        var: Optional[str] = None,
        date: Optional[str] = None,
        start_day: Optional[str] = None,
        end_day: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """展期收益率"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_roll_yield(
            type_method=type_method,
            var=var, date=date,
            start_day=start_day, end_day=end_day,
        )
        records = _df_to_records(df)
        if records is None:
            return None
        return {"type_method": type_method, "var": var, "rows": records, "count": len(records)}

    async def get_contract_info(
        self,
        exchange: str,
        date: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """合约信息"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_contract_info(exchange, date)
        records = _df_to_records(df)
        if records is None:
            return None
        return {"exchange": exchange, "date": date or "", "rows": records, "count": len(records)}

    async def get_trading_calendar(
        self,
        date: str,
    ) -> Optional[Dict[str, Any]]:
        """交易日历 + 合约参数"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_trading_calendar(date)
        records = _df_to_records(df)
        if records is None:
            return None
        return {"date": date, "rows": records, "count": len(records)}

    async def get_realtime_quote(
        self,
        symbols: Union[str, List[str]],
        market: str = "CF",
    ) -> Optional[Dict[str, Any]]:
        """实时行情(CF 商品 / FF 金融)"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_realtime_quote(symbols, market=market)
        records = _df_to_records(df)
        if records is None:
            return None
        sym_str = ",".join(symbols) if isinstance(symbols, list) else symbols
        return {"symbols": sym_str, "market": market, "rows": records, "count": len(records)}

    async def get_minute_kline(
        self,
        symbol: str,
        period: int = 5,
    ) -> Optional[Dict[str, Any]]:
        """分时 K 线"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_minute_kline(symbol, period=period)
        records = _df_to_records(df)
        if records is None:
            return None
        return {"symbol": symbol, "period": period, "rows": records, "count": len(records)}

    async def get_delivery_info(
        self,
        exchange: str,
        date: str,
    ) -> Optional[Dict[str, Any]]:
        """交割统计 / 期转现"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_delivery_info(exchange, date)
        records = _df_to_records(df)
        if records is None:
            return None
        return {"exchange": exchange, "date": date, "rows": records, "count": len(records)}

    async def get_holding_position(
        self,
        symbol: str,
        indicator: str = "成交量",
        date: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """期货成交持仓"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_holding_position(symbol, indicator=indicator, date=date)
        records = _df_to_records(df)
        if records is None:
            return None
        return {"symbol": symbol, "indicator": indicator, "date": date or "",
                "rows": records, "count": len(records)}

    async def get_futures_news(
        self,
        category: str = "all",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """6 类新闻聚合(任何错误都返 [])"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return []
        try:
            result = await provider.get_futures_news(category=category, limit=limit)
        except Exception as e:
            logger.warning(f"get_futures_news({category}) 异常: {e}")
            return []
        if not result:
            return []
        # 截断到 limit
        return result[:limit]

    async def get_news_categories(self) -> List[Dict[str, str]]:
        """新闻分类清单(供前端下拉)"""
        return [
            {"code": "metal",       "name": "有色金属(shmet)"},
            {"code": "precious",    "name": "贵金属(shmet)"},
            {"code": "minor",       "name": "小金属(shmet)"},
            {"code": "headline",    "name": "头条要闻(shmet)"},
            {"code": "vip",         "name": "VIP 专享(shmet)"},
            {"code": "finance",     "name": "财经要闻(shmet)"},
            {"code": "chemical",    "name": "化工合成器"},
            {"code": "energy",      "name": "能源合成器"},
            {"code": "agricultural","name": "农产品合成器"},
            {"code": "financial",   "name": "金融期货合成器"},
            {"code": "global_macro","name": "全球宏观聚合"},
            {"code": "all",         "name": "全部(去重后)"},
        ]


# 全局单例
service = UnifiedCommodityService()
