"""
Cloud auth endpoints (independent from legacy local flow).
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_dependencies import get_current_user, require_admin
from cloud_auth import cloud_auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str = Field(min_length=8)
    role: str = Field(default="agent")


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


@router.post("/login")
async def login(request: LoginRequest) -> Dict[str, Any]:
    auth = cloud_auth_service.authenticate(request.username.strip(), request.password)
    if not auth:
        raise HTTPException(status_code=401, detail="Credenciales invalidas")
    token = cloud_auth_service.issue_token(auth["username"], auth["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": auth["username"],
        "role": auth["role"],
    }


@router.get("/me")
async def me(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return {
        "username": user.get("username"),
        "role": user.get("role"),
    }


@router.get("/users")
async def list_users(_: Dict[str, Any] = Depends(require_admin)) -> Dict[str, List[Dict[str, Any]]]:
    return {"users": cloud_auth_service.list_users()}


@router.post("/users")
async def create_user(
    request: CreateUserRequest,
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return cloud_auth_service.create_user(
            username=request.username,
            password=request.password,
            role=request.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/change-password")
async def change_my_password(
    request: ChangePasswordRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    auth = cloud_auth_service.authenticate(user["username"], request.current_password)
    if not auth:
        raise HTTPException(status_code=401, detail="Password actual invalido")
    try:
        updated = cloud_auth_service.update_password(user["username"], request.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"ok": True}
