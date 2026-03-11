"""
Shared auth dependencies for cloud endpoints.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import Depends, Header, HTTPException

from cloud_auth import cloud_auth_service


def _extract_bearer_token(authorization_header: str) -> str:
    value = (authorization_header or "").strip()
    if not value:
        raise HTTPException(status_code=401, detail="Falta Authorization Bearer token")
    parts = value.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authorization invalido. Usa Bearer <token>")
    token = parts[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token vacio")
    return token


def get_current_user(authorization: str = Header(default="")) -> Dict[str, Any]:
    token = _extract_bearer_token(authorization)
    payload = cloud_auth_service.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalido o expirado")
    return {
        "username": payload.get("sub"),
        "role": payload.get("role"),
        "token_payload": payload,
    }


def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Permisos insuficientes (admin requerido)")
    return user


def require_agent_or_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    role = user.get("role")
    if role not in {"admin", "agent"}:
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    return user

