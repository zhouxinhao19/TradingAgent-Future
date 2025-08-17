from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from webapi.services.auth_service import AuthService

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict

async def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    token_data = AuthService.verify_token(token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    # demo: user info from token subject
    return {"id": token_data.sub, "name": token_data.sub, "roles": ["user"]}

@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest):
    # TODO: integrate with real user store
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail="Username and password required")
    token = AuthService.create_access_token(sub=payload.username)
    return {
        "access_token": token,
        "expires_in": 60 * 60,
        "user": {"id": payload.username, "name": payload.username}
    }

@router.post("/logout")
async def logout():
    return {"ok": True}

@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user