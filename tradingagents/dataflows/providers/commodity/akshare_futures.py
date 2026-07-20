"""
AKShare 国内期货数据源

Phase 1 已有:基础信息 / 实时行情 / 历史 K 线 / 主力连续合约
Phase 2 起新增:手续费 / 保证金 / 库存 / 仓单 / 持仓 / 基差 / 展期 / 合约信息 /
交易日历 / 实时行情(分合约) / 分时 K 线 / 交割统计 / 成交持仓

所有接口均按 *futures_*/ get_roll_* / get_* 等 AKShare 官方函数实现,
详见 `akshare期货数据.txt`。
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
    EXCHANGES,
    get_variety,
    normalize_exchange_code,
)

logger = get_logger("default")


# 国内期货交易所后缀映射(AKShare 接口不识别后缀)
# 同时接受 metadata 的完整交易所代码，兼容用户手动输入的完整标的。
_CHINA_FUTURES_EXCHANGES = (
    "SHF", "SHFE", "DCE", "CZC", "CZCE", "INE", "GFEX", "CFFEX",
)

# 交易所中文名
_EXCHANGE_NAMES = {
    "SHF": "上海期货交易所",
    "DCE": "大连商品交易所",
    "CZC": "郑州商品交易所",
    "INE": "上海国际能源交易中心",
    "GFEX": "广州期货交易所",
    "CFFEX": "中国金融期货交易所",
}

# AKShare 接口参数(交易所) -> 不带后缀的交易所缩写(用于 futures_xxx_em 等)
_AKSHARE_EXCHANGE_MAP = {
    "SHFE": "shfe",
    "INE": "ine",
    "DCE": "dce",
    "CZCE": "czce",
    "GFEX": "gfex",
    "CFFEX": "cffex",
}

# AKShare futures_settle / futures_rule 接受的参数
_SETTLE_MARKET_MAP = {
    "CFFEX": "CFFEX",
    "INE": "INE",
    "CZCE": "CZCE",
    "SHFE": "SHFE",
    "GFEX": "GFEX",
}

# AKShare futures_comm_info 中"symbol"参数接受的交易所中文名
_COMM_INFO_EXCHANGE_MAP = {
    "SHFE": "上海期货交易所",
    "DCE": "大连商品交易所",
    "CZCE": "郑州商品交易所",
    "INE": "上海国际能源交易中心",
    "CFFEX": "中国金融期货交易所",
    "GFEX": "广州期货交易所",
}


def _to_ak_exchange(exchange: str) -> Optional[str]:
    """交易所代码 -> AKShare 接口使用的缩写"""
    if not exchange:
        return None
    return _AKSHARE_EXCHANGE_MAP.get(exchange.upper())


# =============================================================================
# 期货资讯(category → futures_news_shmet symbol)
# AKShare `futures_news_shmet` 只支持以下 symbol:
#   {"全部", "要闻", "VIP", "财经", "铜", "铝", "铅", "锌", "镍", "锡", "贵金属", "小金属"}
# global_macro 通过 `_synth_global_macro_news` 走全球宏观聚合。
# =============================================================================
_NEWS_CATEGORY_MAP = {
    "all": "全部",
    "metal": "全部",        # shmet 全部内容即是有色金属
    "nonferrous": "全部",
    "copper": "铜",
    "cu": "铜",
    "aluminum": "铝",
    "al": "铝",
    "lead": "铅",
    "pb": "铅",
    "zinc": "锌",
    "zn": "锌",
    "nickel": "镍",
    "ni": "镍",
    "tin": "锡",
    "sn": "锡",
    "precious": "贵金属",
    "au": "贵金属",
    "ag": "贵金属",
    "minor": "小金属",
    "headline": "要闻",
    "vip": "VIP",
    "finance": "财经",
}


# 期货市场专用的情感关键词(精简版,避免过度拟合股票侧)
_POS_NEWS_KEYWORDS = {
    "涨停": 1.0, "暴涨": 0.9, "大涨": 0.8, "飙升": 0.8, "大涨": 0.8,
    "创新高": 0.7, "突破": 0.6, "上涨": 0.5, "增长": 0.4, "涨幅": 0.5,
    "利好": 0.6, "看好": 0.5, "推荐": 0.5, "买入": 0.6, "强势": 0.4,
    "提振": 0.5, "回升": 0.4, "反弹": 0.3, "上行": 0.3, "回升": 0.4,
    "投产": 0.3, "增产": 0.3, "扩产": 0.3, "中标": 0.4, "签约": 0.4,
    "补涨": 0.5, "去库": 0.5, "降库": 0.5, "去库存": 0.5,
}

_NEG_NEWS_KEYWORDS = {
    "跌停": -1.0, "暴跌": -0.9, "大跌": -0.8, "跳水": -0.8,
    "创新低": -0.7, "破位": -0.6, "下跌": -0.5, "下滑": -0.4, "降幅": -0.5,
    "利空": -0.6, "看空": -0.5, "卖出": -0.6, "警告": -0.5,
    "累库": -0.5, "累库存": -0.5, "被动累库": -0.5, "垒库": -0.5,
    "减产": -0.3, "停产": -0.4, "检修": -0.1, "亏损": -0.4,
    "违约": -0.7, "诉讼": -0.5, "监管": -0.3, "处罚": -0.5,
    "下调": -0.3, "紧缩": -0.3,
}


def _analyze_futures_news_sentiment(text: str) -> float:
    """简易情感评分(-1.0 ~ 1.0),使用大宗商品专用关键词词典"""
    score = 0.0
    for kw, w in _POS_NEWS_KEYWORDS.items():
        if kw in text:
            score += w
    for kw, w in _NEG_NEWS_KEYWORDS.items():
        if kw in text:
            score += w
    # 截断到 [-1, 1]
    return max(-1.0, min(1.0, score))


def _to_sentiment_label(score: float) -> str:
    if score >= 0.3:
        return "positive"
    if score <= -0.3:
        return "negative"
    return "neutral"


def _parse_shmet_bracket_title(content: str) -> tuple:
    """解析 shmet 快讯格式: 【标题】正文"""
    if not content:
        return ("", "")
    s = str(content).strip()
    if s.startswith("【") and "】" in s:
        end = s.index("】")
        title = s[1:end].strip()
        body = s[end + 1:].strip()
        return (title, body)
    return ("", s)


# 每个 category 调用的新闻生成器函数入口(仅保留 global_macro)
_NEWS_GENERATORS = {
    "global_macro": {
        "func": "_synth_global_macro_news",
        "label": "全球宏观",
        "supported_funcs": [
            "stock_info_cjzc_em",
            "stock_info_global_em",
            "stock_info_global_futu",
            "stock_info_global_ths",
            "stock_info_global_sina",
            "stock_info_global_cls",
        ],
    },
}


async def _safe_call(provider, func_name: str, *args, **kwargs):
    """在 executor 中调用 AKShare 接口并吞错(返回 None)。

    新增 15s 超时保护:防止 stock_info_* 等全球宏观资讯源因对端挂死
    导致整个 news ingestion worker 卡住(2026-07-20 事件:
    global_macro gather 整体被一个 stock_info_* 端点阻塞 24h+)。
    """
    if not await provider._ensure_ak():
        return None
    func = getattr(provider._ak, func_name, None)
    if func is None:
        return None
    try:
        loop = asyncio.get_event_loop()
        fut = loop.run_in_executor(
            None, lambda: func(*args, **kwargs)
        )
        return await asyncio.wait_for(fut, timeout=15.0)
    except (asyncio.TimeoutError, Exception):
        return None


# =============================================================================
# 全球宏观资讯流(global_macro 类别)
# --------------------------------------------------------------------------
# 聚合 6 个 AKShare 资讯源,字段差异:
#   标题/摘要/发布时间/链接: stock_info_cjzc_em (财经早餐)
#   标题/摘要/发布时间/链接: stock_info_global_em (东财全球快讯)
#   标题/内容/发布时间/链接: stock_info_global_futu (富途牛牛)
#   标题/内容/发布时间/链接: stock_info_global_ths (同花顺)
#   标题/内容/发布日期/发布时间: stock_info_global_cls (财联社,可能网络受限)
#   时间/内容 (无标题、无链接): stock_info_global_sina (新浪)
# =============================================================================

from datetime import datetime as _dt
import re as _re


def _parse_global_macro_time(s: str) -> _dt:
    """宽松解析全球宏观源的时间字符串(标准 ISO / 时间-only / 日期+时间)"""
    s = str(s or "").strip()
    if not s:
        return _dt.min
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
    )
    for fmt in formats:
        try:
            return _dt.strptime(s, fmt)
        except ValueError:
            continue
    # 只有时间(财联社的"发布时间")
    m = _re.match(r"^(\d{1,2}):(\d{2}):(\d{2})$", s)
    if m:
        return _dt.now().replace(
            hour=int(m.group(1)),
            minute=int(m.group(2)),
            second=int(m.group(3)),
            microsecond=0,
        )
    return _dt.min


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


class AkshareFuturesProvider(BaseCommodityDataProvider):
    """AKShare 国内期货数据源(行情 + 手续费/库存/基差/持仓/合约信息)"""

    def __init__(self):
        super().__init__("akshare_futures")
        self._ak = None
        self._cache = None  # 延时加载 CommodityCacheManager

    async def connect(self) -> bool:
        """延迟加载 akshare(避免启动时强依赖)"""
        if self.connected:
            return True
        try:
            import akshare as ak
            self._ak = ak
            self.connected = True
            # 延时加载缓存管理器
            if self._cache is None:
                from tradingagents.dataflows.cache.commodity_cache import CommodityCacheManager
                self._cache = CommodityCacheManager()
            self.logger.info("✅ AkshareFuturesProvider 连接成功(懒加载)")
            return True
        except ImportError as e:
            self.logger.error(f"❌ akshare 未安装: {e}")
            return False

    async def _ensure_ak(self) -> bool:
        """确保 akshare 已加载(供所有同步方法使用)

        短路条件:
        - 如果 self._ak 已被设置(mocks / 子类手动注入),
          直接返回 True,避免 connect() 用真实 akshare 覆盖它。
        """
        if self._ak is not None:
            return True
        if not self.connected:
            await self.connect()
        if not self._ak:
            self.logger.warning("❌ akshare 不可用,操作跳过")
            return False
        return True

    async def _call(self, func_name: str, *args, **kwargs) -> Any:
        """在 executor 中执行同步的 akshare 函数"""
        if not await self._ensure_ak():
            return None
        func = getattr(self._ak, func_name, None)
        if func is None:
            self.logger.warning(f"⚠️ AKShare 不提供接口: {func_name}")
            return None
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: func(*args, **kwargs)
            )
        except Exception as e:
            self.logger.warning(f"❌ AKShare.{func_name} 执行失败: {e}")
            return None

    async def _call_roll_yield(self, func_name: str, *args, **kwargs) -> Any:
        """展期收益率接口的容错调用包装。

        AKShare get_roll_yield_bar/get_roll_yield 内部调用了 get_futures_daily，
        部分交易日/交易所源站不可用时会抛出异常或返回空数据。做多层容错。
        """
        result = await self._call(func_name, *args, **kwargs)
        if result is not None and not (hasattr(result, 'empty') and result.empty):
            return result
        # 尝试前一个交易日
        if "date" in kwargs:
            from datetime import timedelta
            orig = datetime.strptime(str(kwargs["date"]), "%Y%m%d")
            for days_back in (1, 2, 3, 5, 7):
                prev = (orig - timedelta(days=days_back)).strftime("%Y%m%d")
                new_kwargs = {**kwargs, "date": prev}
                r = await self._call(func_name, *args, **new_kwargs)
                if r is not None and not (hasattr(r, 'empty') and r.empty):
                    self.logger.info(f"ℹ️ roll_yield 回退到 {prev}")
                    return r
        return None

    # ============================================================
    # Phase 1 基础接口
    # ============================================================

    async def get_commodity_basic_info(
        self, full_symbol: str = None
    ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """
        获取商品基础信息

        Phase 2: 当 full_symbol 为 None 时,调用 AKShare 接口动态拉取
        全品种的合约信息(覆盖全交易所)。

        Args:
            full_symbol: 完整代码,如 CU2501.SHF。空则返回全品种合约列表
        """
        if full_symbol:
            return self._build_basic_info(full_symbol)

        # Phase 2:全品种列表
        contracts = await self.list_all_varieties()
        return contracts or []

    async def list_all_varieties(self) -> List[Dict[str, Any]]:
        """
        列出所有品种(整合 commodity_metadata 静态表 + AKShare 动态合约信息)

        Returns:
            品种字典列表,每项含 symbol / name / exchange / category / unit /
            contract_size / tick_size / list_date 等
        """
        from tradingagents.dataflows.providers.commodity.commodity_metadata import (
            list_varieties as _list_varieties,
        )
        items: List[Dict[str, Any]] = []
        # 1) 静态元数据(必返回,即使 AKShare 失败)
        for v in _list_varieties():
            items.append({
                "type": "variety",
                "code": v["symbol"],
                "symbol": v["symbol"],
                "name": v["name_cn"],
                "exchange": v["exchange"],
                "exchange_name": _EXCHANGE_NAMES.get(
                    {"SHFE": "SHF", "INE": "INE", "DCE": "DCE",
                     "CZCE": "CZC", "GFEX": "GFEX",
                     "CFFEX": "CFFEX"}.get(v["exchange"], ""),
                    "未知交易所",
                ),
                "category": v["category"],
                "unit": v["unit"],
                "contract_size": v["contract_size"],
                "tick_size": v["tick_size"],
                "list_date": v["list_date"],
                "is_china_futures": True,
                "data_source": "akshare_futures",
                "data_version": 1,
                "updated_at": _now_iso(),
            })
        self.logger.info(f"✅ 品种静态元数据: {len(items)} 个")
        return items

    async def get_commodity_quotes(self, full_symbol: str) -> Optional[Dict[str, Any]]:
        """获取实时行情(取最近一根日线作为报价)。

        - 如果 full_symbol 含 YYMM(如 CU2501.SHF):用 futures_hist_em 取具体合约最新日线
        - 如果 full_symbol 不含 YYMM(CU0.SHF):用 futures_main_sina 取主力连续最新日线
        - Fallback:具体合约无数据(已到期/退市)时,自动回退到主力连续(<underlying>0.<exch>)
          并在响应里标记 ``used_continuous_fallback=True`` 与 ``data_source`` 改为
          ``akshare_futures+continuous_fallback``,便于上游识别与排查。
        """
        # ── Layer 1 内存缓存(30秒TTL) ──
        cache_key = f"quotes:{full_symbol}"
        if self._cache:
            cached = self._cache.mem.get(cache_key)
            if cached is not None:
                return cached

        if not await self._ensure_ak():
            return None

        symbol = self._strip_exchange(full_symbol)
        data_source = "akshare_futures"
        used_continuous_fallback = False

        if self._has_yyymm(full_symbol):
            # 具体合约:使用东财个人合约历史接口,取最新 bar
            today = date.today().strftime("%Y%m%d")
            df = await self._call(
                "futures_hist_em",
                symbol=symbol.lower(),
                period="daily",
                start_date="20200101",
                end_date=today,
            )
            date_col = "日期"
            if df is None or df.empty:
                # Fallback:具体合约无行情(已到期/退市),回退到主力连续
                df = await self._try_continuous_fallback(full_symbol)
                if df is not None and not df.empty:
                    used_continuous_fallback = True
                    data_source = "akshare_futures+continuous_fallback"
            if df is None or df.empty:
                return None
            df = self._normalize_hist_em_df(df)
            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else last
        else:
            # 主力连续:使用新浪主力连续接口(原逻辑)
            # 注意: symbol 可能为裸品种代码(如 CU),futures_main_sina 需要 CU0 格式
            main_symbol = symbol
            if not main_symbol.endswith("0"):
                u = CommodityUtils.get_underlying_symbol(full_symbol)
                if u:
                    main_symbol = u + "0"
            df = await self._call("futures_main_sina", symbol=main_symbol)
            if df is None or df.empty:
                return None
            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else last
            date_col = "日期"

        info = self._build_basic_info(full_symbol) or {}
        close = float(last.get("收盘价", 0) or 0)
        pre_close = float(prev.get("收盘价", 0) or 0)
        settlement_price = float(last.get("动态结算价", 0) or 0)
        change = close - pre_close
        pct_chg = (change / pre_close * 100) if pre_close else 0.0

        result = {
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
            "trade_date": str(last.get(date_col, "")),
            "data_source": data_source,
            "used_continuous_fallback": used_continuous_fallback,
            "updated_at": _now_iso(),
        }
        # ── 写入内存缓存(30秒TTL) ──
        if self._cache:
            self._cache.mem.set(cache_key, result, ttl_sec=30.0)
        return result

    async def get_historical_data(
        self,
        full_symbol: str,
        start_date: Union[str, date],
        end_date: Union[str, date] = None,
        adjustment_mode: str = "none",
    ) -> Optional[pd.DataFrame]:
        """获取历史 K 线(日线)。

        - 如果 full_symbol 含 YYMM(如 CU2501.SHF):用 futures_hist_em 取具体合约数据
        - 如果 full_symbol 不含 YYMM(CU0.SHF / CU.SHF):用 futures_main_sina 取主力连续
        - Fallback:具体合约无数据(已到期/退市)时,自动回退到主力连续。
          返回的 DataFrame 会带 ``data_source_note = "continuous_fallback"`` 元数据
          (存放在 ``df.attrs["data_source_note"]``)。

        Args:
            adjustment_mode: 复权模式
                "none" — 原始数据,含 rollover_date 换月标记列
                "back" — 后复权(向前调整)
                "forward" — 前复权(向后调整)
        """
        # ── Layer 2+1: Parquet + 内存缓存 ──
        underlying = CommodityUtils.get_underlying_symbol(full_symbol)
        if underlying and self._cache:
            sd = start_date.strftime("%Y%m%d") if isinstance(start_date, date) else str(start_date).replace("-", "")
            ed = end_date.strftime("%Y%m%d") if end_date and isinstance(end_date, date) else str(end_date or "20500101").replace("-", "")
            # 提取交易所前缀
            mkt = full_symbol.split(".")[-1].upper() if "." in full_symbol else ""
            mkt_long = {"SHF": "SHFE", "CZC": "CZCE"}.get(mkt, mkt)
            # 先尝试 Parquet 文件缓存
            cached = self._cache.get_historical(underlying, sd, ed, mkt_long)
            if cached is not None and not cached.empty:
                self.logger.debug("📂 历史 K 线缓存命中: %s [%s ~ %s]", underlying, sd, ed)
                return cached

        if not await self._ensure_ak():
            return None

        symbol = self._strip_exchange(full_symbol)
        used_continuous_fallback = False

        if self._has_yyymm(full_symbol):
            # 具体合约:使用东财个人合约历史接口
            sd = start_date.strftime("%Y%m%d") if isinstance(start_date, date) else start_date.replace("-", "")
            ed = end_date.strftime("%Y%m%d") if end_date and isinstance(end_date, date) else ""
            if not ed:
                ed = end_date.replace("-", "") if end_date else "20500101"
            df = await self._call("futures_hist_em", symbol=symbol.lower(), period="daily", start_date=sd, end_date=ed)
            if df is None or df.empty:
                # Fallback:具体合约无数据,回退到主力连续
                df = await self._try_continuous_fallback(full_symbol)
                if df is not None and not df.empty:
                    used_continuous_fallback = True
            if df is None or df.empty:
                return None
            if not used_continuous_fallback:
                df = self._normalize_hist_em_df(df)
                # 具体合约无换月问题,rollover_date 全 false
                df["rollover_date"] = False
            else:
                # 主力连续路径:保留换月点/复权处理(与 else 分支一致)
                df["日期"] = pd.to_datetime(df["日期"]).dt.date
                df = df.sort_values("日期").reset_index(drop=True)
                df = self._mark_rollover_dates(df)
                if adjustment_mode in ("back", "forward") and df["rollover_date"].any():
                    df = self._apply_adjustment(df, mode=adjustment_mode)
            start = pd.to_datetime(start_date).date() if isinstance(start_date, str) else start_date
            if end_date is None:
                end = df["日期"].max() if "日期" in df.columns else date.today()
            elif isinstance(end_date, str):
                end = pd.to_datetime(end_date).date()
            else:
                end = end_date
            df = df[(df["日期"] >= start) & (df["日期"] <= end)]
            df = df.sort_values("日期").reset_index(drop=True)
            if used_continuous_fallback:
                df.attrs["data_source_note"] = "continuous_fallback"
            # ── 写入 Parquet 缓存 ──
            if underlying and self._cache:
                self._cache.save_historical(underlying, sd, ed, mkt_long, df)
            return df
        else:
            # 主力连续:使用新浪主力连续接口
            # 注意: symbol 可能为裸品种代码(如 CU),futures_main_sina 需要 CU0 格式
            main_symbol = symbol
            if not main_symbol.endswith("0"):
                u = CommodityUtils.get_underlying_symbol(full_symbol)
                if u:
                    main_symbol = u + "0"
            df = await self._call("futures_main_sina", symbol=main_symbol)
            if df is None or df.empty:
                return None

            df["日期"] = pd.to_datetime(df["日期"]).dt.date
            df = df.sort_values("日期").reset_index(drop=True)

            # 检测换月点并标记
            df = self._mark_rollover_dates(df)

            # 复权处理
            if adjustment_mode in ("back", "forward") and df["rollover_date"].any():
                df = self._apply_adjustment(df, mode=adjustment_mode)

            start = pd.to_datetime(start_date).date() if isinstance(start_date, str) else start_date
            if end_date is None:
                end = df["日期"].max()
            elif isinstance(end_date, str):
                end = pd.to_datetime(end_date).date()
            else:
                end = end_date

            df = df[(df["日期"] >= start) & (df["日期"] <= end)]
            df = df.sort_values("日期").reset_index(drop=True)
            # ── 写入 Parquet 缓存 ──
            if underlying and self._cache:
                self._cache.save_historical(underlying, sd, ed, mkt_long, df)
            return df

    async def get_historical_data_for_index(
        self,
        underlying: str,
        start_date: Union[str, date],
        end_date: Union[str, date] = None,
    ) -> Optional[pd.DataFrame]:
        """获取品种指数连续合约历史K线(99 代码)。

        指数连续合约 = 当前品种全部可交易合约以累计持仓量为权重加权平均得到。
        优先尝试 futures_main_sina(99 代码); 商品期货无 99 代码时,
        通过 get_futures_daily 获取交易所官方指数数据。

        Args:
            underlying: 品种代码, 如 "IF" / "CU"
            start_date: 起始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD(默认到最新)

        Returns:
            DataFrame(列名: 日期/开盘价/最高价/最低价/收盘价/成交量/持仓量)
            或 None(指数不可用)
        """
        if not await self._ensure_ak():
            return None

        from tradingagents.dataflows.providers.commodity.commodity_metadata import (
            get_index_symbol, get_variety,
        )

        index_code = get_index_symbol(underlying)
        if index_code is not None:
            # 金融期货:有标准 99 代码,用 futures_main_sina 获取
            df = await self._call("futures_main_sina", symbol=index_code)
            if df is not None and not df.empty:
                df["日期"] = pd.to_datetime(df["日期"]).dt.date
                df = df.sort_values("日期").reset_index(drop=True)
                # 日期过滤
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

        # 无标准 99 代码 → 尝试通过 get_futures_daily 获取交易所官方指数
        variety_meta = get_variety(underlying.upper())
        if not variety_meta:
            return None
        exchange = variety_meta.get("exchange", "")
        exchange_market_map = {"SHFE": "SHFE", "INE": "INE", "DCE": "DCE",
                               "CZCE": "CZCE", "GFEX": "GFEX", "CFFEX": "CFFEX"}
        market = exchange_market_map.get(exchange)
        if not market:
            return None

        start = start_date if isinstance(start_date, str) else start_date.strftime("%Y%m%d")
        start = start.replace("-", "") if "-" in start else start
        end = end_date if end_date else date.today().strftime("%Y%m%d")
        if isinstance(end, date):
            end = end.strftime("%Y%m%d")
        end = end.replace("-", "") if isinstance(end, str) and "-" in end else end

        df_all = await self._call("get_futures_daily", start_date=start, end_date=end, market=market)
        if df_all is None or df_all.empty:
            return None

        # 过滤该品种的 99 指数合约(如 CU99 / RB99)
        var_upper = underlying.upper()
        index_pattern = rf"^{var_upper}99$"
        match_col = None
        for col in ["symbol", "合约", "合约代码"]:
            if col in df_all.columns:
                match_col = col
                break
        if match_col is None:
            return None

        index_rows = df_all[df_all[match_col].astype(str).str.upper().str.match(index_pattern)]
        if index_rows.empty:
            return None

        # 重命名为标准列
        date_col = "date" if "date" in df_all.columns else ("日期" if "日期" in df_all.columns else None)
        if date_col is None:
            return None

        col_map = {
            date_col: "日期",
            "open": "开盘价", "open_": "开盘价",
            "high": "最高价", "high_": "最高价",
            "low": "最低价", "low_": "最低价",
            "close": "收盘价", "close_": "收盘价",
            "volume": "成交量", "volume_": "成交量",
            "open_interest": "持仓量", "oi": "持仓量",
        }
        # 映射列
        rename = {}
        for c in index_rows.columns:
            cl = c.lower().replace(" ", "_")
            if cl in col_map:
                rename[c] = col_map[cl]
        rename_cols = {k: v for k, v in rename.items() if k != v}

        result = index_rows.rename(columns=rename_cols)
        result["日期"] = pd.to_datetime(result["日期"], errors="coerce")
        result = result.dropna(subset=["日期"])

        std_cols = ["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "持仓量"]
        available = [c for c in std_cols if c in result.columns]
        result = result[available]

        # 日期过滤
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date) if end_date else pd.Timestamp.today()
        result = result[(result["日期"] >= start_dt) & (result["日期"] <= end_dt)]

        result = result.sort_values("日期").reset_index(drop=True)
        result["日期"] = result["日期"].dt.date
        self.logger.info(f"✅ index 从交易所日线获得({underlying}, {len(result)}行)")
        return result

    # ============================================================
    # Phase 2 扩展接口
    # ============================================================

    async def get_fees_and_margin(
        self,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        date: Optional[str] = None,
    ) -> Optional[Union[List[Dict[str, Any]], Dict[str, Any]]]:
        """
        获取手续费 / 保证金 / 涨跌停板数据。

        优先级:
        1. futures_comm_info(symbol=交易所中文名) -- 九期网综合数据(包含手续费、涨跌停、保证金率)
        2. futures_settle(date=…, market=…) -- 交易所结算参数(投机/套保保证金率)
        3. futures_fees_info() -- OpenCTP 全交易所综合(openctp 一次性返回 769 行)

        Args:
            exchange: 交易所代码 SHFE/DCE/CZCE/INE/GFEX/CFFEX,空则取全部
            symbol: 品种代码(暂未用作过滤;comprehensive 表一次性返回更稳)
            date: 交易日 YYYYMMDD,空则用今天
        """
        if not await self._ensure_ak():
            return None

        # 1. futures_comm_info(全交易所汇总)
        if exchange:
            cn_name = _COMM_INFO_EXCHANGE_MAP.get(exchange.upper())
            if cn_name:
                df = await self._call("futures_comm_info", symbol=cn_name)
                if df is not None and not df.empty:
                    return df.to_dict(orient="records")

        # 2. futures_comm_js(单日手续费,金十)
        if not exchange and date:
            df = await self._call("futures_comm_js", date=date)
            if df is not None and not df.empty:
                return df.to_dict(orient="records")

        # 3. 全交易所综合(openctp):一次性 ~769 行
        df_all = await self._call("futures_fees_info")
        if df_all is not None and not df_all.empty:
            return df_all.to_dict(orient="records")

        # 4. futures_settle(单交易所)
        if exchange:
            market = _SETTLE_MARKET_MAP.get(exchange.upper())
            if market and market != "DCE":  # AKShare DCE 不支持 futures_settle
                settle_date = date or datetime.utcnow().strftime("%Y%m%d")
                df = await self._call("futures_settle", date=settle_date, market=market)
                if df is not None and not df.empty:
                    return df.to_dict(orient="records")

        return None

    async def get_inventory(
        self,
        symbol: str,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
    ) -> Optional[pd.DataFrame]:
        """
        获取库存数据。
        优先用东方财富(futures_inventory_em, 60 天近窗口),
        回退用 99 期货网(futures_inventory_99, 长期)。

        Args:
            symbol: 品种代码,如 'A' / '豆一'
            start_date / end_date: 仅 99 期货网支持,em 接口固定返回近 60 个交易日
        """
        # ── Layer 2+1: Parquet + 内存缓存 ──
        if self._cache:
            cached = self._cache.get_inventory(symbol)
            if cached is not None and not cached.empty:
                self.logger.debug("📂 库存缓存命中: %s (%d 行)", symbol, len(cached))
                # 按日期范围过滤
                if start_date:
                    s = pd.to_datetime(start_date)
                    cached = cached[cached.iloc[:, 0] >= s] if cached.shape[1] > 0 and hasattr(cached.iloc[:, 0], 'dtype') else cached
                if end_date:
                    e = pd.to_datetime(end_date)
                    cached = cached[cached.iloc[:, 0] <= e] if cached.shape[1] > 0 and hasattr(cached.iloc[:, 0], 'dtype') else cached
                if not cached.empty:
                    return cached

        if not await self._ensure_ak():
            return None

        # 1. 东方财富(支持代码或中文名;先代码后中文)
        df = await self._call("futures_inventory_em", symbol=symbol)
        if df is not None and not df.empty:
            # ── 写入缓存 ──
            if self._cache:
                self._cache.save_inventory(symbol, df)
            return df

        # 2. 东方财富(中文名,部分品种代码不识别)
        cn = self._symbol_to_chinese(symbol) or symbol
        if cn != symbol:
            df = await self._call("futures_inventory_em", symbol=cn)
            if df is not None and not df.empty:
                if self._cache:
                    self._cache.save_inventory(symbol, df)
                return df

        # 3. 99 期货(需精确中文名,已备 99qh 映射表兜底)
        df = await self._call("futures_inventory_99", symbol=cn)
        if df is not None and not df.empty:
            if self._cache:
                self._cache.save_inventory(symbol, df)
            return df

        # 4. 尝试原始传入的符号(兼容已传入中文名)
        if cn != symbol:
            df = await self._call("futures_inventory_99", symbol=symbol)
            if df is not None and not df.empty and self._cache:
                self._cache.save_inventory(symbol, df)
            return df

        return None

    async def get_warehouse_receipt(
        self,
        exchange: str,
        date: Union[str, date],
    ) -> Optional[Dict[str, pd.DataFrame]]:
        """
        获取仓单日报。

        Args:
            exchange: 交易所代码,支持 SHFE / DCE / CZCE / GFEX
            date: 交易日
        """
        if not await self._ensure_ak():
            return None

        date_str = date.strftime("%Y%m%d") if hasattr(date, "strftime") else str(date)

        ex = exchange.upper()
        if ex == "SHFE":
            df = await self._call("futures_shfe_warehouse_receipt", date=date_str)
            if df is not None:
                if isinstance(df, dict):
                    return df
                # 空 dict 或空 DataFrame 也返回空
                if hasattr(df, 'empty') and df.empty:
                    return None
                return {"data": df}
            return None
        if ex == "DCE":
            df = await self._call("futures_warehouse_receipt_dce", date=date_str)
            if df is not None:
                return {"data": df}
            return None
        if ex in ("CZCE", "CZC"):
            return await self._call("futures_warehouse_receipt_czce", date=date_str)
        if ex == "GFEX":
            return await self._call("futures_gfex_warehouse_receipt", date=date_str)

        self.logger.warning(f"⚠️ 不支持的交易所: {exchange}")
        return None

    async def get_position_rank(
        self,
        exchange: str,
        date: Union[str, date],
        vars_list: Optional[List[str]] = None,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, pd.DataFrame]]:
        """
        获取会员持仓排名。

        在线获取失败时回退到本地缓存数据库 (CommodityLocalCacheAdapter)。

        Args:
            exchange: 交易所代码 DCE / GFEX / SHFE / CFFEX / CZCE
            date: 交易日
            vars_list: 品种代码列表(部分接口可选过滤)
            symbol: 品种代码(可选,用于本地缓存回退的品种过滤)
        """
        if not await self._ensure_ak():
            return None

        date_str = date.strftime("%Y%m%d") if hasattr(date, "strftime") else str(date)

        ex = exchange.upper()
        result = None
        if ex == "DCE":
            kwargs = {"date": date_str}
            if vars_list:
                kwargs["vars_list"] = vars_list
            result = await self._call("futures_dce_position_rank", **kwargs)
        elif ex == "GFEX":
            kwargs = {"date": date_str}
            if vars_list:
                kwargs["vars_list"] = vars_list
            result = await self._call("futures_gfex_position_rank", **kwargs)
        elif ex == "SHFE":
            result = await self._call("get_shfe_rank_table", date=date_str)
        elif ex == "INE":
            # 上期能源(INE)与上期所共用 SHFE 持仓排名接口
            result = await self._call("get_shfe_rank_table", date=date_str)
        elif ex == "CFFEX":
            result = await self._call("get_cffex_rank_table", date=date_str)
        elif ex in ("CZCE", "CZC"):
            result = await self._call("get_rank_table_czce", date=date_str)
        else:
            self.logger.warning(f"⚠️ 不支持的交易所: {exchange}")
            return None

        if result is not None:
            # AKShare 返回 Dict[contract, DataFrame] 或 DataFrame
            if isinstance(result, dict):
                if any(not v.empty for v in result.values()):
                    return result
            elif isinstance(result, pd.DataFrame) and not result.empty:
                return result

        # AKShare 返回空 → 回退到本地缓存
        # symbol 可以是品种代码(如 CU)或 None
        sym = symbol or (vars_list[0] if vars_list else None)
        if sym:
            try:
                from tradingagents.dataflows.providers.commodity.local_cache_adapter import (
                    CommodityLocalCacheAdapter,
                )
                cache = CommodityLocalCacheAdapter()
                df = cache.read_positioning(sym)
                if df is not None and not df.empty:
                    return df
            except Exception:
                pass

        self.logger.warning(f"⚠️ get_position_rank({exchange}, {date_str}) 在线+本地缓存均无数据")
        return None

    async def get_registered_receipt(
        self,
        start_date: Union[str, date],
        end_date: Union[str, date],
        vars_list: List[str],
    ) -> Optional[pd.DataFrame]:
        """
        获取注册仓单(AKShare get_receipt)。

        Args:
            start_date / end_date: 日期范围
            vars_list: 品种代码列表,如 ['CU', 'NI']
        """
        if not await self._ensure_ak():
            return None

        start = start_date.strftime("%Y%m%d") if hasattr(start_date, "strftime") else str(start_date)
        end = end_date.strftime("%Y%m%d") if hasattr(end_date, "strftime") else str(end_date)
        return await self._call(
            "get_receipt", start_date=start, end_date=end, vars_list=vars_list,
        )

    async def get_spot_price(
        self,
        date: Union[str, date],
        symbol: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """
        获取某交易日现货价格 + 基差。

        改用 futures_spot_price_daily (避开 100ppi.com) 避免超时。
        在 date 参数基础上取前后各 3 天窗口以增加命中率。
        在线失败时回退到本地缓存数据库 (CommodityLocalCacheAdapter)。
        """
        # 统一日期格式
        if hasattr(date, "strftime"):
            date_str = date.strftime("%Y%m%d")
            base_date = date.strftime("%Y-%m-%d")
        else:
            raw = str(date).replace("-", "")
            date_str = raw
            base_date = raw[:4] + "-" + raw[4:6] + "-" + raw[6:8]

        # ── Layer 2+1: Parquet 缓存 ──
        cache_key = f"spot:{date_str}"
        if self._cache:
            cached = self._cache.get_spot_price(date_str)
            if cached is not None and not cached.empty:
                self.logger.debug("📂 现货基差缓存命中: %s", date_str)
                if symbol:
                    cached = cached[cached["symbol"].astype(str).str.upper() == symbol.upper()]
                if not cached.empty:
                    return cached

        if not await self._ensure_ak():
            return None

        # 1. 用 futures_spot_price_daily 取前后 3 天窗口(避免节假日偏移)
        from datetime import timedelta
        dt = pd.to_datetime(base_date)
        start_win = (dt - timedelta(days=3)).strftime("%Y%m%d")
        end_win = (dt + timedelta(days=3)).strftime("%Y%m%d")

        vars_param = [symbol.upper()] if symbol else None
        result = None
        try:
            result = await asyncio.wait_for(
                self._call(
                    "futures_spot_price_daily",
                    start_day=start_win, end_day=end_win, vars_list=vars_param,
                ),
                timeout=10,
            )
        except (asyncio.TimeoutError, Exception):
            pass

        if result is not None and not (hasattr(result, 'empty') and result.empty):
            # 只返回最接近 date 的那一天
            if "date" in result.columns:
                result["date"] = pd.to_datetime(result["date"], errors="coerce")
                target = pd.to_datetime(base_date)
                result = result.iloc[(result["date"] - target).abs().argsort()[:1]]
            # ── 写入 Parquet 缓存 ──
            if self._cache and not result.empty:
                self._cache.save_spot_price(date_str, result)
            return result

        # 2. 用 99qh 现货走势作为在线回退
        if symbol:
            cn_name = self._symbol_to_chinese(symbol) or symbol
            try:
                df_spot = await asyncio.wait_for(
                    self._call("spot_price_qh", symbol=cn_name),
                    timeout=10,
                )
                if df_spot is not None and not df_spot.empty:
                    df_spot = df_spot.rename(columns={
                        "日期": "date",
                        "现货价格": "spot_price",
                        "期货收盘价": "dominant_contract_price",
                    })
                    df_spot["symbol"] = symbol.upper()
                    if "date" in df_spot.columns:
                        df_spot["date"] = pd.to_datetime(df_spot["date"], errors="coerce")
                    # 返回最接近 date 的行
                    target = pd.to_datetime(base_date)
                    df_spot = df_spot.iloc[(df_spot["date"] - target).abs().argsort()[:1]]
                    self.logger.info(f"✅ spot_price 回退到 99qh 成功({symbol})")
                    return df_spot
            except Exception:
                pass

        # 3. 回退到本地缓存
        try:
            from tradingagents.dataflows.providers.commodity.local_cache_adapter import (
                CommodityLocalCacheAdapter,
            )
            cache = CommodityLocalCacheAdapter()
            sym = symbol or ""
            df = cache.read_basis(sym)
            if df is not None and not df.empty:
                target = pd.to_datetime(base_date)
                df = df.iloc[(df["date"] - target).abs().argsort()[:1]]
                return df
        except Exception:
            pass

        return None

    async def get_basis_spot_previous(
        self,
        date: Union[str, date],
    ) -> Optional[pd.DataFrame]:
        """
        获取某交易日的历史基差汇总(AKShare: futures_spot_price_previous)。
        含品种 / 现货价格 / 主力合约代码 / 主力变动百分比 /
        180 日内主力基差最高 / 最低 / 平均。
        """
        if not await self._ensure_ak():
            return None

        date_str = date.strftime("%Y%m%d") if hasattr(date, "strftime") else str(date)
        return await self._call("futures_spot_price_previous", date_str)

    async def get_basis_history(
        self,
        start_day: Union[str, date],
        end_day: Union[str, date],
        vars_list: List[str],
    ) -> Optional[pd.DataFrame]:
        """
        获取某段时间的基差值(AKShare: futures_spot_price_daily)。

        AKShare 内部可能依赖 100ppi.com 导致超时,故 AKShare 调用设
        10 秒内部超时,超时后立即回退到本地缓存数据库 (CommodityLocalCacheAdapter)。
        """
        start = start_day.strftime("%Y%m%d") if hasattr(start_day, "strftime") else str(start_day)
        end = end_day.strftime("%Y%m%d") if hasattr(end_day, "strftime") else str(end_day)

        # ── Layer 2+1: Parquet 缓存 ──
        _var = vars_list[0].upper() if vars_list else ""
        if _var and self._cache:
            cached = self._cache.get_basis(_var, start, end)
            if cached is not None and not cached.empty:
                self.logger.debug("📂 基差历史缓存命中: %s [%s~%s]", _var, start, end)
                return cached

        if not await self._ensure_ak():
            return None
        # AKShare 在线调用(最多等 10 秒)
        result = None
        try:
            result = await asyncio.wait_for(
                self._call(
                    "futures_spot_price_daily",
                    start_day=start, end_day=end, vars_list=vars_list,
                ),
                timeout=10,
            )
        except (asyncio.TimeoutError, Exception):
            pass

        if result is not None and not (hasattr(result, 'empty') and result.empty):
            # ── 写入 Parquet 缓存 ──
            if _var and self._cache:
                self._cache.save_basis(_var, start, end, result)
            return result

        # AKShare 100ppi 超时/空 → 2. 用 99qh 现货走势(spot_price_qh)作为在线回退
        # spot_price_qh 不限 100ppi.com,来自 99qh.com,速度快不超时
        if vars_list:
            sym_99qh = vars_list[0] if isinstance(vars_list, list) else vars_list
            cn_name = self._symbol_to_chinese(sym_99qh) or sym_99qh
            try:
                df_99qh = await asyncio.wait_for(
                    self._call("spot_price_qh", symbol=cn_name),
                    timeout=10,
                )
                if df_99qh is not None and not df_99qh.empty:
                    # 标准化列名: 日期/期货收盘价(作主力合约价)/现货价格
                    df_99qh = df_99qh.rename(columns={
                        "日期": "date",
                        "现货价格": "spot_price",
                        "期货收盘价": "dominant_contract_price",
                    })
                    df_99qh["symbol"] = sym_99qh
                    df_99qh["near_contract_price"] = df_99qh["dominant_contract_price"]
                    if "date" in df_99qh.columns:
                        df_99qh["date"] = pd.to_datetime(df_99qh["date"], errors="coerce")
                    # 按日期过滤
                    start_dt = pd.to_datetime(start_day)
                    end_dt = pd.to_datetime(end_day)
                    df_99qh = df_99qh[(df_99qh["date"] >= start_dt) & (df_99qh["date"] <= end_dt)]
                    if not df_99qh.empty:
                        df_99qh = df_99qh.sort_values("date").reset_index(drop=True)
                        self.logger.info(f"✅ basis 回退到 99qh 成功({sym_99qh}, {len(df_99qh)}行)")
                        # ── 写入 Parquet 缓存 ──
                        if _var and self._cache:
                            self._cache.save_basis(_var, start, end, df_99qh)
                        return df_99qh
            except Exception:
                pass

        # 3. 回退本地缓存
        if vars_list:
            sym = vars_list[0] if isinstance(vars_list, list) else vars_list
            try:
                from tradingagents.dataflows.providers.commodity.local_cache_adapter import (
                    CommodityLocalCacheAdapter,
                )
                cache = CommodityLocalCacheAdapter()
                df = cache.read_basis(sym)
                if df is not None and not df.empty:
                    # 按日期过滤
                    start_dt = pd.to_datetime(start_day)
                    end_dt = pd.to_datetime(end_day)
                    df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)]
                    return df
            except Exception:
                pass

        return None

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
        获取展期收益率。

        type_method 取值:
        - "date": 某品种在不同日期的主力/次主力价差 -- 需要 var + start_day + end_day
        - "symbol": 某品种在某天的所有交割月合约价格 -- 需要 var + date
        - "var": 某交易日所有品种的主力/次主力展期收益率 -- 需要 date

        AKShare 在线调用设 10 秒内部超时,超时后回退到本地缓存数据库。
        """
        # ── 构建缓存 key ──
        if type_method == "date" and var and start_day and end_day:
            s = start_day.strftime("%Y%m%d") if hasattr(start_day, "strftime") else str(start_day)
            e = end_day.strftime("%Y%m%d") if hasattr(end_day, "strftime") else str(end_day)
            cache_key = f"roll_yield:date:{var.upper()}:{s}:{e}"
            if self._cache:
                cached = self._cache.get_roll_yield(cache_key)
                if cached is not None and not cached.empty:
                    self.logger.debug("📂 展期收益率缓存命中: %s", cache_key)
                    return cached

        if not await self._ensure_ak():
            return None

        result = None
        try:
            if type_method == "date":
                start = start_day.strftime("%Y%m%d") if hasattr(start_day, "strftime") else str(start_day)
                end = end_day.strftime("%Y%m%d") if hasattr(end_day, "strftime") else str(end_day)
                result = await asyncio.wait_for(
                    self._call_roll_yield(
                        "get_roll_yield_bar",
                        type_method="date", var=var, start_day=start, end_day=end,
                    ),
                    timeout=10,
                )
            elif type_method == "symbol":
                date_str = date.strftime("%Y%m%d") if hasattr(date, "strftime") else str(date)
                result = await asyncio.wait_for(
                    self._call_roll_yield(
                        "get_roll_yield_bar", type_method="symbol", var=var, date=date_str,
                    ),
                    timeout=10,
                )
            elif type_method == "var":
                date_str = date.strftime("%Y%m%d") if hasattr(date, "strftime") else str(date)
                result = await asyncio.wait_for(
                    self._call_roll_yield(
                        "get_roll_yield_bar", type_method="var", date=date_str,
                    ),
                    timeout=10,
                )
            elif symbol1 and symbol2:
                date_str = date.strftime("%Y%m%d") if hasattr(date, "strftime") else str(date)
                result = await asyncio.wait_for(
                    self._call_roll_yield(
                        "get_roll_yield", date=date_str, var=var,
                        symbol1=symbol1, symbol2=symbol2,
                    ),
                    timeout=10,
                )
            else:
                self.logger.warning(f"⚠️ 不支持的 type_method 或参数缺失: {type_method}")
                return None
        except (asyncio.TimeoutError, Exception):
            pass

        # AKShare 在线有结果则返回
        if result is not None and not (hasattr(result, 'empty') and result.empty):
            # ── 写入 Parquet 缓存 ──
            if type_method == "date" and var and self._cache:
                self._cache.save_roll_yield(cache_key, result)
            return result

        # 在线调用失败 → 尝试用交易所日线数据自行计算展期收益率
        if type_method == "date" and var:
            try:
                diy_df = await self._compute_roll_yield_from_exchange(
                    var, start_day, end_day,
                )
                if diy_df is not None and not diy_df.empty:
                    # ── 写入缓存 ──
                    if self._cache:
                        self._cache.save_roll_yield(cache_key, diy_df)
                    return diy_df
            except Exception:
                pass

        # 回退到本地缓存 (type_method="date" 且有 var 时)
        if type_method == "date" and var:
            try:
                from tradingagents.dataflows.providers.commodity.local_cache_adapter import (
                    CommodityLocalCacheAdapter,
                )
                cache = CommodityLocalCacheAdapter()
                df = cache.read_term_structure(var)
                if df is not None and not df.empty:
                    return df
            except Exception:
                pass

        return None

    async def _compute_roll_yield_from_exchange(
        self,
        var: str,
        start_day: Union[str, date],
        end_day: Union[str, date],
    ) -> Optional[pd.DataFrame]:
        """
        用交易所日线数据(get_futures_daily)自行计算展期收益率。

        当 AKShare get_roll_yield_bar 依赖的 100ppi.com 不可用时,
        直接从交易所官方数据计算主力-次主力展期收益率。

        Returns:
            DataFrame: [date, var, near_contract, dominant_contract,
                        roll_yield, near_price, dominant_price, spread]
        """
        from tradingagents.dataflows.providers.commodity.commodity_metadata import get_variety
        variety_meta = get_variety(var.upper())
        if not variety_meta:
            return None

        exchange = variety_meta.get("exchange", "")
        exchange_market_map = {"SHFE": "SHFE", "INE": "INE", "DCE": "DCE",
                               "CZCE": "CZCE", "GFEX": "GFEX", "CFFEX": "CFFEX"}
        market = exchange_market_map.get(exchange)
        if not market:
            return None

        start = start_day.strftime("%Y%m%d") if hasattr(start_day, "strftime") else str(start_day)
        end = end_day.strftime("%Y%m%d") if hasattr(end_day, "strftime") else str(end_day)

        # get_futures_daily 返回该交易所所有合约的日线
        df_raw = await self._call("get_futures_daily", start_date=start, end_date=end, market=market)
        if df_raw is None or df_raw.empty:
            return None

        # 过滤该品种(列名可能是 variety 或 symbol)
        var_upper = var.upper()
        if "variety" in df_raw.columns:
            df_raw = df_raw[df_raw["variety"].astype(str).str.upper() == var_upper].copy()
        elif "symbol" in df_raw.columns:
            df_raw = df_raw[df_raw["symbol"].astype(str).str.upper().str.match(
                rf"^{var_upper}\d{{3,4}}$"
            )].copy()
        else:
            return None

        if df_raw.empty:
            return None

        # 标准化日期
        date_col = "date" if "date" in df_raw.columns else ("日期" if "日期" in df_raw.columns else None)
        if not date_col:
            return None
        df_raw[date_col] = pd.to_datetime(df_raw[date_col], errors="coerce")

        # 标准化列名
        sym_col = "symbol" if "symbol" in df_raw.columns else ("合约" if "合约" in df_raw.columns else None)
        oi_col = "open_interest" if "open_interest" in df_raw.columns else ("持仓量" if "持仓量" in df_raw.columns else None)
        close_col = "close" if "close" in df_raw.columns else ("收盘" if "收盘" in df_raw.columns else None)

        if not sym_col or not oi_col or not close_col:
            # 尝试英文列
            for c in df_raw.columns:
                cl = c.lower()
                if cl in ("symbol", "contract", "合约", "合约代码"):
                    sym_col = c
                elif cl in ("open_interest", "oi", "持仓", "持仓量"):
                    oi_col = c
                elif cl in ("close", "收盘", "收盘价"):
                    close_col = c

        if not all([sym_col, oi_col, close_col]):
            self.logger.warning(f"⚠️ _compute_roll_yield: 无法识别列 {list(df_raw.columns)}")
            return None

        # 对每个交易日，找持仓量最大的两个合约
        records = []
        for dt, group in df_raw.groupby(date_col):
            valid = group[pd.to_numeric(group[oi_col], errors="coerce").fillna(0) > 0]
            if len(valid) < 2:
                continue
            sorted_group = valid.sort_values(by=oi_col, ascending=False)
            near = sorted_group.iloc[0]
            far = sorted_group.iloc[1]

            near_close = pd.to_numeric(near.get(close_col), errors="coerce")
            far_close = pd.to_numeric(far.get(close_col), errors="coerce")
            if pd.isna(near_close) or pd.isna(far_close) or near_close == 0:
                continue

            roll_yield = (near_close - far_close) / near_close
            records.append({
                "date": dt,
                "var": var_upper,
                "near_contract": near.get(sym_col),
                "dominant_contract": far.get(sym_col),
                "roll_yield": round(float(roll_yield), 6),
                "near_price": float(near_close),
                "dominant_price": float(far_close),
                "spread": float(near_close - far_close),
            })

        if not records:
            return None

        result = pd.DataFrame(records)
        result = result.sort_values("date").reset_index(drop=True)
        self.logger.info(f"✅ roll_yield 从交易所日线 DIY 计算成功({var}, {len(result)}行)")
        return result

    async def get_contract_info(
        self,
        exchange: str,
        date: Union[str, date] = None,
    ) -> Optional[pd.DataFrame]:
        """
        获取合约信息。

        Args:
            exchange: 交易所代码 SHFE / INE / DCE / CZCE / GFEX / CFFEX
            date: 交易日(部分接口需要;GFEX/DCE 自动取最新)
        """
        if not await self._ensure_ak():
            return None

        ex = exchange.upper()
        # 统一日期格式:字符串/date对象都转换成 YYYYMMDD
        if date is None:
            date_str = datetime.utcnow().strftime("%Y%m%d")
        elif hasattr(date, "strftime"):
            date_str = date.strftime("%Y%m%d")
        else:
            date_str = str(date)

        if ex == "SHFE":
            return await self._call("futures_contract_info_shfe")
        if ex == "INE":
            return await self._call("futures_contract_info_ine")
        if ex == "DCE":
            return await self._call("futures_contract_info_dce")
        if ex in ("CZCE", "CZC"):
            return await self._call("futures_contract_info_czce")
        if ex == "GFEX":
            return await self._call("futures_contract_info_gfex")
        if ex == "CFFEX":
            return await self._call("futures_contract_info_cffex")

        self.logger.warning(f"⚠️ 不支持的交易所: {exchange}")
        return None

    async def get_trading_calendar(
        self,
        date: Union[str, date],
    ) -> Optional[pd.DataFrame]:
        """
        获取交易日历+合约参数表(AKShare: futures_rule, 国泰君安期货)。
        122 行,含交易所 / 品种 / 交易保证金比例 / 涨跌停板幅度 / 合约乘数 /
        最小变动价位 / 限价单最大下单手数。
        """
        if not await self._ensure_ak():
            return None

        if hasattr(date, "strftime"):
            date_str = date.strftime("%Y%m%d")
        else:
            date_str = str(date)
        return await self._call("futures_rule", date=date_str)

    async def get_realtime_quote(
        self,
        symbols: Union[str, List[str]],
        market: str = "CF",
    ) -> Optional[pd.DataFrame]:
        """
        获取期货实时行情(AKShare: futures_zh_spot)。

        Args:
            symbols: 单合约代码字符串 'V2205' 或多合约 ['V2205','P2205']
                     支持带 .SHF / .DCE 等后缀,自动剥离
            market: "CF" 商品期货 / "FF" 金融期货
        """
        if not await self._ensure_ak():
            return None

        if isinstance(symbols, list):
            symbols_clean = [self._strip_exchange(s) for s in symbols]
            symbols_str = ",".join(symbols_clean)
        else:
            symbols_str = self._strip_exchange(symbols)
            symbols_clean = [symbols_str]

        df = await self._call("futures_zh_spot", symbol=symbols_str, market=market)
        if df is not None and not df.empty:
            return df

        # Fallback: futures_zh_spot 因 AKShare 版本列不匹配失败时,用新浪原始 API
        self.logger.info("ℹ️ futures_zh_spot 返回空,尝试新浪原始 API 回退")
        return await self._get_realtime_quote_fallback(symbols_clean)

    async def _get_realtime_quote_fallback(self, symbols: List[str]) -> Optional[pd.DataFrame]:
        """新浪原始 API 回退: 通过 sinajs.cn 获取实时行情。"""
        try:
            import requests
            loop = asyncio.get_event_loop()
            headers = {"Referer": "https://finance.sina.com.cn"}
            rows = []
            for sym in symbols:
                url = f"http://hq.sinajs.cn/list={sym}"
                r = await loop.run_in_executor(None, lambda: requests.get(url, timeout=10, headers=headers))
                text = r.text.strip()
                if not text or "=" not in text:
                    continue
                data_str = text.split('"')[1] if '"' in text else ""
                parts = data_str.split(",")
                # 新浪期货实时行情格式(28列):
                # [0]=名称 [1]=今开盘 [2]=昨结算 [3]=最新价 [4]=最高 [5]=最低
                # [6]=买价 [7]=卖价 [8]=持仓量 [9]=成交量
                if len(parts) >= 10:
                    f = lambda x: float(x) if x else 0.0  # noqa: E731
                    rows.append({
                        "symbol": parts[0],
                        "open": f(parts[1]),
                        "last_settle": f(parts[2]),
                        "current_price": f(parts[3]),
                        "high": f(parts[4]),
                        "low": f(parts[5]),
                        "bid": f(parts[6]),
                        "ask": f(parts[7]),
                        "hold": f(parts[8]),
                        "volume": f(parts[9]),
                    })
            if not rows:
                return None
            return pd.DataFrame(rows)
        except Exception as e:
            self.logger.warning(f"⚠️ 新浪实时行情回退失败: {e}")
            return None

    async def get_minute_kline(
        self,
        symbol: str,
        period: int = 1,
    ) -> Optional[pd.DataFrame]:
        """
        获取分时 K 线(AKShare: futures_zh_minute_sina)。

        Args:
            symbol: 主力连续合约代码, 如 'RB0'
            period: 1 / 5 / 15 / 30 / 60 分钟
        """
        if not await self._ensure_ak():
            return None
        return await self._call("futures_zh_minute_sina", symbol=symbol, period=period)

    async def get_delivery_info(
        self,
        exchange: str,
        date: Union[str, date],
    ) -> Optional[pd.DataFrame]:
        """
        获取交割统计 / 期转现数据(AKShare: futures_delivery_*/futures_to_spot_*)。

        Args:
            exchange: SHFE / DCE / CZCE
            date: 交易月份 YYYYMM(交割) 或 交易日 YYYYMMDD(期转现)
        """
        if not await self._ensure_ak():
            return None

        if hasattr(date, "strftime"):
            date_str = date.strftime("%Y%m")
            date_full = date.strftime("%Y%m%d")
        else:
            s = str(date)
            date_str = s[:6] if len(s) >= 6 else s
            date_full = s if len(s) == 8 else s

        ex = exchange.upper()
        # 交割统计
        if ex == "DCE":
            df = await self._call("futures_delivery_dce", date=date_str)
            if df is not None and not df.empty:
                return df
            return await self._call("futures_to_spot_dce", date=date_str)
        if ex in ("CZCE", "CZC"):
            df = await self._call("futures_delivery_czce", date=date_full)
            if df is not None and not df.empty:
                return df
            return await self._call("futures_to_spot_czce", date=date_full)
        if ex == "SHFE":
            df = await self._call("futures_delivery_shfe", date=date_str)
            if df is not None and not df.empty:
                return df
            return await self._call("futures_to_spot_shfe", date=date_str)

        self.logger.warning(f"⚠️ 不支持的交易所: {exchange}")
        return None

    async def get_holding_position(
        self,
        symbol: str,
        indicator: str = "成交量",
        date: Union[str, date] = None,
    ) -> Optional[pd.DataFrame]:
        """
        获取期货成交持仓(AKShare: futures_hold_pos_sina)。

        Args:
            symbol: 商品期货合约, 如 'OI2501'
            indicator: "成交量" / "多单持仓" / "空单持仓"
            date: 交易日 YYYYMMDD
        """
        if not await self._ensure_ak():
            return None

        if date is None:
            date = datetime.utcnow().date()
        if hasattr(date, "strftime"):
            date_str = date.strftime("%Y%m%d")
        else:
            date_str = str(date)

        return await self._call(
            "futures_hold_pos_sina", symbol=indicator, contract=symbol, date=date_str,
        )

    async def get_futures_news(
        self,
        category: str = "all",
        limit: int = 50,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取期货市场资讯。

        覆盖范围:
        1. shmet 有色金属快讯:
           - all/metal/nonferrous/copper/aluminum/lead/zinc/nickel/tin
           - precious/minor/headline/vip/finance
        2. 全球宏观(global_macro):
           - 聚合 6 个资讯源(东全球快讯/财联社/同花顺/富途/财经早餐/新浪)

        Args:
            category: 资讯分类
            limit: 最多返回条数(shmet 接口 ~1000 条)

        Returns:
            [
                {
                    "published_at": "2024-03-21T14:02:44+08:00",
                    "title": "金诚信资源:Lonshi 铜矿增储情况",
                    "content": "金诚信近日接受机构调研时表示...",
                    "category": "copper",                        # 用户入参
                    "metal": "铜",                                # shmet 分类
                    "sentiment": "positive",
                    "sentiment_score": 0.6,
                    "source": "shmet" | "global_macro",          # 标记来源
                    "url": "...",
                },
                ...
            ]
        """
        if not await self._ensure_ak():
            return None

        key = (category or "all").lower()

        # ===== 路径 A:shmet 文本快讯 =====
        if key in _NEWS_CATEGORY_MAP:
            shmet_symbol = _NEWS_CATEGORY_MAP[key]
            # 注意:None 表示不支持,传 "全部" 兜底
            if shmet_symbol is None:
                shmet_symbol = "全部"

            df = await self._call("futures_news_shmet", symbol=shmet_symbol)
            if df is None or df.empty:
                return []

            items: List[Dict[str, Any]] = []
            for _, row in df.iterrows():
                published_at = str(row.get("发布时间", "") or "")
                raw_content = row.get("内容", "") or ""
                title, body = _parse_shmet_bracket_title(str(raw_content))
                text_for_sentiment = f"{title} {body}"
                score = _analyze_futures_news_sentiment(text_for_sentiment)
                sentiment = _to_sentiment_label(score)

                items.append({
                    "published_at": published_at,
                    "title": title,
                    "content": body,
                    "category": key,
                    "metal": shmet_symbol,
                    "sentiment": sentiment,
                    "sentiment_score": score,
                    "source": "shmet",
                    "url": "https://www.shmet.com/newsFlash/newsFlash.html?searchKeyword=",
                })

                if limit and len(items) >= limit:
                    break
            return items

        # ===== 路径 B:宏观合成卡片 =====
        generator = _NEWS_GENERATORS.get(key)
        if generator:
            func_name = generator["func"]
            label = generator["label"]
            synth_method = getattr(self, func_name, None)
            if synth_method is None:
                self.logger.warning(f"⚠️ 合成器未实现: {func_name}")
                return []
            items = await synth_method(limit=limit)
            # 给每个 item 补上 category + label
            for it in items:
                it["category"] = key
                it["metal"] = label
            return items

        # ===== 路径 C:未识别分类 =====
        self.logger.warning(
            f"⚠️ get_futures_news 不支持分类 {category!r}(支持: "
            f"{list(_NEWS_CATEGORY_MAP.keys()) + list(_NEWS_GENERATORS.keys())})"
        )
        return []


    # ========================================================================
    # 全球宏观资讯流(聚合 6 个源: 财经早餐 / 东财 / 同花顺 / 富途 / 财联社 / 新浪)
    # --------------------------------------------------------------------------
    # 字段差异处理:
    # - 财经早餐 / 东财: 标题 + 摘要 + 发布时间 + 链接
    # - 同花顺 / 富途: 标题 + 内容 + 发布时间 + 链接
    # - 新浪: 只有 时间 + 内容(无标题,从【】解析)
    # - 财联社: 标题 + 内容 + 发布日期 + 发布时间(可能网络不通,失败兜底)
    # ========================================================================

    # ========================================================================
    # 全球宏观资讯流(聚合 6 个源: 财经早餐 / 东财 / 同花顺 / 富途 / 财联社 / 新浪)
    # --------------------------------------------------------------------------
    # 字段差异处理:
    # - 财经早餐 / 东财: 标题 + 摘要 + 发布时间 + 链接
    # - 同花顺 / 富途: 标题 + 内容 + 发布时间 + 链接
    # - 新浪: 只有 时间 + 内容(无标题,从【】解析)
    # - 财联社: 标题 + 内容 + 发布日期 + 发布时间(可能网络不通,失败兜底)
    # ========================================================================

    async def _synth_global_macro_news(self, limit: int = 50) -> List[Dict[str, Any]]:
        """聚合全球宏观多源,统一格式输出。"""
        # (akshare 函数名, kwargs, source_key, 单源最多取 N 条)
        sources = [
            ("stock_info_global_cls", {"symbol": "全部"}, "cls", 20),
            ("stock_info_global_em", {}, "eastmoney", 50),
            ("stock_info_global_ths", {}, "ths", 20),
            ("stock_info_global_futu", {}, "futu", 25),
            ("stock_info_cjzc_em", {}, "cjzc", 30),
            ("stock_info_global_sina", {}, "sina", 15),
        ]

        items: List[Dict[str, Any]] = []
        for func_name, kwargs, source_key, max_count in sources:
            df = await _safe_call(self, func_name, **kwargs)
            if df is None or df.empty:
                continue

            cols = list(df.columns)
            title_col = "标题" if "标题" in cols else None
            content_col = next((c for c in ("内容", "摘要") if c in cols), None)
            time_col = next(
                (c for c in ("发布时间", "时间", "发布日期") if c in cols), None
            )
            link_col = "链接" if "链接" in cols else None

            if not content_col:
                continue

            count = 0
            for _, row in df.iterrows():
                if count >= max_count:
                    break
                title = (str(row[title_col]).strip() if title_col else "")
                content = str(row[content_col]).strip()
                if not content:
                    continue
                # 新浪没有 title,从【】解析
                if not title and content:
                    t, body = _parse_shmet_bracket_title(content)
                    title = t or content[:40]
                    content = body or content

                published_at = str(row[time_col]) if time_col else ""
                link = str(row[link_col]).strip() if link_col else ""

                text = f"{title} {content}"
                score = _analyze_futures_news_sentiment(text)
                items.append({
                    "_sort_ts": _parse_global_macro_time(published_at),
                    "published_at": published_at,
                    "title": title,
                    "content": content,
                    "sentiment": _to_sentiment_label(score),
                    "sentiment_score": score,
                    "source": source_key,        # cls / eastmoney / ths / futu / cjzc / sina
                    "url": link,
                })
                count += 1

        # 按时间倒序(时间缺失的排到末尾)
        items.sort(key=lambda x: x["_sort_ts"], reverse=True)
        # 摘掉 _sort_ts 内部字段
        for it in items:
            it.pop("_sort_ts", None)
            # 补齐 category / metal
            it["category"] = "global_macro"
            it["metal"] = "全球宏观"
        if limit and len(items) > limit:
            items = items[:limit]
        return items

    # ========================================================================
    # 金融期货合成器(QVIX + 国债 + SHIBOR + LPR)
    # --------------------------------------------------------------------------
    # 服务于:
    #   - 股指期货 IF / IH / IC / IM: QVIX(股指期权波动率)反映市场恐慌程度
    #   - 国债期货 T / TF / TS / TL: 中美国债收益率利差 + SHIBOR 短端 + LPR 报价
    # 数据源:
    #   - index_option_300index_qvix  (中证300 QVIX)
    #   - index_option_300etf_qvix    (300 ETF 期权 QVIX)
    #   - index_option_1000index_qvix (中证1000 QVIX)
    #   - bond_zh_us_rate             (中美国债收益率)
    #   - macro_china_shibor_all      (SHIBOR 8 个品种)
    #   - macro_china_lpr             (LPR 1Y/5Y)
    # ========================================================================


    async def get_active_contract_history(
        self,
        symbol: str,
        start_date: Union[str, date],
        end_date: Union[str, date] = None,
    ) -> Optional[pd.DataFrame]:
        """
        获取每日主力合约代码历史序列。

        方法:从交易所合约信息获取该品种所有合约的到期日,
        对每个交易日,选择到期日 > 当日且最接近的合约作为主力合约。

        Args:
            symbol: 品种代码(如 CU / RB / A),纯字母代码
            start_date: 开始日期
            end_date: 结束日期(默认到今天)

        Returns:
            DataFrame: [date, active_contract, exchange, days_to_expiry, last_delivery_date]
            若该品种在某日无有效合约则当日跳过。
        """
        if not await self._ensure_ak():
            return None

        # 1. 从 commodity_metadata 查找品种所属交易所
        from tradingagents.dataflows.providers.commodity.commodity_metadata import (
            get_variety, _ALL_VARIETIES, EXCHANGES
        )
        variety = get_variety(symbol.upper())
        if not variety:
            self.logger.warning(f"⚠️ get_active_contract_history: 未知品种 {symbol}")
            return None
        exchange = variety.get("exchange", "")
        if not exchange:
            return None

        # 2. 标准化交易所代码
        exchange_norm = {"SHFE": "SHFE", "INE": "INE", "DCE": "DCE",
                         "CZCE": "CZCE", "GFEX": "GFEX", "CFFEX": "CFFEX"}.get(exchange, "")
        if not exchange_norm:
            return None

        # 3. 获取该交易所所有合约信息
        sd = start_date.strftime("%Y%m%d") if isinstance(start_date, date) else start_date.replace("-", "")
        ed = end_date.strftime("%Y%m%d") if end_date and isinstance(end_date, date) else ""
        if not ed:
            ed = end_date.replace("-", "") if end_date else date.today().strftime("%Y%m%d")
        # 用合约信息的最新日期查(合约信息是静态的快照)
        contract_df = await self.get_contract_info(exchange_norm, date.today().strftime("%Y%m%d"))
        if contract_df is None or contract_df.empty:
            return None

        # 4. 过滤该品种的合约
        symbol_upper = symbol.upper()
        # 合约代码列(第一个)可能是小写,统一大写匹配
        code_col = contract_df.columns[0]
        contract_df["_code_upper"] = contract_df[code_col].astype(str).str.upper()
        mask = contract_df["_code_upper"].str.match(rf"^{symbol_upper}\d{{3,4}}$")
        filtered = contract_df[mask].copy()
        if filtered.empty:
            self.logger.warning(f"⚠️ get_active_contract_history: {symbol} 在 {exchange_norm} 无有效合约")
            return None

        # 5. 解析到期日(第二个列通常是到期日)
        expiry_col = contract_df.columns[2]  # 第3列=到期日
        delivery_col = contract_df.columns[4]  # 第5列=最后交割日

        contracts = []
        for _, row in filtered.iterrows():
            code = row["_code_upper"]
            expiry_str = str(row.get(expiry_col, ""))
            delivery_str = str(row.get(delivery_col, ""))
            try:
                expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            try:
                delivery_date = datetime.strptime(delivery_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                delivery_date = expiry_date
            contracts.append({
                "code": code,
                "expiry": expiry_date,
                "last_delivery": delivery_date,
            })

        if not contracts:
            return None

        # 6. 生成日期序列
        start = pd.to_datetime(start_date).date() if isinstance(start_date, str) else start_date
        end = pd.to_datetime(end_date).date() if isinstance(end_date, str) else (end_date or date.today())
        if isinstance(end, str):
            end = pd.to_datetime(end).date()

        # 按到期日排序
        contracts.sort(key=lambda c: c["expiry"])

        # 对每个日期,找到期日 > 当日且最接近的合约
        records = []
        current = start
        while current <= end:
            best = None
            best_dte = None
            for c in contracts:
                dte = (c["expiry"] - current).days
                if dte > 0:  # 未到期
                    if best_dte is None or dte < best_dte:
                        best = c
                        best_dte = dte
            if best:
                records.append({
                    "date": current,
                    "active_contract": best["code"],
                    "exchange": exchange_norm,
                    "days_to_expiry": best_dte,
                    "last_delivery_date": best["last_delivery"],
                })
            else:
                # 该日无有效合约(可能所有合约都已到期)
                records.append({
                    "date": current,
                    "active_contract": None,
                    "exchange": exchange_norm,
                    "days_to_expiry": None,
                    "last_delivery_date": None,
                })
            current += pd.Timedelta(days=1)

        result = pd.DataFrame(records)
        # 去掉无有效合约的日期
        result = result.dropna(subset=["active_contract"])
        return result.reset_index(drop=True)

    # ============================================================
    # 辅助方法
    # ============================================================

    @staticmethod
    def _symbol_to_chinese(symbol: str) -> Optional[str]:
        """将品种英文代码转为中文名(用于 AKShare 部分需中文名的接口)。

        例: ``"A"`` → ``"豆一"``, ``"CU"`` → ``"铜"``。
        如果传入的已经是中文名或查不到,返回 None。
        """
        # 先用静态映射表(兼容 AKShare futures_inventory_em 的中文名)
        _EN_TO_CN = {
            "A": "豆一", "B": "豆二", "C": "玉米", "M": "豆粕", "Y": "豆油",
            "P": "棕榈油", "I": "铁矿石", "J": "焦炭", "JM": "焦煤",
            "L": "聚乙烯", "V": "PVC", "PP": "聚丙烯", "EG": "乙二醇",
            "EB": "苯乙烯", "PG": "液化石油气", "JD": "鸡蛋", "RR": "粳米",
            "LH": "生猪", "FB": "纤维板", "BB": "胶合板", "LG": "原木",
            "CU": "沪铜", "AL": "沪铝", "ZN": "沪锌", "PB": "沪铅", "NI": "镍",
            "SN": "锡", "AU": "沪金", "AG": "沪银", "RB": "螺纹钢",
            "WR": "线材", "HC": "热轧卷板", "SS": "不锈钢", "BU": "石油沥青",
            "RU": "天然橡胶", "BR": "合成橡胶", "SP": "纸浆", "FU": "燃料油",
            "AO": "氧化铝",
            "SC": "原油", "NR": "20号胶", "LU": "低硫燃料油",
            "EC": "集运指数(欧线)", "BC": "国际铜",
            "CF": "郑棉", "SR": "白糖", "CY": "棉纱", "AP": "苹果",
            "CJ": "红枣", "PK": "花生", "RM": "菜粕", "OI": "菜籽油",
            "RS": "菜籽", "TA": "PTA", "MA": "甲醇", "FG": "玻璃",
            "SA": "纯碱", "SH": "烧碱", "UR": "尿素", "PF": "短纤",
            "PX": "对二甲苯", "PR": "瓶片", "ZC": "动力煤", "SF": "硅铁",
            "SM": "锰硅",
            "SI": "工业硅", "LC": "碳酸锂", "PS": "多晶硅",
            "IF": "沪深300", "IH": "上证50", "IC": "中证500",
            "IM": "中证1000", "TS": "2年期国债", "TF": "5年期国债",
            "T": "10年期国债", "TL": "30年期国债",
        }
        cn = _EN_TO_CN.get(symbol)
        if cn:
            return cn
        try:
            v = get_variety(symbol)
            if v:
                return v.get("name_cn")
        except Exception:
            pass
        return None

    @staticmethod
    def _strip_exchange(full_symbol: str) -> str:
        """去掉交易所后缀(AKShare 接口不识别)"""
        for exch in _CHINA_FUTURES_EXCHANGES:
            suffix = f".{exch}"
            if full_symbol.upper().endswith(suffix):
                return full_symbol[: -len(suffix)]
        # CFFEX 不在 FUTURES 上(金融期货标的就是 IF0 这种连续合约)直接返回
        if full_symbol.upper().endswith(".CFFEX"):
            return full_symbol[:-6]
        return full_symbol

    @staticmethod
    def _has_yyymm(full_symbol: str) -> bool:
        """
        判断 full_symbol 是否包含具体合约月份(YYMM)。

        例: CU2501.SHF → True(有 2501); CU0.SHF → False(主力连续);
            CU.SHF → False(裸品种); RB0.SHF → False(主力连续); A2501.SHF → True
        """
        code = full_symbol.split(".")[0] if "." in full_symbol else full_symbol
        underlying = CommodityUtils.get_underlying_symbol(full_symbol)
        if not underlying:
            return False
        suffix = code[len(underlying):]
        # 具体合约:后缀是 3-4 位纯数字(CZCE 部分品种 3 位如 AP410→10,标准 4 位如 CU2501→2501)
        return bool(suffix) and suffix.isdigit() and len(suffix) in (3, 4)

    async def _try_continuous_fallback(self, full_symbol: str):
        """
        尝试用主力连续(<underlying>0.<exch>)作为回退,适用于具体合约无行情的场景。

        Returns:
            pandas.DataFrame 或 None
        """
        underlying = CommodityUtils.get_underlying_symbol(full_symbol)
        if not underlying:
            return None
        fallback_symbol = f"{underlying}0"
        df = await self._call("futures_main_sina", symbol=fallback_symbol)
        if df is None or df.empty:
            return None
        self.logger.warning(
            "⚠️ 具体合约 %s 无行情,回退到主力连续 %s 成功",
            full_symbol, fallback_symbol,
        )
        return df

    @staticmethod
    def _normalize_hist_em_df(df: pd.DataFrame) -> pd.DataFrame:
        """
        将 futures_hist_em 的列名映射为与 futures_main_sina 一致的格式。

        输入列: 时间, 开盘, 最高, 最低, 收盘, 涨跌, 涨跌幅, 成交量, 成交额, 持仓量
        输出列: 日期, 开盘价, 最高价, 最低价, 收盘价, 成交量, 持仓量, 动态结算价
        """
        if df is None or df.empty:
            return df
        col_map = {
            "时间": "日期", "开盘": "开盘价", "最高": "最高价",
            "最低": "最低价", "收盘": "收盘价",
            "成交量": "成交量", "持仓量": "持仓量",
        }
        df = df.rename(columns=col_map)
        # 只保留映射后的标准列
        std_cols = ["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "持仓量"]
        available = [c for c in std_cols if c in df.columns]
        df["动态结算价"] = df.get("收盘价", 0)
        # 确保日期是 datetime
        if "日期" in df.columns:
            df["日期"] = pd.to_datetime(df["日期"]).dt.date
        return df[available + ["动态结算价"]]

    @staticmethod
    def _mark_rollover_dates(df: pd.DataFrame, gap_threshold: float = 0.03) -> pd.DataFrame:
        """
        在主力连续数据中检测换月点。

        策略:计算每日收盘涨跌幅,若某日涨跌幅绝对值 > gap_threshold 且
        持仓量同时大幅变化(降 30%+ 或增 50%+),标记该日为换月日。

        Args:
            df: 含 日期/开盘价/收盘价/成交量/持仓量 列的 DataFrame
            gap_threshold: 价格跳变阈值(默认 3%)

        Returns:
            增加 rollover_date(bool)列的 DataFrame
        """
        if df is None or df.empty:
            return df
        df = df.copy()
        df["rollover_date"] = False

        if len(df) < 3:
            return df

        # 计算每日涨跌幅
        df["pct_chg"] = df["收盘价"].pct_change().abs()
        # 持仓量变化率(次日 vs 前日)
        if "持仓量" in df.columns:
            oi = pd.to_numeric(df["持仓量"], errors="coerce").fillna(0)
            df["oi_chg_pct"] = oi.pct_change().abs()
        else:
            df["oi_chg_pct"] = 0.0

        # 检测条件:涨跌幅 > 阈值 且 (持仓量变化 > 30% 或 序列中前 5% 的大跳变)
        for i in range(1, len(df) - 1):
            if df.iloc[i]["pct_chg"] > gap_threshold:
                # 持仓量验证:换月日通常旧合约减仓、新合约增仓
                if df.iloc[i]["oi_chg_pct"] > 0.3:
                    df.loc[df.index[i], "rollover_date"] = True

        # 如果完全没检测到,尝试更灵敏的阈值:取前 1% 最大跳变
        if not df["rollover_date"].any():
            top_threshold = df["pct_chg"].quantile(0.99)
            if top_threshold > gap_threshold:
                for i in range(1, len(df) - 1):
                    if df.iloc[i]["pct_chg"] > top_threshold:
                        df.loc[df.index[i], "rollover_date"] = True

        # 清理辅助列
        df = df.drop(columns=["pct_chg", "oi_chg_pct"], errors="ignore")
        return df

    @staticmethod
    def _apply_adjustment(df: pd.DataFrame, mode: str = "back") -> pd.DataFrame:
        """
        对主力连续数据应用复权。

        Args:
            df: 含 rollover_date 列的 DataFrame
            mode: "back"(后复权) 或 "forward"(前复权)

        复权方法(比率法):
        - 在每个换月点,计算前合约收盘价 / 后合约开盘价的比值作为调整因子
        - back: 将换月点之前的价格乘以该因子(使前后价格连续)
        - forward: 将换月点之后的价格乘以该因子
        """
        if df is None or df.empty:
            return df
        if "rollover_date" not in df.columns or not df["rollover_date"].any():
            return df

        df = df.copy()
        roll_indices = df.index[df["rollover_date"]].tolist()

        price_cols = ["开盘价", "最高价", "最低价", "收盘价"]
        # 确保价格列是 float,避免 int64 × float 的 dtype 冲突
        for col in price_cols:
            if col in df.columns:
                df[col] = df[col].astype(float)

        if mode == "back":
            # 后复权:从最老的换月点开始向前调整
            for ri in sorted(roll_indices):
                if ri + 1 >= len(df):
                    continue
                close_before = float(df.loc[ri, "收盘价"])
                open_after = float(df.loc[ri + 1, "开盘价"])
                if open_after == 0 or close_before == 0:
                    continue
                factor = close_before / open_after
                # 调整 ri 之前(含 ri)的所有价格
                mask = df.index <= ri
                for col in price_cols:
                    df.loc[mask, col] = df.loc[mask, col] * factor
        elif mode == "forward":
            # 前复权:从最新的换月点开始向后调整
            for ri in sorted(roll_indices, reverse=True):
                if ri + 1 >= len(df):
                    continue
                close_before = float(df.loc[ri, "收盘价"])
                open_after = float(df.loc[ri + 1, "开盘价"])
                if open_after == 0 or close_before == 0:
                    continue
                factor = open_after / close_before
                # 调整 ri+1 之后(含 ri+1)的所有价格
                mask = df.index >= ri + 1
                for col in price_cols:
                    df.loc[mask, col] = df.loc[mask, col] * factor

        return df

    @staticmethod
    def _build_basic_info(full_symbol: str) -> Optional[Dict[str, Any]]:
        """从 full_symbol 构造基础信息(优先 commodity_metadata 静态元数据)"""
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

        # 优先使用 commodity_metadata 静态元数据中的中文名
        variety_meta = get_variety(underlying) or {}
        chinese_name = variety_meta.get("name_cn", underlying)
        name = f"{chinese_name}期货{yymm_str}合约" if yymm_str else f"{chinese_name}期货"
        ex_norm = normalize_exchange_code(exchange) or ""

        return {
            "code": code,
            "full_symbol": full_symbol,
            "symbol": code,
            "name": name,
            "exchange": exchange,
            "exchange_canonical": ex_norm,
            "exchange_name": variety_meta.get("name_cn", "")
                            and _EXCHANGE_NAMES.get(
                                {"SHFE": "SHF", "INE": "INE", "DCE": "DCE",
                                 "CZCE": "CZC", "GFEX": "GFEX", "CFFEX": "CFFEX"}.get(ex_norm, ""),
                                "未知交易所"),
            "category": variety_meta.get("category") or info.get("category", "unknown"),
            "underlying": underlying,
            "currency": info.get("currency", "CNY"),
            "unit": variety_meta.get("unit") or info.get("unit", "手"),
            "contract_size": variety_meta.get("contract_size") or info.get("contract_size", 1.0),
            "tick_size": variety_meta.get("tick_size"),
            "list_date": variety_meta.get("list_date"),
            "is_china_futures": True,
            "is_international": False,
            "is_spot_cn": False,
            "data_source": "akshare_futures",
            "data_version": 2,
            "updated_at": _now_iso(),
        }
