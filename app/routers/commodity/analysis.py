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
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user
from app.services.websocket_manager import get_websocket_manager

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
    full_symbol: str = Field(..., description="合约代码或品种代码,如 CU2501.SHF 或 CU(自动解析为主力连续)")
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


def _resolve_input_symbol(raw: str) -> Optional[Dict[str, str]]:
    """智能解析输入代码:品种代码 → 全量合约元信息。

    支持:
      - 完整合约: "RB2501.SHF" → 返回 None(已有 YYMM,走具体合约)
      - 带交易所: "RB.SHF"     → 返回 None(无 YYMM,provider 自动走主力连续)
      - 裸品种:   "RB" / "CU"  → 查 metadata,解析为 "RB.SHF"
    不支持或找不到 → 返回 None(保持兼容,让下游自行报错)
    """
    raw = raw.strip().upper()
    # 已经是完整合约格式(如 RB2501.SHF) → 不动
    if re.search(r'\d{3,4}\.[A-Z]', raw):
        return None
    # 带交易所后缀(如 RB.SHF) → 不动,provider 自动走主力连续
    if re.match(r'^[A-Z]{1,3}\.[A-Z]{2,}$', raw):
        return None
    # 纯品种代码 → 查 metadata 解析
    from tradingagents.dataflows.providers.commodity.commodity_metadata import (
        resolve_variety_to_symbol,
    )
    return resolve_variety_to_symbol(raw)


# ==================== 任务元数据 MongoDB 层 ====================
# 商品分析任务元数据存于 `commodity_analysis_tasks` 集合 (Phase 5+)
# 与报告文件 (data/analysis_results/commodity/...) 物理隔离

def _tasks_collection():
    """懒加载 MongoDB 集合句柄。失败时返回 None(允许任务跟踪降级)。"""
    try:
        from app.core.database import get_database
        return get_database().commodity_analysis_tasks
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠️ MongoDB 不可用，任务跟踪降级: {e}")
        return None


def _serialize_task(doc: Dict[str, Any]) -> Dict[str, Any]:
    """MongoDB doc → API 响应;剥离 _id,统一 datetime 为 ISO 字符串"""
    if doc is None:
        return {}
    doc = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("created_at", "completed_at"):
        v = doc.get(k)
        if v is not None and hasattr(v, "isoformat"):
            doc[k] = v.isoformat()
    return doc


async def _task_set(task_id: str, fields: Dict[str, Any]) -> None:
    """Best-effort 写任务元数据;失败仅日志,不影响业务逻辑"""
    coll = _tasks_collection()
    if coll is None:
        return
    try:
        await coll.update_one({"task_id": task_id}, {"$set": fields}, upsert=True)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠️ 任务元数据写入失败 (task={task_id}): {e}")


async def _push_progress(task_id: str, progress: int, message: str = "") -> None:
    """更新任务进度并推送 WebSocket。"""
    fields: Dict[str, Any] = {"progress": progress}
    if message:
        fields["progress_message"] = message
    await _task_set(task_id, fields)
    try:
        ws = get_websocket_manager()
        await ws.send_progress_update(task_id, {
            "type": "progress_update",
            "task_id": task_id,
            "progress": progress,
            "message": message,
        })
    except Exception as e:
        logger.debug(f"⚠️ WebSocket 推送失败 (task={task_id}): {e}")


async def _backfill_completed_tasks() -> int:
    """回填:扫描现有报告 JSON,创建任务记录 (status=completed)

    给历史报告补 task 记录,保证任务中心能看到老数据。
    重复执行幂等 (upsert by task_id)。
    """
    coll = _tasks_collection()
    if coll is None:
        return 0
    count = 0
    if not _REPORTS_BASE.exists():
        return 0
    for report_file in _REPORTS_BASE.rglob("*.json"):
        try:
            data = json.loads(report_file.read_text(encoding="utf-8"))
            tid = data.get("task_id")
            if not tid:
                continue
            full_sym = data.get("full_symbol", "")
            trade_date = data.get("trade_date", "")
            mtime = datetime.fromtimestamp(report_file.stat().st_mtime, tz=timezone.utc)
            await coll.update_one(
                {"task_id": tid},
                {"$set": {
                    "task_id": tid,
                    "full_symbol": full_sym,
                    "trade_date": trade_date,
                    "user_id": "legacy-backfill",
                    "status": "completed",
                    "report_id": report_file.stem,
                    "created_at": mtime,
                    "completed_at": mtime,
                }},
                upsert=True,
            )
            count += 1
        except Exception as e:  # noqa: BLE001
            logger.debug(f"跳过报告 {report_file}: {e}")
            continue
    if count > 0:
        # 加索引 (幂等)
        try:
            await coll.create_index([("user_id", 1), ("status", 1), ("created_at", -1)])
        except Exception:  # noqa: BLE001
            pass
    return count


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

    # 初始化 provider 用于 auto_features
    from tradingagents.dataflows.providers.commodity.akshare_futures import (
        AkshareFuturesProvider,
    )

    provider = None
    try:
        provider = AkshareFuturesProvider()
        provider.connect()
    except Exception as e:
        logger.warning(f"⚠️ 商品 provider 初始化失败,将使用空特征: {e}")

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
        auto_features=True,
        provider=provider,
    )

    return {
        "full_symbol": full_symbol,
        "trade_date": trade_date,
        "decision": decision,
        "market_report": final_state.get("market_report", ""),
        "fundamentals_report": final_state.get("fundamentals_report", ""),
        "fundamentals_structured": final_state.get("fundamentals_structured", {}),
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
                        f_path.stat().st_mtime, tz=timezone.utc
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
                            "created_at": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
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

    # ---- 品种代码自动解析(如 "RB" → "RB.SHF") ----
    resolved = _resolve_input_symbol(request.full_symbol)
    if resolved:
        logger.info(
            f"🌾 [CommodityAnalysis] 品种解析: {request.full_symbol} → "
            f"{resolved['full_symbol']} ({resolved['variety_name']})"
        )
        request.full_symbol = resolved["full_symbol"]
        if not request.variety_name:
            request.variety_name = resolved["variety_name"]
        if not request.exchange:
            request.exchange = resolved["exchange"]
        if not request.category:
            request.category = resolved["category"]
        if not request.quote_unit:
            request.quote_unit = resolved.get("quote_unit", "")

    task_id = f"commodity_{uuid.uuid4().hex[:12]}"
    trade_date = request.trade_date or _today()

    logger.info(
        f"🌾 [CommodityAnalysis] 提交分析: {request.full_symbol} @ {trade_date}, "
        f"task_id={task_id}"
    )

    background_tasks.add_task(
        _run_and_save_analysis,
        full_symbol=request.full_symbol,
        trade_date=trade_date,
        variety_name=request.variety_name,
        exchange=request.exchange,
        category=request.category,
        quote_unit=request.quote_unit,
        max_debate_rounds=request.max_debate_rounds,
        max_risk_discuss_rounds=request.max_risk_discuss_rounds,
        task_id=task_id,
        user_id=str(user.get("id", "anonymous")),
    )

    return {
        "success": True,
        "data": {
            "task_id": task_id,
            "full_symbol": request.full_symbol,
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
    user_id: str = "anonymous",
):
    """后台运行分析 + 保存报告 + 更新任务状态。"""
    logger.info(f"🚀 [BackgroundTask] 开始商品分析: {full_symbol} (task={task_id})")

    # 1. 创建/更新任务为 processing
    await _task_set(task_id, {
        "task_id": task_id,
        "full_symbol": full_symbol,
        "trade_date": trade_date,
        "variety_name": variety_name,
        "exchange": exchange,
        "user_id": user_id,
        "status": "processing",
        "progress": 0,
        "progress_message": "初始化中…",
        "created_at": datetime.now(timezone.utc),
    })

    try:
        await _push_progress(task_id, 5, "构建分析配置…")
        config = _build_config(
            max_debate_rounds=max_debate_rounds,
            max_risk_discuss_rounds=max_risk_discuss_rounds,
        )

        await _push_progress(task_id, 15, "执行分析中(多智能体决策链)…")
        result = _run_commodity_analysis(
            full_symbol=full_symbol,
            trade_date=trade_date,
            variety_name=variety_name,
            exchange=exchange,
            category=category,
            quote_unit=quote_unit,
            config_override=config,
        )

        await _push_progress(task_id, 75, "分析完成，保存报告…")
        result["task_id"] = task_id
        report_id = _save_report(full_symbol, trade_date, result)

        # 2. 标记完成
        await _task_set(task_id, {
            "status": "completed",
            "report_id": report_id,
            "progress": 100,
            "progress_message": "已完成",
            "completed_at": datetime.now(timezone.utc),
        })
        await _push_progress(task_id, 100, "分析完成")
        logger.info(f"✅ [BackgroundTask] 分析完成: {full_symbol}, report_id={report_id}")
    except Exception as e:
        # 3. 标记失败 (截断长错误避免 MongoDB 文档过大)
        err_msg = str(e)[:500]
        await _task_set(task_id, {
            "status": "failed",
            "error_message": err_msg,
            "progress": 0,
            "progress_message": "失败",
            "completed_at": datetime.now(timezone.utc),
        })
        await _push_progress(task_id, 0, f"失败: {err_msg[:100]}")
        logger.error(
            f"❌ [BackgroundTask] 分析失败: {full_symbol}, error={err_msg}", exc_info=True
        )


@router.post("/tasks/{task_id}/mark-failed", response_model=dict, summary="标记任务为失败")
async def mark_commodity_task_failed(
    task_id: str,
    user: dict = Depends(get_current_user),
):
    """将 stuck(processing 超时)的任务标记为失败。"""
    coll = _tasks_collection()
    if coll is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务存储不可用",
        )
    user_id = str(user.get("id", ""))
    doc = await coll.find_one({
        "task_id": task_id,
        "$or": [
            {"user_id": user_id},
            {"user_id": "legacy-backfill"},
        ],
    })
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_id}",
        )
    if doc.get("status") not in ("processing", "pending"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"只能标记 processing/pending 状态的任务,当前状态: {doc.get('status')}",
        )
    await _task_set(task_id, {
        "status": "failed",
        "error_message": "用户手动标记为失败",
        "progress": 0,
        "progress_message": "手动标记失败",
        "completed_at": datetime.now(timezone.utc),
    })
    return {"success": True, "message": "任务已标记为失败"}


@router.get("/tasks/{task_id}/result", response_model=dict, summary="获取任务结果")
async def get_commodity_task_result(
    task_id: str,
    user: dict = Depends(get_current_user),
):
    """获取已完成任务的完整分析结果（读取 report JSON）。"""
    coll = _tasks_collection()
    if coll is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务存储不可用",
        )
    user_id = str(user.get("id", ""))
    doc = await coll.find_one({
        "task_id": task_id,
        "$or": [
            {"user_id": user_id},
            {"user_id": "legacy-backfill"},
        ],
    })
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_id}",
        )
    if doc.get("status") != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务尚未完成,当前状态: {doc.get('status')}",
        )
    report_id = doc.get("report_id")
    if not report_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务无关联报告",
        )
    safe_id = _safe_symbol(report_id)
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
                    "message": "获取任务结果成功",
                }
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"报告文件不存在: {report_id}",
    )


@router.websocket("/ws/task/{task_id}")
async def commodity_task_ws(websocket: WebSocket, task_id: str):
    """WebSocket 实时推送指定任务的进度更新。"""
    ws_manager = get_websocket_manager()
    await ws_manager.connect(websocket, task_id)
    try:
        # 保持连接，等待客户端断开
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket, task_id)


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


@router.get("/tasks", response_model=dict, summary="商品分析任务列表")
async def list_commodity_tasks(
    status: Optional[str] = Query(None, description="processing|completed|failed"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
    user: dict = Depends(get_current_user),
):
    """按状态过滤返回商品分析任务列表。

    返回当前用户创建的任务 + 系统回填的旧报告。
    """
    coll = _tasks_collection()
    if coll is None:
        return {
            "success": True,
            "data": {"total": 0, "tasks": []},
            "message": "任务存储不可用",
        }
    user_id = str(user.get("id", ""))
    # 当前用户的 + legacy 回填的(供 admin / 任何活跃用户查看历史)
    query: Dict[str, Any] = {
        "$or": [
            {"user_id": user_id},
            {"user_id": "legacy-backfill"},
        ]
    }
    if status:
        query["status"] = status
    try:
        cursor = coll.find(query).sort("created_at", -1).skip(offset).limit(limit)
        tasks = [_serialize_task(doc) async for doc in cursor]
        total = await coll.count_documents(query)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠️ 任务列表查询失败: {e}")
        return {
            "success": True,
            "data": {"total": 0, "tasks": []},
            "message": "查询失败，请稍后重试",
        }
    return {
        "success": True,
        "data": {"total": total, "tasks": tasks},
        "message": "获取任务列表成功" if tasks else "暂无任务",
    }


@router.get("/tasks/{task_id}", response_model=dict, summary="查询单个任务")
async def get_commodity_task(
    task_id: str,
    user: dict = Depends(get_current_user),
):
    """查询单个任务的当前状态。"""
    coll = _tasks_collection()
    if coll is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务存储不可用",
        )
    user_id = str(user.get("id", ""))
    doc = await coll.find_one({
        "task_id": task_id,
        "$or": [
            {"user_id": user_id},
            {"user_id": "legacy-backfill"},
        ],
    })
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_id}",
        )
    return {
        "success": True,
        "data": _serialize_task(doc),
        "message": "获取任务成功",
    }


@router.delete("/tasks/{task_id}", response_model=dict, summary="删除任务及关联报告")
async def delete_commodity_task(
    task_id: str,
    user: dict = Depends(get_current_user),
):
    """删除任务记录及关联的 JSON 报告文件。"""
    coll = _tasks_collection()
    if coll is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务存储不可用",
        )
    user_id = str(user.get("id", ""))
    doc = await coll.find_one({
        "task_id": task_id,
        "$or": [
            {"user_id": user_id},
            {"user_id": "legacy-backfill"},
        ],
    })
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_id}",
        )
    # 删除关联报告文件
    report_id = doc.get("report_id")
    if report_id:
        for f_path in _REPORTS_BASE.rglob(f"{report_id}.json"):
            try:
                f_path.unlink()
                logger.info(f"🗑️ 已删除报告文件: {f_path}")
            except OSError as e:
                logger.warning(f"⚠️ 删除报告文件失败: {f_path} - {e}")
    # 删除 MongoDB 记录
    await coll.delete_one({"task_id": task_id})
    logger.info(f"🗑️ 已删除任务: {task_id}")
    return {"success": True, "message": f"任务已删除"}


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
