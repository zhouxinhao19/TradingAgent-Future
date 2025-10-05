from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, Dict
import re

from app.core.config import settings
from app.routers.auth import get_current_user

router = APIRouter()

SENSITIVE_KEYS = {
    "MONGODB_PASSWORD",
    "REDIS_PASSWORD",
    "JWT_SECRET",
    "CSRF_SECRET",
    "STOCK_DATA_API_KEY",
    "REFRESH_TOKEN_EXPIRE_DAYS",  # not sensitive itself, but keep for completeness
}

MASK = "***"


def _mask_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in SENSITIVE_KEYS:
        return MASK
    # Mask URLs that may contain credentials
    if key in {"MONGO_URI", "REDIS_URL"} and isinstance(value, str):
        v = value
        # mongodb://user:pass@host:port/db?...
        v = re.sub(r"(mongodb://[^:/?#]+):([^@/]+)@", r"\1:***@", v)
        # redis://:pass@host:port/db
        v = re.sub(r"(redis://:)[^@/]+@", r"\1***@", v)
        return v
    return value


def _build_summary() -> Dict[str, Any]:
    raw = settings.model_dump()
    # Attach derived URLs
    raw["MONGO_URI"] = settings.MONGO_URI
    raw["REDIS_URL"] = settings.REDIS_URL

    summary: Dict[str, Any] = {}
    for k, v in raw.items():
        summary[k] = _mask_value(k, v)
    return summary


@router.get("/config/summary", tags=["system"], summary="配置概要（已屏蔽敏感项，需管理员）")
async def get_config_summary(current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """
    返回当前生效的设置概要。敏感字段将以 *** 掩码显示。
    访问控制：需管理员身份。
    """
    if not current_user.get("is_admin", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return {"settings": _build_summary()}


@router.get("/config/validate", tags=["system"], summary="验证配置完整性")
async def validate_config():
    """
    验证系统配置的完整性和有效性。
    返回验证结果，包括缺少的配置项和无效的配置。
    """
    from app.core.startup_validator import StartupValidator

    try:
        validator = StartupValidator()
        result = validator.validate()

        return {
            "success": True,
            "data": {
                "success": result.success,
                "missing_required": [
                    {"key": config.key, "description": config.description}
                    for config in result.missing_required
                ],
                "missing_recommended": [
                    {"key": config.key, "description": config.description}
                    for config in result.missing_recommended
                ],
                "invalid_configs": [
                    {"key": config.key, "error": config.description}
                    for config in result.invalid_configs
                ],
                "warnings": result.warnings
            },
            "message": "配置验证完成"
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "message": f"配置验证失败: {str(e)}"
        }
