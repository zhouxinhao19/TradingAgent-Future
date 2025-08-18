from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from app.services.auth_service import AuthService

# 统一响应格式
class ApiResponse(BaseModel):
    success: bool = True
    data: dict = {}
    message: str = ""

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

async def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"🔐 认证检查开始")
    logger.info(f"📋 Authorization header: {authorization[:50] if authorization else 'None'}...")

    if not authorization:
        logger.warning("❌ 没有Authorization header")
        raise HTTPException(status_code=401, detail="No authorization header")

    if not authorization.lower().startswith("bearer "):
        logger.warning(f"❌ Authorization header格式错误: {authorization[:20]}...")
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization.split(" ", 1)[1]
    logger.info(f"🎫 提取的token长度: {len(token)}")
    logger.info(f"🎫 Token前20位: {token[:20]}...")

    token_data = AuthService.verify_token(token)
    logger.info(f"🔍 Token验证结果: {token_data is not None}")

    if not token_data:
        logger.warning("❌ Token验证失败")
        raise HTTPException(status_code=401, detail="Invalid token")

    logger.info(f"✅ 认证成功，用户: {token_data.sub}")

    # 开源版只有admin用户
    return {
        "id": "admin",
        "username": "admin",
        "name": "管理员",
        "is_admin": True,
        "roles": ["admin"]
    }

@router.post("/login")
async def login(payload: LoginRequest):
    # 开源版只支持admin账号
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")

    # 验证admin账号
    if payload.username != "admin" or payload.password != "admin123":
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = AuthService.create_access_token(sub=payload.username)
    refresh_token = AuthService.create_access_token(sub=payload.username, expires_delta=60*60*24*7)  # 7天有效期

    return {
        "success": True,
        "data": {
            "access_token": token,
            "refresh_token": refresh_token,
            "expires_in": 60 * 60,
            "user": {
                "id": "admin",
                "username": "admin",
                "name": "管理员",
                "is_admin": True
            }
        },
        "message": "登录成功"
    }

@router.post("/refresh")
async def refresh_token(payload: RefreshTokenRequest):
    """刷新访问令牌"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"🔄 收到refresh token请求")
        logger.info(f"📝 Refresh token长度: {len(payload.refresh_token) if payload.refresh_token else 0}")

        if not payload.refresh_token:
            logger.warning("❌ Refresh token为空")
            raise HTTPException(status_code=401, detail="Refresh token is required")

        # 验证refresh token
        token_data = AuthService.verify_token(payload.refresh_token)
        logger.info(f"🔍 Token验证结果: {token_data is not None}")

        if not token_data:
            logger.warning("❌ Refresh token验证失败")
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        logger.info(f"✅ Token验证成功，用户: {token_data.sub}")

        # 生成新的tokens
        new_token = AuthService.create_access_token(sub=token_data.sub)
        new_refresh_token = AuthService.create_access_token(sub=token_data.sub, expires_delta=60*60*24*7)

        logger.info(f"🎉 新token生成成功")

        return {
            "success": True,
            "data": {
                "access_token": new_token,
                "refresh_token": new_refresh_token,
                "expires_in": 60 * 60
            },
            "message": "Token刷新成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Refresh token处理异常: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Token refresh failed: {str(e)}")

@router.post("/logout")
async def logout():
    return {
        "success": True,
        "data": {},
        "message": "登出成功"
    }

@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {
        "success": True,
        "data": user,
        "message": "获取用户信息成功"
    }

@router.post("/debug-token")
async def debug_token(payload: dict):
    """调试token信息"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        refresh_token = payload.get("refresh_token", "")
        logger.info(f"🔍 调试token信息:")
        logger.info(f"  - Token长度: {len(refresh_token)}")
        logger.info(f"  - Token前10位: {refresh_token[:10] if refresh_token else 'None'}")

        if refresh_token:
            token_data = AuthService.verify_token(refresh_token)
            logger.info(f"  - 验证结果: {token_data is not None}")
            if token_data:
                logger.info(f"  - 用户: {token_data.sub}")
                logger.info(f"  - 过期时间: {token_data.exp}")
                import time
                current_time = int(time.time())
                logger.info(f"  - 当前时间: {current_time}")
                logger.info(f"  - 是否过期: {token_data.exp < current_time}")

        return {
            "success": True,
            "data": {
                "token_length": len(refresh_token),
                "token_valid": AuthService.verify_token(refresh_token) is not None if refresh_token else False
            },
            "message": "调试信息已记录"
        }
    except Exception as e:
        logger.error(f"❌ 调试token异常: {str(e)}")
        return {
            "success": False,
            "data": {},
            "message": f"调试失败: {str(e)}"
        }