"""
股票分析API路由
增强版本，支持优先级、进度跟踪、任务管理等功能
"""

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
import time

from app.routers.auth import get_current_user
from app.services.queue_service import get_queue_service, QueueService
from app.services.analysis_service import get_analysis_service
from app.services.simple_analysis_service import get_simple_analysis_service
from app.services.websocket_manager import get_websocket_manager
from app.models.analysis import (
    SingleAnalysisRequest, BatchAnalysisRequest, AnalysisParameters,
    AnalysisTaskResponse, AnalysisBatchResponse, AnalysisHistoryQuery
)

router = APIRouter()
logger = logging.getLogger("webapi")

# 兼容性：保留原有的请求模型
class SingleAnalyzeRequest(BaseModel):
    symbol: str
    parameters: dict = Field(default_factory=dict)

class BatchAnalyzeRequest(BaseModel):
    symbols: List[str]
    parameters: dict = Field(default_factory=dict)
    title: str = Field(default="批量分析", description="批次标题")
    description: Optional[str] = Field(None, description="批次描述")

# 新版API端点
@router.post("/single", response_model=Dict[str, Any])
async def submit_single_analysis(
    request: SingleAnalysisRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    """提交单股分析任务 - 使用 BackgroundTasks 异步执行"""
    try:
        logger.info(f"🎯 收到单股分析请求")
        logger.info(f"👤 用户信息: {user}")
        logger.info(f"📊 请求数据: {request}")

        # 立即创建任务记录并返回，不等待执行完成
        analysis_service = get_simple_analysis_service()
        result = await analysis_service.create_analysis_task(user["id"], request)

        # 在后台执行分析任务
        background_tasks.add_task(
            analysis_service.execute_analysis_background,
            result["task_id"],
            user["id"],
            request
        )

        logger.info(f"✅ 分析任务已在后台启动: {result}")

        return {
            "success": True,
            "data": result,
            "message": "分析任务已在后台启动"
        }
    except Exception as e:
        logger.error(f"❌ 提交单股分析任务失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# 测试路由 - 验证路由是否被正确注册
@router.get("/test-route")
async def test_route():
    """测试路由是否工作"""
    logger.info("🧪 测试路由被调用了！")
    return {"message": "测试路由工作正常", "timestamp": time.time()}

@router.get("/tasks/{task_id}/status", response_model=Dict[str, Any])
async def get_task_status_new(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """获取分析任务状态（新版异步实现）"""
    try:
        logger.info(f"🔍 [NEW ROUTE] 进入新版状态查询路由: {task_id}")
        logger.info(f"👤 [NEW ROUTE] 用户: {user}")

        analysis_service = get_simple_analysis_service()
        logger.info(f"🔧 [NEW ROUTE] 获取分析服务实例: {id(analysis_service)}")

        result = await analysis_service.get_task_status(task_id)
        logger.info(f"📊 [NEW ROUTE] 查询结果: {result is not None}")

        if result:
            return {
                "success": True,
                "data": result,
                "message": "任务状态获取成功"
            }
        else:
            # 内存中没有找到，尝试从MongoDB中查找
            logger.info(f"📊 [STATUS] 内存中未找到，尝试从MongoDB查找: {task_id}")

            from app.core.database import get_mongo_db
            db = get_mongo_db()

            # 从analysis_reports集合中查找
            mongo_result = await db.analysis_reports.find_one({"task_id": task_id})

            if mongo_result:
                logger.info(f"✅ [STATUS] 从MongoDB找到任务: {task_id}")

                # 构造状态响应（模拟已完成的任务）
                # 计算已完成任务的时间信息
                start_time = mongo_result.get("created_at")
                end_time = mongo_result.get("updated_at")
                elapsed_time = 0
                if start_time and end_time:
                    elapsed_time = (end_time - start_time).total_seconds()

                status_data = {
                    "task_id": task_id,
                    "status": "completed",
                    "progress": 100,
                    "message": "分析完成（从历史记录恢复）",
                    "current_step": "completed",
                    "start_time": start_time,
                    "end_time": end_time,
                    "elapsed_time": elapsed_time,
                    "remaining_time": 0,
                    "estimated_total_time": elapsed_time,  # 已完成任务的总时长就是已用时间
                    "stock_code": mongo_result.get("stock_symbol"),
                    "stock_symbol": mongo_result.get("stock_symbol"),
                    "analysts": mongo_result.get("analysts", []),
                    "research_depth": mongo_result.get("research_depth", "快速"),
                    "source": "mongodb_recovery"  # 标记数据来源
                }

                return {
                    "success": True,
                    "data": status_data,
                    "message": "任务状态获取成功（从历史记录恢复）"
                }
            else:
                logger.warning(f"❌ [STATUS] MongoDB中也未找到: {task_id}")
                raise HTTPException(status_code=404, detail="任务不存在")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks/{task_id}/result", response_model=Dict[str, Any])
async def get_task_result(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """获取分析任务结果"""
    try:
        logger.info(f"🔍 [RESULT] 获取任务结果: {task_id}")
        logger.info(f"👤 [RESULT] 用户: {user}")

        analysis_service = get_simple_analysis_service()
        task_status = await analysis_service.get_task_status(task_id)

        result_data = None

        if task_status and task_status.get('status') == 'completed':
            # 从内存中获取结果数据
            result_data = task_status.get('result_data')
            logger.info(f"📊 [RESULT] 从内存中获取到结果数据")

            # 🔍 调试：检查内存中的数据结构
            if result_data:
                logger.info(f"📊 [RESULT] 内存数据键: {list(result_data.keys())}")
                logger.info(f"📊 [RESULT] 内存中有decision字段: {bool(result_data.get('decision'))}")
                logger.info(f"📊 [RESULT] 内存中summary长度: {len(result_data.get('summary', ''))}")
                logger.info(f"📊 [RESULT] 内存中recommendation长度: {len(result_data.get('recommendation', ''))}")
                if result_data.get('decision'):
                    decision = result_data['decision']
                    logger.info(f"📊 [RESULT] 内存decision内容: action={decision.get('action')}, target_price={decision.get('target_price')}")
            else:
                logger.warning(f"⚠️ [RESULT] 内存中result_data为空")

        if not result_data:
            # 内存中没有找到，尝试从MongoDB中查找
            logger.info(f"📊 [RESULT] 内存中未找到，尝试从MongoDB查找: {task_id}")

            from app.core.database import get_mongo_db
            db = get_mongo_db()

            # 从analysis_reports集合中查找
            mongo_result = await db.analysis_reports.find_one({"task_id": task_id})

            if mongo_result:
                logger.info(f"✅ [RESULT] 从MongoDB找到结果: {task_id}")

                # 直接使用MongoDB中的数据结构（与web目录保持一致）
                result_data = {
                    "analysis_id": mongo_result.get("analysis_id"),
                    "stock_symbol": mongo_result.get("stock_symbol"),
                    "stock_code": mongo_result.get("stock_symbol"),  # 兼容性
                    "analysis_date": mongo_result.get("analysis_date"),
                    "summary": mongo_result.get("summary", ""),
                    "recommendation": mongo_result.get("recommendation", ""),
                    "confidence_score": mongo_result.get("confidence_score", 0.0),
                    "risk_level": mongo_result.get("risk_level", "中等"),
                    "key_points": mongo_result.get("key_points", []),
                    "execution_time": mongo_result.get("execution_time", 0),
                    "tokens_used": mongo_result.get("tokens_used", 0),
                    "analysts": mongo_result.get("analysts", []),
                    "research_depth": mongo_result.get("research_depth", "快速"),
                    "reports": mongo_result.get("reports", {}),
                    "created_at": mongo_result.get("created_at"),
                    "updated_at": mongo_result.get("updated_at"),
                    "status": mongo_result.get("status", "completed"),
                    "decision": mongo_result.get("decision", {}),
                    "source": "mongodb"  # 标记数据来源
                }

                # 添加调试信息
                logger.info(f"📊 [RESULT] MongoDB数据结构: {list(result_data.keys())}")
                logger.info(f"📊 [RESULT] MongoDB summary长度: {len(result_data['summary'])}")
                logger.info(f"📊 [RESULT] MongoDB recommendation长度: {len(result_data['recommendation'])}")
                logger.info(f"📊 [RESULT] MongoDB decision字段: {bool(result_data.get('decision'))}")
                if result_data.get('decision'):
                    decision = result_data['decision']
                    logger.info(f"📊 [RESULT] MongoDB decision内容: action={decision.get('action')}, target_price={decision.get('target_price')}, confidence={decision.get('confidence')}")

        if not result_data:
            logger.warning(f"❌ [RESULT] 所有数据源都未找到结果: {task_id}")
            raise HTTPException(status_code=404, detail="分析结果不存在")

        if not result_data:
            raise HTTPException(status_code=404, detail="分析结果不存在")

        # 处理reports字段 - 如果没有reports字段，从state中提取
        if 'reports' not in result_data or not result_data['reports']:
            logger.info(f"📊 [RESULT] reports字段缺失，尝试从state中提取")

            # 从state中提取报告内容
            reports = {}
            state = result_data.get('state', {})

            if isinstance(state, dict):
                # 定义所有可能的报告字段
                report_fields = [
                    'market_report',
                    'sentiment_report',
                    'news_report',
                    'fundamentals_report',
                    'investment_plan',
                    'trader_investment_plan',
                    'final_trade_decision'
                ]

                # 从state中提取报告内容
                for field in report_fields:
                    value = state.get(field, "")
                    if isinstance(value, str) and len(value.strip()) > 10:
                        reports[field] = value.strip()

                # 处理复杂的辩论状态报告
                investment_debate_state = state.get('investment_debate_state', {})
                if isinstance(investment_debate_state, dict):
                    judge_decision = investment_debate_state.get('judge_decision', "")
                    if isinstance(judge_decision, str) and len(judge_decision.strip()) > 10:
                        reports['research_team_decision'] = judge_decision.strip()

                risk_debate_state = state.get('risk_debate_state', {})
                if isinstance(risk_debate_state, dict):
                    risk_decision = risk_debate_state.get('judge_decision', "")
                    if isinstance(risk_decision, str) and len(risk_decision.strip()) > 10:
                        reports['risk_management_decision'] = risk_decision.strip()

                logger.info(f"📊 [RESULT] 从state中提取到 {len(reports)} 个报告: {list(reports.keys())}")
                result_data['reports'] = reports
            else:
                logger.warning(f"⚠️ [RESULT] state字段不是字典类型: {type(state)}")

        # 确保reports字段中的所有内容都是字符串类型
        if 'reports' in result_data and result_data['reports']:
            reports = result_data['reports']
            if isinstance(reports, dict):
                # 确保每个报告内容都是字符串且不为空
                cleaned_reports = {}
                for key, value in reports.items():
                    if isinstance(value, str) and value.strip():
                        # 确保字符串不为空
                        cleaned_reports[key] = value.strip()
                    elif value is not None:
                        # 如果不是字符串，转换为字符串
                        str_value = str(value).strip()
                        if str_value:  # 只保存非空字符串
                            cleaned_reports[key] = str_value
                    # 如果value为None或空字符串，则跳过该报告

                result_data['reports'] = cleaned_reports
                logger.info(f"📊 [RESULT] 清理reports字段，包含 {len(cleaned_reports)} 个有效报告")

                # 如果清理后没有有效报告，设置为空字典
                if not cleaned_reports:
                    logger.warning(f"⚠️ [RESULT] 清理后没有有效报告")
                    result_data['reports'] = {}
            else:
                logger.warning(f"⚠️ [RESULT] reports字段不是字典类型: {type(reports)}")
                result_data['reports'] = {}

        # 严格的数据格式化和验证
        def safe_string(value, default=""):
            """安全地转换为字符串"""
            if value is None:
                return default
            if isinstance(value, str):
                return value
            return str(value)

        def safe_number(value, default=0):
            """安全地转换为数字"""
            if value is None:
                return default
            if isinstance(value, (int, float)):
                return value
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        def safe_list(value, default=None):
            """安全地转换为列表"""
            if default is None:
                default = []
            if value is None:
                return default
            if isinstance(value, list):
                return value
            return default

        def safe_dict(value, default=None):
            """安全地转换为字典"""
            if default is None:
                default = {}
            if value is None:
                return default
            if isinstance(value, dict):
                return value
            return default

        # 🔍 调试：检查最终构建前的result_data
        logger.info(f"🔍 [FINAL] 构建最终结果前，result_data键: {list(result_data.keys())}")
        logger.info(f"🔍 [FINAL] result_data中有decision: {bool(result_data.get('decision'))}")
        if result_data.get('decision'):
            logger.info(f"🔍 [FINAL] decision内容: {result_data['decision']}")

        # 构建严格验证的结果数据
        final_result_data = {
            "analysis_id": safe_string(result_data.get("analysis_id"), "unknown"),
            "stock_symbol": safe_string(result_data.get("stock_symbol"), "UNKNOWN"),
            "stock_code": safe_string(result_data.get("stock_code"), "UNKNOWN"),
            "analysis_date": safe_string(result_data.get("analysis_date"), "2025-08-20"),
            "summary": safe_string(result_data.get("summary"), "分析摘要暂无"),
            "recommendation": safe_string(result_data.get("recommendation"), "投资建议暂无"),
            "confidence_score": safe_number(result_data.get("confidence_score"), 0.0),
            "risk_level": safe_string(result_data.get("risk_level"), "中等"),
            "key_points": safe_list(result_data.get("key_points")),
            "execution_time": safe_number(result_data.get("execution_time"), 0),
            "tokens_used": safe_number(result_data.get("tokens_used"), 0),
            "analysts": safe_list(result_data.get("analysts")),
            "research_depth": safe_string(result_data.get("research_depth"), "快速"),
            "detailed_analysis": safe_dict(result_data.get("detailed_analysis")),
            "state": safe_dict(result_data.get("state")),
            # 🔥 关键修复：添加decision字段！
            "decision": safe_dict(result_data.get("decision"))
        }

        # 特别处理reports字段 - 确保每个报告都是有效字符串
        reports_data = safe_dict(result_data.get("reports"))
        validated_reports = {}

        for report_key, report_content in reports_data.items():
            # 确保报告键是字符串
            safe_key = safe_string(report_key, "unknown_report")

            # 确保报告内容是非空字符串
            if report_content is None:
                validated_content = "报告内容暂无"
            elif isinstance(report_content, str):
                validated_content = report_content.strip() if report_content.strip() else "报告内容为空"
            else:
                validated_content = str(report_content).strip() if str(report_content).strip() else "报告内容格式错误"

            validated_reports[safe_key] = validated_content

        final_result_data["reports"] = validated_reports

        logger.info(f"✅ [RESULT] 成功获取任务结果: {task_id}")
        logger.info(f"📊 [RESULT] 最终返回 {len(final_result_data.get('reports', {}))} 个报告")

        # 🔍 调试：检查最终返回的数据
        logger.info(f"🔍 [FINAL] 最终返回数据键: {list(final_result_data.keys())}")
        logger.info(f"🔍 [FINAL] 最终返回中有decision: {bool(final_result_data.get('decision'))}")
        if final_result_data.get('decision'):
            logger.info(f"🔍 [FINAL] 最终decision内容: {final_result_data['decision']}")

        return {
            "success": True,
            "data": final_result_data,
            "message": "分析结果获取成功"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [RESULT] 获取任务结果失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/tasks", response_model=Dict[str, Any])
async def list_user_tasks(
    user: dict = Depends(get_current_user),
    status: Optional[str] = Query(None, description="任务状态过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量")
):
    """获取用户的任务列表"""
    try:
        logger.info(f"📋 查询用户任务列表: {user['id']}")

        tasks = await get_simple_analysis_service().list_user_tasks(
            user_id=user["id"],
            status=status,
            limit=limit,
            offset=offset
        )

        return {
            "success": True,
            "data": {
                "tasks": tasks,
                "total": len(tasks),
                "limit": limit,
                "offset": offset
            },
            "message": "任务列表获取成功"
        }

    except Exception as e:
        logger.error(f"❌ 获取任务列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch", response_model=Dict[str, Any])
async def submit_batch_analysis(
    request: BatchAnalysisRequest,
    user: dict = Depends(get_current_user)
):
    """提交批量分析任务"""
    try:
        result = await get_analysis_service().submit_batch_analysis(user["id"], request)
        return {
            "success": True,
            "data": result,
            "message": f"批量分析任务已提交，共{result['total_tasks']}个股票"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 兼容性：保留原有端点
@router.post("/analyze")
async def analyze_single(
    req: SingleAnalyzeRequest,
    user: dict = Depends(get_current_user),
    svc: QueueService = Depends(get_queue_service)
):
    """单股分析（兼容性端点）"""
    try:
        task_id = await svc.enqueue_task(
            user_id=user["id"],
            symbol=req.symbol,
            params=req.parameters
        )
        return {"task_id": task_id, "status": "queued"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/analyze/batch")
async def analyze_batch(
    req: BatchAnalyzeRequest,
    user: dict = Depends(get_current_user),
    svc: QueueService = Depends(get_queue_service)
):
    """批量分析（兼容性端点）"""
    try:
        batch_id, submitted = await svc.create_batch(
            user_id=user["id"],
            symbols=req.symbols,
            params=req.parameters
        )
        return {"batch_id": batch_id, "submitted": submitted}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/batches/{batch_id}")
async def get_batch(batch_id: str, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service)):
    b = await svc.get_batch(batch_id)
    if not b or b.get("user") != user["id"]:
        raise HTTPException(status_code=404, detail="batch not found")
    return b

# 任务和批次查询端点
# 注意：这个路由被移到了 /tasks/{task_id}/status 之后，避免路由冲突
# @router.get("/tasks/{task_id}")
# async def get_task(
#     task_id: str,
#     user: dict = Depends(get_current_user),
#     svc: QueueService = Depends(get_queue_service)
# ):
#     """获取任务详情"""
#     t = await svc.get_task(task_id)
#     if not t or t.get("user") != user["id"]:
#         raise HTTPException(status_code=404, detail="任务不存在")
#     return t

# 原有的路由已被新的异步实现替代
# @router.get("/tasks/{task_id}/status")
# async def get_task_status_old(
#     task_id: str,
#     user: dict = Depends(get_current_user)
# ):
#     """获取任务状态和进度（旧版实现）"""
#     try:
#         status = await get_analysis_service().get_task_status(task_id)
#         if not status:
#             raise HTTPException(status_code=404, detail="任务不存在")
#         return {
#             "success": True,
#             "data": status
#         }
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    svc: QueueService = Depends(get_queue_service)
):
    """取消任务"""
    try:
        # 验证任务所有权
        task = await svc.get_task(task_id)
        if not task or task.get("user") != user["id"]:
            raise HTTPException(status_code=404, detail="任务不存在")

        success = await svc.cancel_task(task_id)
        if success:
            return {"success": True, "message": "任务已取消"}
        else:
            raise HTTPException(status_code=400, detail="取消任务失败")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/user/queue-status")
async def get_user_queue_status(
    user: dict = Depends(get_current_user),
    svc: QueueService = Depends(get_queue_service)
):
    """获取用户队列状态"""
    try:
        status = await svc.get_user_queue_status(user["id"])
        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/user/history")
async def get_user_analysis_history(
    user: dict = Depends(get_current_user),
    status: Optional[str] = Query(None, description="任务状态过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小")
):
    """获取用户分析历史"""
    try:
        # TODO: 实现历史查询逻辑
        return {
            "success": True,
            "data": {
                "tasks": [],
                "total": 0,
                "page": page,
                "page_size": page_size
            },
            "message": "历史查询功能开发中"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# WebSocket 端点
@router.websocket("/ws/task/{task_id}")
async def websocket_task_progress(websocket: WebSocket, task_id: str):
    """WebSocket 端点：实时获取任务进度"""
    import json
    websocket_manager = get_websocket_manager()

    try:
        await websocket_manager.connect(websocket, task_id)

        # 发送连接确认消息
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "task_id": task_id,
            "message": "WebSocket 连接已建立"
        }))

        # 保持连接活跃
        while True:
            try:
                # 接收客户端的心跳消息
                data = await websocket.receive_text()
                # 可以处理客户端发送的消息
                logger.debug(f"📡 收到 WebSocket 消息: {data}")
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning(f"⚠️ WebSocket 消息处理错误: {e}")
                break

    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket 客户端断开连接: {task_id}")
    except Exception as e:
        logger.error(f"❌ WebSocket 连接错误: {e}")
    finally:
        await websocket_manager.disconnect(websocket, task_id)

# 任务详情查询路由（放在最后避免与 /tasks/{task_id}/status 冲突）
@router.get("/tasks/{task_id}/details")
async def get_task_details(
    task_id: str,
    user: dict = Depends(get_current_user),
    svc: QueueService = Depends(get_queue_service)
):
    """获取任务详情（使用不同的路径避免冲突）"""
    t = await svc.get_task(task_id)
    if not t or t.get("user") != user["id"]:
        raise HTTPException(status_code=404, detail="任务不存在")
    return t