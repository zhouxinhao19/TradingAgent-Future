"""
大宗商品分析路由 (Phase 3b-ii-D)

端点:
  - POST /api/commodity/{full_symbol}/analyze — 提交分析任务(异步,走 BackgroundTasks)
  - GET /api/commodity/{full_symbol}/reports — 拉历史报告列表
  - GET /api/commodity/reports/{report_id} — 获取单份报告详情

依赖:
  - FEATURE_COMMODITY_ANALYSIS=true (在 main.py 条件 include)
  - tradingagents.graph.commodity_graph.CommodityTradingAgentsGraph
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user

logger = logging.getLogger("webapi")
router = APIRouter(prefix="/commodity", tags=["commodity-analysis"])

# 报告存储目录(相对于项目根)
_REPORTS_BASE = Path(__file__).resolve().parents[3] / "data" / "analysis_results" / "commodity"
_REPORTS_BASE.mkdir(parents=True, exist_ok=True)


def _safe_symbol(raw: str) -> str:
    """净化 full_symbol,防止路径遍历攻击。

    - 只允许字母、数字、点、连字符、下划线
    - 移除所有路径分隔符(`/` `\`)和 `..` 序列
    - 同时返回净化后的字符串和其相对于 _REPORTS_BASE 的解析路径
    """
    import re
    cleaned = re.sub(r'[^a-zA-Z0-9.\-_]', '', raw)
    # 额外防御:不允许以点开头(隐藏文件)或连续点(..)
    cleaned = cleaned.lstrip('.')
    if not cleaned:
        cleaned = "unknown"
    resolved = (_REPORTS_BASE / cleaned).resolve()
    # 最终安全校验:必须仍在 _REPORTS_BASE 下
    if not str(resolved).startswith(str(_REPORTS_BASE.resolve())):
        raise ValueError(f"路径遍历攻击被拦截: {raw!r}")
    return cleaned


# ==================== 请求/响应模型 ====================

class AnalysisRequest(BaseModel):
    """商品分析请求参数"""
    full_symbol: str = Field(..., description="完整合约代码,如 CU2501.SHF")
    trade_date: Optional[str] = Field(None, description="交易日期 YYYY-MM-DD(默认当天)")
    variety_name: str = Field("", description="品种中文名,如 螺纹钢")
    exchange: str = Field("", description="交易所代码,如 SHF")
    category: str = Field("", description="行业分类")
    quote_unit: str = Field("", description="报价单位,如 元/吨")
    max_debate_rounds: int = Field(1, ge=0, le=3, description="多空辩论轮次")
    max_risk_discuss_rounds: int = Field(1, ge=0, le=3, description="风控辩论轮次")


class AnalysisTaskResponse(BaseModel):
    """分析任务响应"""
    task_id: str
    full_symbol: str
    status: str
    message: str


class ReportSummary(BaseModel):
    """报告摘要"""
    report_id: str
    full_symbol: str
    trade_date: str
    direction: str
    confidence: float
    created_at: str


# ==================== 服务辅助函数 ====================

def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _build_config(
    max_debate_rounds: int = 1,
    max_risk_discuss_rounds: int = 1,
) -> Dict[str, Any]:
    """构建 CommodityTradingAgentsGraph 配置。

    LLM 配置来自环境变量或数据库(经由 config_bridge 写入 os.environ),
    当前默认 deepseek-chat(测试用),上线前改为 DB 配置读取。
    """
    import os

    provider = os.getenv("COMMODITY_LLM_PROVIDER", "deepseek")
    deep = os.getenv("COMMODITY_DEEP_LLM", "deepseek-chat")
    quick = os.getenv("COMMODITY_QUICK_LLM", "deepseek-chat")

    config = {
        "llm_provider": provider,
        "deep_think_llm": deep,
        "quick_think_llm": quick,
        "max_debate_rounds": max_debate_rounds,
        "max_risk_discuss_rounds": max_risk_discuss_rounds,
        "online_tools": False,
        "memory_enabled": False,
        "project_dir": str(Path(__file__).resolve().parents[3]),
    }
    return config


def _run_commodity_analysis(
    full_symbol: str,
    trade_date: str,
    variety_name: str = "",
    exchange: str = "",
    category: str = "",
    quote_unit: str = "",
    config_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """同步运行 CommodityTradingAgentsGraph 分析。"""
    from tradingagents.graph.commodity_graph import CommodityTradingAgentsGraph

    cfg = _build_config()
    if config_override:
        cfg.update(config_override)

    graph = CommodityTradingAgentsGraph(debug=False, config=cfg)
    final_state, decision = graph.propagate(
        full_symbol=full_symbol,
        trade_date=trade_date,
        commodity_features={},
        latest_news=[],
        variety_name=variety_name,
        exchange=exchange,
        category=category,
        quote_unit=quote_unit,
    )

    return {
        "full_symbol": full_symbol,
        "trade_date": trade_date,
        "decision": decision,
        "market_report": final_state.get("market_report", ""),
        "fundamentals_report": final_state.get("fundamentals_report", ""),
        "sentiment_report": final_state.get("sentiment_report", ""),
        "news_report": final_state.get("news_report", ""),
        "investment_plan": final_state.get("investment_plan", ""),
        "trader_investment_plan": final_state.get("trader_investment_plan", ""),
        "final_trade_decision": final_state.get("final_trade_decision", ""),
        "final_decision": final_state.get("final_decision", ""),
    }


def _save_report(full_symbol: str, trade_date: str, result: Dict[str, Any]) -> str:
    """保存分析报告到 JSON 文件,返回 report_id。"""
    safe_sym = _safe_symbol(full_symbol)
    report_id = f"{safe_sym}_{trade_date}_{uuid.uuid4().hex[:8]}"
    report_dir = _REPORTS_BASE / safe_sym / trade_date
    report_dir.mkdir(parents=True, exist_ok=True)

    report_path = report_dir / f"{report_id}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"✅ 报告已保存: {report_path}")
    return report_id


def _list_reports(full_symbol: str, limit: int = 20) -> List[Dict[str, Any]]:
    """列出某个品种的历史报告。"""
    safe_sym = _safe_symbol(full_symbol)
    symbol_dir = _REPORTS_BASE / safe_sym
    if not symbol_dir.exists():
        return []

    reports = []
    for date_dir in sorted(symbol_dir.iterdir(), reverse=True)[:limit]:
        for f_path in sorted(date_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f_path.read_text(encoding="utf-8"))
                decision = data.get("decision", {})
                reports.append({
                    "report_id": f_path.stem,
                    "full_symbol": full_symbol,
                    "trade_date": date_dir.name,
                    "direction": decision.get("action", "hold"),
                    "confidence": decision.get("confidence", 0.0),
                    "created_at": datetime.fromtimestamp(
                        f_path.stat().st_mtime
                    ).isoformat(),
                })
            except Exception:
                continue

    return reports[:limit]


def _list_recent_reports(limit: int = 10) -> List[Dict[str, Any]]:
    """列出所有品种中最近的分析报告(全局按 mtime 排序)。"""
    all_reports: List[tuple[float, Dict[str, Any]]] = []

    for symbol_dir in _REPORTS_BASE.iterdir():
        if not symbol_dir.is_dir():
            continue
        safe_sym = symbol_dir.name
        for date_dir in symbol_dir.iterdir():
            if not date_dir.is_dir():
                continue
            for f_path in date_dir.glob("*.json"):
                try:
                    mtime = f_path.stat().st_mtime
                    data = json.loads(f_path.read_text(encoding="utf-8"))
                    decision = data.get("decision", {})
                    all_reports.append((
                        mtime,
                        {
                            "report_id": f_path.stem,
                            "full_symbol": safe_sym,
                            "trade_date": date_dir.name,
                            "direction": decision.get("action", "hold"),
                            "confidence": decision.get("confidence", 0.0),
                            "created_at": datetime.fromtimestamp(mtime).isoformat(),
                        },
                    ))
                except Exception:
                    continue

    all_reports.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in all_reports[:limit]]


# ==================== 端点 ====================

@router.post("/{full_symbol}/analyze", response_model=dict, summary="提交商品分析任务")
async def submit_commodity_analysis(
    full_symbol: str,
    background_tasks: BackgroundTasks,
    raw_request: Request,
    user: dict = Depends(get_current_user),
):
    """提交大宗商品期货分析任务。

    后台异步执行完整决策链:
      4 分析师 → 多空辩论 → 交易员 → 风控 → CIO 最终决策
    耗时约 1-5 分钟(取决于 LLM 速度)。
    完成后报告自动保存,可通过 GET /reports 查看。

    body 兼容性:full_symbol 在路径参数和 body 都接受;
    - 完全没 body / body={} → 用路径参数填充
    - body 含 full_symbol → 用 body 的(优先级更高)
    - body 含其它字段(trade_date/variety_name/...) → 正常解析
    """
    # 容错:body 缺失或为空时用路径参数填充 full_symbol
    try:
        body_bytes = await raw_request.body()
        body_data: Dict[str, Any] = json.loads(body_bytes) if body_bytes else {}
    except (json.JSONDecodeError, ValueError):
        body_data = {}
    if not body_data.get("full_symbol"):
        body_data["full_symbol"] = full_symbol
    try:
        request = AnalysisRequest(**body_data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"请求体校验失败: {exc}",
        )

    task_id = f"commodity_{uuid.uuid4().hex[:12]}"
    trade_date = request.trade_date or _today()

    logger.info(
        f"🌾 [CommodityAnalysis] 提交分析: {full_symbol} @ {trade_date}, "
        f"task_id={task_id}"
    )

    background_tasks.add_task(
        _run_and_save_analysis,
        full_symbol=full_symbol,
        trade_date=trade_date,
        variety_name=request.variety_name,
        exchange=request.exchange,
        category=request.category,
        quote_unit=request.quote_unit,
        max_debate_rounds=request.max_debate_rounds,
        max_risk_discuss_rounds=request.max_risk_discuss_rounds,
        task_id=task_id,
    )

    return {
        "success": True,
        "data": {
            "task_id": task_id,
            "full_symbol": full_symbol,
            "trade_date": trade_date,
            "status": "submitted",
        },
        "message": "分析任务已提交,后台执行中。请稍后通过 GET /reports 查看结果。",
    }


async def _run_and_save_analysis(
    full_symbol: str,
    trade_date: str,
    variety_name: str,
    exchange: str,
    category: str,
    quote_unit: str,
    max_debate_rounds: int,
    max_risk_discuss_rounds: int,
    task_id: str,
):
    """后台运行分析 + 保存报告。"""
    logger.info(f"🚀 [BackgroundTask] 开始商品分析: {full_symbol} (task={task_id})")

    try:
        config = _build_config(
            max_debate_rounds=max_debate_rounds,
            max_risk_discuss_rounds=max_risk_discuss_rounds,
        )
        result = _run_commodity_analysis(
            full_symbol=full_symbol,
            trade_date=trade_date,
            variety_name=variety_name,
            exchange=exchange,
            category=category,
            quote_unit=quote_unit,
            config_override=config,
        )
        result["task_id"] = task_id
        report_id = _save_report(full_symbol, trade_date, result)
        logger.info(f"✅ [BackgroundTask] 分析完成: {full_symbol}, report_id={report_id}")
    except Exception as e:
        logger.error(
            f"❌ [BackgroundTask] 分析失败: {full_symbol}, error={e}", exc_info=True
        )


@router.get("/{full_symbol}/reports", response_model=dict, summary="历史报告列表")
async def get_commodity_reports(
    full_symbol: str,
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    user: dict = Depends(get_current_user),
):
    """获取某个大宗商品品种的历史分析报告列表。"""
    reports = _list_reports(full_symbol, limit=limit)
    return {
        "success": True,
        "data": {
            "full_symbol": full_symbol,
            "total": len(reports),
            "reports": reports,
        },
        "message": "获取报告列表成功" if reports else "暂无历史报告",
    }


@router.get("/reports/recent", response_model=dict, summary="全局最近报告")
async def get_recent_commodity_reports(
    limit: int = Query(10, ge=1, le=50, description="返回条数"),
    user: dict = Depends(get_current_user),
):
    """获取所有商品品种中最近的分析报告(全局)。"""
    reports = _list_recent_reports(limit=limit)
    return {
        "success": True,
        "data": {
            "total": len(reports),
            "reports": reports,
        },
        "message": "获取最近报告成功" if reports else "暂无历史报告",
    }


@router.get("/reports/{report_id}", response_model=dict, summary="报告详情")
async def get_commodity_report_detail(
    report_id: str,
    user: dict = Depends(get_current_user),
):
    """获取单份分析报告的完整内容。"""
    safe_id = _safe_symbol(report_id)
    # 在所有品种目录中查找
    for symbol_dir in _REPORTS_BASE.iterdir():
        if not symbol_dir.is_dir():
            continue
        for date_dir in symbol_dir.iterdir():
            if not date_dir.is_dir():
                continue
            report_path = (date_dir / f"{safe_id}.json").resolve()
            if not str(report_path).startswith(str(_REPORTS_BASE.resolve())):
                continue
            if report_path.exists():
                data = json.loads(report_path.read_text(encoding="utf-8"))
                return {
                    "success": True,
                    "data": data,
                    "message": "获取报告成功",
                }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"报告不存在: {report_id}",
    )
