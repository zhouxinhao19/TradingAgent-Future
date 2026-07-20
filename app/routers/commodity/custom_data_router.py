"""
custom_data_router.py — 自定义数据文件分析路由 (Phase Data Analyst)

端点:
  - POST /api/commodity/custom-data/upload     — 上传数据文件
  - GET  /api/commodity/custom-data/skills      — 获取可用技能列表
  - POST /api/commodity/custom-data/analyze     — 提交自定义数据文件分析任务
  - POST /api/commodity/{full_symbol}/analyze-with-data — 分析时附加数据文件

依赖:
  - FEATURE_COMMODITY_ENABLED + FEATURE_COMMODITY_ANALYSIS=true
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from app.routers.auth_db import get_current_user
from pydantic import BaseModel, Field

from tradingagents.agents.custom_data.skills.registry import SkillsRegistry
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")
web_logger = logging.getLogger("webapi")

router = APIRouter(prefix="/commodity/custom-data", tags=["commodity-custom-data"])

# 文件上传存储目录
_UPLOADS_BASE = Path(__file__).resolve().parents[3] / "data" / "uploads" / "commodity"

# 最大文件大小 (50MB)
_MAX_FILE_SIZE = 50 * 1024 * 1024

# 允许的文件扩展名
_ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


# ==================== 模型 ====================

class SkillInfo(BaseModel):
    """技能信息"""
    name: str
    title: str
    description: str
    content_types: List[str]


class CustomDataAnalysisRequest(BaseModel):
    """自定义数据文件分析请求"""
    file_ids: List[str] = Field(..., min_length=1, max_length=10, description="上传文件的 UUID 列表")
    skill_name: str = Field("general-analysis", description="技能名称")
    user_context: str = Field("", description="用户上下文描述")
    full_symbol: str = Field(..., description="关联的合约代码,如 CU.SHF")
    trade_date: Optional[str] = Field(None, description="交易日期 YYYY-MM-DD")


def _validate_file_id(file_id: str) -> None:
    """校验 file_id 是否为合法的 UUID hex 格式（防御路径穿越）。"""
    import re
    if not re.match(r'^[0-9a-fA-F]{12}$', file_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法的 file_id 格式: {file_id!r}",
        )


class FileInfo(BaseModel):
    """文件信息"""
    file_id: str
    original_name: str
    size: int
    content_type: str
    uploaded_at: str


# ==================== 文件存储 ====================

def _get_user_upload_dir(user_id: str = "anonymous") -> Path:
    """获取用户上传目录。"""
    today = datetime.now().strftime("%Y-%m-%d")
    dir_path = _UPLOADS_BASE / user_id / today
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def _save_upload_file(upload: UploadFile, user_id: str = "anonymous") -> Dict[str, Any]:
    """保存上传文件，返回文件元信息。"""
    ext = Path(upload.filename or "unknown").suffix.lower() if upload.filename else ".unknown"
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式: {ext}，支持的格式: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    file_id = uuid.uuid4().hex[:12]
    upload_dir = _get_user_upload_dir(user_id)
    session_dir = upload_dir / file_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # 安全保存文件：使用随机 UUID 文件名，原始名称仅存 meta.json
    import re
    original_name = upload.filename or f"file{ext}"
    # 过滤：只保留文件名（去掉路径部分），剔除 `..` 和路径分隔符
    safe_name = re.sub(r'[^a-zA-Z0-9一-鿿_.\-() ]', '_', original_name.split("\\")[-1].split("/")[-1]) or f"file{file_id}{ext}"
    if safe_name.startswith("."):
        safe_name = f"file{file_id}{ext}"
    # 磁盘上存为 UUID 文件名 + 原扩展名，避免路径穿越
    stored_filename = f"{file_id}{ext}"
    file_path = session_dir / stored_filename
    try:
        content = upload.file.read()
        if len(content) > _MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"文件过大: {len(content)} bytes，最大允许 {_MAX_FILE_SIZE} bytes",
            )
        file_path.write_bytes(content)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件保存失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件保存失败: {e}")

    # 写 meta.json
    meta = {
        "file_id": file_id,
        "original_name": upload.filename or "unknown",
        "size": len(content),
        "ext": ext,
        "content_type": upload.content_type or "",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
    }
    (session_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(f"文件上传成功: {upload.filename} → {file_path} (id={file_id})")
    return {
        "file_id": file_id,
        "original_name": meta["original_name"],
        "size": meta["size"],
        "content_type": meta["content_type"],
        "uploaded_at": meta["uploaded_at"],
    }


def _get_file_path(file_id: str, user_id: str = "anonymous") -> Optional[Path]:
    """根据 file_id 查找文件绝对路径。先校验 file_id 格式防止路径穿越。

    搜索顺序:
      1. user_id / today
      2. user_id / yesterday
      3. anonymous / today (回退 anonymous 上传)
      4. anonymous / yesterday
    """
    _validate_file_id(file_id)
    today = datetime.now().strftime("%Y-%m-%d")
    from datetime import timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    candidates = [
        _UPLOADS_BASE / user_id / today / file_id,
        _UPLOADS_BASE / user_id / yesterday / file_id,
    ]
    # 如果 user_id != anonymous，再追加 anonymous 目录作为回退
    if user_id != "anonymous":
        candidates.extend([
            _UPLOADS_BASE / "anonymous" / today / file_id,
            _UPLOADS_BASE / "anonymous" / yesterday / file_id,
        ])

    for session_dir in candidates:
        if session_dir.exists():
            # 找第一个非 meta.json 文件
            for f in session_dir.iterdir():
                if f.name != "meta.json":
                    # resolve 后检查仍在 _UPLOADS_BASE 路径下
                    resolved = f.resolve()
                    if not str(resolved).startswith(str(_UPLOADS_BASE.resolve())):
                        logger.warning(f"路径穿越拦截: {resolved}")
                        return None
                    return resolved
    return None


# ==================== 端点 ====================

@router.post("/upload", response_model=dict)
async def upload_file(
    file: UploadFile = File(..., description="数据文件(.xlsx/.xls/.csv)"),
    user: dict = Depends(get_current_user),
):
    """上传自定义数据文件。返回 file_id 供后续分析使用。"""
    user_id = str(user.get("id", "anonymous"))

    result = _save_upload_file(file, user_id=user_id)
    return {
        "success": True,
        "data": result,
        "message": "上传成功",
    }


@router.get("/skills")
async def list_skills():
    """获取所有可用的自定义数据分析技能。"""
    registry = SkillsRegistry()
    skills = registry.list_skills()
    return {
        "success": True,
        "data": [
            SkillInfo(
                name=s["name"],
                title=s["title"],
                description=s["description"],
                content_types=s["content_types"],
            )
            for s in skills
        ],
    }


@router.post("/analyze")
async def custom_data_analyze(
    req: CustomDataAnalysisRequest,
    request: Request = None,
    user: dict = Depends(get_current_user),
):
    """提交自定义数据文件分析。

    将文件路径注入到 commodity 分析任务中，
    """
    user_id = str(user.get("id", "anonymous"))

    # 查找文件实际路径
    file_paths: List[str] = []
    missing: List[str] = []
    for fid in req.file_ids:
        fp = _get_file_path(fid, user_id=user_id)
        if fp:
            file_paths.append(str(fp.resolve()))
        else:
            missing.append(fid)

    if not file_paths:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"所有文件都未找到: {', '.join(missing)}",
        )

    if missing:
        web_logger.warning(f"部分文件未找到，已跳过: {', '.join(missing)}")

    # 创建 commodity 分析任务（复用现有队列），custom_data 字段单次写入避免竞态
    from app.routers.commodity.analysis import _create_queued_task

    full_symbol = req.full_symbol
    trade_date = req.trade_date or datetime.now().strftime("%Y-%m-%d")

    web_logger.info(
        f"[custom_data/analyze] calling _create_queued_task with "
        f"custom_data_file_paths={file_paths}, skill={req.skill_name}"
    )

    task_id = await _create_queued_task(
        full_symbol=full_symbol,
        trade_date=trade_date,
        user_id=user_id,
        custom_data_file_paths=file_paths,
        custom_data_skill_name=req.skill_name,
        custom_data_user_context=req.user_context,
    )

    web_logger.info(
        f"[custom_data/analyze] created task_id={task_id}, "
        f"file_paths={file_paths}, skill={req.skill_name}"
    )

    return {
        "success": True,
        "data": {
            "task_id": task_id,
            "full_symbol": full_symbol,
            "status": "queued",
            "file_count": len(file_paths),
        },
        "message": f"自定义数据文件分析已提交，file_ids={req.file_ids}, skill={req.skill_name}",
    }


__all__ = ["router"]
