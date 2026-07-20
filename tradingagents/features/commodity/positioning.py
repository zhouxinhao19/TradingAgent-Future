"""
positioning.py — 商品期货持仓/拥挤度特征模块 (Phase 3b-i + 品种级多合约增强)

输入: 来自 `AkshareFuturesProvider.get_position_rank(exchange, date)` 或
      `app/services/commodity/unified_commodity_service` 聚合后的 DataFrame。
      期望列(中文 / 英文):
        日期/date, 品种/symbol,
        long_top20 / long_open_interest_top20,
        short_top20 / short_open_interest_top20,
        total_oi / total_open_interest(可选),
        net_long_top20(可选,缺则 long_top20 - short_top20)

      也接受 Dict[合约代码, DataFrame] 形式(provider 原始返回),此时传入 `symbol` 品种过滤。

增强: 多合约版本不再"选一个合约丢弃其余",而是聚合所有匹配合约:
  - 品种级总 OI / 总净多
  - 各合约 OI 占比明细
  - 移仓换月检测(近月 OI 下降 + 远月 OI 上升)
  - 跨合约方向一致性(所有合约同向 vs 分化)
  - 四象限价仓配合分类(price_oi_regime)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from tradingagents.features.commodity import _helpers as h


def _coerce_input(
    df_or_dict: Union[pd.DataFrame, Dict[str, pd.DataFrame], None],
    symbol: Optional[str],
) -> pd.DataFrame:
    """统一输入: DataFrame 直接用;Dict 按 symbol 匹配品种,返回主力合约DataFrame(向后兼容)。"""
    if df_or_dict is None:
        return pd.DataFrame()
    if isinstance(df_or_dict, dict):
        if not df_or_dict:
            return pd.DataFrame()
        if symbol is None:
            symbol = next(iter(df_or_dict.keys()))
        if symbol in df_or_dict:
            return df_or_dict[symbol]
        from tradingagents.utils.commodity_utils import CommodityUtils
        sym_upper = symbol.upper()
        candidates = []
        for key, val in df_or_dict.items():
            underlying = (CommodityUtils.get_underlying_symbol(key) or "").upper()
            if underlying == sym_upper:
                candidates.append((key, val))
        if not candidates:
            return pd.DataFrame()
        if len(candidates) == 1:
            return candidates[0][1]
        candidates.sort(key=lambda kv: len(kv[1]) if kv[1] is not None else 0, reverse=True)
        best_key, best_df = candidates[0]
        if len(candidates) > 1:
            from tradingagents.utils.logging_init import get_logger
            get_logger("default").info(
                f"📊 _coerce_input: 品种 {symbol} 有 {len(candidates)} 个合约匹配,"
                f"选主力 {best_key}({len(best_df)} 行)"
            )
        return best_df
    if isinstance(df_or_dict, pd.DataFrame):
        return df_or_dict
    return pd.DataFrame()


def _prepare(df: pd.DataFrame, symbol: Optional[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = h.normalize_columns(df)
    if symbol and "symbol" in out.columns:
        from tradingagents.utils.commodity_utils import CommodityUtils
        sym_upper = symbol.upper()
        out = out[out["symbol"].astype(str).str.upper().apply(
            lambda s: (CommodityUtils.get_underlying_symbol(s) or "").upper() == sym_upper
        )].copy()
    out = h.ensure_columns(
        out,
        ["date", "long_top20", "short_top20", "total_oi", "net_long_top20"],
    )
    for c in ["long_top20", "short_top20", "total_oi", "net_long_top20"]:
        out[c] = h.to_numeric(out[c])

    # 修复口径:AKShare get_shfe_rank_table / 同类接口返回长表(每行 = 一日一合约的
    # 前 20 多/空合计,rank=999 表示汇总行),并不直接提供 total_oi。
    # 用 (long_top20 + short_top20) 作为该合约 OI 近似值:前 20 名通常吃掉 60%+
    # 双边持仓,既能反映品种活跃度又避免分母为 0 时的 nan 链式污染。
    if "total_oi" not in out.columns or out["total_oi"].isna().all():
        if {"long_top20", "short_top20"}.issubset(out.columns):
            out["total_oi"] = out["long_top20"].fillna(0) + out["short_top20"].fillna(0)
        else:
            out["total_oi"] = np.nan

    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        if out["date"].notna().any():
            out = out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        else:
            out = out.drop(columns=["date"])
            out["date"] = pd.Timestamp.now().normalize()
    if "net_long_top20" not in out.columns or out["net_long_top20"].isna().all():
        if {"long_top20", "short_top20"}.issubset(out.columns):
            out["net_long_top20"] = out["long_top20"] - out["short_top20"]
    return out


def _concentration(data: pd.DataFrame) -> pd.Series:
    """前 20 名多/空持仓份额。

    由于 AKShare get_shfe_rank_table 等接口仅返回长表(每行 = 一日一合约的
    前 20 多/空合计),不直接提供 total_market_oi。`_prepare` 已用
    `long_top20 + short_top20` 作为合约 OI 近似,故此处直接返回 `long_share`:
        concentration = long_top20 / (long_top20 + short_top20)
    该值越大,表示前 20 名多头相对空头越集中(多头集中度)。
    范围 [0, 1];0.5 = 多空对称,>0.6 = 多头相对集中,<0.4 = 空头相对集中。
    """
    if {"long_top20", "short_top20"}.issubset(data.columns):
        long_v = data["long_top20"].fillna(0)
        short_v = data["short_top20"].fillna(0)
        total = long_v + short_v
        # 防止分母为 0
        return long_v / total.replace(0, np.nan)
    if "long_top20" in data.columns:
        # 退化路径:无 short 数据时,用 zscore 当"集中度变化"
        m = data["long_top20"].rolling(60, min_periods=10).mean()
        sd = data["long_top20"].rolling(60, min_periods=10).std()
        return (data["long_top20"] - m) / sd.replace(0, np.nan)
    return pd.Series(np.nan, index=data.index)


def _classify_price_oi_regime(
    price_direction: Optional[str],
    oi_change_5d: Optional[float],
) -> str:
    """四象限价仓配合分类。

    经典框架:
      - 价涨 + 仓增 → 多头强势(新多资金入场,趋势延续)
      - 价涨 + 仓减 → 空头回补(空头平仓推动,动力存疑)
      - 价跌 + 仓增 → 空头强势(新空资金入场,趋势延续)
      - 价跌 + 仓减 → 多头止损(多头离场,衰竭信号)
    """
    if not price_direction or price_direction == "neutral":
        return "震荡待判"
    if oi_change_5d is None:
        return "震荡待判"

    threshold = 0.0  # 任何非零变化即视为有效
    if price_direction == "bullish":
        if oi_change_5d > threshold:
            return "多头强势(价涨仓增)"
        elif oi_change_5d < -threshold:
            return "空头回补(价涨仓减)"
    elif price_direction == "bearish":
        if oi_change_5d > threshold:
            return "空头强势(价跌仓增)"
        elif oi_change_5d < -threshold:
            return "多头止损(价跌仓减)"
    return "震荡待判"


def _aggregate_contracts(
    df_or_dict: Union[pd.DataFrame, Dict[str, pd.DataFrame], None],
    symbol: Optional[str],
) -> Dict[str, Any]:
    """聚合所有匹配合约为品种级视图。

    不再"选一个合约丢弃其余",而是:
    1. 提取所有匹配合约
    2. 对每个合约独立规范化
    3. 构建品种级汇总(总 OI、总净多)
    4. 检测移仓换月
    5. 判断跨合约方向一致性

    Args:
        df_or_dict: 原始输入(DataFrame 或 Dict)
        symbol: 品种过滤

    Returns:
        {
            "primary": DataFrame,       # 主力合约(数据最丰富)的规范化数据
            "contracts": [...],          # 各合约快照
            "variety_aggregate": {...},  # 品种级汇总
            "rollover": {...},           # 移仓信号
            "cross_contract": {...},     # 跨合约一致性
        }
        单合约输入时 contracts 只含一个元素,rollover.detected=False。
    """
    # 单 DataFrame 输入:直接返回主力合约(已规范化)
    if isinstance(df_or_dict, pd.DataFrame) or df_or_dict is None:
        raw = _coerce_input(df_or_dict, symbol)
        if isinstance(raw, pd.DataFrame) and not raw.empty:
            prepared = _prepare(raw, symbol)
            return {"primary": prepared}
        return {"primary": raw}

    if not isinstance(df_or_dict, dict) or not df_or_dict:
        return {"primary": pd.DataFrame()}

    # 提取所有匹配合约
    from tradingagents.utils.commodity_utils import CommodityUtils
    sym_upper = symbol.upper() if symbol else ""
    candidates = []
    for key, val in df_or_dict.items():
        if val is None or (isinstance(val, pd.DataFrame) and val.empty):
            continue
        if symbol and key == symbol:
            candidates.append((key, val))
        elif symbol:
            underlying = (CommodityUtils.get_underlying_symbol(key) or "").upper()
            if underlying == sym_upper:
                candidates.append((key, val))
        else:
            candidates.append((key, val))

    if not candidates:
        return {"primary": pd.DataFrame()}

    # 对每个合约规范化
    prepared: Dict[str, pd.DataFrame] = {}
    for key, val in candidates:
        try:
            df = _prepare(val, symbol)
            if not df.empty and len(df) >= 3:
                prepared[key] = df
        except Exception:
            continue

    if not prepared:
        return {"primary": pd.DataFrame()}

    # 选主力合约(数据行数最多)
    dominant = max(prepared, key=lambda k: len(prepared[k]))

    # 构建各合约快照(取最后一行的最新数据)
    contracts: List[Dict[str, Any]] = []
    for key, df in prepared.items():
        if df.empty:
            continue
        last = df.iloc[-1]
        oi = h.safe_float(last.get("total_oi"))
        net_long = h.safe_float(last.get("net_long_top20"))
        long_v = h.safe_float(last.get("long_top20"))
        short_v = h.safe_float(last.get("short_top20"))

        # 净多 5 日变化(在各自合约上独立计算)
        nl_change = None
        if len(df) >= 6 and "net_long_top20" in df.columns:
            v_last = df["net_long_top20"].iloc[-1]
            v_prev = df["net_long_top20"].iloc[-6]
            if pd.notna(v_last) and pd.notna(v_prev):
                nl_change = float(v_last - v_prev)

        contracts.append({
            "contract": key,
            "oi": oi,
            "net_long": net_long,
            "long_top20": long_v,
            "short_top20": short_v,
            "net_long_change_5d": nl_change,
            "is_dominant": key == dominant,
            "rows": int(len(df)),
        })

    # 计算 OI share
    valid_oi = [c["oi"] for c in contracts if c["oi"] is not None and c["oi"] > 0]
    total_oi = sum(valid_oi) if valid_oi else 0
    if total_oi > 0:
        for c in contracts:
            c["oi_share"] = round((c["oi"] or 0) / total_oi, 4)
    else:
        for c in contracts:
            c["oi_share"] = 0

    # 品种级汇总
    valid_nl = [c["net_long"] for c in contracts if c["net_long"] is not None]
    variety_aggregate = {
        "total_oi": total_oi,
        "total_net_long": sum(valid_nl) if valid_nl else None,
        "active_contracts": len(contracts),
    }

    # 移仓检测(基于主力合约和次主力合约)
    rollover = _detect_rollover(prepared, contracts, dominant)

    # 跨合约一致性
    cross_contract = _cross_contract_consistency(contracts)

    return {
        "primary": prepared[dominant],
        "contracts": contracts,
        "variety_aggregate": variety_aggregate,
        "rollover": rollover,
        "cross_contract": cross_contract,
    }


def _detect_rollover(
    prepared: Dict[str, pd.DataFrame],
    contracts: List[Dict[str, Any]],
    dominant: str,
) -> Dict[str, Any]:
    """检测移仓换月信号。

    逻辑:
    1. 按 OI 排序取前 2 个合约(近月 + 次近月)
    2. 对每个合约,计算最近 5 日 OI 变化
    3. 近月 OI 下降 + 次近月 OI 上升 → 移仓中
    4. progress = 次近月 OI / (近月 OI + 次近月 OI)

    Returns:
        {"detected": bool, "from_contract": str, "to_contract": str,
         "progress": float, "description": str}
    """
    result: Dict[str, Any] = {
        "detected": False,
        "from_contract": "",
        "to_contract": "",
        "progress": 0.0,
        "description": "未检测到移仓换月",
    }

    # 按 OI 降序排列(排除无 OI 的合约)
    sorted_contracts = sorted(
        [c for c in contracts if c["oi"] is not None and c["oi"] > 0],
        key=lambda c: c["oi"],
        reverse=True,
    )
    if len(sorted_contracts) < 2:
        return result

    front = sorted_contracts[0]
    next_ = sorted_contracts[1]

    # 计算近月合约 OI 5 日变化
    front_df = prepared.get(front["contract"])
    next_df = prepared.get(next_["contract"])

    front_oi_change = _oi_change_5d(front_df)
    next_oi_change = _oi_change_5d(next_df)

    if front_oi_change is None or next_oi_change is None:
        return result

    # 检测:近月 OI 下降 + 次近月 OI 上升
    if front_oi_change < -0.02 and next_oi_change > 0.02:
        total_oi = (front["oi"] or 0) + (next_["oi"] or 0)
        progress = round((next_["oi"] or 0) / total_oi, 3) if total_oi > 0 else 0
        result.update({
            "detected": True,
            "from_contract": front["contract"],
            "to_contract": next_["contract"],
            "progress": progress,
            "description": (
                f"移仓进行中: {front['contract']}(OI {front_oi_change:+.1%}) → "
                f"{next_['contract']}(OI {next_oi_change:+.1%}), 进度 {progress:.0%}"
            ),
        })
    elif front_oi_change < -0.02:
        result["description"] = (
            f"{front['contract']} OI 下降({front_oi_change:+.1%}), "
            f"但 {next_['contract']} OI 未同步上升({next_oi_change:+.1%}), 可能是减仓而非移仓"
        )

    return result


def _oi_change_5d(df: Optional[pd.DataFrame]) -> Optional[float]:
    """计算 DataFrame 最近 5 日 OI 变化率。"""
    if df is None or df.empty or len(df) < 6:
        return None
    if "total_oi" not in df.columns:
        return None
    oi_recent = df["total_oi"].tail(6)
    if oi_recent.isna().any():
        return None
    v_last = float(oi_recent.iloc[-1])
    v_prev = float(oi_recent.iloc[0])
    if v_prev == 0:
        return None
    return (v_last - v_prev) / v_prev


def _cross_contract_consistency(contracts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """判断跨合约方向一致性。

    看各合约 net_long 符号:
    - 全部 > 0 → "同向看多"
    - 全部 < 0 → "同向看空"
    - 混合 → "分化"
    """
    directions = []
    for c in contracts:
        nl = c.get("net_long")
        if nl is not None and nl > 0:
            directions.append("long")
        elif nl is not None and nl < 0:
            directions.append("short")

    total = len(directions)
    if total == 0:
        return {"consistency": "待定(无净多数据)", "contracts_same_direction": 0, "total_active_contracts": total}

    long_count = directions.count("long")
    short_count = directions.count("short")

    if long_count == total:
        return {"consistency": "同向看多", "contracts_same_direction": total, "total_active_contracts": total}
    elif short_count == total:
        return {"consistency": "同向看空", "contracts_same_direction": total, "total_active_contracts": total}
    else:
        return {"consistency": "分化", "contracts_same_direction": max(long_count, short_count), "total_active_contracts": total}


def _build_contracts_table(contracts: List[Dict[str, Any]]) -> str:
    """构建合约明细 Markdown 表格。"""
    if not contracts:
        return "(无合约数据)"
    # 按 OI 降序
    sorted_c = sorted(contracts, key=lambda c: c.get("oi") or 0, reverse=True)
    lines = ["| 合约 | OI | OI占比 | 净多 | 净多5日变化 | 主力 |",
             "|------|----|--------|------|-------------|------|"]
    for c in sorted_c:
        oi = f"{c.get('oi') or 0:,.0f}" if c.get("oi") else "N/A"
        share = f"{c.get('oi_share', 0):.1%}" if c.get("oi_share") else "N/A"
        nl = f"{c.get('net_long') or 0:+,.0f}" if c.get("net_long") is not None else "N/A"
        nl_chg = f"{c.get('net_long_change_5d') or 0:+,.0f}" if c.get("net_long_change_5d") is not None else "N/A"
        dom = "★" if c.get("is_dominant") else ""
        lines.append(f"| {c['contract']} | {oi} | {share} | {nl} | {nl_chg} | {dom} |")
    return "\n".join(lines)


def _signals(
    pctl: Optional[float],
    net_chg_5d: Optional[float],
    concentration: Optional[float],
    long_change_5d: Optional[float] = None,
    short_change_5d: Optional[float] = None,
    lsr_change_5d: Optional[float] = None,
    consecutive_days: Optional[int] = None,
    price_pos_alignment: Optional[str] = None,
    # 多合约增强信号
    rollover_detected: bool = False,
    rollover_desc: str = "",
    cross_consistency: str = "",
    oi_change_pct_5d: Optional[float] = None,
    price_oi_regime: str = "",
) -> List[str]:
    sigs: List[str] = []
    if pctl is not None and not (isinstance(pctl, float) and np.isnan(pctl)):
        if pctl >= 0.8:
            sigs.append("拥挤度处高分位(警惕反转)")
        elif pctl <= 0.2:
            sigs.append("拥挤度处低分位(关注建仓)")
    if net_chg_5d is not None:
        if net_chg_5d > 0:
            sigs.append("前20净多增加(主力看多)")
        elif net_chg_5d < 0:
            sigs.append("前20净多减少(主力看空)")
    if concentration is not None:
        if concentration >= 0.6:
            sigs.append(f"前20多头相对集中({concentration:.1%},空头相对分散)")
        elif concentration <= 0.4:
            sigs.append(f"前20空头相对集中({concentration:.1%},多头相对分散)")
    if long_change_5d is not None:
        if long_change_5d > 0:
            sigs.append(f"多头前20主动加仓({long_change_5d:+.0f})")
        elif long_change_5d < 0:
            sigs.append(f"多头前20减仓({long_change_5d:+.0f})")
    if short_change_5d is not None:
        if short_change_5d > 0:
            sigs.append(f"空头前20加仓({short_change_5d:+.0f})")
        elif short_change_5d < 0:
            sigs.append(f"空头前20减仓({short_change_5d:+.0f})")
    if lsr_change_5d is not None and abs(lsr_change_5d) > 0.2:
        sigs.append(f"多空比急剧变化({lsr_change_5d:+.2f})")
    if consecutive_days is not None and abs(consecutive_days) >= 2:
        if consecutive_days > 0:
            sigs.append(f"连续{consecutive_days}日净多增加(主力稳步建仓)")
        else:
            sigs.append(f"连续{abs(consecutive_days)}日净多减少(主力持续撤退)")
    if price_pos_alignment is not None and "背离" in price_pos_alignment:
        sigs.append(f"价格-持仓背离({price_pos_alignment})")
    # 多合约信号
    if rollover_detected and rollover_desc:
        sigs.append(f"移仓信号: {rollover_desc}")
    if cross_consistency:
        if "同向" in cross_consistency:
            sigs.append(f"跨合约一致性: {cross_consistency}")
        elif "分化" in cross_consistency:
            sigs.append(f"跨合约分化: {cross_consistency}")
    if oi_change_pct_5d is not None:
        if oi_change_pct_5d > 0.05:
            sigs.append(f"总持仓5日大幅增加({oi_change_pct_5d:+.1%})")
        elif oi_change_pct_5d < -0.05:
            sigs.append(f"总持仓5日大幅减少({oi_change_pct_5d:+.1%})")
    if price_oi_regime and "价涨仓增" in price_oi_regime:
        sigs.append("价仓共振:多头强势(新多资金入场确认趋势)")
    elif price_oi_regime and "价涨仓减" in price_oi_regime:
        sigs.append("价仓背离:上涨由空头回补推动,动力存疑")
    elif price_oi_regime and "价跌仓增" in price_oi_regime:
        sigs.append("价仓共振:空头强势(新空资金入场确认趋势)")
    elif price_oi_regime and "价跌仓减" in price_oi_regime:
        sigs.append("价仓背离:下跌由多头止损推动,衰竭信号")
    return sigs


def compute_positioning_metrics(
    df_or_dict: Union[pd.DataFrame, Dict[str, pd.DataFrame], None],
    symbol: Optional[str] = None,
    price_direction: Optional[str] = None,
) -> Dict[str, Any]:
    """席位与拥挤度指标(品种级多合约版)。

    Args:
        df_or_dict: 单品种 DataFrame 或多品种 Dict[合约代码, DataFrame]
        symbol: 品种过滤(Dict 模式下用于选 key)
        price_direction: 日线价格方向(bullish/bearish/neutral),用于价格-持仓交叉验证

    Returns:
        {
            "latest": {...}, "stats": {...}, "signals": [...], "snapshot": {...}, "quality": {...},
            # 新增多合约字段:
            "contracts": [...],          # 各合约明细
            "variety_aggregate": {...},  # 品种级汇总
            "rollover": {...},           # 移仓信号
            "cross_contract": {...},     # 跨合约一致性
        }
    """
    if df_or_dict is None:
        return h.empty_result("无席位缓存")

    # 多合约聚合
    agg = _aggregate_contracts(df_or_dict, symbol)
    data = agg["primary"]

    if data.empty:
        return h.empty_result(f"目标品种 {symbol or '?'} 无席位数据")
    if len(data) < 5:
        return h.empty_result(f"样本不足(仅 {len(data)} 行)")

    # 集中度
    data = data.copy()
    data["conc_metric"] = _concentration(data)

    last = data.iloc[-1]
    latest = {
        "date": str(last.get("date")) if pd.notna(last.get("date")) else None,
        "symbol": last.get("symbol"),
        "long_top20": h.safe_float(last.get("long_top20")),
        "short_top20": h.safe_float(last.get("short_top20")),
        "total_oi": h.safe_float(last.get("total_oi")),
        "net_long_top20": h.safe_float(last.get("net_long_top20")),
        "long_short_ratio": (
            float(last["long_top20"] / last["short_top20"])
            if pd.notna(last.get("long_top20")) and pd.notna(last.get("short_top20"))
            and last.get("short_top20") not in (None, 0)
            else None
        ),
    }
    concentration = h.safe_float(last.get("conc_metric"))
    pctl = h.percentile_rank(data["conc_metric"].dropna() if data["conc_metric"].notna().any() else pd.Series(dtype=float), 180)

    # 净多单边变化
    net_chg_5d = None
    long_chg_5d = None
    short_chg_5d = None
    if len(data) >= 6:
        if "net_long_top20" in data.columns:
            v_last = data["net_long_top20"].iloc[-1]
            v_prev = data["net_long_top20"].iloc[-6]
            if pd.notna(v_last) and pd.notna(v_prev):
                net_chg_5d = float(v_last - v_prev)
        if "long_top20" in data.columns:
            v_last = data["long_top20"].iloc[-1]
            v_prev = data["long_top20"].iloc[-6]
            if pd.notna(v_last) and pd.notna(v_prev):
                long_chg_5d = float(v_last - v_prev)
        if "short_top20" in data.columns:
            v_last = data["short_top20"].iloc[-1]
            v_prev = data["short_top20"].iloc[-6]
            if pd.notna(v_last) and pd.notna(v_prev):
                short_chg_5d = float(v_last - v_prev)

    # 多空比 5 日变化
    lsr_change_5d = None
    if len(data) >= 6:
        lsr_cur = latest.get("long_short_ratio") or (
            float(data["long_top20"].iloc[-1] / data["short_top20"].iloc[-1])
            if "long_top20" in data.columns and "short_top20" in data.columns
            and pd.notna(data["short_top20"].iloc[-1]) and data["short_top20"].iloc[-1] != 0
            else None
        )
        lsr_prev = (
            float(data["long_top20"].iloc[-6] / data["short_top20"].iloc[-6])
            if "long_top20" in data.columns and "short_top20" in data.columns
            and pd.notna(data["short_top20"].iloc[-6]) and data["short_top20"].iloc[-6] != 0
            else None
        )
        if lsr_cur is not None and lsr_prev is not None:
            lsr_change_5d = float(lsr_cur - lsr_prev)

    # 连续净多变化天数
    consecutive_net_long_days = 0
    if "net_long_top20" in data.columns:
        nl = data["net_long_top20"]
        sign_series = nl.diff().apply(lambda x: 1 if (pd.notna(x) and x > 0) else (-1 if (pd.notna(x) and x < 0) else 0))
        cnt = 0
        for i in range(len(sign_series) - 1, -1, -1):
            s = sign_series.iloc[i]
            if s == 0:
                continue
            if cnt == 0 or s == (1 if cnt > 0 else -1):
                cnt += s
            else:
                break
        consecutive_net_long_days = cnt

    # 品种级 OI 变化(从主力合约计算)
    oi_change_5d = None
    oi_change_pct_5d = None
    if len(data) >= 6 and "total_oi" in data.columns:
        oi_last = h.safe_float(data["total_oi"].iloc[-1])
        oi_prev = h.safe_float(data["total_oi"].iloc[-6])
        if oi_last is not None and oi_prev is not None and oi_prev != 0:
            oi_change_5d = float(oi_last - oi_prev)
            oi_change_pct_5d = float((oi_last - oi_prev) / oi_prev)

    # 价格-持仓对齐(旧版:基于净多变化,保持向后兼容)
    price_pos_alignment = None
    if price_direction:
        if price_direction == "bullish" and (net_chg_5d is not None and net_chg_5d > 0):
            price_pos_alignment = "同向看多(价涨仓增)"
        elif price_direction == "bearish" and (net_chg_5d is not None and net_chg_5d < 0):
            price_pos_alignment = "同向看空(价跌仓减)"
        elif price_direction == "bullish" and (net_chg_5d is not None and net_chg_5d < 0):
            price_pos_alignment = "背离(价涨仓减)"
        elif price_direction == "bearish" and (net_chg_5d is not None and net_chg_5d > 0):
            price_pos_alignment = "背离(价跌仓增)"

    # 四象限价仓分类(基于总 OI 变化)
    price_oi_regime = _classify_price_oi_regime(price_direction, oi_change_5d)

    # 多合约数据
    contracts = agg.get("contracts", [])
    variety_aggregate = agg.get("variety_aggregate", {})
    rollover = agg.get("rollover", {})
    cross_contract = agg.get("cross_contract", {})

    # 合约明细表格
    contracts_table = _build_contracts_table(contracts)

    signals = _signals(
        pctl, net_chg_5d, concentration,
        long_change_5d=long_chg_5d,
        short_change_5d=short_chg_5d,
        lsr_change_5d=lsr_change_5d,
        consecutive_days=consecutive_net_long_days,
        price_pos_alignment=price_pos_alignment,
        rollover_detected=rollover.get("detected", False),
        rollover_desc=rollover.get("description", ""),
        cross_consistency=cross_contract.get("consistency", ""),
        oi_change_pct_5d=oi_change_pct_5d,
        price_oi_regime=price_oi_regime,
    )
    snapshot = {
        **latest,
        "concentration": concentration,
        "crowding_pctl_180d": pctl,
        "net_long_change_5d": net_chg_5d,
        "long_top20_change_5d": long_chg_5d,
        "short_top20_change_5d": short_chg_5d,
        "long_short_ratio_change_5d": lsr_change_5d,
        "consecutive_net_long_days": consecutive_net_long_days,
        "price_direction": price_direction or "N/A",
        "price_position_alignment": price_pos_alignment or "N/A",
        "net_long_slope_20d": h.slope(data["net_long_top20"], 20) if "net_long_top20" in data.columns else None,
        "long_share": (
            float(last["long_top20"] / (2 * last["total_oi"]))
            if pd.notna(last.get("long_top20")) and pd.notna(last.get("total_oi"))
            and last.get("total_oi") not in (None, 0)
            else None
        ),
        "short_share": (
            float(last["short_top20"] / (2 * last["total_oi"]))
            if pd.notna(last.get("short_top20")) and pd.notna(last.get("total_oi"))
            and last.get("total_oi") not in (None, 0)
            else None
        ),
        # 品种级多合约新增字段
        "oi_change_5d": oi_change_5d,
        "oi_change_pct_5d": oi_change_pct_5d,
        "price_oi_regime": price_oi_regime,
        "total_oi_variety": variety_aggregate.get("total_oi"),
        "total_net_long_variety": variety_aggregate.get("total_net_long"),
        "active_contracts": variety_aggregate.get("active_contracts", 0),
        "rollover_detected": rollover.get("detected", False),
        "rollover_description": rollover.get("description", ""),
        "cross_contract_consistency": cross_contract.get("consistency", ""),
    }
    quality = h.data_quality(data, value_col="long_top20")
    quality["symbol"] = symbol or latest.get("symbol")

    result = {
        "latest": latest,
        "stats": {"zscore_180d": pctl, "slope_20d": snapshot.get("net_long_slope_20d")},
        "signals": signals,
        "snapshot": snapshot,
        "quality": quality,
        # 多合约字段
        "contracts": contracts,
        "variety_aggregate": variety_aggregate,
        "rollover": rollover,
        "cross_contract": cross_contract,
        "contracts_table": contracts_table,
    }
    return result