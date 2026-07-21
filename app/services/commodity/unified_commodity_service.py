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

        result = {
            "full_symbol": full_symbol,
            "rows": rows,
            "count": len(rows),
            "start_date": str(df["日期"].min()) if not df.empty else start_date,
            "end_date": str(df["日期"].max()) if not df.empty else (end_date or ""),
        }
        # 传递数据来源标记(如具体合约回退到主力连续)
        note = df.attrs.get("data_source_note") if hasattr(df, "attrs") else None
        if note:
            result["data_source_note"] = note
        return result

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
        no_cache: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """库存数据(EM 60 天,99 长期)"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_inventory(symbol, start_date, end_date, no_cache=no_cache)
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
        no_cache: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """当日现货价格 + 基差"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_spot_price(date, no_cache=no_cache)
        records = _df_to_records(df)
        if records is None:
            return None
        return {"date": date, "rows": records, "count": len(records)}

    async def get_basis_history(
        self,
        start_day: str,
        end_day: str,
        vars_list: List[str],
        no_cache: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """历史基差"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_basis_history(start_day, end_day, vars_list, no_cache=no_cache)
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

    async def get_contracts_list(self, full_symbol: str) -> Optional[Dict[str, Any]]:
        """
        列出某品种下的所有到期合约代码 + 主力连续代码。

        从 full_symbol (如 CU2501.SHF) 提取 underlying (CU) 和 exchange (SHF)，
        调用 get_contract_info 并过滤出该品种的所有合约。

        过滤逻辑:
        1. 合约代码以品种代码开头
        2. 剔除已到期合约(到期日 < 今天)
        """
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None

        from tradingagents.dataflows.providers.commodity.commodity_metadata import (
            get_main_continuous_symbol, get_variety,
        )
        from tradingagents.utils.commodity_utils import CommodityUtils

        info = CommodityUtils.get_market_info(full_symbol)
        underlying = info.get("underlying", "")
        code = full_symbol.split(".")[0] if "." in full_symbol else full_symbol
        exchange = full_symbol.split(".")[-1].upper() if "." in full_symbol else ""

        if not underlying or not exchange:
            return None

        # 主力连续合约代码
        continuous = get_main_continuous_symbol(underlying)
        continuous_full = f"{continuous}.{exchange}" if continuous else None

        # 品种中文名
        variety_meta = get_variety(underlying) or {}
        chinese_name = variety_meta.get("name_cn", underlying)

        # 获取该交易所的所有合约，过滤出该品种的
        ex_long = {"SHF": "SHFE", "CZC": "CZCE"}.get(exchange, exchange)
        contract_data = await self.get_contract_info(ex_long)
        if not contract_data or not contract_data.get("rows"):
            return {
                "underlying": underlying,
                "chinese_name": chinese_name,
                "exchange": exchange,
                "continuous": continuous_full,
                "current": full_symbol,
                "contracts": [],
                "count": 0,
            }

        rows = contract_data["rows"]
        # 找包含合约代码的列名
        code_key = None
        candidates = ["合约代码", "contract_code", "code", "symbol", "品种代码"]
        for c in candidates:
            if rows and c in rows[0]:
                code_key = c
                break
        if not code_key:
            code_key = list(rows[0].keys())[0] if rows else "合约代码"

        # 找到期日/最后交易日列，用于过滤已到期合约
        expiry_candidates = ['到期日', '最后交易日', 'expiry_date', 'last_trade_date', '最后交割日']
        expiry_key = None
        if rows:
            for c in expiry_candidates:
                if c in rows[0]:
                    expiry_key = c
                    break

        today = date.today()

        # 过滤:合约代码以 underlying 开头 + 未到期
        contracts = []
        seen = set()
        for r in rows:
            raw = str(r.get(code_key, "")).strip()
            if not raw.upper().startswith(underlying.upper()) or raw in seen:
                continue
            seen.add(raw)

            # 过滤已到期合约(到期日 < 今天)
            if expiry_key:
                expiry_str = str(r.get(expiry_key, "")).strip()
                if expiry_str:
                    try:
                        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
                        if expiry_date < today:
                            continue
                    except ValueError:
                        pass  # 日期解析失败则保留该合约

            contracts.append(f"{raw}.{exchange}")

        contracts.sort()
        return {
            "underlying": underlying,
            "chinese_name": chinese_name,
            "exchange": exchange,
            "continuous": continuous_full,
            "current": full_symbol,
            "contracts": contracts,
            "count": len(contracts),
        }

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
        no_cache: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """期货成交持仓"""
        await self.initialize()
        provider = self._providers.get("akshare_futures")
        if not provider:
            return None
        df = await provider.get_holding_position(symbol, indicator=indicator, date=date, no_cache=no_cache)
        if isinstance(df, tuple):
            df, actual_date = df
        else:
            actual_date = date or ""
        records = _df_to_records(df)
        if records is None:
            return None
        return {"symbol": symbol, "indicator": indicator, "date": actual_date or date or "",
                "rows": records, "count": len(records)}

    async def get_futures_news(
        self,
        category: str = "all",
        limit: int = 50,
        variety: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """6 类新闻聚合,支持按品种筛选。

        Phase 新闻改造:
        优先从 MongoDB commodity_news_annotations 读取已 LLM 标注的新闻,
        缓存不足时实时拉取 AKShare + LLM 标注作为降级。

        Args:
            category: 新闻分类(metal/energy/.../all)
            limit: 返回条数
            variety: 品种代码(如 CU),筛选 relevant_varieties 包含该品种的新闻

        返回字段:
          - 原始字段: published_at / title / content / source / url
          - LLM 标注字段:
            relevant_varieties / llm_sentiment / llm_sentiment_confidence /
            llm_sentiment_reasoning / llm_summary / llm_importance /
            annotated_at / annotator_model
        """
        await self.initialize()

        # ── 路径 A: 从 MongoDB 读取已标注新闻 ──
        try:
            from app.core.database import get_database
            db = get_database()
            coll = db["commodity_news_annotations"]

            # 构建 MongoDB 查询:支持 category + variety 组合筛选
            query = {}
            conditions = []

            if category and category not in ("all", "global_macro"):
                cat_map = {
                    "metal": ["CU", "AL", "ZN", "PB", "NI", "SN", "AO", "BC"],
                    "precious": ["AU", "AG"],
                    "black": ["RB", "HC", "I", "J", "JM", "SS", "WR", "SI", "LC", "PS"],
                    "minor": ["SI", "LC", "PS", "SF", "SM"],
                }
                variety_codes = cat_map.get(category, [category.upper()])
                conditions.append({"relevant_varieties": {"$in": variety_codes}})

            if variety:
                v = variety.upper()
                conditions.append({"relevant_varieties": {"$in": [v]}})

            if conditions:
                query["$and"] = conditions

            cursor = coll.find(query).sort("annotated_at", -1).limit(limit)
            cached = await cursor.to_list(length=limit)

            if len(cached) >= limit // 2:
                result = []
                for doc in cached:
                    result.append({
                        "published_at": doc.get("published_at") or str(doc.get("annotated_at", "")),
                        "title": doc.get("title", ""),
                        "content": doc.get("content", ""),
                        "source": doc.get("source", "llm_annotated"),
                        "url": doc.get("url", ""),
                        "category": category,
                        "metal": category,
                        # 保留字段兼容
                        "sentiment": doc.get("sentiment", "neutral"),
                        "sentiment_score": 0.0,
                        # LLM 标注字段
                        "relevant_varieties": doc.get("relevant_varieties", []),
                        "llm_sentiment": doc.get("sentiment", "neutral"),
                        "llm_sentiment_confidence": float(doc.get("sentiment_confidence", 0.0)),
                        "llm_sentiment_reasoning": doc.get("sentiment_reasoning", ""),
                        "llm_importance": doc.get("importance", "medium"),
                        "llm_summary": doc.get("summary", ""),
                        "annotated_at": str(doc.get("annotated_at", "")),
                        "annotator_model": doc.get("annotator_model", ""),
                    })
                return result[:limit]
        except Exception as e:
            logger.debug(f"MongoDB 查询已标注新闻失败: {e}")

        # ── 路径 B: 降级 — 实时拉取 + 实时标注 ──
        provider = self._providers.get("akshare_futures")
        if not provider:
            return []
        try:
            raw = await provider.get_futures_news(category=category, limit=limit)
        except Exception as e:
            logger.warning(f"get_futures_news({category}) 异常: {e}")
            return []
        if not raw:
            return []

        # 尝试实时 LLM 标注(降级)
        try:
            from tradingagents.annotators.commodity.news_annotator import NewsAnnotator
            from app.core.database import get_database

            db = get_database()
            coll = db["commodity_news_annotations"]

            llm = await self._get_quick_llm()
            if llm:
                annotator = NewsAnnotator(
                    llm=llm,
                    cache_collection=coll,
                    annotator_model=getattr(llm, "model_name", "live_fallback"),
                )
                raw = await annotator.annotate_batch(raw, max_concurrent=3)
        except Exception as e:
            logger.debug(f"实时 LLM 标注降级失败: {e}")

        # variety 客户端过滤(降级路径也支持按品种筛选)
        if variety and raw:
            v = variety.upper()
            filtered = [it for it in raw if any(
                rv.upper() == v for rv in (it.get("relevant_varieties") or [])
            )]
            return filtered[:limit] if filtered else []

        return (raw or [])[:limit]

    async def _get_quick_llm(self):
        """获取用于标注的快速 LLM(降级用)。"""
        try:
            from tradingagents.llm_clients.factory import create_llm_client
            llm_client = create_llm_client(
                provider="deepseek",
                model="deepseek-chat",
                temperature=0,
            )
            return llm_client.get_llm() if llm_client else None
        except Exception:
            return None

    async def get_news_categories(self) -> List[Dict[str, str]]:
        """新闻分类清单(供前端下拉,仅保留有效大类)"""
        return [
            {"code": "all",         "name": "全部"},
            {"code": "metal",       "name": "有色金属"},
            {"code": "precious",    "name": "贵金属"},
            {"code": "black",       "name": "黑色系"},
            {"code": "global_macro","name": "全球宏观"},
        ]


# 全局单例
service = UnifiedCommodityService()
