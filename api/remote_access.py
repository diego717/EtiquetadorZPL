"""
Login obligatorio para las peticiones que llegan desde Internet por el tunel de Cloudflare.

Las peticiones de la PC o de la red local siguen sin login, como siempre. Cloudflare agrega
``CF-Connecting-IP``/``CF-Ray`` a todo lo que pasa por el tunel y cloudflared lo reenvia desde
127.0.0.1, asi que la IP de origen no sirve: se decide por esas cabeceras.
"""

from __future__ import annotations

from typing import Mapping

from fastapi.responses import JSONResponse

from cloud_auth import cloud_auth_service

TUNNEL_HEADERS = ("cf-connecting-ip", "cf-ray")

# Rutas que se pueden usar sin login aun por el tunel: el login mismo, el chequeo de vida
# que usan las paginas para encontrar la API, y las que llama Mercado Libre desde afuera.
PUBLIC_API_PATHS = frozenset({
    "/api/status",
    "/api/auth/login",
    "/api/mercadolibre/webhook",
    "/api/mercadolibre/oauth/callback",
})

LOGIN_REQUIRED_HEADER = "X-Login-Required"


def is_tunnel_request(headers: Mapping[str, str]) -> bool:
    return any(headers.get(name) for name in TUNNEL_HEADERS)


def needs_login(path: str, method: str, headers: Mapping[str, str]) -> bool:
    if method == "OPTIONS" or not is_tunnel_request(headers):
        return False
    if not (path == "/api" or path.startswith("/api/")):
        return False
    if path.rstrip("/") in PUBLIC_API_PATHS:
        return False
    authorization = str(headers.get("authorization") or "").strip()
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return True
    return not cloud_auth_service.verify_token(token.strip())


def login_required_response() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": "Inicia sesion para usar la app desde fuera de la oficina"},
        headers={LOGIN_REQUIRED_HEADER: "1"},
    )
