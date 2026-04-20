"""
Shared auth dependencies for cloud endpoints.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Cookie, Depends, Header, HTTPException

from cloud_auth import cloud_auth_service

AUTH_COOKIE_NAME = "etiq_access_token"


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


def _verify_token_to_user(token: str) -> Dict[str, Any]:
    payload = cloud_auth_service.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalido o expirado")
    return {
        "username": payload.get("sub"),
        "role": payload.get("role"),
        "token_payload": payload,
    }


def get_optional_current_user(
    authorization: str = Header(default=""),
    etiq_access_token: str = Cookie(default=""),
) -> Optional[Dict[str, Any]]:
    auth_value = (authorization or "").strip()
    cookie_value = (etiq_access_token or "").strip()

    if auth_value:
        token = _extract_bearer_token(auth_value)
        return _verify_token_to_user(token)

    if cookie_value:
        return _verify_token_to_user(cookie_value)

    return None


def get_current_user(
    authorization: str = Header(default=""),
    etiq_access_token: str = Cookie(default=""),
) -> Dict[str, Any]:
    user = get_optional_current_user(
        authorization=authorization,
        etiq_access_token=etiq_access_token,
    )
    if not user:
        raise HTTPException(status_code=401, detail="No hay sesion autenticada")
    return user


def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Permisos insuficientes (admin requerido)")
    return user


def require_agent_or_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    role = user.get("role")
    if role not in {"admin", "agent"}:
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    return user

